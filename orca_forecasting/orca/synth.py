"""Schema-accurate synthetic ocean data generator (for tests & demos).

Produces a small dataset with exactly the raw contract
(``depth_bin, time, latitude, longitude, thetao, so, uo, vo, chl, sla, u10,
v10``) so the whole pipeline — ingest -> climatology -> features -> train ->
infer -> serve — can be exercised end-to-end without the real 13M-row file.

The generator bakes in structure the pipeline should *learn* (latitudinal
temperature gradient, seasonal cycle, positive-only chlorophyll) and can inject a
known space-time anomaly block so tests can assert the detector actually flags it.
Nothing here is used in production scoring.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd

from .schema import DEPTH_COLUMN, RAW_FEATURES


@dataclass
class SyntheticSpec:
    n_lat: int = 6
    n_lon: int = 6
    lat_start: float = 5.0
    lon_start: float = 60.0
    grid_step_deg: float = 1.0
    n_months: int = 36
    start_date: str = "2018-01-01"
    depth_layers: List[str] = field(default_factory=lambda: ["0-50m", "50-200m"])
    seed: int = 7
    # Injected anomaly block (a "marine heatwave") for detection tests.
    inject_anomalies: bool = True
    anomaly_lat_frac: Tuple[float, float] = (0.0, 0.34)   # lower-left quadrant
    anomaly_lon_frac: Tuple[float, float] = (0.0, 0.34)
    anomaly_time_frac: Tuple[float, float] = (0.85, 1.0)  # near the end (test block)
    anomaly_thetao_boost: float = 6.0
    anomaly_chl_boost: float = 5.0


def make_synthetic_dataset(spec: Optional[SyntheticSpec] = None) -> pd.DataFrame:
    """Return a DataFrame with the raw schema plus a hidden ``_injected`` flag."""
    spec = spec or SyntheticSpec()
    rng = np.random.default_rng(spec.seed)

    lats = spec.lat_start + spec.grid_step_deg * np.arange(spec.n_lat)
    lons = spec.lon_start + spec.grid_step_deg * np.arange(spec.n_lon)
    times = pd.date_range(spec.start_date, periods=spec.n_months, freq="MS")

    lat_g, lon_g, t_g, d_g = _mesh(lats, lons, times, spec.depth_layers)
    n = len(lat_g)

    month = pd.DatetimeIndex(t_g).month.to_numpy()
    seasonal = np.cos(2 * np.pi * (month - 1) / 12.0)
    depth_factor = np.where(np.asarray(d_g) == spec.depth_layers[0], 1.0, 0.6)

    # Physically-plausible base fields (structure the climatology should capture).
    thetao = (28.0 - 0.35 * np.abs(lat_g) + 2.5 * seasonal) * depth_factor + rng.normal(0, 0.4, n)
    so = 35.0 + 0.05 * lat_g + rng.normal(0, 0.1, n)
    uo = rng.normal(0, 0.15, n)
    vo = rng.normal(0, 0.15, n)
    chl = np.exp(rng.normal(-1.0, 0.4, n)) + 0.02 * np.abs(lat_g)   # positive, right-skewed
    sla = rng.normal(0, 0.05, n)
    u10 = rng.normal(0, 3.0, n)
    v10 = rng.normal(0, 3.0, n)

    df = pd.DataFrame({
        DEPTH_COLUMN: pd.Series(d_g, dtype="object"),
        "time": pd.DatetimeIndex(t_g).strftime("%Y-%m-%d"),   # stored as string (matches caster)
        "latitude": lat_g.astype("float32"),
        "longitude": lon_g.astype("float32"),
        "thetao": thetao.astype("float32"),
        "so": so.astype("float32"),
        "uo": uo.astype("float32"),
        "vo": vo.astype("float32"),
        "chl": chl.astype("float32"),
        "sla": sla.astype("float32"),
        "u10": u10.astype("float32"),
        "v10": v10.astype("float32"),
    })

    injected = np.zeros(n, dtype=bool)
    if spec.inject_anomalies:
        injected = _inject(df, spec, lats, lons, times)
    df["_injected"] = injected
    return df


def write_synthetic_parquet(path: str | Path, spec: Optional[SyntheticSpec] = None) -> dict:
    """Write a synthetic dataset to Parquet (schema columns only) and summarize."""
    df = make_synthetic_dataset(spec)
    labels = df["_injected"].to_numpy()
    out = df.drop(columns=["_injected"])
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(path, index=False)
    return {
        "path": str(path),
        "rows": int(len(out)),
        "injected": int(labels.sum()),
        "distinct_times": int(out["time"].nunique()),
        "depth_layers": sorted(out[DEPTH_COLUMN].unique().tolist()),
    }


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _mesh(lats, lons, times, depths):
    """Full cartesian product of (lat, lon, time, depth) as flat arrays."""
    la, lo, ti, de = [], [], [], []
    for d in depths:
        for t in times:
            for a in lats:
                for o in lons:
                    la.append(a); lo.append(o); ti.append(t); de.append(d)
    return (
        np.asarray(la, dtype="float64"),
        np.asarray(lo, dtype="float64"),
        np.asarray(ti, dtype="datetime64[ns]"),
        de,
    )


def _inject(df: pd.DataFrame, spec: SyntheticSpec, lats, lons, times) -> np.ndarray:
    """Add a warm/high-chl anomaly block in a known space-time window."""
    def _bounds(vals, frac):
        v = np.asarray(vals, dtype="float64")
        lo = np.quantile(v, frac[0]); hi = np.quantile(v, frac[1])
        return lo, hi

    lat_lo, lat_hi = _bounds(lats, spec.anomaly_lat_frac)
    lon_lo, lon_hi = _bounds(lons, spec.anomaly_lon_frac)
    t_vals = pd.DatetimeIndex(times).astype("int64")
    t_lo, t_hi = _bounds(t_vals, spec.anomaly_time_frac)

    t_int = pd.to_datetime(df["time"]).astype("int64").to_numpy()
    mask = (
        (df["latitude"].to_numpy() >= lat_lo) & (df["latitude"].to_numpy() <= lat_hi) &
        (df["longitude"].to_numpy() >= lon_lo) & (df["longitude"].to_numpy() <= lon_hi) &
        (t_int >= t_lo) & (t_int <= t_hi) &
        (df[DEPTH_COLUMN].to_numpy() == spec.depth_layers[0])
    )
    df.loc[mask, "thetao"] = (df.loc[mask, "thetao"] + spec.anomaly_thetao_boost).astype("float32")
    df.loc[mask, "chl"] = (df.loc[mask, "chl"] + spec.anomaly_chl_boost).astype("float32")
    df.loc[mask, "u10"] = (df.loc[mask, "u10"] * 0.1).astype("float32")  # calm winds
    df.loc[mask, "v10"] = (df.loc[mask, "v10"] * 0.1).astype("float32")
    return mask
