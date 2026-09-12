"""Central, declarative configuration for the ORCA anomaly pipeline.

Everything that could vary between deployments or geographies lives here, not in
the code.  There are **no hardcoded coordinates, basins, or grid extents** in the
package logic; anything spatial is either configurable or inferred from the data
at run time.  A deployment overrides only the keys it cares about via a YAML file
(see ``configs/default.yaml``) and everything else falls back to the defaults
defined below.

The config is intentionally built from plain ``dataclasses`` (plus optional
``PyYAML`` for file loading) so that importing the training/inference code does
not drag in a heavy settings framework.
"""

from __future__ import annotations

import typing
from dataclasses import dataclass, field, asdict, fields, is_dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


# --------------------------------------------------------------------------- #
# Sub-configs
# --------------------------------------------------------------------------- #
@dataclass
class DataConfig:
    """Where the data lives and how to read it."""

    # Optional raw CSV (the original 13M+ row export).  Used only by the
    # CSV -> Parquet caster; the pipeline itself always reads Parquet.
    source_csv: Optional[str] = None
    # The processed / cast Parquet the pipeline trains and scores against.
    source_parquet: Optional[str] = None

    # Column contract.  Renaming a column in a new dataset only touches config.
    time_column: str = "time"
    lat_column: str = "latitude"
    lon_column: str = "longitude"
    depth_column: str = "depth_bin"

    # ``None`` means "no explicit format, let pandas infer".  A fixed format is
    # ~10x faster on large frames, so we default to the known daily format.
    time_format: Optional[str] = "%Y-%m-%d"

    # Which depth layer to keep.  ``None`` disables the filter entirely so the
    # same code works for single-layer or full-column datasets.
    surface_layer: Optional[str] = "0-50m"

    # Physical variables that must be present and non-null for a usable row.
    raw_features: List[str] = field(
        default_factory=lambda: ["thetao", "so", "uo", "vo", "chl", "sla", "u10", "v10"]
    )

    # Streaming batch size for every Parquet read.  Keeps peak RAM bounded
    # regardless of total dataset size.
    chunk_rows: int = 250_000

    # Optional inclusive deployment bounding box.  When all four values are
    # set, it is enforced for both historical reads and live requests.  Keep
    # these unset in a reusable library config; set them in a deployment YAML.
    # This makes changing ocean regions a configuration change, never a code
    # rewrite.
    lat_min: Optional[float] = None
    lat_max: Optional[float] = None
    lon_min: Optional[float] = None
    lon_max: Optional[float] = None


@dataclass
class LiveDataConfig:
    """Configuration for an authenticated, normalized daily observation feed.

    The model deliberately does not contain vendor-specific credentials or
    dataset ids.  A Copernicus/INCOIS/NOAA adapter or gateway should return JSON
    records and be described here.  ``column_map`` maps canonical ORCA names to
    fields in that response, for example ``{"thetao": "temperature"}``.
    """

    enabled: bool = False
    endpoint: Optional[str] = None
    # A JSON endpoint is intentionally the narrow production boundary.  It can
    # be a small internal adapter around provider-specific NetCDF/subset APIs.
    request_method: str = "GET"
    records_path: Optional[str] = None  # dot path to a JSON list, e.g. "data.records"
    column_map: Dict[str, str] = field(default_factory=dict)
    static_params: Dict[str, Any] = field(default_factory=dict)
    date_param: str = "date"
    lat_min_param: str = "lat_min"
    lat_max_param: str = "lat_max"
    lon_min_param: str = "lon_min"
    lon_max_param: str = "lon_max"
    api_key_env: Optional[str] = None
    api_key_header: str = "Authorization"
    api_key_prefix: str = "Bearer "
    timeout_seconds: float = 30.0
    retry_attempts: int = 3
    retry_backoff_seconds: float = 1.0
    max_response_rows: int = 100_000


