"""測試共用設定：隔離開發者本機的環境變數與 .env；整合測試用的資料庫 fixture（S05 起）。"""

from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from sqlalchemy import Connection, Engine, create_engine, inspect, text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from alembic import command
from alembic.config import Config
from app import config

ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"

SETTING_NAMES = (
    "APP_ENV",
    "ANTHROPIC_API_KEY",
    "HIGGSFIELD_API_KEY",
    "FIRECRAWL_API_KEY",
    "HF_IMAGE_MODEL",
    "HF_VIDEO_MODEL",
    "CLAUDE_MODEL",
    "CLAUDE_EFFORT",
    "CLAUDE_REFUSAL_FALLBACK",
    "CREATIVE_ENGINE",
    "COST_TABLE",
    "RETRY_RESERVE_SHOTS",
    "WEBHOOK_ENABLED",
    "GENERATION_TIMEOUT_S",
    "GENERATION_POLL_INTERVAL_S",
    "PRESIGN_TTL_S",
    "SSE_KEEPALIVE_S",
    "S3_ENDPOINT_URL",
    "S3_PUBLIC_ENDPOINT_URL",
    "S3_BUCKET",
    "S3_ACCESS_KEY_ID",
    "S3_SECRET_ACCESS_KEY",
    "S3_REGION",
)
# DATABASE_URL 不清除：整合測試可用環境變數指向其他測試資料庫


@pytest.fixture(autouse=True)
def isolated_settings_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """清除設定相關環境變數，並讓 load_settings 預設不讀取 repo 的 .env。"""
    for name in SETTING_NAMES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(config, "ENV_FILE", None)
    yield


def database_url() -> str:
    """測試資料庫：DATABASE_URL 環境變數，未設定時為 infra/docker-compose.test.yml 的預設值。"""
    return config.load_settings(env_file=None).database_url


def alembic_config(connection: Connection) -> Config:
    cfg = Config(str(ALEMBIC_INI))
    cfg.attributes["connection"] = connection
    cfg.attributes["configure_logger"] = False
    return cfg


@pytest.fixture(scope="session")
def sync_engine() -> Iterator[Engine]:
    engine = create_engine(database_url())
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def migrated_db(sync_engine: Engine) -> Iterator[None]:
    """整個測試工作階段只遷移一次：清空 public schema 後 upgrade head。"""
    with sync_engine.begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
        command.upgrade(alembic_config(conn), "head")
    yield


@pytest.fixture
def clean_db(migrated_db: None, sync_engine: Engine) -> Iterator[None]:
    """每個測試結束時清空所有資料表，測試之間互不影響。"""
    yield
    with sync_engine.begin() as conn:
        tables = [t for t in inspect(conn).get_table_names(schema="public") if t != "alembic_version"]
        if tables:
            conn.execute(text(f"TRUNCATE {', '.join(tables)} CASCADE"))


@pytest.fixture
async def async_engine(clean_db: None) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(database_url())
    yield engine
    await engine.dispose()
