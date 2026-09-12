"""Offline spatial event clustering (DBSCAN + spherical area)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from orca.config import EventsConfig
from orca.events import detect_events, map_extent


def _two_clusters():
    rng = np.random.default_rng(3)
    a = pd.DataFrame({
        "latitude": 10.0 + rng.normal(0, 0.05, 6),
        "longitude": 70.0 + rng.normal(0, 0.05, 6),
    })
    b = pd.DataFrame({
        "latitude": -20.0 + rng.normal(0, 0.05, 5),
        "longitude": 100.0 + rng.normal(0, 0.05, 5),
    })
    df = pd.concat([a, b], ignore_index=True)
    df["time"] = pd.to_datetime("2021-06-01")
    df["anomaly_score"] = rng.uniform(1, 3, len(df))
    return df


def test_detect_two_events_with_positive_area():
    pytest.importorskip("sklearn")
    df = _two_clusters()
    cfg = EventsConfig(enable=True, eps_deg=1.0, min_samples=3, grid_spacing_deg=0.25)
    events = detect_events(df, cfg)
    assert len(events) == 2
    assert (events["area_km2"] > 0).all()
    assert set(events["n_points"]) == {6, 5}


def test_widely_separated_points_do_not_cluster():
    pytest.importorskip("sklearn")
    df = pd.DataFrame({
        "latitude": [0.0, 40.0, -40.0],
        "longitude": [0.0, 120.0, -120.0],
        "time": pd.to_datetime("2021-01-01"),
        "anomaly_score": [1.0, 2.0, 3.0],
    })
    cfg = EventsConfig(enable=True, eps_deg=0.6, min_samples=3)
    events = detect_events(df, cfg)
    assert events.empty  # all noise -> no events


def test_map_extent_is_data_driven():
    df = pd.DataFrame({"latitude": [-5.0, 15.0], "longitude": [60.0, 80.0]})
    ext = map_extent(df)
    assert ext["lat_center"] == 5.0 and ext["lon_center"] == 70.0
