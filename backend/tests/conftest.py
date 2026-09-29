"""測試共用設定：隔離開發者本機的環境變數與 .env。"""

from collections.abc import Iterator

import pytest

from app import config

SETTING_NAMES = (
    "APP_ENV",
    "ANTHROPIC_API_KEY",
    "HIGGSFIELD_API_KEY",
    "FIRECRAWL_API_KEY",
    "HF_IMAGE_MODEL",
    "HF_VIDEO_MODEL",
    "CLAUDE_MODEL",
    "COST_TABLE",
    "RETRY_RESERVE_SHOTS",
    "WEBHOOK_ENABLED",
)


@pytest.fixture(autouse=True)
def isolated_settings_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """清除設定相關環境變數，並讓 load_settings 預設不讀取 repo 的 .env。"""
    for name in SETTING_NAMES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(config, "ENV_FILE", None)
    yield
