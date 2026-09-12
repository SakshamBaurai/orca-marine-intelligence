"""Training orchestration.

Wires the leak-free pieces together in the correct order and enforces the
temporal blocking at every step:

    time axis  ->  train / calibration / test boundaries
    climatology (fit on TRAIN block only)
    bounded training pool (sampled from TRAIN block only)  ->  fit pipeline
    threshold calibration (CALIBRATION block only)
    held-out evaluation (TEST block only)
    persist bundle (climatology + pipeline + ONNX + threshold + manifest)

Everything streams, so peak memory is bounded by ``chunk_rows`` plus the bounded
training pool — never the full dataset.  A separate spatio-temporal
cross-validation routine refits the climatology and model per fold to measure
stability without leakage.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from . import geo
from .artifacts import ArtifactBundle
from .climatology import Climatology, fit_climatology, fit_climatology_from_frame
from .config import Config
from .cv import SpatioTemporalBlockCV, population_stability_index
from .features import build_features, feature_names
from .ingest import iter_clean_surface_batches, scan_time_axis
from .model import build_pipeline, calibrate_threshold, score_samples
from .splits import compute_boundaries, TemporalBoundaries


@dataclass
class TrainingResult:
    artifact_dir: str
    boundaries: Dict[str, str]
    threshold: float
    feature_names: List[str]
    calibration: Dict[str, Any]
    evaluation: Dict[str, Any]
    cv_report: Optional[Dict[str, Any]] = None
    manifest: Dict[str, Any] = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Streaming helpers (bounded memory)
# --------------------------------------------------------------------------- #
def _build_training_pool(
    parquet: str | Path, cfg: Config, clim: Climatology, calib_start: pd.Timestamp
) -> pd.DataFrame:
    """Bounded random pool of engineered features from the TRAIN block only."""
    rng = np.random.default_rng(cfg.seed)
    target = cfg.model.train_pool_target
    time_col = cfg.data.time_column

    # First pass counts train rows to set an unbiased per-row sampling rate.
    train_rows = 0
    for chunk in iter_clean_surface_batches(parquet, cfg.data):
        train_rows += int((chunk[time_col] < calib_start).sum())
    if train_rows == 0:
        raise ValueError("No training rows before the calibration boundary.")
    rate = min(1.0, target / train_rows)

    parts: List[pd.DataFrame] = []
    for chunk in iter_clean_surface_batches(parquet, cfg.data):
        tr = chunk.loc[chunk[time_col] < calib_start]
        if tr.empty:
            continue
        feats = build_features(tr, clim, cfg.data)
        take = rng.random(len(feats)) < rate
        if take.any():
            parts.append(feats.loc[take])

    if not parts:
        # Extremely small rate + unlucky draw: fall back to a deterministic pass
        # that keeps at most ``target`` rows, so we never concat an empty list.
        for chunk in iter_clean_surface_batches(parquet, cfg.data):
            tr = chunk.loc[chunk[time_col] < calib_start]
            if tr.empty:
                continue
            parts.append(build_features(tr, clim, cfg.data))
            if sum(len(p) for p in parts) >= target:
                break

    pool = pd.concat(parts, ignore_index=True)
    if len(pool) > target:
        pool = pool.sample(n=target, random_state=cfg.seed, ignore_index=True)
    return pool


def _collect_block_scores(
    parquet: str | Path,
    cfg: Config,
    clim: Climatology,
    pipeline,
    lo: Optional[pd.Timestamp],
    hi: Optional[pd.Timestamp],
    max_rows: int = 500_000,
) -> np.ndarray:
    """Score a temporal block [lo, hi) in a streaming fashion (bounded sample)."""
    rng = np.random.default_rng(cfg.seed + 1)
    time_col = cfg.data.time_column
    collected: List[np.ndarray] = []
    n_seen = 0
    for chunk in iter_clean_surface_batches(parquet, cfg.data):
        mask = pd.Series(True, index=chunk.index)
        if lo is not None:
            mask &= chunk[time_col] >= lo
        if hi is not None:
            mask &= chunk[time_col] < hi
        block = chunk.loc[mask]
        if block.empty:
            continue
        n_seen += len(block)
        feats = build_features(block, clim, cfg.data)
        s = score_samples(pipeline, feats.to_numpy(dtype="float32"))
        collected.append(s)
        # Keep memory bounded: subsample once we exceed the cap.
        total = sum(len(x) for x in collected)
        if total > max_rows:
            alls = np.concatenate(collected)
            idx = rng.choice(len(alls), size=max_rows, replace=False)
            collected = [alls[idx]]
    return np.concatenate(collected) if collected else np.array([], dtype="float32")


# --------------------------------------------------------------------------- #
# Public entry points
# --------------------------------------------------------------------------- #
def train(cfg: Config, run_cv: bool = True) -> TrainingResult:
    """Fit the full leak-free pipeline and persist a serving bundle."""
    parquet = cfg.data.source_parquet
    if not parquet:
        raise ValueError("cfg.data.source_parquet must be set.")
    artifact_dir = Path(cfg.paths.artifact_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)

    # 1) Temporal blocking.
    time_axis = scan_time_axis(parquet, cfg.data)
    boundaries = compute_boundaries(time_axis, cfg.split)

    # 2) Climatology on the TRAIN block only.
    clim = fit_climatology(parquet, cfg.data, cfg.climatology, boundaries.calib_start)

    # 3) Bounded training pool -> fit regularized pipeline.
    pool = _build_training_pool(parquet, cfg, clim, boundaries.calib_start)
    names = feature_names(clim)
    pipeline = build_pipeline(cfg.model)
    pipeline.fit(pool[names].to_numpy(dtype="float32"))

    # 4) Calibrate the alert threshold on the CALIBRATION block only.
    calib_scores = _collect_block_scores(
        parquet, cfg, clim, pipeline, boundaries.calib_start, boundaries.test_start
    )
    threshold = calibrate_threshold(calib_scores, cfg.calibration.target_alert_rate)
    calib_report = {
        "rows_scored": int(calib_scores.size),
        "target_alert_rate": cfg.calibration.target_alert_rate,
        "threshold": threshold,
        "achieved_alert_rate": float(np.mean(calib_scores <= threshold)) if calib_scores.size else None,
    }

    # 5) Held-out evaluation on the TEST block (operational, not scientific truth).
    test_scores = _collect_block_scores(
        parquet, cfg, clim, pipeline, boundaries.test_start, None
    )
    eval_report = {
        "rows_scored": int(test_scores.size),
        "alert_rate_at_threshold": float(np.mean(test_scores <= threshold)) if test_scores.size else None,
        "score_mean": float(np.mean(test_scores)) if test_scores.size else None,
        "score_std": float(np.std(test_scores)) if test_scores.size else None,
        "calibration_to_test_psi": population_stability_index(calib_scores, test_scores)
        if test_scores.size and calib_scores.size else None,
    }

    # 6) Optional spatio-temporal CV (stability / overfitting diagnostic).
    cv_report = cross_validate(cfg) if run_cv else None

    # 7) Persist bundle (climatology + pipeline + ONNX + metadata).
    data_extent = _data_extent(parquet, cfg)
    metadata = {
        "version": cfg.version,
        "source_parquet": str(parquet),
        "boundaries": boundaries.to_dict(),
        "model": {
            "n_estimators": cfg.model.n_estimators,
            "max_samples": cfg.model.max_samples,
            "max_features": cfg.model.max_features,
            "contamination": cfg.model.contamination,
        },
        "climatology": {
            "cell_size_deg": cfg.climatology.cell_size_deg,
            "temporal_resolution": cfg.climatology.temporal_resolution,
            "anomaly_vars": cfg.climatology.anomaly_vars,
        },
        "calibration": calib_report,
        "evaluation": eval_report,
        "training_pool_rows": int(len(pool)),
        "data_extent": data_extent,
    }
    bundle = ArtifactBundle(
        pipeline=pipeline, climatology=clim, threshold=threshold,
        feature_names=names, metadata=metadata,
    )
    parity_sample = pool[names].to_numpy(dtype="float32")[:512]
    saved_meta = bundle.save(
        artifact_dir, write_onnx=cfg.onnx.enable, onnx_cfg=cfg.onnx, parity_sample=parity_sample
    )

    manifest = {
        **metadata,
        "onnx": saved_meta.get("onnx"),
        "cv_report": cv_report,
        "artifact_dir": str(artifact_dir),
    }
    (artifact_dir / cfg.paths.manifest_name).write_text(
        json.dumps(manifest, indent=2, default=str), encoding="utf-8"
    )

    return TrainingResult(
        artifact_dir=str(artifact_dir),
        boundaries=boundaries.to_dict(),
        threshold=threshold,
        feature_names=names,
        calibration=calib_report,
        evaluation=eval_report,
        cv_report=cv_report,
        manifest=manifest,
    )


def cross_validate(cfg: Config, sample_rows: int = 300_000) -> Dict[str, Any]:
    """Spatio-temporal CV on a bounded in-memory sample of the dev block.

    For each fold the climatology and the pipeline are refit on the fold's
    training rows only, so no validation information leaks in.  We report the
    stability of the operational alert rate and the train->val score drift (PSI);
    large variance or high PSI indicates overfitting or non-stationarity.
    """
    parquet = cfg.data.source_parquet
    time_axis = scan_time_axis(parquet, cfg.data)
    boundaries = compute_boundaries(time_axis, cfg.split)

    # Bounded, time-spanning sample of the pre-test (dev) block.
    sample = _load_dev_sample(parquet, cfg, boundaries, sample_rows)
    if len(sample) < 1000:
        return {"status": "skipped", "reason": "insufficient sample", "rows": int(len(sample))}

    splitter = SpatioTemporalBlockCV.from_config(
        cfg.cv, time_column=cfg.data.time_column, lon_column=cfg.data.lon_column
    )

    folds: List[Dict[str, Any]] = []
    for i, (tr_idx, va_idx) in enumerate(splitter.split(sample)):
        train_frame = sample.iloc[tr_idx]
        val_frame = sample.iloc[va_idx]
        try:
            clim_fold = fit_climatology_from_frame(train_frame, cfg.data, cfg.climatology)
            names = feature_names(clim_fold)
            Xtr = build_features(train_frame, clim_fold, cfg.data)[names]
            Xva = build_features(val_frame, clim_fold, cfg.data)[names]

            if len(Xtr) > cfg.model.train_pool_target:
                Xtr = Xtr.sample(n=cfg.model.train_pool_target, random_state=cfg.seed)

            pipe = build_pipeline(cfg.model)
            pipe.fit(Xtr.to_numpy(dtype="float32"))
            tr_scores = score_samples(pipe, Xtr.to_numpy(dtype="float32"))
            va_scores = score_samples(pipe, Xva.to_numpy(dtype="float32"))
            thr = calibrate_threshold(tr_scores, cfg.calibration.target_alert_rate)

            folds.append({
                "fold": i,
                "n_train": int(len(Xtr)),
                "n_val": int(len(Xva)),
                "val_alert_rate": float(np.mean(va_scores <= thr)),
                "psi_train_val": population_stability_index(tr_scores, va_scores),
            })
        except Exception as exc:  # pragma: no cover - keep CV robust to a bad fold
            folds.append({"fold": i, "error": str(exc)})

    valid = [f for f in folds if "val_alert_rate" in f]
    if not valid:
        return {"status": "failed", "folds": folds}

    alert_rates = np.array([f["val_alert_rate"] for f in valid])
    psis = np.array([f["psi_train_val"] for f in valid])
    return {
        "status": "ok",
        "n_folds": len(valid),
        "scheme": cfg.cv.scheme,
        "spatial_blocking": cfg.cv.spatial_blocking,
        "val_alert_rate_mean": float(alert_rates.mean()),
        "val_alert_rate_std": float(alert_rates.std()),
        "psi_mean": float(psis.mean()),
        "psi_max": float(psis.max()),
        "unstable": bool(psis.max() > cfg.cv.psi_warn_threshold),
        "folds": folds,
    }


# --------------------------------------------------------------------------- #
# Small utilities
# --------------------------------------------------------------------------- #
def _load_dev_sample(
    parquet, cfg: Config, boundaries: TemporalBoundaries, sample_rows: int
) -> pd.DataFrame:
    """Reservoir-style bounded sample of clean rows before the test boundary."""
    rng = np.random.default_rng(cfg.seed + 2)
    time_col = cfg.data.time_column
    reservoir: Optional[pd.DataFrame] = None
    n_seen = 0
    for chunk in iter_clean_surface_batches(parquet, cfg.data):
        dev = chunk.loc[chunk[time_col] < boundaries.test_start]
        if dev.empty:
            continue
        if reservoir is None:
            reservoir = dev.copy()
        else:
            reservoir = pd.concat([reservoir, dev], ignore_index=True)
        n_seen += len(dev)
        if len(reservoir) > sample_rows * 2:
            reservoir = reservoir.sample(n=sample_rows, random_state=cfg.seed).reset_index(drop=True)
    if reservoir is None:
        return pd.DataFrame()
    if len(reservoir) > sample_rows:
        reservoir = reservoir.sample(n=sample_rows, random_state=cfg.seed).reset_index(drop=True)
    return reservoir.sort_values(time_col).reset_index(drop=True)


def _data_extent(parquet, cfg: Config) -> Dict[str, Any]:
    """Data-driven spatial extent + grid spacing (no hardcoded coordinates)."""
    lat_lo = lat_hi = lon_lo = lon_hi = None
    lat_col, lon_col = cfg.data.lat_column, cfg.data.lon_column
    lat_vals, lon_vals = [], []
    for chunk in iter_clean_surface_batches(parquet, cfg.data, columns=None):
        lat_lo = chunk[lat_col].min() if lat_lo is None else min(lat_lo, chunk[lat_col].min())
        lat_hi = chunk[lat_col].max() if lat_hi is None else max(lat_hi, chunk[lat_col].max())
        lon_lo = chunk[lon_col].min() if lon_lo is None else min(lon_lo, chunk[lon_col].min())
        lon_hi = chunk[lon_col].max() if lon_hi is None else max(lon_hi, chunk[lon_col].max())
        if len(lat_vals) < 5000:
            lat_vals.extend(chunk[lat_col].unique()[:2000].tolist())
            lon_vals.extend(chunk[lon_col].unique()[:2000].tolist())
    return {
        "lat_min": float(lat_lo), "lat_max": float(lat_hi),
        "lon_min": float(lon_lo), "lon_max": float(lon_hi),
        "grid_spacing_lat_deg": geo.infer_grid_spacing(np.array(lat_vals)) if lat_vals else None,
        "grid_spacing_lon_deg": geo.infer_grid_spacing(np.array(lon_vals)) if lon_vals else None,
    }
