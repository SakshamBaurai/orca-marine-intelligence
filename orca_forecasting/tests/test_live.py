"""Live-feed normalization and geographic-scope guards (no external network)."""

from __future__ import annotations

from datetime import date

import pytest

from orca.config import Config
from orca.live import LiveIngestionError, fetch_daily_observations


def _cfg() -> Config:
    return Config.from_dict({
        "data": {"lat_min": 8.0, "lat_max": 22.0, "lon_min": 65.0, "lon_max": 77.0},
        "live": {
            "enabled": True,
            "endpoint": "https://example.test/ocean",
            "records_path": "data.records",
            "column_map": {"thetao": "temperature"},
            "static_params": {"dataset": "daily"},
        },
    })


def _record(latitude=12.0, longitude=70.0) -> dict:
    return {
        "time": "2026-09-10", "latitude": latitude, "longitude": longitude,
        "temperature": 28.0, "so": 35.0, "uo": 0.1, "vo": 0.2,
        "chl": 1.0, "sla": 0.03, "u10": 4.0, "v10": 2.0,
    }


def test_live_feed_maps_provider_fields_and_discards_out_of_region_rows(monkeypatch):
    cfg = _cfg()
    captured = {}

    def fake_request(_live, params):
        captured.update(params)
        return {"data": {"records": [_record(), _record(latitude=25.0)]}}

    monkeypatch.setattr("orca.live._request_json", fake_request)
    frame, report = fetch_daily_observations(cfg, date(2026, 9, 10))

    assert len(frame) == 1
    assert frame.loc[0, "thetao"] == pytest.approx(28.0)
    assert report["rows_received"] == 2 and report["rows_accepted"] == 1
    assert captured["date"] == "2026-09-10"
    assert captured["lat_min"] == 8.0 and captured["lon_max"] == 77.0


def test_live_feed_requires_complete_bounding_box():
    cfg = _cfg()
    cfg.data.lon_max = None
    with pytest.raises(LiveIngestionError, match="all four data bounds"):
        fetch_daily_observations(cfg, date(2026, 9, 10))
