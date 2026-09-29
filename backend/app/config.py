"""系統設定：以環境變數與 repo 根目錄的 .env 載入。"""

from pathlib import Path
from typing import Any, Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE: Path | None = REPO_ROOT / ".env"

AppEnv = Literal["development", "test", "production"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    app_env: AppEnv = "development"
    anthropic_api_key: SecretStr | None = None
    higgsfield_api_key: SecretStr | None = None
    firecrawl_api_key: SecretStr | None = None
    hf_image_model: str = ""
    hf_video_model: str = ""
    claude_model: str = ""
    cost_table: Path = REPO_ROOT / "config" / "cost_table.json"
    retry_reserve_shots: int = Field(default=1, ge=0)  # 成本上限預留幾鏡的完整重生（S04）
    webhook_enabled: bool = True


class ConfigError(Exception):
    """設定不完整；只帶變數名稱，不帶任何值。"""

    def __init__(self, missing: tuple[str, ...]) -> None:
        self.missing = missing
        super().__init__(f"正式環境缺少必要設定：{', '.join(missing)}")


REQUIRED_IN_PRODUCTION = ("anthropic_api_key", "higgsfield_api_key", "hf_image_model", "hf_video_model")

_UNSET: Any = object()


def _is_blank(value: SecretStr | str | None) -> bool:
    if isinstance(value, SecretStr):
        value = value.get_secret_value()
    return not value or not value.strip()


def load_settings(env_file: Path | None = _UNSET) -> Settings:
    """載入設定；正式環境一次列出所有缺少的必要設定。

    必要檢查不放在 Pydantic validator：ValidationError 會附帶輸入值，可能洩漏金鑰。
    """
    if env_file is _UNSET:
        env_file = ENV_FILE
    settings = Settings(_env_file=env_file)
    if settings.app_env == "production":
        missing = tuple(n.upper() for n in REQUIRED_IN_PRODUCTION if _is_blank(getattr(settings, n)))
        if missing:
            raise ConfigError(missing)
    return settings
