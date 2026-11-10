from fastapi.testclient import TestClient

from app.api.routes import health
from app.main import create_app


def test_ping() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/api/ping")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_loads_demo_catalogue() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/api/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_when_catalogue_is_unavailable(monkeypatch) -> None:
    def unavailable():
        raise FileNotFoundError

    monkeypatch.setattr(health, "atlas", unavailable)
    with TestClient(create_app()) as client:
        response = client.get("/api/health/ready")
    assert response.status_code == 503
