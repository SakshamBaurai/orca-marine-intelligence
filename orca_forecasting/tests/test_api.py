"""FastAPI service smoke tests (stateless scoring over HTTP)."""

from __future__ import annotations

import pandas as pd
import pytest

fastapi = pytest.importorskip("fastapi")
pytest.importorskip("httpx")  # required by fastapi.testclient.TestClient

from fastapi.testclient import TestClient  # noqa: E402

from orca.inference import InferenceEngine  # noqa: E402
from orca.synth import make_synthetic_dataset  # noqa: E402


@pytest.fixture
def client(trained_bundle, synth_spec):
    from service import app as app_module

    cfg = trained_bundle["cfg"]
    engine = InferenceEngine.from_dir(trained_bundle["artifact_dir"], prefer_onnx=False, data_cfg=cfg.data)
    app_module.configure(engine, cfg)
    return TestClient(app_module.app)


def _sample_observation(synth_spec, cfg) -> dict:
    df = make_synthetic_dataset(synth_spec)
    row = df[df["depth_bin"] == cfg.data.surface_layer].iloc[0]
    return {
        "time": str(row["time"]),
        "latitude": float(row["latitude"]),
        "longitude": float(row["longitude"]),
        "thetao": float(row["thetao"]), "so": float(row["so"]),
        "uo": float(row["uo"]), "vo": float(row["vo"]),
        "chl": float(row["chl"]), "sla": float(row["sla"]),
        "u10": float(row["u10"]), "v10": float(row["v10"]),
    }


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and body["model_loaded"] is True
    assert body["backend"] in {"joblib", "onnx"}


def test_metadata_exposes_feature_contract(client):
    r = client.get("/metadata")
    assert r.status_code == 200
    body = r.json()
    assert len(body["feature_names"]) == 10
    assert "thetao_clim_z" in body["feature_names"]
    assert isinstance(body["threshold"], float)
    assert set(["time", "latitude", "longitude"]).issubset(body["required_input_columns"])


def test_predict_single(client, synth_spec, trained_bundle):
    obs = _sample_observation(synth_spec, trained_bundle["cfg"])
    r = client.post("/predict", json={"observation": obs})
    assert r.status_code == 200, r.text
    pred = r.json()["prediction"]
    assert set(["raw_score", "anomaly_score", "is_anomaly"]).issubset(pred)
    assert isinstance(pred["is_anomaly"], bool)


def test_predict_batch(client, synth_spec, trained_bundle):
    obs = _sample_observation(synth_spec, trained_bundle["cfg"])
    r = client.post("/predict/batch", json={"observations": [obs, obs, obs]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["n"] == 3
    assert len(body["predictions"]) == 3


def test_predict_rejects_incomplete_record(client):
    r = client.post("/predict", json={"observation": {"time": "2020-01-01", "latitude": 1.0}})
    # Missing required physical fields -> Pydantic validation error (422).
    assert r.status_code == 422