@dataclass
class ClimatologyConfig:
    """Leak-free, geography-agnostic climatology baseline.

    Anomalies are computed as standardized deviations from a per-cell, per-season
    climatology fit **only on the training time block**.  This replaces the
    original basin-wide ``groupby('time').transform('mean')`` (a global spatial +
    temporal aggregation) and simultaneously removes the need for a global scaler.
    """

    # Spatial cell size in degrees.  Coarser than the native grid so each cell
    # accumulates enough samples for a stable climatology.  Fully configurable
    # to scale from regional (fine) to global (coarse) grids.
    cell_size_deg: float = 1.0

    # Seasonal resolution: "month" (12 bins) or "doy_window" (day-of-year bins).
    temporal_resolution: str = "month"
    doy_window_days: int = 15  # only used when temporal_resolution == "doy_window"

    # Variables that get a climatological anomaly (z-score) feature.
    anomaly_vars: List[str] = field(
        default_factory=lambda: ["thetao", "so", "sla", "chl"]
    )
    # Variables log1p-transformed before climatology (right-skewed, e.g. chl).
    log_vars: List[str] = field(default_factory=lambda: ["chl"])

    # A (cell, season) bucket needs at least this many training samples to be
    # trusted; otherwise the fallback hierarchy is used.
    min_cell_count: int = 30
    # Latitude band width (degrees) for the intermediate fallback level.
    band_size_deg: float = 5.0
    # Floor on std to avoid divide-by-zero / blow-ups in near-constant cells.
    min_std: float = 1e-6


@dataclass
class SplitConfig:
    """Temporal blocking for train / calibration / test."""

    # Absolute cutoffs (ISO date strings) take priority when provided.
    train_end: Optional[str] = None
    test_start: Optional[str] = None
    # Otherwise fractions of the sorted unique time axis are used.
    train_fraction: float = 0.70
    test_fraction: float = 0.15
    # Fraction of the *training* block held out (temporally, at its tail) to
    # calibrate the alert threshold without touching test data.
    calibration_fraction: float = 0.15


@dataclass
class ModelConfig:
    """Regularized Isolation Forest hyper-parameters."""

    n_estimators: int = 200
    # Bounded subsampling per tree: strong regularizer, prevents masking, and
    # keeps fit time flat as the dataset grows.
    max_samples: int = 2048
    # <1.0 decorrelates trees (feature subsampling) -> less overfitting.
    max_features: float = 0.7
    contamination: str = "auto"  # threshold is calibrated separately, see below
    random_state: int = 42
    n_jobs: int = 1  # set to -1 on an unrestricted machine
    # Bounded random training pool drawn *within the training time block*.
    train_pool_target: int = 200_000


@dataclass
class CalibrationConfig:
    """Operational alert-threshold calibration."""

    # Target fraction of rows flagged as anomalies on held-out calibration data.
    # This is an operational choice, not a scientific ground truth.
    target_alert_rate: float = 0.01


@dataclass
class CVConfig:
    """Spatio-temporal cross-validation."""

    n_temporal_folds: int = 4
    scheme: str = "expanding"  # "expanding" (forward-chaining) or "rolling"
    min_train_fraction: float = 0.3  # smallest training window (fraction of time)
    spatial_blocking: bool = False
    n_spatial_blocks: int = 4
    # PSI above this between fold train/val score distributions flags instability.
    psi_warn_threshold: float = 0.25


@dataclass
class AnalyticsConfig:
    """Optional heuristic marine-health post-processing (not ML, fully configurable)."""

    enable: bool = True
    # Ecological-state rule thresholds (in z-score / physical units).
    upwelling_thetao_z_max: float = -0.5   # cold anomaly
    upwelling_chl_z_min: float = 0.5       # elevated productivity
    heatwave_thetao_z_min: float = 1.0     # warm anomaly
    heatwave_wind_max: float = 4.0         # calm winds (m/s)
    eutrophication_chl_z_min: float = 1.5
    eutrophication_current_max: float = 0.15  # stagnant (m/s)
    # Marine Health Index weights (must sum to 1.0).
    mhi_bio_weight: float = 0.45
    mhi_thermal_weight: float = 0.35
    mhi_circulation_weight: float = 0.20


