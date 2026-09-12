"""Geography-agnostic helpers: cells, bands, spherical area, grid inference."""

from __future__ import annotations

import numpy as np
import pandas as pd

from orca import geo


def test_spatial_cell_floors_to_cell_corner():
    lat = pd.Series([14.2, 14.9, -0.1])
    lon = pd.Series([71.6, 71.05, 0.4])
    la, lo = geo.spatial_cell(lat, lon, 1.0)
    np.testing.assert_allclose(la, [14.0, 14.0, -1.0])
    np.testing.assert_allclose(lo, [71.0, 71.0, 0.0])


def test_cell_area_matches_spherical_formula_and_shrinks_toward_poles():
    # Analytic: R^2 * dlon_rad * (sin(top) - sin(bottom))
    R = geo.EARTH_RADIUS_KM
    dlat = dlon = 0.25
    for lat in [0.0, 30.0, 60.0, 85.0]:
        top = np.deg2rad(lat + dlat / 2)
        bot = np.deg2rad(lat - dlat / 2)
        expected = (R ** 2) * np.deg2rad(dlon) * (np.sin(top) - np.sin(bot))
        got = geo.cell_area_km2(np.array([lat]), dlat, dlon)[0]
        np.testing.assert_allclose(got, abs(expected), rtol=1e-6)
    # Monotonic decrease with latitude.
    areas = geo.cell_area_km2(np.array([0.0, 30.0, 60.0, 85.0]), dlat, dlon)
    assert np.all(np.diff(areas) < 0)


def test_infer_grid_spacing_from_regular_grid():
    coords = np.arange(0, 10.0001, 0.25)
    assert abs(geo.infer_grid_spacing(coords) - 0.25) < 1e-9


def test_season_bin_month_and_doy_window():
    t = pd.Series(pd.to_datetime(["2020-01-15", "2020-12-31"]))
    months = geo.season_bin(t, "month")
    assert list(months) == [1, 12]
    windows = geo.season_bin(t, "doy_window", doy_window_days=15)
    assert windows[0] == 0  # first window of the year


def test_data_bounds():
    lat = pd.Series([-5.0, 5.0, 2.0])
    lon = pd.Series([10.0, 30.0, 20.0])
    assert geo.data_bounds(lat, lon) == (-5.0, 5.0, 10.0, 30.0)
