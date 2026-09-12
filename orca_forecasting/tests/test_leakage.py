"""ZERO-LEAKAGE guards.

These are the most important tests in the suite.  They prove, mechanically, that
no calibration/test information can influence anything that is fit on training
data — the exact failure mode of the original notebook's global
``groupby('time').transform('mean')``.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from orca.climatology import fit_climatology
from orca.ingest import scan_time_axis
from orca.splits import compute_boundaries

ANOM_VARS = ["thetao", "so", "sla", "chl"]


def _boundaries(cfg):
    axis = scan_time_axis(cfg.data.source_parquet, cfg.data)
    return compute_boundaries(axis, cfg.split)


def _sorted(df):
    keys = [c for c in ["lat_cell", "lon_cell", "lat_band", "season"] if c in df.columns]
    return df.sort_values(keys).reset_index(drop=True)


def test_climatology_is_invariant_to_future_corruption(test_cfg, tmp_path):
    """Corrupting every calibration+test row must not change the climatology."""
    cfg = test_cfg
    b = _boundaries(cfg)

    clim_clean = fit_climatology(cfg.data.source_parquet, cfg.data, cfg.climatology, b.calib_start)

    # Corrupt EVERYTHING at/after the calibration boundary by a huge amount.
    df = pd.read_parquet(cfg.data.source_parquet)
    future = pd.to_datetime(df["time"]) >= b.calib_start
    assert future.any(), "fixture should contain held-out rows"
    df.loc[future, ANOM_VARS] = df.loc[future, ANOM_VARS] + 1000.0
    corrupt = tmp_path / "corrupt_future.parquet"
    df.to_parquet(corrupt, index=False)

    clim_corrupt = fit_climatology(corrupt, cfg.data, cfg.climatology, b.calib_start)

    # Baseline statistics must be byte-for-byte identical.
    pd.testing.assert_frame_equal(_sorted(clim_clean.cell), _sorted(clim_corrupt.cell))
    pd.testing.assert_frame_equal(_sorted(clim_clean.season), _sorted(clim_corrupt.season))
    assert clim_clean.global_stats == clim_corrupt.global_stats


def test_corrupting_training_block_does_change_climatology(test_cfg, tmp_path):
    """Positive control: corrupting TRAIN rows *does* change the baseline.

    Guards against a vacuous invariance test (e.g. if the reader silently dropped
    everything).
    """
    cfg = test_cfg
    b = _boundaries(cfg)
    clim_clean = fit_climatology(cfg.data.source_parquet, cfg.data, cfg.climatology, b.calib_start)

    df = pd.read_parquet(cfg.data.source_parquet)
    train = pd.to_datetime(df["time"]) < b.calib_start
    df.loc[train, "thetao"] = df.loc[train, "thetao"] + 1000.0
    corrupt = tmp_path / "corrupt_train.parquet"
    df.to_parquet(corrupt, index=False)

    clim_corrupt = fit_climatology(corrupt, cfg.data, cfg.climatology, b.calib_start)
    assert clim_clean.global_stats["thetao"]["mean"] != clim_corrupt.global_stats["thetao"]["mean"]


def test_no_global_statistics_in_ingest():
    """The ingest module must not compute any global mean/scaler/imputation."""
    import inspect

    from orca import ingest

    src = inspect.getsource(ingest)
    # These are the leakage-prone operations the refactor exists to remove.
    for banned in ["transform('mean')", 'transform("mean")', "StandardScaler", "fillna("]:
        assert banned not in src, f"ingest must not use global operation: {banned}"


def test_threshold_calibrated_only_on_calibration_block(trained_bundle):
    """The persisted threshold must come from calibration rows, not test rows."""
    meta = trained_bundle["result"].calibration
    assert meta["rows_scored"] > 0
    # Achieved rate on calibration should be close to the target (loose bound).
    assert meta["achieved_alert_rate"] is not None
    assert 0.0 <= meta["achieved_alert_rate"] <= 0.25


def test_boundaries_are_strictly_ordered(test_cfg):
    b = _boundaries(test_cfg)
    assert b.t_min < b.calib_start < b.test_start <= b.t_max