@dataclass
class EventsConfig:
    """Optional offline spatial event clustering (batch reporting only)."""

    enable: bool = False
    eps_deg: float = 0.6
    min_samples: int = 3
    # Native grid spacing in degrees; ``None`` -> inferred from the data so the
    # per-pixel area is correct for any grid.  Area itself is computed with
    # spherical geometry (cos-latitude), never a hardcoded constant.
    grid_spacing_deg: Optional[float] = None


@dataclass
class PathsConfig:
    """Where artifacts and outputs are written."""

    artifact_dir: str = "artifacts"
    prediction_dir: str = "predictions_parquet"
    manifest_name: str = "run_manifest.json"


@dataclass
class OnnxConfig:
    enable: bool = True
    opset: int = 15
    # Max allowed mean abs difference between joblib and ONNX scores in parity
    # check; above this, ONNX export is rejected and joblib remains authoritative.
    parity_atol: float = 1e-4


@dataclass
class Config:
    """Top-level configuration container."""

    data: DataConfig = field(default_factory=DataConfig)
    live: LiveDataConfig = field(default_factory=LiveDataConfig)
    climatology: ClimatologyConfig = field(default_factory=ClimatologyConfig)
    split: SplitConfig = field(default_factory=SplitConfig)
    model: ModelConfig = field(default_factory=ModelConfig)
    calibration: CalibrationConfig = field(default_factory=CalibrationConfig)
    cv: CVConfig = field(default_factory=CVConfig)
    analytics: AnalyticsConfig = field(default_factory=AnalyticsConfig)
    events: EventsConfig = field(default_factory=EventsConfig)
    paths: PathsConfig = field(default_factory=PathsConfig)
    onnx: OnnxConfig = field(default_factory=OnnxConfig)
    seed: int = 42
    version: str = "1.0.0"

    # ------------------------------------------------------------------ #
    # (De)serialization helpers
    # ------------------------------------------------------------------ #
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Config":
        """Build a Config from a (possibly partial) nested dict."""
        return _from_dict(cls, data or {})

    @classmethod
    def from_yaml(cls, path: str | Path) -> "Config":
        import yaml  # local import: only needed when loading from file

        with open(path, "r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh) or {}
        return cls.from_dict(raw)

    @classmethod
    def load(cls, path: Optional[str | Path] = None) -> "Config":
        """Load from YAML if a path is given/exists, else return defaults."""
        if path is None:
            return cls()
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"Config file not found: {p}")
        return cls.from_yaml(p)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _from_dict(dc_type: Any, data: Dict[str, Any]) -> Any:
    """Recursively construct nested dataclasses, ignoring unknown keys.

    ``from __future__ import annotations`` turns every field annotation into a
    *string*, so ``dataclasses.fields(...).type`` cannot be passed to
    ``is_dataclass`` directly.  We resolve the real types once via
    ``typing.get_type_hints`` and fall back to the raw field types if resolution
    fails (e.g. an exotic forward reference).
    """
    if not is_dataclass(dc_type):
        return data
    try:
        hints = typing.get_type_hints(dc_type)
    except Exception:  # pragma: no cover - defensive
        hints = {f.name: f.type for f in fields(dc_type)}

    kwargs: Dict[str, Any] = {}
    known = {f.name for f in fields(dc_type)}
    for key, value in (data or {}).items():
        if key not in known:
            # Unknown keys are ignored rather than fatal, so newer config files
            # remain loadable by older code and vice versa.
            continue
        ftype = hints.get(key)
        if ftype is not None and is_dataclass(ftype) and isinstance(value, dict):
            kwargs[key] = _from_dict(ftype, value)
        else:
            kwargs[key] = value
    return dc_type(**kwargs)
