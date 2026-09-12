"""Live daily ingestion: bounded provider response -> canonical ORCA records.

This module intentionally has a narrow, vendor-neutral boundary: the configured
endpoint returns JSON records.  For a provider that exposes NetCDF (such as
Copernicus Marine), deploy a small adapter/gateway that performs the provider
download and returns the eight canonical variables.  Credentials remain in an
environment variable, never in YAML or source control.
"""

from __future__ import annotations

import json
import os
import time
from datetime import date
from typing import Any, Dict, Iterable, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd

from .config import Config, LiveDataConfig
from .inference import InferenceEngine
from .schema import ID_COLUMNS, RAW_FEATURES


class LiveIngestionError(RuntimeError):
    """A recoverable failure while obtaining or validating current observations."""


def _configured_bbox(cfg: Config) -> Dict[str, float]:
    d = cfg.data
    values = (d.lat_min, d.lat_max, d.lon_min, d.lon_max)
    if any(v is None for v in values):
        raise LiveIngestionError("Live ingestion requires all four data bounds: lat_min, lat_max, lon_min, lon_max.")
    if d.lat_min > d.lat_max or d.lon_min > d.lon_max:
        raise LiveIngestionError("Configured geographic bounds are invalid.")
    return {"lat_min": float(d.lat_min), "lat_max": float(d.lat_max), "lon_min": float(d.lon_min), "lon_max": float(d.lon_max)}


def _records_at_path(payload: Any, path: str | None) -> Iterable[Dict[str, Any]]:
    current = payload
    if path:
        for part in path.split("."):
            if not isinstance(current, dict) or part not in current:
                raise LiveIngestionError(f"Live response does not contain records_path {path!r}.")
            current = current[part]
    if not isinstance(current, list) or not all(isinstance(row, dict) for row in current):
        raise LiveIngestionError("Live response must be a JSON list of records (or records_path must resolve to one).")
    return current


def _request_json(live: LiveDataConfig, params: Dict[str, Any]) -> Any:
    if not live.enabled:
        raise LiveIngestionError("Live ingestion is disabled. Set live.enabled: true after configuring an endpoint.")
    if not live.endpoint:
        raise LiveIngestionError("live.endpoint is required when live ingestion is enabled.")
    if live.request_method.upper() != "GET":
        raise LiveIngestionError("Only GET live endpoints are supported by this adapter.")
    if not live.endpoint.lower().startswith("https://"):
        raise LiveIngestionError("Live endpoint must use HTTPS.")

    headers = {"Accept": "application/json"}
    if live.api_key_env:
        token = os.environ.get(live.api_key_env)
        if not token:
            raise LiveIngestionError(f"Required live API credential {live.api_key_env!r} is not set.")
        headers[live.api_key_header] = f"{live.api_key_prefix}{token}"
    sep = "&" if "?" in live.endpoint else "?"
    url = f"{live.endpoint}{sep}{urlencode(params, doseq=True)}"
    attempts = max(1, int(live.retry_attempts))
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            request = Request(url, headers=headers, method="GET")
            with urlopen(request, timeout=float(live.timeout_seconds)) as response:
                return json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc
            # Do not retry non-rate-limited client errors; these are config/auth issues.
            if isinstance(exc, HTTPError) and 400 <= exc.code < 500 and exc.code != 429:
                break
            if attempt < attempts - 1:
                time.sleep(float(live.retry_backoff_seconds) * (2**attempt))
    raise LiveIngestionError(f"Live provider request failed: {last_error}") from last_error


def fetch_daily_observations(cfg: Config, observation_date: date) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Fetch, normalize and strictly bound one day's records from the configured feed."""
    bbox = _configured_bbox(cfg)
    live = cfg.live
    params: Dict[str, Any] = dict(live.static_params)
    params.update({
        live.date_param: observation_date.isoformat(),
        live.lat_min_param: bbox["lat_min"], live.lat_max_param: bbox["lat_max"],
        live.lon_min_param: bbox["lon_min"], live.lon_max_param: bbox["lon_max"],
    })
    payload = _request_json(live, params)
    rows = list(_records_at_path(payload, live.records_path))
    if len(rows) > int(live.max_response_rows):
        raise LiveIngestionError(f"Live response has {len(rows)} rows; exceeds max_response_rows.")

    # Canonical keys map to provider keys; omitted keys are assumed canonical.
    frame = pd.DataFrame.from_records(rows)
    rename = {source: canonical for canonical, source in live.column_map.items() if source in frame.columns}
    frame = frame.rename(columns=rename)
    required = [*ID_COLUMNS, *RAW_FEATURES]
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise LiveIngestionError(f"Live response is missing canonical columns: {', '.join(missing)}.")
    frame = frame[required].copy()
    frame["time"] = pd.to_datetime(frame["time"], errors="coerce")
    for column in ["latitude", "longitude", *RAW_FEATURES]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce").astype("float32")
    frame = frame.dropna(subset=required)
    frame = frame.loc[
        frame["latitude"].between(bbox["lat_min"], bbox["lat_max"])
        & frame["longitude"].between(bbox["lon_min"], bbox["lon_max"])
    ].reset_index(drop=True)
    report = {"date": observation_date.isoformat(), "rows_received": len(rows), "rows_accepted": len(frame), "bbox": bbox}
    return frame, report


def fetch_and_score_daily(cfg: Config, engine: InferenceEngine, observation_date: date) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """The live operational path: fetch normalized daily records and score the fixed baseline."""
    frame, report = fetch_daily_observations(cfg, observation_date)
    if frame.empty:
        raise LiveIngestionError("No valid live observations remain inside the configured bounding box.")
    scored = engine.score_frame(frame, with_features=cfg.analytics.enable)
    report.update({"backend": engine.backend, "threshold": engine.threshold, "alerts": int(scored["is_anomaly"].sum())})
    return scored, report
