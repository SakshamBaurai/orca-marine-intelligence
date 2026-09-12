"""Heuristic marine-health post-processing (optional, not machine learning).

This layer is deliberately separate from the detector.  The Isolation Forest
answers "is this row statistically anomalous?"; this module offers an
*interpretable*, fully-configurable ecological reading on top of the same
leak-free z-score features (marine heatwave / upwelling / eutrophication risk)
plus a bounded Marine Health Index.

Design choices that keep it geography-general and leakage-free:

* It consumes the **already-standardized** climatological anomalies (z-scores),
  so a threshold like "thetao_z >= 1" means the same thing in any basin.
* Every threshold and weight lives in :class:`~orca.config.AnalyticsConfig`;
  there are no hardcoded coordinates or basin-specific constants.
* It is a pure per-row function — no aggregation over other rows, no fitting —
  so it is safe to run inside the stateless service.
"""

from __future__ import annotations

from typing import Dict, List

import numpy as np
import pandas as pd

from .config import AnalyticsConfig
from .schema import anomaly_var_to_feature

# Feature column names (derived, never hardcoded strings elsewhere).
_THETAO_Z = anomaly_var_to_feature("thetao")
_SLA_Z = anomaly_var_to_feature("sla")
_CHL_Z = anomaly_var_to_feature("chl")

STATE_NOMINAL = "nominal"
STATE_HEATWAVE = "marine_heatwave"
STATE_UPWELLING = "upwelling"
STATE_EUTROPHICATION = "eutrophication_risk"

# Priority order when multiple rules match (most acute / actionable first).
STATE_PRIORITY: List[str] = [STATE_HEATWAVE, STATE_EUTROPHICATION, STATE_UPWELLING, STATE_NOMINAL]


def classify_states(features: pd.DataFrame, cfg: AnalyticsConfig) -> pd.Series:
    """Assign an ecological state label to each row from configurable rules.

    Rules operate on z-score anomalies (unit-free, basin-independent) plus the
    physical ``wind_speed`` / ``current_speed`` magnitudes.  Missing feature
    columns simply make the dependent rule inactive rather than raising.
    """
    n = len(features)
    thetao_z = _col(features, _THETAO_Z)
    chl_z = _col(features, _CHL_Z)
    wind = _col(features, "wind_speed")
    current = _col(features, "current_speed")

    heatwave = (thetao_z >= cfg.heatwave_thetao_z_min) & (wind <= cfg.heatwave_wind_max)
    upwelling = (thetao_z <= cfg.upwelling_thetao_z_max) & (chl_z >= cfg.upwelling_chl_z_min)
    eutrophication = (chl_z >= cfg.eutrophication_chl_z_min) & (current <= cfg.eutrophication_current_max)

    state = np.full(n, STATE_NOMINAL, dtype=object)
    # Apply in reverse priority so higher-priority labels overwrite lower ones.
    state[upwelling.to_numpy()] = STATE_UPWELLING
    state[eutrophication.to_numpy()] = STATE_EUTROPHICATION
    state[heatwave.to_numpy()] = STATE_HEATWAVE
    return pd.Series(state, index=features.index, name="ecological_state")


def marine_health_index(features: pd.DataFrame, cfg: AnalyticsConfig) -> pd.Series:
    """Bounded [0, 1] health score; 1 = at climatological normal, 0 = extreme.

    Health degrades with the *magnitude* of standardized anomalies across three
    facets — biological (chl), thermal (thetao) and circulation (sla) — combined
    with the configured weights.  Anomalies are squashed to [0, 1] by ``|z| / 3``
    (clipped), so ~3 sigma is treated as maximally stressed.  Weights are
    renormalized over whichever facets are actually available.
    """
    facets = {
        "bio": (_CHL_Z, cfg.mhi_bio_weight),
        "thermal": (_THETAO_Z, cfg.mhi_thermal_weight),
        "circulation": (_SLA_Z, cfg.mhi_circulation_weight),
    }
    stress_total = np.zeros(len(features), dtype="float64")
    weight_total = 0.0
    for _, (col, weight) in facets.items():
        if col not in features.columns or weight <= 0:
            continue
        z = np.abs(features[col].to_numpy(dtype="float64"))
        stress = np.clip(z / 3.0, 0.0, 1.0)
        stress_total += weight * stress
        weight_total += weight

    if weight_total == 0:
        return pd.Series(np.ones(len(features), dtype="float32"), index=features.index, name="marine_health_index")

    health = 1.0 - (stress_total / weight_total)
    return pd.Series(np.clip(health, 0.0, 1.0).astype("float32"), index=features.index, name="marine_health_index")


def annotate(features: pd.DataFrame, cfg: AnalyticsConfig) -> pd.DataFrame:
    """Return the ecological state + MHI columns aligned to ``features``."""
    out = pd.DataFrame(index=features.index)
    out["ecological_state"] = classify_states(features, cfg)
    out["marine_health_index"] = marine_health_index(features, cfg)
    return out


def summarize_states(states: pd.Series) -> Dict[str, int]:
    """Count rows per ecological state (for reporting)."""
    counts = states.value_counts().to_dict()
    return {str(k): int(v) for k, v in counts.items()}


def _col(features: pd.DataFrame, name: str) -> pd.Series:
    """Fetch a feature column or an all-NaN placeholder (rule stays inactive)."""
    if name in features.columns:
        return features[name].astype("float64")
    return pd.Series(np.full(len(features), np.nan), index=features.index)
