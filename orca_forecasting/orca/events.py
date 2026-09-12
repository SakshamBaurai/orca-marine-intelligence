"""Offline spatial clustering of flagged anomalies into coherent "events".

Batch reporting only — not part of the low-latency serving path.  Given the rows
an operator has flagged (e.g. the output of batch inference filtered to
``is_anomaly``), it groups nearby points into spatial events using DBSCAN and
summarizes each with a centroid, bounding box, footprint area and severity.

Geographic generality:

* Clustering uses the **haversine** metric on (lat, lon) in radians, so the same
  ``eps`` (in degrees) behaves sensibly at any latitude — no planar/basin
  assumption.
* Footprint area is the sum of per-point **spherical** cell areas
  (:func:`orca.geo.cell_area_km2`) at each point's latitude, with the native grid
  spacing *inferred from the data* when not configured.  This replaces the
  notebook's hardcoded ``pixel_count * 740 km^2``.
* Map centering uses data-driven bounds, never fixed coordinates.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from . import geo
from .config import EventsConfig


def detect_events(
    df: pd.DataFrame,
    cfg: EventsConfig,
    lat_col: str = "latitude",
    lon_col: str = "longitude",
    time_col: str = "time",
    score_col: str = "anomaly_score",
    grid_spacing_deg: Optional[float] = None,
) -> pd.DataFrame:
    """Cluster flagged points into events; return one summary row per event.

    ``df`` should already be filtered to the points of interest (e.g. anomalies).
    Returns an empty, correctly-typed frame when there is nothing to cluster.
    """
    cols = [
        "event_id", "n_points", "lat_center", "lon_center",
        "lat_min", "lat_max", "lon_min", "lon_max",
        "area_km2", "mean_score", "max_score", "time_start", "time_end", "duration_days",
    ]
    if df is None or len(df) < max(cfg.min_samples, 1):
        return pd.DataFrame(columns=cols)

    from sklearn.cluster import DBSCAN

    lat = df[lat_col].to_numpy(dtype="float64")
    lon = df[lon_col].to_numpy(dtype="float64")
    coords_rad = np.radians(np.column_stack([lat, lon]))
    eps_rad = np.radians(cfg.eps_deg)

    labels = DBSCAN(
        eps=eps_rad, min_samples=cfg.min_samples, metric="haversine"
    ).fit_predict(coords_rad)

    # Grid spacing for area: config override -> inferred from data -> geo default.
    spacing = grid_spacing_deg if grid_spacing_deg is not None else cfg.grid_spacing_deg
    if spacing is None:
        sp_lat = geo.infer_grid_spacing(lat)
        sp_lon = geo.infer_grid_spacing(lon)
        spacing_lat, spacing_lon = sp_lat, sp_lon
    else:
        spacing_lat = spacing_lon = float(spacing)

    scores = df[score_col].to_numpy(dtype="float64") if score_col in df.columns else np.full(len(df), np.nan)
    times = pd.to_datetime(df[time_col]) if time_col in df.columns else None

    rows: List[Dict[str, Any]] = []
    for label in sorted(set(labels)):
        if label == -1:  # DBSCAN noise
            continue
        m = labels == label
        plat, plon, pscore = lat[m], lon[m], scores[m]
        per_point_area = geo.cell_area_km2(plat, spacing_lat, spacing_lon)
        row: Dict[str, Any] = {
            "event_id": int(label),
            "n_points": int(m.sum()),
            "lat_center": float(plat.mean()),
            "lon_center": float(plon.mean()),
            "lat_min": float(plat.min()), "lat_max": float(plat.max()),
            "lon_min": float(plon.min()), "lon_max": float(plon.max()),
            "area_km2": float(np.nansum(per_point_area)),
            "mean_score": float(np.nanmean(pscore)) if pscore.size else None,
            "max_score": float(np.nanmax(pscore)) if pscore.size else None,
        }
        if times is not None:
            pt = times[m]
            row["time_start"] = pt.min()
            row["time_end"] = pt.max()
            row["duration_days"] = float((pt.max() - pt.min()).days)
        else:
            row["time_start"] = row["time_end"] = None
            row["duration_days"] = None
        rows.append(row)

    events = pd.DataFrame(rows, columns=cols)
    if not events.empty:
        events = events.sort_values("area_km2", ascending=False, ignore_index=True)
    return events


def map_extent(df: pd.DataFrame, lat_col: str = "latitude", lon_col: str = "longitude") -> Dict[str, float]:
    """Data-driven bounding box + center for map rendering (no fixed coords)."""
    lat_min, lat_max, lon_min, lon_max = geo.data_bounds(df[lat_col], df[lon_col])
    return {
        "lat_min": lat_min, "lat_max": lat_max, "lon_min": lon_min, "lon_max": lon_max,
        "lat_center": (lat_min + lat_max) / 2.0, "lon_center": (lon_min + lon_max) / 2.0,
    }
