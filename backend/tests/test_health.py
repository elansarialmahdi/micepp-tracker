from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def test_liveness_returns_service_metadata() -> None:
    app = create_app(Settings(app_env="test", app_name="MICEPP-Test", app_version="9.9.9"))
    with TestClient(app) as client:
        response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "MICEPP-Test", "version": "9.9.9"}
    assert response.headers["X-Request-ID"]


def test_readiness_returns_503_when_dependencies_are_unavailable() -> None:
    app = create_app(Settings(app_env="test"))
    with TestClient(app) as client:
        response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"
    assert response.json()["checks"]["postgresql"]["detail"] == "connection failed"
    assert "localhost" not in response.text
