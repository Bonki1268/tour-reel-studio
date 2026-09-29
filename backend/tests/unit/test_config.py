from pathlib import Path

import pytest

from app.api.main import create_app
from app.config import ConfigError, load_settings

pytestmark = pytest.mark.S01

REQUIRED = ("ANTHROPIC_API_KEY", "HIGGSFIELD_API_KEY", "HF_IMAGE_MODEL", "HF_VIDEO_MODEL")
FAKE_ANTHROPIC = "anthropic-test-value-7f3a"


def set_all_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_ANTHROPIC)
    monkeypatch.setenv("HIGGSFIELD_API_KEY", "higgsfield-test-id:higgsfield-test-secret")
    monkeypatch.setenv("HF_IMAGE_MODEL", "img-model-x")
    monkeypatch.setenv("HF_VIDEO_MODEL", "vid-model-x")


def test_r002_test_mode_loads_without_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "test")

    settings = load_settings()
    create_app(settings)

    assert settings.app_env == "test"
    assert settings.anthropic_api_key is None
    assert settings.higgsfield_api_key is None
    assert settings.hf_video_model == ""


def test_r002_default_env_is_development() -> None:
    assert load_settings().app_env == "development"


def test_r003_production_lists_all_missing_names(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("HF_IMAGE_MODEL", "")

    with pytest.raises(ConfigError) as exc:
        load_settings()

    assert set(exc.value.missing) == set(REQUIRED)
    for name in REQUIRED:
        assert name in str(exc.value)


def test_r003_production_treats_blank_as_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    set_all_required(monkeypatch)
    monkeypatch.setenv("HIGGSFIELD_API_KEY", "   ")

    with pytest.raises(ConfigError) as exc:
        load_settings()

    assert exc.value.missing == ("HIGGSFIELD_API_KEY",)


def test_r003_production_ok_when_all_required_set(monkeypatch: pytest.MonkeyPatch) -> None:
    set_all_required(monkeypatch)

    settings = load_settings()

    assert settings.app_env == "production"
    assert settings.hf_video_model == "vid-model-x"


def test_r004_env_var_overrides_env_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "HF_IMAGE_MODEL=file-img\nHF_VIDEO_MODEL=file-vid\nCLAUDE_MODEL=file-claude\n"
        "COST_TABLE=/from/file/cost.json\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HF_IMAGE_MODEL", "env-img")
    monkeypatch.setenv("CLAUDE_MODEL", "env-claude")
    monkeypatch.setenv("COST_TABLE", "/from/env/cost.json")

    settings = load_settings(env_file=env_file)

    assert settings.hf_image_model == "env-img"
    assert settings.claude_model == "env-claude"
    assert settings.cost_table == Path("/from/env/cost.json")
    assert settings.hf_video_model == "file-vid"


def test_r005_secret_not_in_repr_or_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_ANTHROPIC)
    settings = load_settings()
    assert FAKE_ANTHROPIC not in str(settings)
    assert FAKE_ANTHROPIC not in repr(settings)

    set_all_required(monkeypatch)
    monkeypatch.delenv("HIGGSFIELD_API_KEY")
    with pytest.raises(ConfigError) as exc:
        load_settings()
    assert FAKE_ANTHROPIC not in str(exc.value)
    assert FAKE_ANTHROPIC not in repr(exc.value)
