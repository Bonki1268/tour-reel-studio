import pytest
from fastapi.testclient import TestClient

from app.api.main import create_app
from app.config import load_settings

pytestmark = pytest.mark.S01


def test_r001_health_returns_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    client = TestClient(create_app(load_settings()))

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
