"""Stateless inference engine.

The engine loads a trained bundle once and then scores arbitrary incoming rows
with **no fitting, no global aggregation, and no dependence on neighbouring
rows** — each record is transformed through the same pure ``build_features`` path
used in training and scored either by the ONNX runtime (preferred, portable) or
the joblib sklearn pipeline (authoritative fallback).

Because the climatology lookup is a per-point ``(cell, season) -> (mean, std)``
operation and the detector is a fixed forest, a single record and a million
records go through identical code.  This is what makes the engine safe to embed
in a request/response service.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from .artifacts import LoadedArtifacts, load_artifacts
from .config import DataConfig
from .features import build_features
from .schema import ID_COLUMNS, RAW_FEATURES


class InferenceEngine:
    """Load a bundle once; score many times, statelessly."""

    def __init__(self, artifacts: LoadedArtifacts, data_cfg: Optional[DataConfig] = None):
        self.a = artifacts
        self.data_cfg = data_cfg or DataConfig()
        self._onnx_meta = (artifacts.metadata or {}).get("onnx", {}) or {}
        # Cache the ONNX score mapping (index + affine offset) discovered at export.
        self._score_idx = self._onnx_meta.get("score_output_index")
        self._offset = float(self._onnx_meta.get("onnx_offset", 0.0) or 0.0)

    # ------------------------------------------------------------------ #
    # Constructors
    # ------------------------------------------------------------------ #
    @classmethod
    def from_dir(
        cls,
        artifact_dir: str | Path,
        prefer_onnx: bool = True,
        data_cfg: Optional[DataConfig] = None,
    ) -> "InferenceEngine":
        return cls(load_artifacts(artifact_dir, prefer_onnx=prefer_onnx), data_cfg=data_cfg)

    # ------------------------------------------------------------------ #
    # Core scoring
    # ------------------------------------------------------------------ #
    def _score_matrix(self, X: np.ndarray) -> np.ndarray:
        """Return score_samples-equivalent scores using the active backend."""
        X = np.ascontiguousarray(np.asarray(X, dtype="float32"))
        if self.a.backend == "onnx" and self.a.onnx_session is not None and self._score_idx is not None:
            from .onnx_export import onnx_score_samples

            return onnx_score_samples(
                self.a.onnx_session,
                self.a.onnx_input_name,
                X,
                score_output_index=int(self._score_idx),
                offset=self._offset,
            )
        # joblib fallback (authoritative).
        return self.a.pipeline.score_samples(X).astype("float32")

    def score_features(self, features: pd.DataFrame) -> np.ndarray:
        """Score an already-engineered, correctly-ordered feature frame."""
        X = features[self.a.feature_names].to_numpy(dtype="float32")
        return self._score_matrix(X)

    def score_frame(self, df: pd.DataFrame, with_features: bool = False) -> pd.DataFrame:
        """Score raw clean records.

        ``df`` must contain time/lat/lon and the raw physical features.  Returns a
        frame preserving the identifier columns plus ``anomaly_score`` (higher =
        more anomalous, i.e. the negated score_samples), ``raw_score`` (the raw
        score_samples value), and a boolean ``is_anomaly`` at the calibrated
        threshold.
        """
        feats = build_features(df, self.a.climatology, self.data_cfg, check_finite=False)
        raw = self.score_features(feats)

        out_cols: Dict[str, Any] = {}
        for c in ID_COLUMNS:
            if c in df.columns:
                out_cols[c] = df[c].to_numpy()
        out = pd.DataFrame(out_cols, index=df.index) if out_cols else pd.DataFrame(index=df.index)
        out["raw_score"] = raw
        # Report a monotonic "higher = more anomalous" severity for downstream use.
        out["anomaly_score"] = (-raw).astype("float32")
        out["is_anomaly"] = raw <= np.float32(self.a.threshold)
        if with_features:
            for name in self.a.feature_names:
                out[name] = feats[name].to_numpy()
        return out

    # ------------------------------------------------------------------ #
    # Convenience for the API layer
    # ------------------------------------------------------------------ #
    def score_records(self, records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Score a list of JSON-like records (used by the FastAPI service)."""
        if not records:
            return []
        df = pd.DataFrame.from_records(records)
        self._coerce_types(df)
        scored = self.score_frame(df)
        return scored.to_dict(orient="records")

    def _coerce_types(self, df: pd.DataFrame) -> None:
        """Best-effort dtype coercion for loosely-typed request payloads."""
        tcol = self.data_cfg.time_column
        if tcol in df.columns:
            df[tcol] = pd.to_datetime(df[tcol], errors="coerce")
        for c in [self.data_cfg.lat_column, self.data_cfg.lon_column, *RAW_FEATURES]:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce").astype("float32")

    # ------------------------------------------------------------------ #
    # Introspection
    # ------------------------------------------------------------------ #
    @property
    def feature_names(self) -> List[str]:
        return list(self.a.feature_names)

    @property
    def threshold(self) -> float:
        return float(self.a.threshold)

    @property
    def backend(self) -> str:
        return self.a.backend

    def required_input_columns(self) -> List[str]:
        """Raw columns a caller must supply for a scorable record."""
        needed = set(RAW_FEATURES)
        return [self.data_cfg.time_column, self.data_cfg.lat_column, self.data_cfg.lon_column, *sorted(needed)]
