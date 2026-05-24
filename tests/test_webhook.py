import json
from pathlib import Path
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from webhook.server import create_app


def build_payload(timestamp: datetime) -> dict:
    return {
        "symbol": "ETHUSDT",
        "timeframe": "1m",
        "signal": "LONG",
        "strategy_name": "Example Strategy",
        "strategy_parameters": {"risk_pct": 0.01},
        "timestamp": timestamp.isoformat(),
        "price": 2000.0,
        "risk_settings": {"stop_loss_pct": 0.01, "take_profit_pct": 0.02},
    }


def test_webhook_endpoint_accepts_valid_payload(tmp_path, monkeypatch):
    monkeypatch.setenv("WEBHOOK_DB_PATH", str(tmp_path / "webhook.db"))
    monkeypatch.setenv("WEBHOOK_REPORT_DIR", str(tmp_path / "reports"))
    monkeypatch.setenv("WEBHOOK_LOG_DIR", str(tmp_path / "logs"))
    app = create_app()
    client = TestClient(app)

    payload = build_payload(datetime.now(timezone.utc))
    response = client.post("/webhook", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["result"]["order_created"] is True


def test_webhook_rejects_duplicate_payloads(tmp_path, monkeypatch):
    monkeypatch.setenv("WEBHOOK_DB_PATH", str(tmp_path / "webhook.db"))
    monkeypatch.setenv("WEBHOOK_REPORT_DIR", str(tmp_path / "reports"))
    monkeypatch.setenv("WEBHOOK_LOG_DIR", str(tmp_path / "logs"))
    app = create_app()
    client = TestClient(app)

    payload = build_payload(datetime.now(timezone.utc))
    response = client.post("/webhook", json=payload)
    assert response.status_code == 200
    second = client.post("/webhook", json=payload)
    assert second.status_code == 400
    assert "Duplicate alert" in second.json()["detail"]


def test_webhook_replay_endpoint_runs_payloads(tmp_path, monkeypatch):
    monkeypatch.setenv("WEBHOOK_DB_PATH", str(tmp_path / "webhook.db"))
    monkeypatch.setenv("WEBHOOK_REPORT_DIR", str(tmp_path / "reports"))
    monkeypatch.setenv("WEBHOOK_LOG_DIR", str(tmp_path / "logs"))
    app = create_app()
    client = TestClient(app)

    payloads = [build_payload(datetime.now(timezone.utc)) for _ in range(2)]
    response = client.post("/replay", json={"payloads": payloads, "speed_multiplier": 20.0})
    assert response.status_code == 200
    assert response.json()["count"] == 2


def test_webhook_malformed_payload_returns_bad_request(tmp_path, monkeypatch):
    monkeypatch.setenv("WEBHOOK_DB_PATH", str(tmp_path / "webhook.db"))
    monkeypatch.setenv("WEBHOOK_REPORT_DIR", str(tmp_path / "reports"))
    monkeypatch.setenv("WEBHOOK_LOG_DIR", str(tmp_path / "logs"))
    app = create_app()
    client = TestClient(app)

    response = client.post("/webhook", json={"symbol": "ETHUSDT"})
    assert response.status_code == 422


def test_railway_deployment_files_exist():
    root = Path(__file__).resolve().parents[1]
    assert (root / "Dockerfile").exists()
    assert (root / "Procfile").exists()
    assert (root / "railway.json").exists()
    assert (root / ".github" / "workflows" / "ci.yml").exists()
