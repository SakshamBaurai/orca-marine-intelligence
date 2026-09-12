"""Leak-free climatology baseline.

This module is the heart of the no-leakage design.  It replaces the original
notebook's ``daily_means = df.groupby('time').transform('mean')`` — a global
spatial + temporal aggregation computed over *all* data (train and test
together) — with a **per-spatial-cell, per-season climatology fit strictly on the
training time block**.

Why this satisfies the mandates:

* **Zero leakage** — every statistic is accumulated only from rows earlier than
  the calibration/test boundary.  Test rows never influence the baseline.
* **Stateless at serving time** — an anomaly for a single incoming point is a
  pure lookup ``(cell, season) -> (mean, std)`` followed by ``(x - mean) / std``.
  No basin-wide aggregation over "today's" grid is required, so the service can
  score one point at a time.
* **Geographically general** — cells are arithmetic (any lat/lon), and a
  fallback hierarchy (cell -> latitude band -> season-global -> global) keeps the
  baseline defined for sparse cells and unseen regions on a global grid.
* **No global scaler needed** — the per-cell standard deviation standardizes each
  variable locally, so the anomaly features are already z-scores.

The climatology is accumulated in a single streaming pass (sum, sum-of-squares,
count per bucket), so memory scales with the number of occupied buckets, not the
number of rows.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from . import geo
from .config import ClimatologyConfig, DataConfig, SplitConfig
from .ingest import iter_clean_surface_batches
from .schema import anomaly_var_to_feature

_CELL_KEYS = ["lat_cell", "lon_cell", "season"]
_BAND_KEYS = ["lat_band", "season"]
_SEASON_KEYS = ["season"]


# --------------------------------------------------------------------------- #
# Streaming accumulator
# --------------------------------------------------------------------------- #
def _transform_var(values: pd.Series, var: str, log_vars: List[str]) -> pd.Series:
    """Apply the modelling transform (log1p for skewed vars) before stats."""
    if var in log_vars:
        return np.log1p(values.astype("float64"))
    return values.astype("float64")


def _partial_stats(df: pd.DataFrame, keys: List[str], vars_: List[str]) -> pd.DataFrame:
    """Per-bucket sum, sum-of-squares and count for the given grouping keys."""
    agg = {}
    for v in vars_:
        agg[f"{v}__sum"] = (v, "sum")
        agg[f"{v}__sqsum"] = (f"{v}__sq", "sum")
        agg[f"{v}__cnt"] = (v, "count")
    return df.groupby(keys, sort=False).agg(**agg)


def _finalize(
    totals: pd.DataFrame, vars_: List[str], min_std: float
) -> pd.DataFrame:
    """Turn accumulated sums into mean/std/count columns per variable."""
    out = pd.DataFrame(index=totals.index)
    for v in vars_:
        cnt = totals[f"{v}__cnt"].astype("float64")
        mean = totals[f"{v}__sum"] / cnt
        var = totals[f"{v}__sqsum"] / cnt - mean ** 2
        std = np.sqrt(np.clip(var, 0.0, None))
        std = np.where(std < min_std, min_std, std)
        out[f"{v}_mean"] = mean.astype("float32")
        out[f"{v}_std"] = np.asarray(std, dtype="float32")
        out[f"{v}_count"] = totals[f"{v}__cnt"].astype("int64")
    return out.reset_index()


@dataclass
class Climatology:
    """Fitted, persistable climatology with a hierarchical lookup."""

    cell: pd.DataFrame
    band: pd.DataFrame
    season: pd.DataFrame
    global_stats: Dict[str, Dict[str, float]]
    cfg: ClimatologyConfig
    train_time_range: Optional[Dict[str, str]] = None
    meta: Dict = field(default_factory=dict)

    # ------------------------------------------------------------------ #
    # Transform: raw chunk -> standardized anomaly (z-score) features
    # ------------------------------------------------------------------ #
    def transform(
        self, df: pd.DataFrame, lat_col: str = "latitude", lon_col: str = "longitude",
        time_col: str = "time",
    ) -> pd.DataFrame:
        """Return z-score anomaly features for each row, fully vectorized.

        Pure function of the incoming rows + fitted stats -> identical in
        training and serving.
        """
        n = len(df)
        keys = pd.DataFrame(index=np.arange(n))
        lat_cell, lon_cell = geo.spatial_cell(df[lat_col], df[lon_col], self.cfg.cell_size_deg)
        keys["lat_cell"] = lat_cell
        keys["lon_cell"] = lon_cell
        keys["lat_band"] = geo.lat_band(df[lat_col], self.cfg.band_size_deg)
        keys["season"] = geo.season_bin(
            df[time_col], self.cfg.temporal_resolution, self.cfg.doy_window_days
        )

        # Merge each fallback level once.
        merged = keys.copy()
        merged = merged.merge(
            self.cell, on=_CELL_KEYS, how="left", suffixes=("", "")
        )
        band = self.band.rename(columns=lambda c: c if c in _BAND_KEYS else f"{c}__band")
        merged = merged.merge(band, on=_BAND_KEYS, how="left")
        seas = self.season.rename(columns=lambda c: c if c in _SEASON_KEYS else f"{c}__seas")
        merged = merged.merge(seas, on=_SEASON_KEYS, how="left")

        min_cnt = self.cfg.min_cell_count
        out = pd.DataFrame(index=df.index)
        for var in self.cfg.anomaly_vars:
            x = _transform_var(df[var], var, self.cfg.log_vars).to_numpy()

            # Hierarchical coalesce of (mean, std): cell -> band -> season -> global.
            cell_ok = merged.get(f"{var}_count", pd.Series(np.nan, index=merged.index)).to_numpy()
            cell_ok = np.nan_to_num(cell_ok, nan=0.0) >= min_cnt
            band_ok = np.nan_to_num(
                merged.get(f"{var}_count__band", pd.Series(np.nan, index=merged.index)).to_numpy(),
                nan=0.0,
            ) >= min_cnt

            g = self.global_stats.get(var, {"mean": 0.0, "std": 1.0})
            mean = np.full(n, g["mean"], dtype="float64")
            std = np.full(n, g["std"], dtype="float64")

            # season level (almost always populated) then band then cell.
            self._coalesce(mean, std, merged, var, "__seas",
                           np.isfinite(merged.get(f"{var}_mean__seas", pd.Series(np.nan, index=merged.index)).to_numpy()))
            self._coalesce(mean, std, merged, var, "__band", band_ok)
            self._coalesce(mean, std, merged, var, "", cell_ok)

            std = np.where(std < self.cfg.min_std, self.cfg.min_std, std)
            out[anomaly_var_to_feature(var)] = ((x - mean) / std).astype("float32")

        return out

    @staticmethod
    def _coalesce(mean, std, merged, var, suffix, mask):
        """In-place overwrite mean/std where ``mask`` is True with the given level."""
        m = merged.get(f"{var}_mean{suffix}")
        s = merged.get(f"{var}_std{suffix}")
        if m is None or s is None:
            return
        m = m.to_numpy()
        s = s.to_numpy()
        use = mask & np.isfinite(m) & np.isfinite(s) & (s > 0)
        mean[use] = m[use]
        std[use] = s[use]

    # ------------------------------------------------------------------ #
    # Persistence
    # ------------------------------------------------------------------ #
    def save(self, directory: str | Path) -> None:
        d = Path(directory)
        d.mkdir(parents=True, exist_ok=True)
        self.cell.to_parquet(d / "climatology_cell.parquet", index=False)
        self.band.to_parquet(d / "climatology_band.parquet", index=False)
        self.season.to_parquet(d / "climatology_season.parquet", index=False)
        meta = {
            "global_stats": self.global_stats,
            "cfg": {
                "cell_size_deg": self.cfg.cell_size_deg,
                "temporal_resolution": self.cfg.temporal_resolution,
                "doy_window_days": self.cfg.doy_window_days,
                "anomaly_vars": self.cfg.anomaly_vars,
                "log_vars": self.cfg.log_vars,
                "min_cell_count": self.cfg.min_cell_count,
                "band_size_deg": self.cfg.band_size_deg,
                "min_std": self.cfg.min_std,
            },
            "train_time_range": self.train_time_range,
            **self.meta,
        }
        (d / "climatology_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, directory: str | Path) -> "Climatology":
        d = Path(directory)
        meta = json.loads((d / "climatology_meta.json").read_text(encoding="utf-8"))
        cfg = ClimatologyConfig(**meta["cfg"])
        return cls(
            cell=pd.read_parquet(d / "climatology_cell.parquet"),
            band=pd.read_parquet(d / "climatology_band.parquet"),
            season=pd.read_parquet(d / "climatology_season.parquet"),
            global_stats=meta["global_stats"],
            cfg=cfg,
            train_time_range=meta.get("train_time_range"),
        )


# --------------------------------------------------------------------------- #
# Fitting entry point
# --------------------------------------------------------------------------- #
def fit_climatology(
    parquet_path: str | Path,
    data_cfg: DataConfig,
    clim_cfg: ClimatologyConfig,
    train_end_exclusive: pd.Timestamp,
) -> Climatology:
    """Fit the climatology using ONLY rows strictly before ``train_end_exclusive``.

    ``train_end_exclusive`` is the calibration-block start: everything at or after
    it is withheld, guaranteeing no calibration/test information leaks into the
    baseline.
    """
    vars_ = list(clim_cfg.anomaly_vars)
    cell_parts: List[pd.DataFrame] = []
    band_parts: List[pd.DataFrame] = []
    season_parts: List[pd.DataFrame] = []
    train_end_exclusive = pd.Timestamp(train_end_exclusive)
    t_lo: Optional[pd.Timestamp] = None
    t_hi: Optional[pd.Timestamp] = None

    for chunk in iter_clean_surface_batches(parquet_path, data_cfg):
        train_chunk = chunk.loc[chunk[data_cfg.time_column] < train_end_exclusive]
        if train_chunk.empty:
            continue

        tmin, tmax = train_chunk[data_cfg.time_column].min(), train_chunk[data_cfg.time_column].max()
        t_lo = tmin if t_lo is None else min(t_lo, tmin)
        t_hi = tmax if t_hi is None else max(t_hi, tmax)

        work = pd.DataFrame(index=train_chunk.index)
        lat_cell, lon_cell = geo.spatial_cell(
            train_chunk[data_cfg.lat_column], train_chunk[data_cfg.lon_column], clim_cfg.cell_size_deg
        )
        work["lat_cell"] = lat_cell
        work["lon_cell"] = lon_cell
        work["lat_band"] = geo.lat_band(train_chunk[data_cfg.lat_column], clim_cfg.band_size_deg)
        work["season"] = geo.season_bin(
            train_chunk[data_cfg.time_column], clim_cfg.temporal_resolution, clim_cfg.doy_window_days
        )
        for v in vars_:
            tv = _transform_var(train_chunk[v], v, clim_cfg.log_vars)
            work[v] = tv
            work[f"{v}__sq"] = tv * tv

        cell_parts.append(_partial_stats(work, _CELL_KEYS, vars_))
        band_parts.append(_partial_stats(work, _BAND_KEYS, vars_))
        season_parts.append(_partial_stats(work, _SEASON_KEYS, vars_))
        del work, train_chunk

    if not season_parts:
        raise ValueError(
            "No training rows found before the split boundary; check data range / split config."
        )

    def _combine(parts: List[pd.DataFrame]) -> pd.DataFrame:
        return pd.concat(parts).groupby(level=list(range(parts[0].index.nlevels)), sort=True).sum()

    cell_tot = _combine(cell_parts)
    band_tot = _combine(band_parts)
    season_tot = _combine(season_parts)

    cell_df = _finalize(cell_tot, vars_, clim_cfg.min_std)
    band_df = _finalize(band_tot, vars_, clim_cfg.min_std)
    season_df = _finalize(season_tot, vars_, clim_cfg.min_std)

    # Global fallback: aggregate across all seasons (still train-only).
    global_stats: Dict[str, Dict[str, float]] = {}
    for v in vars_:
        cnt = season_tot[f"{v}__cnt"].sum()
        s = season_tot[f"{v}__sum"].sum()
        sq = season_tot[f"{v}__sqsum"].sum()
        mean = s / cnt if cnt else 0.0
        var = (sq / cnt - mean ** 2) if cnt else 1.0
        std = float(np.sqrt(max(var, 0.0)))
        global_stats[v] = {"mean": float(mean), "std": max(std, clim_cfg.min_std)}

    return Climatology(
        cell=cell_df,
        band=band_df,
        season=season_df,
        global_stats=global_stats,
        cfg=clim_cfg,
        train_time_range={
            "start": str(pd.Timestamp(t_lo).date()) if t_lo is not None else None,
            "end_exclusive": str(train_end_exclusive.date()),
            "last_seen": str(pd.Timestamp(t_hi).date()) if t_hi is not None else None,
        },
        meta={"n_cells": int(len(cell_df)), "n_bands": int(len(band_df))},
    )


def fit_climatology_from_frame(
    frame: pd.DataFrame,
    data_cfg: DataConfig,
    clim_cfg: ClimatologyConfig,
) -> Climatology:
    """Fit a climatology from an in-memory frame (treated entirely as training).

    Used by the cross-validation loop, which passes only a fold's *training rows*
    so each fold's baseline stays leak-free.  Mirrors :func:`fit_climatology` but
    without streaming or time filtering.
    """
    vars_ = list(clim_cfg.anomaly_vars)
    work = pd.DataFrame(index=frame.index)
    lat_cell, lon_cell = geo.spatial_cell(
        frame[data_cfg.lat_column], frame[data_cfg.lon_column], clim_cfg.cell_size_deg
    )
    work["lat_cell"] = lat_cell
    work["lon_cell"] = lon_cell
    work["lat_band"] = geo.lat_band(frame[data_cfg.lat_column], clim_cfg.band_size_deg)
    work["season"] = geo.season_bin(
        frame[data_cfg.time_column], clim_cfg.temporal_resolution, clim_cfg.doy_window_days
    )
    for v in vars_:
        tv = _transform_var(frame[v], v, clim_cfg.log_vars)
        work[v] = tv
        work[f"{v}__sq"] = tv * tv

    cell_df = _finalize(_partial_stats(work, _CELL_KEYS, vars_), vars_, clim_cfg.min_std)
    band_df = _finalize(_partial_stats(work, _BAND_KEYS, vars_), vars_, clim_cfg.min_std)
    season_tot = _partial_stats(work, _SEASON_KEYS, vars_)
    season_df = _finalize(season_tot, vars_, clim_cfg.min_std)

    global_stats: Dict[str, Dict[str, float]] = {}
    for v in vars_:
        cnt = season_tot[f"{v}__cnt"].sum()
        s = season_tot[f"{v}__sum"].sum()
        sq = season_tot[f"{v}__sqsum"].sum()
        mean = s / cnt if cnt else 0.0
        var = (sq / cnt - mean ** 2) if cnt else 1.0
        std = float(np.sqrt(max(var, 0.0)))
        global_stats[v] = {"mean": float(mean), "std": max(std, clim_cfg.min_std)}

    return Climatology(
        cell=cell_df, band=band_df, season=season_df,
        global_stats=global_stats, cfg=clim_cfg,
        train_time_range=None, meta={"in_memory": True},
    )
