from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from app.db.session import get_db_session
from app.main import create_app


def test_ping_does_not_require_database() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/api/ping")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_checks_database() -> None:
    class HealthySession:
        async def execute(self, statement):
            assert str(statement) == "SELECT 1"

    async def fake_session():
        yield HealthySession()

    app = create_app()
    app.dependency_overrides[get_db_session] = fake_session
    with TestClient(app) as client:
        response = client.get("/api/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_returns_503_when_database_is_unavailable() -> None:
    class BrokenSession:
        async def execute(self, statement):
            raise SQLAlchemyError("connection refused")

    async def fake_session():
        yield BrokenSession()

    app = create_app()
    app.dependency_overrides[get_db_session] = fake_session
    with TestClient(app) as client:
        response = client.get("/api/health/ready")
    assert response.status_code == 503
    assert response.json() == {"detail": "Database unavailable"}
