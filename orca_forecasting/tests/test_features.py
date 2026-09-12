"""Feature-engineering contract & train/serve parity."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from orca.climatology import fit_climatology
from orca.features import build_features, feature_names
from orca.ingest import iter_clean_surface_batches, scan_time_axis
from orca.schema import MODEL_FEATURES, validate_model_features
from orca.splits import compute_boundaries


def _fit_clim_and_chunk(cfg):
    axis = scan_time_axis(cfg.data.source_parquet, cfg.data)
    b = compute_boundaries(axis, cfg.split)
    clim = fit_climatology(cfg.data.source_parquet, cfg.data, cfg.climatology, b.calib_start)
    chunk = next(iter_clean_surface_batches(cfg.data.source_parquet, cfg.data))
    return clim, chunk


def test_feature_order_matches_contract(test_cfg):
    clim, chunk = _fit_clim_and_chunk(test_cfg)
    names = feature_names(clim)
    # Default anomaly_vars produce exactly the documented contract order.
    assert names == MODEL_FEATURES
    feats = build_features(chunk, clim, test_cfg.data)
    assert list(feats.columns) == MODEL_FEATURES
    validate_model_features(list(feats.columns))


def test_features_are_float32_and_finite(test_cfg):
    clim, chunk = _fit_clim_and_chunk(test_cfg)
    feats = build_features(chunk, clim, test_cfg.data)
    assert all(str(dt) == "float32" for dt in feats.dtypes)
    assert np.isfinite(feats.to_numpy()).all()


def test_build_features_is_deterministic(test_cfg):
    """Same rows + same climatology -> identical features (no train/serve skew)."""
    clim, chunk = _fit_clim_and_chunk(test_cfg)
    f1 = build_features(chunk, clim, test_cfg.data)
    f2 = build_features(chunk.copy(), clim, test_cfg.data)
    pd.testing.assert_frame_equal(f1, f2)


def test_kinematic_magnitudes_are_correct(test_cfg):
    clim, chunk = _fit_clim_and_chunk(test_cfg)
    feats = build_features(chunk, clim, test_cfg.data)
    exp_current = np.hypot(chunk["uo"].to_numpy(), chunk["vo"].to_numpy())
    exp_wind = np.hypot(chunk["u10"].to_numpy(), chunk["v10"].to_numpy())
    np.testing.assert_allclose(feats["current_speed"].to_numpy(), exp_current, rtol=1e-4, atol=1e-4)
    np.testing.assert_allclose(feats["wind_speed"].to_numpy(), exp_wind, rtol=1e-4, atol=1e-4)


def test_large_positive_anomaly_yields_large_zscore(test_cfg):
    """A far-above-climatology temperature must map to a large positive z-score."""
    clim, chunk = _fit_clim_and_chunk(test_cfg)
    spiked = chunk.copy()
    spiked["thetao"] = spiked["thetao"] + 50.0
    z0 = build_features(chunk, clim, test_cfg.data)["thetao_clim_z"].to_numpy()
    z1 = build_features(spiked, clim, test_cfg.data)["thetao_clim_z"].to_numpy()
    assert np.mean(z1) > np.mean(z0) + 3.0
