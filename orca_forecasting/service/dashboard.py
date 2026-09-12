"""Dashboard-ready telemetry derived from the latest ORCA forecast artifact.

This adapter deliberately does not make a second prediction or invent weather
values.  It reads the parquet emitted by ``predict_forecast.py`` (or the package
inference command), selects observations around a requested coastal station, and
returns the model's observed/derived values with clear availability metadata.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


STATIONS: dict[str, dict[str, float | str]] = {
    # --- GUJARAT COASTLINE ---
    "Kandla": {"lat": 23.01, "lon": 70.22, "region": "Gujarat"},
    "Mundra": {"lat": 22.74, "lon": 69.71, "region": "Gujarat"},
    "Porbandar": {"lat": 21.64, "lon": 69.61, "region": "Gujarat"},
    "Veraval": {"lat": 20.91, "lon": 70.37, "region": "Gujarat"},
    "Pipavav": {"lat": 20.91, "lon": 71.50, "region": "Gujarat"},
    "Hazira": {"lat": 21.10, "lon": 72.64, "region": "Gujarat"},
    "Jakhau": {"lat": 23.24, "lon": 68.71, "region": "Gujarat"},
    "Mandvi": {"lat": 22.83, "lon": 69.36, "region": "Gujarat"},
    "Navlakhi": {"lat": 22.96, "lon": 70.45, "region": "Gujarat"},
    "Bedi": {"lat": 22.50, "lon": 70.04, "region": "Gujarat"},
    "Sikka": {"lat": 22.43, "lon": 69.84, "region": "Gujarat"},
    "Salaya": {"lat": 22.31, "lon": 69.60, "region": "Gujarat"},
    "Okha": {"lat": 22.47, "lon": 69.07, "region": "Gujarat"},
    "Mangrol": {"lat": 21.12, "lon": 70.11, "region": "Gujarat"},
    "Jafrabad": {"lat": 20.87, "lon": 71.37, "region": "Gujarat"},
    "Alang": {"lat": 21.41, "lon": 72.20, "region": "Gujarat"},
    "Bhavnagar": {"lat": 21.78, "lon": 72.18, "region": "Gujarat"},
    "Dahej": {"lat": 21.70, "lon": 72.53, "region": "Gujarat"},
    "Daman": {"lat": 20.40, "lon": 72.83, "region": "Daman & Diu"},

    # --- MAHARASHTRA / KONKAN COASTLINE ---
    "Mumbai": {"lat": 18.94, "lon": 72.84, "region": "Maharashtra"},
    "JNPT": {"lat": 18.95, "lon": 72.95, "region": "Maharashtra"},
    "Alibaug": {"lat": 18.73, "lon": 72.88, "region": "Maharashtra"},
    "Dighi": {"lat": 18.28, "lon": 72.98, "region": "Maharashtra"},
    "Dabhol": {"lat": 17.59, "lon": 73.18, "region": "Maharashtra"},
    "Jaigad": {"lat": 17.30, "lon": 73.21, "region": "Maharashtra"},
    "Ratnagiri": {"lat": 16.99, "lon": 73.30, "region": "Maharashtra"},
    "Vijaydurg": {"lat": 16.56, "lon": 73.33, "region": "Maharashtra"},
    "Devgad": {"lat": 16.38, "lon": 73.38, "region": "Maharashtra"},
    "Malvan": {"lat": 16.05, "lon": 73.47, "region": "Maharashtra"},

    # --- GOA COASTLINE ---
    "Mormugao": {"lat": 15.41, "lon": 73.80, "region": "Goa"},
    "Panaji": {"lat": 15.50, "lon": 73.83, "region": "Goa"},

    # --- KARNATAKA / KANARA COASTLINE ---
    "Karwar": {"lat": 14.80, "lon": 74.12, "region": "Karnataka"},
    "Tadri": {"lat": 14.52, "lon": 74.35, "region": "Karnataka"},
    "Honnavar": {"lat": 14.28, "lon": 74.44, "region": "Karnataka"},
    "Bhatkal": {"lat": 13.98, "lon": 74.55, "region": "Karnataka"},
    "Kundapura": {"lat": 13.63, "lon": 74.69, "region": "Karnataka"},
    "Malpe": {"lat": 13.35, "lon": 74.70, "region": "Karnataka"},
    "Mangaluru": {"lat": 12.91, "lon": 74.86, "region": "Karnataka"},

    # --- SOUTH WEST & EAST COAST ---
    "Kochi": {"lat": 9.93, "lon": 76.27, "region": "Kerala"},
    "Kollam": {"lat": 8.89, "lon": 76.59, "region": "Kerala"},
    "Thiruvananthapuram": {"lat": 8.52, "lon": 76.94, "region": "Kerala"},
    "Thoothukudi": {"lat": 8.76, "lon": 78.13, "region": "Tamil Nadu"},
    "Chennai": {"lat": 13.08, "lon": 80.27, "region": "Tamil Nadu"},
    "Kakinada": {"lat": 16.99, "lon": 82.25, "region": "Andhra Pradesh"},
    "Visakhapatnam": {"lat": 17.69, "lon": 83.22, "region": "Andhra Pradesh"},
    "Puri": {"lat": 19.81, "lon": 85.83, "region": "Odisha"},
    "Paradip": {"lat": 20.27, "lon": 86.67, "region": "Odisha"},
    "Digha": {"lat": 21.62, "lon": 87.51, "region": "West Bengal"},
}


def _forecast_path() -> Path:
    """Resolve both package and legacy predict_forecast.py output locations."""
    configured = os.environ.get("ORCA_DASHBOARD_FORECAST_PATH")
    repo_root = Path(__file__).resolve().parent.parent
    master_root = repo_root.parent
    candidates = [
        Path(configured) if configured else None,
        Path("latest_forecast_predictions.parquet"),
        Path("predictions.parquet"),
        master_root / "latest_forecast_predictions.parquet",
        repo_root / "predictions.parquet",
        master_root / "core_scripts" / "latest_forecast_predictions.parquet",
    ]
    for candidate in candidates:
        if candidate and candidate.exists():
            return candidate.resolve()
    raise FileNotFoundError(
        "No ORCA forecast parquet found. Set ORCA_DASHBOARD_FORECAST_PATH to the "
        "latest_forecast_predictions.parquet emitted by predict_forecast.py."
    )


def _source_path(forecast_path: Path) -> Path | None:
    """Optional physical-variable source paired with package score-only output."""
    configured = os.environ.get("ORCA_DASHBOARD_SOURCE_PATH")
    repo_root = Path(__file__).resolve().parent.parent
    master_root = repo_root.parent
    candidates = [
        Path(configured) if configured else None,
        forecast_path.parent / "orca_processed_ocean_data.parquet",
        forecast_path.parent.parent / "orca_processed_ocean_data.parquet",
        master_root / "orca_processed_ocean_data.parquet",
        repo_root / "orca_processed_ocean_data.parquet",
    ]
    return next((candidate.resolve() for candidate in candidates if candidate and candidate.exists()), None)


@lru_cache(maxsize=2)
def _read_forecast_cached(path_string: str, modified_ns: int) -> pd.DataFrame:
    # Column projection avoids loading unused model fields; parquet filtering keeps
    # the adapter compatible with both the legacy and refactored inference output.
    wanted = [
        "time", "latitude", "longitude", "thetao", "SSTA", "chl", "so", "MHI",
        "marine_health_state", "anomaly", "anomaly_score", "is_anomaly",
        "uo", "vo", "u10", "v10", "wind_speed", "current_speed", "salinity_anomaly",
        "sla_anomaly", "sla", "wave_height", "air_temperature",
        "weather", "event_id",
    ]
    path = Path(path_string)
    import pyarrow.parquet as pq

    columns = [name for name in wanted if name in pq.ParquetFile(path).schema.names]
    if not {"latitude", "longitude"}.issubset(columns):
        raise ValueError("Forecast parquet must contain latitude and longitude columns.")
    return pd.read_parquet(path, columns=columns)


def _read_forecast(path: Path) -> pd.DataFrame:
    """Reuse a large artifact until the forecast writer replaces it."""
    return _read_forecast_cached(str(path), path.stat().st_mtime_ns)


def _read_source_window(path: Path, forecast_time: Any, station: dict[str, float | str]) -> pd.DataFrame:
    """Read only the matching forecast day and coastal window from the raw feed."""
    import pyarrow.parquet as pq
    schema = pq.ParquetFile(path).schema.names
    wanted = [name for name in ["time", "latitude", "longitude", "thetao", "so", "chl", "MHI", "SSTA", "uo", "vo", "u10", "v10", "wind_speed", "current_speed", "marine_health_state", "anomaly", "anomaly_score"] if name in schema]
    if not {"latitude", "longitude"}.issubset(wanted):
        return pd.DataFrame()
    filters: list[tuple[str, str, Any]] = [
        ("latitude", ">=", float(station["lat"]) - 1.2), ("latitude", "<=", float(station["lat"]) + 1.2),
        ("longitude", ">=", float(station["lon"]) - 1.2), ("longitude", "<=", float(station["lon"]) + 1.2),
    ]
    if forecast_time is not None and "time" in wanted:
        # Avoid PyArrow type mismatch between timestamp[us] and string
        try:
            if isinstance(forecast_time, str):
                import pandas as pd
                forecast_time = pd.to_datetime(forecast_time)
            filters.insert(0, ("time", "==", forecast_time))
        except Exception:
            pass
    try:
        return pq.read_table(path, columns=wanted, filters=filters).to_pandas()
    except (TypeError, ValueError, OSError):
        return pd.DataFrame()


def _number(frame: pd.DataFrame, column: str, digits: int = 1) -> float | None:
    if column not in frame:
        return None
    values = pd.to_numeric(frame[column], errors="coerce").dropna()
    return round(float(values.mean()), digits) if not values.empty else None

def _log_number(frame: pd.DataFrame, column: str, digits: int = 2) -> float | None:
    """Return log1p-transformed mean of a column if available."""
    if column not in frame:
        return None
    values = pd.to_numeric(frame[column], errors="coerce").dropna()
    if values.empty:
        return None
    return round(float(np.log1p(values).mean()), digits) if not values.empty else None


def _timestamp(value: Any) -> str | None:
    if value is None:
        return None
    try:
        # Forecast package output may use epoch seconds while the legacy script
        # emits a YYYY-MM-DD string.
        parsed = pd.to_datetime(value, unit="s", utc=True) if isinstance(value, (int, float, np.integer)) else pd.to_datetime(value, utc=True)
        return parsed.isoformat()
    except (TypeError, ValueError, OverflowError):
        return str(value)


def _nearest_window(df: pd.DataFrame, station: dict[str, float | str]) -> pd.DataFrame:
    distance = np.hypot(df["latitude"] - float(station["lat"]), df["longitude"] - float(station["lon"]))
    # A nearest-cell window works with sparse forecast grids without pretending
    # that coastal stations lie exactly on an ocean grid point.
    return df.assign(_distance=distance).nsmallest(min(64, len(df)), "_distance")


def _pfz_candidates(df: pd.DataFrame, maximum: int = 8) -> list[dict[str, Any]]:
    if not {"chl", "latitude", "longitude"}.issubset(df.columns):
        return []
    work = df.dropna(subset=["chl", "latitude", "longitude"]).copy()
    if work.empty:
        return []
    # SSTA/temperature departure is the thermal-front proxy supplied by the
    # forecast.  If absent, no thermal-front claim is made.
    front = "SSTA" if "SSTA" in work.columns else "thetao" if "thetao" in work.columns else None
    if front is None:
        return []
    work["thermal_gradient"] = work.groupby("latitude")[front].transform(lambda x: x.diff().abs().fillna(0))
    chl_cutoff = work["chl"].quantile(0.75)
    gradient_cutoff = work["thermal_gradient"].quantile(0.75)
    selected = work[(work["chl"] >= chl_cutoff) & (work["thermal_gradient"] >= gradient_cutoff)]
    selected = selected.nlargest(maximum, ["chl", "thermal_gradient"])
    return [
        {
            "lat": round(float(row.latitude), 3),
            "lon": round(float(row.longitude), 3),
            "chlorophyll": round(float(row.chl), 2),
            "thermal_gradient": round(float(row.thermal_gradient), 3),
        }
        for row in selected.itertuples()
    ]


def build_dashboard_payload(station_name: str = "Kochi") -> dict[str, Any]:
    if station_name not in STATIONS:
        raise KeyError(station_name)
    source = _forecast_path()
    forecast = _read_forecast(source)
    if forecast.empty:
        raise ValueError("The forecast parquet contains no observations.")
    station = STATIONS[station_name]
    local = _nearest_window(forecast, station)
    source_time = local["time"].iloc[0] if "time" in local else None
    physical_source = _source_path(source)
    physical = _read_source_window(physical_source, source_time, station) if physical_source else pd.DataFrame()
    measurements = _nearest_window(physical, station) if not physical.empty else local

    if "is_anomaly" in local:
        alert_mask = local["is_anomaly"].astype(bool)
    elif "anomaly" in local:
        # Legacy predict_forecast.py follows sklearn's -1 (outlier) / 1
        # (inlier) convention; casting those integers to bool would flag both.
        alert_mask = pd.to_numeric(local["anomaly"], errors="coerce").eq(-1)
    else:
        alert_mask = pd.Series(False, index=local.index)
    alerts = int(alert_mask.sum())
    mhi = _number(measurements, "MHI")
    if mhi is None:
        # For the package output no MHI is persisted; expose a transparent proxy
        # based on the share of model-alert cells, labelled as such in the payload.
        mhi = round(max(0.0, 100.0 * (1 - alerts / max(len(local), 1))), 1)
        health_source = "alert-rate proxy (MHI not present in forecast artifact)"
    else:
        health_source = "forecast MHI"
    wind_u, wind_v = _number(measurements, "u10", 3), _number(measurements, "v10", 3)
    wind_speed = _number(measurements, "wind_speed")
    if wind_speed is None and wind_u is not None and wind_v is not None:
        wind_speed = round(float(np.hypot(wind_u, wind_v)), 1)
    bearing = round((np.degrees(np.arctan2(wind_u, wind_v)) + 360) % 360) if wind_u is not None and wind_v is not None else None
    states = measurements.get("marine_health_state")
    state = str(states.mode().iat[0]) if states is not None and not states.dropna().empty else ("Anomaly detected" if alerts else "Stable baseline")
    pfzs = _pfz_candidates(measurements)

    metrics = {
        "wave_height": {"label": "Wave Height", "value": _number(measurements, "wave_height"), "unit": "m"},
        "wind_speed": {"label": "Wind Speed", "value": wind_speed, "unit": "m/s"},
        "wind_direction": {"label": "Wind Direction", "value": bearing, "unit": "° bearing"},
        "sst": {"label": "Sea Surface Temp", "value": _number(measurements, "thetao"), "unit": "°C"},
        "air_temperature": {"label": "Air Temp", "value": _number(measurements, "air_temperature"), "unit": "°C"},
        "weather": {"label": "Atmospheric Weather", "value": str(measurements["weather"].mode().iat[0]) if "weather" in measurements and not measurements["weather"].dropna().empty else None, "unit": ""},
    }
    for metric in metrics.values():
        metric["available"] = metric["value"] is not None

    observation_time = _timestamp(source_time)
    return {
        "station": {"name": station_name, **station},
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "forecast_time": observation_time,
        "source": {"file": source.name, "model_output": True, "physical_source": physical_source.name if physical_source else None},
        "health": {"index": mhi, "state": state, "source": health_source, "local_alerts": alerts, "sample_cells": len(local)},
        "safety": {"status": "review" if alerts else "caution", "message": "Model signal available; confirm official marine advisories before departure."},
        "metrics": metrics,
        "station_telemetry": {
            "sst": _number(measurements, "thetao"),
            "salinity": _number(measurements, "so", 2),
            "chlorophyll": _number(measurements, "chl", 2),
            "log_chl": _log_number(measurements, "chl", 2),
            "wind_speed": wind_speed,
            "current_speed": _number(measurements, "current_speed", 2),
            "mhi": mhi,
            "thetao_anom": _number(measurements, "SSTA", 2) if "SSTA" in measurements else _number(measurements, "thetao_daily_anomaly", 2),
            "so_anom": _number(measurements, "salinity_anomaly", 2) if "salinity_anomaly" in measurements else _number(measurements, "so_daily_anomaly", 2),
            "sla_anom": _number(measurements, "sla_anomaly", 2) if "sla_anomaly" in measurements else _number(measurements, "sla_daily_anomaly", 2),
        },
        "pfzs": pfzs,
        "routes": [{"from": station_name, "to": {"lat": point["lat"], "lon": point["lon"]}, "type": "PFZ planning line"} for point in pfzs[:3]],
        "stations": [{"name": name, **data} for name, data in STATIONS.items()],
        "catch_species": ["Sardines", "Mackerel", "Squid"],
        "disclaimer": "PFZs are model-derived planning cues, not safe-navigation clearance. Use official notices, charts, weather and local harbour authority guidance.",
    }
