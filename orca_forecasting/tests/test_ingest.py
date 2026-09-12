"""Memory-efficient ingestion: projection, filtering, dtype, NaN handling."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from orca.ingest import iter_clean_surface_batches, scan_time_axis
from orca.schema import RAW_FEATURES


def test_surface_filter_and_no_nans_and_float32(test_cfg):
    total = 0
    for chunk in iter_clean_surface_batches(test_cfg.data.source_parquet, test_cfg.data):
        total += len(chunk)
        # All rows are the configured surface layer (depth col is dropped from output,
        # but the filter must have applied -> only surface rows remain).
        assert not chunk[RAW_FEATURES].isna().any().any()
        for c in RAW_FEATURES + ["latitude", "longitude"]:
            assert str(chunk[c].dtype) == "float32"
        assert np.issubdtype(chunk["time"].dtype, np.datetime64)
    assert total > 0


def test_ingest_drops_missing_feature_rows(tmp_path, synth_parquet):
    from orca.config import DataConfig

    df = pd.read_parquet(synth_parquet["path"])
    # Knock a hole in a physical variable for the surface layer.
    surface = df["depth_bin"] == "0-50m"
    idx = df.index[surface][:10]
    df.loc[idx, "thetao"] = np.nan
    holed = tmp_path / "holed.parquet"
    df.to_parquet(holed, index=False)

    cfg = DataConfig(source_parquet=str(holed), surface_layer="0-50m", chunk_rows=100_000)
    kept = sum(len(c) for c in iter_clean_surface_batches(holed, cfg))
    surface_rows = int(surface.sum())
    assert kept == surface_rows - len(idx)


def test_scan_time_axis_is_sorted_unique(test_cfg, synth_parquet):
    axis = scan_time_axis(test_cfg.data.source_parquet, test_cfg.data)
    assert axis.ndim == 1
    assert (np.diff(axis.astype("datetime64[ns]")).astype("int64") > 0).all()  # strictly increasing
    assert len(axis) == synth_parquet["summary"]["distinct_times"]
