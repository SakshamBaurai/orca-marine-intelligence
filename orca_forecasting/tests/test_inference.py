"""Inference engine: joblib/ONNX parity, reproducibility, and detection signal."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from orca.artifacts import DETECTOR_ONNX, load_artifacts
from orca.inference import InferenceEngine
from orca.ingest import iter_clean_surface_batches
from orca.synth import make_synthetic_dataset


def _all_surface(cfg):
    parts = [c for c in iter_clean_surface_batches(cfg.data.source_parquet, cfg.data)]
    return pd.concat(parts, ignore_index=True)


def test_score_frame_matches_pipeline_score_samples(trained_bundle):
    """Engine (joblib backend) must reproduce the raw pipeline score exactly."""
    cfg = trained_bundle["cfg"]
    engine = InferenceEngine.from_dir(trained_bundle["artifact_dir"], prefer_onnx=False, data_cfg=cfg.data)
    assert engine.backend == "joblib"

    df = _all_surface(cfg).head(200)
    scored = engine.score_frame(df)
    # Recompute directly through the pipeline for the same rows.
    from orca.features import build_features

    feats = build_features(df, engine.a.climatology, cfg.data, check_finite=False)
    ref = engine.a.pipeline.score_samples(feats.to_numpy(dtype="float32"))
    np.testing.assert_allclose(scored["raw_score"].to_numpy(), ref, rtol=1e-5, atol=1e-5)
    # anomaly_score is the monotonic negation of raw_score.
    np.testing.assert_allclose(scored["anomaly_score"].to_numpy(), -scored["raw_score"].to_numpy(), atol=1e-6)


def test_onnx_and_joblib_parity(trained_bundle):
    """If an ONNX export exists, its scores must match joblib within tolerance."""
    pytest.importorskip("onnxruntime")
    from pathlib import Path

    onnx_path = Path(trained_bundle["artifact_dir"]) / DETECTOR_ONNX
    if not onnx_path.exists():
        pytest.skip("ONNX export not produced in this environment (skl2onnx missing).")

    cfg = trained_bundle["cfg"]
    df = _all_surface(cfg).head(300)

    eng_joblib = InferenceEngine.from_dir(trained_bundle["artifact_dir"], prefer_onnx=False, data_cfg=cfg.data)
    eng_onnx = InferenceEngine.from_dir(trained_bundle["artifact_dir"], prefer_onnx=True, data_cfg=cfg.data)
    assert eng_onnx.backend == "onnx"

    s_joblib = eng_joblib.score_frame(df)["raw_score"].to_numpy()
    s_onnx = eng_onnx.score_frame(df)["raw_score"].to_numpy()
    np.testing.assert_allclose(s_onnx, s_joblib, atol=1e-3)


def test_injected_anomalies_are_more_anomalous(trained_bundle, synth_spec):
    """The known injected heatwave block must score as more anomalous than normal."""
    cfg = trained_bundle["cfg"]

    # The generator is deterministic (fixed seed), so we can rebuild the exact
    # dataset and recover the ground-truth injected mask on the surface subset.
    full = make_synthetic_dataset(synth_spec)
    surf = full["depth_bin"] == cfg.data.surface_layer
    labels = full.loc[surf, "_injected"].to_numpy()
    df = full.loc[surf].drop(columns=["_injected"]).reset_index(drop=True)

    engine = InferenceEngine.from_dir(trained_bundle["artifact_dir"], prefer_onnx=False, data_cfg=cfg.data)
    scored = engine.score_frame(df)
    sev = scored["anomaly_score"].to_numpy()

    assert labels.sum() > 0
    assert sev[labels].mean() > sev[~labels].mean(), "injected anomalies should have higher severity"
    # A meaningful fraction of injected rows should trip the calibrated alert.
    recall = scored.loc[labels, "is_anomaly"].mean()
    assert recall >= 0.2
