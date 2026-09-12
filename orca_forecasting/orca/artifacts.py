"""Versioned artifact bundle: save & load everything the service needs.

A trained bundle is a self-contained directory:

    artifacts/
      climatology/                 # leak-free baseline (parquet + meta)
      detector.joblib              # RobustScaler + IsolationForest pipeline
      detector.onnx                # portable ONNX graph (optional)
      metadata.json                # feature order, threshold, params, provenance

The service loads this directory once at startup and then serves statelessly.
joblib is always written and is the authoritative scorer; ONNX is an additional,
portable export validated for parity at training time.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import joblib
from sklearn.pipeline import Pipeline

from .climatology import Climatology

DETECTOR_JOBLIB = "detector.joblib"
DETECTOR_ONNX = "detector.onnx"
METADATA_JSON = "metadata.json"
CLIMATOLOGY_DIR = "climatology"


@dataclass
class ArtifactBundle:
    """In-memory representation of a trained bundle."""

    pipeline: Pipeline
    climatology: Climatology
    threshold: float
    feature_names: List[str]
    metadata: Dict[str, Any] = field(default_factory=dict)

    def save(
        self,
        artifact_dir: str | Path,
        write_onnx: bool = True,
        onnx_cfg=None,
        parity_sample=None,
    ) -> Dict[str, Any]:
        d = Path(artifact_dir)
        d.mkdir(parents=True, exist_ok=True)

        # 1) climatology
        self.climatology.save(d / CLIMATOLOGY_DIR)

        # 2) sklearn pipeline + minimal header
        joblib.dump(
            {
                "pipeline": self.pipeline,
                "feature_names": self.feature_names,
                "threshold": self.threshold,
            },
            d / DETECTOR_JOBLIB,
            compress=3,
        )

        # 3) ONNX export (best-effort; joblib stays authoritative)
        onnx_status: Dict[str, Any] = {"exported": False}
        if write_onnx:
            try:
                from .onnx_export import export_pipeline_to_onnx

                onnx_status = export_pipeline_to_onnx(
                    self.pipeline,
                    n_features=len(self.feature_names),
                    output_path=d / DETECTOR_ONNX,
                    onnx_cfg=onnx_cfg,
                    parity_sample=parity_sample,
                )
            except Exception as exc:  # pragma: no cover - environment dependent
                onnx_status = {"exported": False, "error": str(exc)}

        # 4) metadata
        meta = {
            "version": self.metadata.get("version", "1.0.0"),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "feature_names": self.feature_names,
            "threshold": self.threshold,
            "onnx": onnx_status,
            **self.metadata,
        }
        (d / METADATA_JSON).write_text(json.dumps(meta, indent=2), encoding="utf-8")
        return meta


@dataclass
class LoadedArtifacts:
    """What the inference engine holds after loading a bundle."""

    climatology: Climatology
    feature_names: List[str]
    threshold: float
    pipeline: Optional[Pipeline] = None
    onnx_session: Optional[Any] = None
    onnx_input_name: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    backend: str = "joblib"  # which scorer is active: "onnx" | "joblib"


def load_artifacts(artifact_dir: str | Path, prefer_onnx: bool = True) -> LoadedArtifacts:
    """Load a bundle for serving.

    Prefers the ONNX runtime when available and requested (portable, fast,
    dependency-light) and otherwise falls back to the joblib pipeline.
    """
    d = Path(artifact_dir)
    if not d.exists():
        raise FileNotFoundError(f"Artifact directory not found: {d}")

    climatology = Climatology.load(d / CLIMATOLOGY_DIR)
    metadata = json.loads((d / METADATA_JSON).read_text(encoding="utf-8"))
    feature_names = metadata["feature_names"]
    threshold = float(metadata["threshold"])

    payload = joblib.load(d / DETECTOR_JOBLIB)
    pipeline = payload["pipeline"]

    onnx_session = None
    onnx_input_name = None
    backend = "joblib"
    onnx_path = d / DETECTOR_ONNX
    if prefer_onnx and onnx_path.exists():
        try:
            import onnxruntime as ort

            onnx_session = ort.InferenceSession(
                str(onnx_path), providers=["CPUExecutionProvider"]
            )
            onnx_input_name = onnx_session.get_inputs()[0].name
            backend = "onnx"
        except Exception:  # pragma: no cover - fall back silently to joblib
            onnx_session = None
            backend = "joblib"

    return LoadedArtifacts(
        climatology=climatology,
        feature_names=feature_names,
        threshold=threshold,
        pipeline=pipeline,
        onnx_session=onnx_session,
        onnx_input_name=onnx_input_name,
        metadata=metadata,
        backend=backend,
    )
