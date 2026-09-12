"""ONNX export for the detector pipeline.

Exports the fitted ``RobustScaler + IsolationForest`` pipeline to ONNX so the
microservice can score with a light-weight, portable ``onnxruntime`` instead of a
full scikit-learn install.

Two robustness measures make this safe across skl2onnx / sklearn versions:

1. **Score-output discovery** — the IsolationForest ONNX graph emits both a label
   and a score output; we identify the score output empirically rather than
   assuming a fixed name/index.
2. **Affine parity check** — ``decision_function == score_samples - offset_``, so
   the ONNX score can differ from ``score_samples`` only by a constant.  We detect
   that constant, verify the residual is within tolerance, and persist the offset
   so ONNX scores are mapped back into ``score_samples`` space exactly.  If the
   relationship is *not* a constant offset, ONNX export is rejected and the joblib
   pipeline remains the authoritative scorer.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np
from sklearn.pipeline import Pipeline

from .config import OnnxConfig


def export_pipeline_to_onnx(
    pipeline: Pipeline,
    n_features: int,
    output_path: str | Path,
    onnx_cfg: Optional[OnnxConfig] = None,
    parity_sample: Optional[np.ndarray] = None,
) -> Dict[str, Any]:
    """Convert ``pipeline`` to ONNX and validate parity against score_samples.

    Returns a status dict recording whether export succeeded, the detected score
    output index, the affine offset mapping ONNX -> score_samples space, and the
    max residual observed during the parity check.
    """
    onnx_cfg = onnx_cfg or OnnxConfig()
    output_path = Path(output_path)

    from skl2onnx import convert_sklearn
    from skl2onnx.common.data_types import FloatTensorType

    initial_types = [("input", FloatTensorType([None, int(n_features)]))]
    onx = convert_sklearn(pipeline, initial_types=initial_types, target_opset=onnx_cfg.opset)
    output_path.write_bytes(onx.SerializeToString())

    status: Dict[str, Any] = {
        "exported": True,
        "path": str(output_path),
        "opset": onnx_cfg.opset,
        "score_output_index": None,
        "onnx_offset": 0.0,
        "max_residual": None,
        "parity_ok": None,
    }

    # Parity / offset detection needs a representative sample.
    if parity_sample is None or len(parity_sample) == 0:
        return status

    import onnxruntime as ort

    X = np.ascontiguousarray(np.asarray(parity_sample, dtype="float32"))
    ref = pipeline.score_samples(X).astype("float64")

    sess = ort.InferenceSession(str(output_path), providers=["CPUExecutionProvider"])
    input_name = sess.get_inputs()[0].name
    outputs = sess.run(None, {input_name: X})

    best_idx, best_offset, best_resid = None, 0.0, np.inf
    for idx, out in enumerate(outputs):
        arr = np.asarray(out)
        if not np.issubdtype(arr.dtype, np.floating):
            continue  # skip the integer label output
        vals = arr.reshape(len(X), -1)
        if vals.shape[1] != 1:
            continue
        vals = vals.ravel().astype("float64")
        # score_samples ~= onnx + offset  => offset = mean(ref - onnx)
        offset = float(np.mean(ref - vals))
        resid = float(np.max(np.abs((vals + offset) - ref)))
        if resid < best_resid:
            best_idx, best_offset, best_resid = idx, offset, resid

    status["score_output_index"] = best_idx
    status["onnx_offset"] = best_offset
    status["max_residual"] = best_resid
    status["parity_ok"] = bool(best_idx is not None and best_resid <= onnx_cfg.parity_atol)

    if not status["parity_ok"]:
        # Reject an untrustworthy export; joblib remains authoritative.
        try:
            output_path.unlink(missing_ok=True)
        except Exception:  # pragma: no cover
            pass
        status["exported"] = False

    return status


def onnx_score_samples(
    session: Any,
    input_name: str,
    X: np.ndarray,
    score_output_index: int,
    offset: float = 0.0,
) -> np.ndarray:
    """Return score_samples-equivalent scores from an ONNX session."""
    X = np.ascontiguousarray(np.asarray(X, dtype="float32"))
    outputs = session.run(None, {input_name: X})
    vals = np.asarray(outputs[score_output_index]).reshape(len(X), -1).ravel().astype("float32")
    return (vals + np.float32(offset)).astype("float32")
