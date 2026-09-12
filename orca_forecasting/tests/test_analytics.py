"""Heuristic analytics: ecological state rules and Marine Health Index bounds."""

from __future__ import annotations

import numpy as np
import pandas as pd

from orca.analytics import (
    STATE_EUTROPHICATION,
    STATE_HEATWAVE,
    STATE_NOMINAL,
    STATE_UPWELLING,
    annotate,
    classify_states,
    marine_health_index,
)
from orca.config import AnalyticsConfig
from orca.schema import MODEL_FEATURES


def _features(rows):
    return pd.DataFrame(rows, columns=MODEL_FEATURES).astype("float32")


def test_state_rules_fire_as_configured():
    cfg = AnalyticsConfig()
    # columns: thetao_z, so_z, sla_z, chl_z, uo, vo, current_speed, u10, v10, wind_speed
    rows = [
        [2.0, 0, 0, 0.0, 0, 0, 0.3, 0, 0, 1.0],   # warm + calm      -> heatwave
        [-1.0, 0, 0, 1.0, 0, 0, 0.3, 0, 0, 6.0],  # cold + productive-> upwelling
        [0.0, 0, 0, 2.0, 0, 0, 0.05, 0, 0, 6.0],  # high chl + stagnant -> eutrophication
        [0.0, 0, 0, 0.0, 0, 0, 0.3, 0, 0, 6.0],   # baseline         -> nominal
    ]
    states = classify_states(_features(rows), cfg).tolist()
    assert states == [STATE_HEATWAVE, STATE_UPWELLING, STATE_EUTROPHICATION, STATE_NOMINAL]


def test_mhi_is_one_at_climatology_and_low_under_extreme_anomaly():
    cfg = AnalyticsConfig()
    calm = _features([[0, 0, 0, 0, 0, 0, 0.1, 0, 0, 3.0]])
    extreme = _features([[4.0, 0, 4.0, 4.0, 0, 0, 0.1, 0, 0, 3.0]])
    assert abs(float(marine_health_index(calm, cfg).iloc[0]) - 1.0) < 1e-6
    assert float(marine_health_index(extreme, cfg).iloc[0]) < 0.3


def test_mhi_bounded_unit_interval_on_random_input():
    rng = np.random.default_rng(0)
    rows = rng.normal(0, 3, size=(500, len(MODEL_FEATURES)))
    mhi = marine_health_index(_features(rows), AnalyticsConfig()).to_numpy()
    assert mhi.min() >= 0.0 and mhi.max() <= 1.0


def test_annotate_returns_both_columns():
    out = annotate(_features([[0, 0, 0, 0, 0, 0, 0.1, 0, 0, 3.0]]), AnalyticsConfig())
    assert list(out.columns) == ["ecological_state", "marine_health_index"]
