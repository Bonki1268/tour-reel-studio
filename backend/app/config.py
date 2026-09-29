"""系統設定：以環境變數與 repo 根目錄的 .env 載入。"""

from pathlib import Path
from typing import Any, Literal

from pydantic import SecretStr
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
    retry_reserve_ratio: float | None = None
    webhook_enabled: bool = True


class ConfigError(Exception):
    """設定不完整；只帶變數名稱，不帶任何值。"""

    def __init__(self, missing: tuple[str, ...]) -> None:
        self.missing = missing
        super().__init__(f"正式環境缺少必要設定：{', '.join(missing)}")


_UNSET: Any = object()


def load_settings(env_file: Path | None = _UNSET) -> Settings:
    raise NotImplementedError
