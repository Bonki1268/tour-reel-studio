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
    # Higgsfield adapter（S12）：webhook 簽章密鑰與對外網址都有設定時才附回呼網址
    higgsfield_base_url: str = "https://api.higgsfield.ai"
    higgsfield_webhook_secret: SecretStr | None = None
    public_base_url: str = ""
    claude_model: str = ""
    claude_effort: Literal["low", "medium", "high", "xhigh", "max"] = "medium"
    claude_refusal_fallback: bool = True  # Claude 拒絕回應時由伺服器端改用其他模型（S10）
    creative_engine: Literal["prompt", "fake"] = "prompt"
    cost_table: Path = REPO_ROOT / "config" / "cost_table.json"
    retry_reserve_shots: int = Field(default=1, ge=0)  # 成本上限預留幾鏡的完整重生（S04）
    webhook_enabled: bool = True
    # 合成（S13）：BGM_KEY 為自有儲存中的背景音樂，空白時輸出靜音音軌
    renderer: Literal["ffmpeg", "fake"] = "ffmpeg"
    bgm_key: str = ""
    render_timeout_s: float = Field(default=120, gt=0)
    generation_timeout_s: float = Field(default=600, gt=0)  # 自 submitted 起算（S06）
    generation_poll_interval_s: float = Field(default=5, gt=0)
    # 保底成品（S18）：自有儲存中的物件路徑；生成超過門檻秒數時 GET /videos/{id} 回傳 fallback_url
    demo_fallback_video: str = ""
    demo_fallback_after_s: float = Field(default=420, gt=0)
    # 預設值對應 infra/docker-compose.test.yml 的本機測試 Redis（S08）
    redis_url: str = "redis://localhost:56379/0"
    presign_ttl_s: int = Field(default=900, gt=0, le=900)  # 預簽名網址有效期，上限 15 分鐘（S08）
    sse_keepalive_s: float = Field(default=15, gt=0)
    # S3 相容儲存（S09）；預設值對應 infra/docker-compose.test.yml 的本機測試 MinIO
    s3_endpoint_url: str = "http://localhost:59000"
    s3_public_endpoint_url: str = ""  # 產生預簽名網址用的瀏覽器可連位址；空白時使用 s3_endpoint_url
    s3_bucket: str = "trs-test"
    s3_access_key_id: str = "trs"
    s3_secret_access_key: SecretStr = SecretStr("trs-secret-123")
    s3_region: str = "us-east-1"
    # 預設值對應 infra/docker-compose.test.yml 的本機測試資料庫（S05）
    database_url: str = "postgresql+psycopg://trs:trs@localhost:55432/trs"


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
