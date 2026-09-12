"""Artifact bundle persistence and climatology round-trip."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from orca.artifacts import (
    CLIMATOLOGY_DIR,
    DETECTOR_JOBLIB,
    METADATA_JSON,
    load_artifacts,
)
from orca.climatology import Climatology


def test_bundle_files_exist(trained_bundle):
    d = Path(trained_bundle["artifact_dir"])
    assert (d / DETECTOR_JOBLIB).exists()
    assert (d / METADATA_JSON).exists()
    assert (d / CLIMATOLOGY_DIR / "climatology_cell.parquet").exists()
    assert (d / "run_manifest.json").exists()


def test_metadata_contract(trained_bundle):
    d = Path(trained_bundle["artifact_dir"])
    meta = json.loads((d / METADATA_JSON).read_text(encoding="utf-8"))
    assert len(meta["feature_names"]) == 10
    assert "threshold" in meta
    assert "data_extent" in meta and "lat_min" in meta["data_extent"]
    assert "boundaries" in meta


def test_load_artifacts_round_trip(trained_bundle):
    loaded = load_artifacts(trained_bundle["artifact_dir"], prefer_onnx=False)
    assert loaded.backend == "joblib"
    assert loaded.pipeline is not None
    assert len(loaded.feature_names) == 10
    assert isinstance(loaded.threshold, float)


def test_climatology_save_load_equal(trained_bundle, tmp_path):
    d = Path(trained_bundle["artifact_dir"]) / CLIMATOLOGY_DIR
    clim = Climatology.load(d)
    out = tmp_path / "clim2"
    clim.save(out)
    clim2 = Climatology.load(out)
    pd.testing.assert_frame_equal(clim.cell, clim2.cell)
    pd.testing.assert_frame_equal(clim.season, clim2.season)
    assert clim.global_stats == clim2.global_stats
