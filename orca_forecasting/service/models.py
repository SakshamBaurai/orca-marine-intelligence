"""Pydantic request/response models for the ORCA scoring service.

Kept intentionally permissive: the core physical inputs are required, but unknown
extra keys are allowed so upstream producers can attach provenance without
breaking the contract.

The package targets Pydantic v2 (see ``pyproject.toml`` service extra), but the
imports degrade gracefully to v1 so the module still loads in a mixed
environment.  A tiny shim hides the v1/v2 spelling differences (``min_items`` vs
``min_length`` for list length; ``class Config`` vs ``ConfigDict`` for ``extra``).
"""

from __future__ import annotations

from datetime import date as Date
from typing import Any, Dict, List, Optional

try:  # Pydantic v2 (the pinned target)
    from pydantic import BaseModel, ConfigDict, Field

    _PYDANTIC_V2 = True
except ImportError:  # pragma: no cover - v1 fallback
    from pydantic import BaseModel, Field  # type: ignore

    ConfigDict = None  # type: ignore
    _PYDANTIC_V2 = False


def _min_len_field(n: int):
    """A required list Field with a minimum length, spelled for the installed pydantic."""
    key = "min_length" if _PYDANTIC_V2 else "min_items"
    return Field(..., **{key: n})


class Observation(BaseModel):
    """A single clean surface observation to be scored."""

    time: str = Field(..., description="ISO timestamp/date of the observation.")
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float
    thetao: float = Field(..., description="Sea-water potential temperature.")
    so: float = Field(..., description="Salinity.")
    uo: float = Field(..., description="Eastward ocean current velocity.")
    vo: float = Field(..., description="Northward ocean current velocity.")
    chl: float = Field(..., description="Chlorophyll concentration.")
    sla: float = Field(..., description="Sea-level anomaly.")
    u10: float = Field(..., description="Eastward 10 m wind.")
    v10: float = Field(..., description="Northward 10 m wind.")

    # Allow unknown extra keys (provenance, source ids, ...) without breaking.
    if _PYDANTIC_V2:
        model_config = ConfigDict(extra="allow")
    else:  # pragma: no cover - v1 path

        class Config:
            extra = "allow"


class PredictRequest(BaseModel):
    observation: Observation


class BatchPredictRequest(BaseModel):
    observations: List[Observation] = _min_len_field(1)


class Prediction(BaseModel):
    raw_score: float = Field(..., description="Raw IsolationForest score_samples (lower = more anomalous).")
    anomaly_score: float = Field(..., description="Monotonic severity (higher = more anomalous).")
    is_anomaly: bool = Field(..., description="True when raw_score <= calibrated threshold.")
    ecological_state: Optional[str] = None
    marine_health_index: Optional[float] = None


class PredictResponse(BaseModel):
    prediction: Prediction
    threshold: float
    backend: str


class BatchPredictResponse(BaseModel):
    predictions: List[Prediction]
    n: int
    n_alerts: int
    threshold: float
    backend: str


class LivePredictRequest(BaseModel):
    """Request a bounded daily provider fetch followed by comparative scoring."""

    observation_date: Optional[Date] = None
    max_records: int = Field(10_000, ge=1, le=100_000)


class LivePredictResponse(BaseModel):
    predictions: List[Prediction]
    n: int
    n_alerts: int
    threshold: float
    backend: str
    ingestion: Dict[str, Any]


class HealthResponse(BaseModel):
    status: str
    model_loaded: bool
    backend: Optional[str] = None
    version: Optional[str] = None


class MetadataResponse(BaseModel):
    version: str
    backend: str
    threshold: float
    feature_names: List[str]
    required_input_columns: List[str]
    model: Dict[str, Any] = {}
    climatology: Dict[str, Any] = {}
    data_extent: Dict[str, Any] = {}
    boundaries: Dict[str, Any] = {}


class ChatContext(BaseModel):
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    selected_location: Optional[Dict[str, float]] = None
    selected_port: Optional[str] = None
    selected_station: Optional[str] = None
    active_layer: Optional[str] = None
    viewport: Optional[Dict[str, float]] = None
    view_mode: Optional[str] = None

    if _PYDANTIC_V2:
        model_config = ConfigDict(extra="allow")
    else:  # pragma: no cover
        class Config:
            extra = "allow"


class AgentChatRequest(BaseModel):
    message: str = Field(..., description="User query for the ORCA agent")
    session_id: Optional[str] = Field("default", description="Session ID for conversational state")
    language: Optional[str] = Field("en", description="Selected language code (en, hi, mr, gu, ml, ta, te, kn, bn, pa, or)")
    context: Optional[ChatContext] = Field(default=None, description="Current frontend view/location context")


class SafeAction(BaseModel):
    type: str = Field(..., description="Action type: FLY_TO, SHOW_FISHING_SPOT, etc.")
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    height: Optional[float] = None
    port_id: Optional[str] = None
    station_id: Optional[str] = None
    metric: Optional[str] = None
    score: Optional[float] = None
    status: Optional[str] = None

    if _PYDANTIC_V2:
        model_config = ConfigDict(extra="allow")
    else:  # pragma: no cover
        class Config:
            extra = "allow"


class AgentChatResponse(BaseModel):
    session_id: str
    message: str = Field(..., description="Response message from the agent")
    reply: Optional[str] = Field(None, description="Alias for message")
    language: Optional[str] = Field("en", description="Language code of the returned response")
    data: List[Dict[str, Any]] = Field(default_factory=list, description="Structured scientific data cards")
    actions: List[Dict[str, Any]] = Field(default_factory=list, description="Whitelisted safe UI actions")
    tool_calls: List[Dict[str, Any]] = Field(default_factory=list, description="Executed scientific tools")
    spots: List[Dict[str, Any]] = Field(default_factory=list, description="Ranked candidate fishing spots")
    selected_spot_index: int = Field(0, description="Active selected spot index")
    origin_port: Optional[Dict[str, Any]] = Field(None, description="Origin port metadata")
