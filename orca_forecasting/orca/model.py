"""Regularized Isolation Forest detector.

The detector is an sklearn ``Pipeline`` of ``RobustScaler`` + ``IsolationForest``.
Two things matter for the mandates:

* **The scaler is fit only on the training block** (it lives inside the pipeline
  that ``train.py`` fits on training rows), so it is *not* a global scaler over
  train+test.  RobustScaler (median/IQR) is used because ocean fields are heavy
  tailed and it resists the very outliers we are trying to detect.

* **Regularization** is explicit and lives in config:
    - ``max_samples`` bounds the sample each tree sees (strong regularizer, also
      keeps fit time flat as data grows and prevents "masking" of anomalies),
    - ``max_features`` < 1.0 subsamples features per split to decorrelate trees,
    - a moderate ``n_estimators`` for stable score estimates,
    - the operating point is set by a *calibrated threshold* on held-out data
      rather than a guessed ``contamination`` value.

Lower ``score_samples`` values are more anomalous; a row is flagged when its score
is at or below the calibrated threshold.
"""

from __future__ import annotations

import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import RobustScaler

from .config import ModelConfig


def build_pipeline(cfg: ModelConfig) -> Pipeline:
    """Construct the (unfitted) RobustScaler + IsolationForest pipeline."""
    contamination = cfg.contamination
    if isinstance(contamination, str) and contamination != "auto":
        contamination = float(contamination)

    return Pipeline(
        steps=[
            ("scale", RobustScaler()),
            (
                "iforest",
                IsolationForest(
                    n_estimators=cfg.n_estimators,
                    max_samples=cfg.max_samples,
                    max_features=cfg.max_features,
                    contamination=contamination,
                    bootstrap=False,
                    random_state=cfg.random_state,
                    n_jobs=cfg.n_jobs,
                ),
            ),
        ]
    )


def score_samples(pipeline: Pipeline, X) -> np.ndarray:
    """Anomaly scores (float32); lower = more anomalous."""
    return pipeline.score_samples(X).astype("float32")


def calibrate_threshold(scores: np.ndarray, target_alert_rate: float) -> float:
    """Threshold at the ``target_alert_rate`` quantile of held-out scores.

    Rows with ``score <= threshold`` are flagged.  This is an operational knob,
    not a scientific ground-truth cutoff.
    """
    scores = np.asarray(scores, dtype="float64")
    if scores.size == 0:
        raise ValueError("Cannot calibrate a threshold on an empty score array.")
    return float(np.quantile(scores, target_alert_rate))
