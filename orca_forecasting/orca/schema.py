"""Data & feature schema contracts.

A single source of truth for column names, dtypes, the Arrow/Parquet schema used
for memory-efficient IO, and the ordered model-feature contract shared by
training and serving.  Keeping the feature order in one place is what guarantees
that the vector the model was trained on is byte-for-byte the vector produced at
inference time.
"""

from __future__ import annotations

from typing import Dict, List

import numpy as np

try:  # pyarrow is required for IO but we degrade gracefully for pure-schema use
    import pyarrow as pa
except Exception:  # pragma: no cover
    pa = None  # type: ignore


# --------------------------------------------------------------------------- #
# Raw input contract (what a valid source Parquet/CSV must contain)
# --------------------------------------------------------------------------- #
ID_COLUMNS: List[str] = ["time", "latitude", "longitude"]

# Physical variables required (non-null) for a usable ocean row.
RAW_FEATURES: List[str] = ["thetao", "so", "uo", "vo", "chl", "sla", "u10", "v10"]

DEPTH_COLUMN = "depth_bin"

# Compact numeric dtypes: ocean variables never need float64 precision, and
# float32 halves the memory footprint of every batch.
FLOAT_DTYPE = np.float32

# Pandas dtype map applied on every read / cast.  ``depth_bin`` is a category
# (few distinct values -> tiny memory) and time is parsed separately.
PANDAS_DTYPES: Dict[str, str] = {c: "float32" for c in RAW_FEATURES}
PANDAS_DTYPES.update({"latitude": "float32", "longitude": "float32"})


def raw_arrow_schema() -> "pa.Schema":
    """Arrow schema for the raw/cast Parquet.

    float32 for all measurements, dictionary-encoded depth, string time (parsed
    to datetime after read).  Used by the CSV->Parquet caster so the on-disk
    file is compact and reads back with the right types automatically.
    """
    if pa is None:  # pragma: no cover
        raise ImportError("pyarrow is required for Arrow schema construction")
    fields = [
        pa.field(DEPTH_COLUMN, pa.dictionary(pa.int16(), pa.string())),
        pa.field("time", pa.string()),
        pa.field("latitude", pa.float32()),
        pa.field("longitude", pa.float32()),
    ]
    for c in RAW_FEATURES:
        fields.append(pa.field(c, pa.float32()))
    return pa.schema(fields)


def load_columns(depth_column: str = DEPTH_COLUMN) -> List[str]:
    """Minimal column projection for reads (never load unused columns)."""
    return [depth_column, *ID_COLUMNS, *RAW_FEATURES]


# --------------------------------------------------------------------------- #
# Model feature contract (ORDER MATTERS — shared by train and serve)
# --------------------------------------------------------------------------- #
# Daily anomaly features (computed dynamically per batch) ...
ANOMALY_FEATURES: List[str] = [
    "thetao_daily_anomaly",
    "so_daily_anomaly", 
    "sla_daily_anomaly",
]
# ... plus direct kinematic / forcing features and log-transformed chlorophyll.
KINEMATIC_FEATURES: List[str] = [
    "uo",
    "vo",
    "current_speed",
    "u10",
    "v10",
    "wind_speed",
    "log_chl",
]

MODEL_FEATURES: List[str] = ANOMALY_FEATURES + KINEMATIC_FEATURES


def anomaly_var_to_feature(var: str) -> str:
    """Map a climatology variable name to its daily anomaly feature name."""
    return f"{var}_daily_anomaly"


def validate_model_features(names: List[str]) -> None:
    """Guard: fail loudly if a produced feature frame violates the contract."""
    if list(names) != MODEL_FEATURES:
        raise ValueError(
            "Model feature contract violated.\n"
            f"  expected: {MODEL_FEATURES}\n"
            f"  received: {list(names)}"
        )
