from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from pytest_bdd import given, parsers, scenarios, then, when

from app.api.main import create_app
from app.config import ConfigError, Settings, load_settings

pytestmark = pytest.mark.S01

scenarios("api/s01_skeleton.feature")


@pytest.fixture
def ctx() -> dict[str, Any]:
    return {"env_file": None}


@given("API 服務以測試設定啟動", target_fixture="client")
def api_with_test_settings(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("APP_ENV", "test")
    return TestClient(create_app(load_settings()))


@given(parsers.parse('環境變數 {name} 為 "{value}"'))
def set_env(monkeypatch: pytest.MonkeyPatch, name: str, value: str) -> None:
    monkeypatch.setenv(name, value)


@given(parsers.parse("未設定 {name}"))
def unset_env(monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    monkeypatch.delenv(name, raising=False)


@given(parsers.parse('設定檔的 {name} 為 "{value}"'))
def write_env_file(ctx: dict[str, Any], tmp_path: Path, name: str, value: str) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(f"{name}={value}\n", encoding="utf-8")
    ctx["env_file"] = env_file


@when("呼叫 GET /health", target_fixture="response")
def call_health(client: TestClient) -> httpx.Response:
    return client.get("/health")


@when("載入系統設定", target_fixture="loaded")
def load(ctx: dict[str, Any]) -> Settings | ConfigError:
    try:
        return load_settings(env_file=ctx["env_file"])
    except ConfigError as e:
        return e


@then(parsers.parse("回應狀態碼為 {code:d}"))
def status_is(response: httpx.Response, code: int) -> None:
    assert response.status_code == code


@then(parsers.parse('回應內容的 status 為 "{value}"'))
def body_status_is(response: httpx.Response, value: str) -> None:
    assert response.json()["status"] == value


@then(parsers.parse('應拋出設定錯誤並指出缺少 "{name}"'))
def config_error_names(loaded: Settings | ConfigError, name: str) -> None:
    assert isinstance(loaded, ConfigError)
    assert name in loaded.missing
    assert name in str(loaded)


@then(parsers.parse('影片模型設定為 "{value}"'))
def video_model_is(loaded: Settings | ConfigError, value: str) -> None:
    assert isinstance(loaded, Settings)
    assert loaded.hf_video_model == value
