"""Geography-agnostic spatial/temporal helpers.

None of these functions assume a particular basin, hemisphere, or grid extent.
Spatial cells and latitude bands are derived arithmetically from configurable
resolutions; pixel areas use proper spherical geometry (cos-latitude) instead of
a hardcoded constant; grid spacing and map extent are inferred from the data.
This is what lets the same code scale from a single regional basin to a global
grid.
"""

from __future__ import annotations

from typing import Tuple, Union

import numpy as np
import pandas as pd

ArrayLike = Union[np.ndarray, pd.Series]

EARTH_RADIUS_KM = 6371.0088


def _as_float_array(x: ArrayLike) -> np.ndarray:
    return np.asarray(x, dtype="float64")


def spatial_cell(
    lat: ArrayLike, lon: ArrayLike, cell_size_deg: float
) -> Tuple[np.ndarray, np.ndarray]:
    """Snap coordinates to the lower-left corner of their containing cell.

    Works for any coordinate range; longitudes are not wrapped so both 0..360
    and -180..180 conventions are handled consistently as long as the dataset is
    self-consistent.
    """
    if cell_size_deg <= 0:
        raise ValueError("cell_size_deg must be positive")
    la = _as_float_array(lat)
    lo = _as_float_array(lon)
    lat_cell = np.floor(la / cell_size_deg) * cell_size_deg
    lon_cell = np.floor(lo / cell_size_deg) * cell_size_deg
    # Round to mitigate float noise so identical coords map to identical labels.
    return np.round(lat_cell, 4).astype("float32"), np.round(lon_cell, 4).astype("float32")


def lat_band(lat: ArrayLike, band_size_deg: float) -> np.ndarray:
    """Latitude band lower edge — the intermediate climatology fallback level."""
    if band_size_deg <= 0:
        raise ValueError("band_size_deg must be positive")
    la = _as_float_array(lat)
    band = np.floor(la / band_size_deg) * band_size_deg
    return np.round(band, 4).astype("float32")


def season_bin(
    time: pd.Series, temporal_resolution: str = "month", doy_window_days: int = 15
) -> np.ndarray:
    """Map timestamps to an integer seasonal bin.

    ``month`` -> 1..12.  ``doy_window`` -> day-of-year windows (e.g. 15-day),
    which generalizes to unseen dates because it never keys on the exact date.
    """
    t = pd.to_datetime(pd.Series(time).reset_index(drop=True))
    if temporal_resolution == "month":
        return t.dt.month.to_numpy().astype("int16")
    if temporal_resolution == "doy_window":
        if doy_window_days <= 0:
            raise ValueError("doy_window_days must be positive")
        doy = t.dt.dayofyear.to_numpy()
        return ((doy - 1) // doy_window_days).astype("int16")
    raise ValueError(f"Unknown temporal_resolution: {temporal_resolution!r}")


def cell_area_km2(
    lat_center_deg: ArrayLike, dlat_deg: float, dlon_deg: float
) -> np.ndarray:
    """Area of a lat/lon grid cell in km^2 using spherical geometry.

    area = R^2 * dlon_rad * (sin(lat_top) - sin(lat_bottom))

    Correct at any latitude (poles included), replacing the notebook's
    hardcoded ``pixel_count * 740`` which silently assumed a 0.25 deg grid near
    ~15 N.
    """
    lat_c = _as_float_array(lat_center_deg)
    dlat = np.deg2rad(dlat_deg)
    dlon = np.deg2rad(dlon_deg)
    lat_c_rad = np.deg2rad(lat_c)
    top = lat_c_rad + dlat / 2.0
    bottom = lat_c_rad - dlat / 2.0
    area = (EARTH_RADIUS_KM ** 2) * dlon * (np.sin(top) - np.sin(bottom))
    return np.abs(area)


def infer_grid_spacing(coord: ArrayLike, default: float = 0.25) -> float:
    """Infer native grid spacing as the smallest positive coordinate step."""
    vals = np.unique(_as_float_array(coord))
    if vals.size < 2:
        return float(default)
    diffs = np.diff(vals)
    diffs = diffs[diffs > 1e-9]
    if diffs.size == 0:
        return float(default)
    return float(np.round(np.min(diffs), 6))


def data_bounds(
    lat: ArrayLike, lon: ArrayLike
) -> Tuple[float, float, float, float]:
    """(lat_min, lat_max, lon_min, lon_max) — for data-driven map centering."""
    la = _as_float_array(lat)
    lo = _as_float_array(lon)
    return float(np.min(la)), float(np.max(la)), float(np.min(lo)), float(np.max(lo))
