"""Spatio-temporal cross-validation: no leakage across folds."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from orca.cv import SpatioTemporalBlockCV, population_stability_index


def _frame(n_times=20, n_lon=8, seed=0):
    rng = np.random.default_rng(seed)
    times = pd.date_range("2020-01-01", periods=n_times, freq="D")
    lons = np.linspace(-20, 20, n_lon)
    rows = []
    for t in times:
        for lo in lons:
            rows.append({"time": t, "longitude": float(lo), "latitude": float(rng.uniform(-5, 5))})
    return pd.DataFrame(rows)


def test_temporal_folds_have_no_index_overlap_and_are_forward_chained():
    df = _frame()
    cv = SpatioTemporalBlockCV(n_temporal_folds=4, scheme="expanding", min_train_fraction=0.3)
    times = pd.to_datetime(df["time"]).to_numpy()
    n_folds = 0
    for tr, va in cv.split(df):
        n_folds += 1
        assert set(tr).isdisjoint(set(va)), "train/val indices overlap"
        # Forward-chaining: every validation timestamp is strictly after all train ones.
        assert times[tr].max() < times[va].min()
    assert n_folds == cv.get_n_splits(df)


def test_rolling_scheme_bounds_training_window():
    df = _frame(n_times=24)
    cv = SpatioTemporalBlockCV(n_temporal_folds=4, scheme="rolling", min_train_fraction=0.3)
    windows = cv._temporal_windows(np.array(sorted(pd.unique(df["time"]))))
    # Rolling windows should not all start at 0 (that would be "expanding").
    assert any(train_lo > 0 for (train_lo, _, _) in windows)


def test_spatial_blocking_holds_out_disjoint_longitudes():
    df = _frame()
    cv = SpatioTemporalBlockCV(
        n_temporal_folds=3, scheme="expanding", min_train_fraction=0.3,
        spatial_blocking=True, n_spatial_blocks=4,
    )
    for tr, va in cv.split(df):
        tr_lon = set(np.round(df.iloc[tr]["longitude"].to_numpy(), 6))
        va_lon = set(np.round(df.iloc[va]["longitude"].to_numpy(), 6))
        assert tr_lon.isdisjoint(va_lon), "spatial block leaked longitudes into training"


def test_psi_zero_for_identical_and_positive_for_shift():
    rng = np.random.default_rng(1)
    a = rng.normal(0, 1, 5000)
    assert population_stability_index(a, a.copy()) < 1e-6
    shifted = a + 3.0
    assert population_stability_index(a, shifted) > 0.25


def test_cross_validate_reports_stability(test_cfg):
    from orca.train import cross_validate

    report = cross_validate(test_cfg, sample_rows=100_000)
    assert report["status"] in {"ok", "skipped"}
    if report["status"] == "ok":
        assert report["n_folds"] >= 1
        assert "val_alert_rate_mean" in report
        assert report["psi_max"] >= 0.0
