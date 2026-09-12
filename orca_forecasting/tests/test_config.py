"""Config (de)serialization — especially nested dataclass construction.

Regression guard for the ``from __future__ import annotations`` pitfall where
``dataclasses.fields().type`` is a *string*, which previously prevented nested
sub-configs from being built from YAML/dict.
"""

from __future__ import annotations

from orca.config import ClimatologyConfig, Config, DataConfig, LiveDataConfig


def test_from_dict_builds_nested_dataclasses():
    cfg = Config.from_dict({
        "data": {"source_parquet": "/tmp/x.parquet", "chunk_rows": 1234},
        "climatology": {"cell_size_deg": 2.0, "anomaly_vars": ["thetao", "chl"]},
        "model": {"n_estimators": 33},
    })
    assert isinstance(cfg.data, DataConfig)
    assert cfg.data.source_parquet == "/tmp/x.parquet"
    assert cfg.data.chunk_rows == 1234
    assert isinstance(cfg.climatology, ClimatologyConfig)
    assert cfg.climatology.cell_size_deg == 2.0
    assert cfg.climatology.anomaly_vars == ["thetao", "chl"]
    assert cfg.model.n_estimators == 33
    # Untouched sub-configs keep their defaults.
    assert cfg.calibration.target_alert_rate == 0.01


def test_live_and_geographic_configuration_are_deserialized():
    cfg = Config.from_dict({
        "data": {"lat_min": 8.25, "lat_max": 21.75, "lon_min": 65.25, "lon_max": 77.0},
        "live": {"enabled": True, "endpoint": "https://provider.example/data"},
    })
    assert cfg.data.lat_min == 8.25 and cfg.data.lon_max == 77.0
    assert isinstance(cfg.live, LiveDataConfig)
    assert cfg.live.enabled is True


def test_unknown_keys_are_ignored():
    cfg = Config.from_dict({"data": {"nope": 1}, "totally_unknown": {"a": 2}})
    assert isinstance(cfg.data, DataConfig)


def test_yaml_round_trip(tmp_path):
    import yaml

    cfg = Config.from_dict({"data": {"source_parquet": "/data/p.parquet"}, "seed": 99})
    p = tmp_path / "cfg.yaml"
    p.write_text(yaml.safe_dump(cfg.to_dict()), encoding="utf-8")

    loaded = Config.from_yaml(p)
    assert isinstance(loaded.data, DataConfig)
    assert loaded.data.source_parquet == "/data/p.parquet"
    assert loaded.seed == 99
