"""Shared pytest fixtures.

A tiny synthetic dataset (see :mod:`orca.synth`) is written to a temp Parquet once
per session and a fast bundle is trained on it, so every test exercises the real
streaming / leak-free code paths without needing the 13M-row production file.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from orca.config import Config
from orca.synth import SyntheticSpec, write_synthetic_parquet


def make_test_config(parquet_path, artifact_dir) -> Config:
    """A small, fast, but faithful configuration for tests."""
    return Config.from_dict({
        "data": {
            "source_parquet": str(parquet_path),
            "surface_layer": "0-50m",
            "chunk_rows": 400,  # small -> force multi-batch streaming paths
        },
        "climatology": {"min_cell_count": 2, "cell_size_deg": 1.0, "band_size_deg": 5.0},
        "model": {"n_estimators": 60, "max_samples": 256, "train_pool_target": 5000, "n_jobs": 1},
        "calibration": {"target_alert_rate": 0.05},
        "cv": {"n_temporal_folds": 3, "min_train_fraction": 0.4},
        "paths": {"artifact_dir": str(artifact_dir)},
    })


@pytest.fixture(scope="session")
def synth_spec() -> SyntheticSpec:
    return SyntheticSpec(seed=7)


@pytest.fixture(scope="session")
def synth_parquet(tmp_path_factory, synth_spec) -> dict:
    d = tmp_path_factory.mktemp("data")
    path = d / "synthetic_ocean.parquet"
    summary = write_synthetic_parquet(path, synth_spec)
    return {"path": str(path), "summary": summary, "spec": synth_spec}


@pytest.fixture
def test_cfg(synth_parquet, tmp_path) -> Config:
    return make_test_config(synth_parquet["path"], tmp_path / "artifacts")


@pytest.fixture(scope="session")
def trained_bundle(tmp_path_factory, synth_parquet) -> dict:
    from orca.train import train

    artifact_dir = tmp_path_factory.mktemp("artifacts")
    cfg = make_test_config(synth_parquet["path"], artifact_dir)
    result = train(cfg, run_cv=False)
    return {"artifact_dir": str(artifact_dir), "result": result, "cfg": cfg}
