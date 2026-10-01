"""Higgsfield adapter：ImageProvider、VideoProvider、ResultSource 的真實實作（架構書 §5.5；spec 0012）。

以 httpx 直接呼叫（不使用官方 SDK）：送出（POST）不自動重試，重試只由 S06 工作流程決定。
"""

import logging
from collections.abc import Iterable, Mapping
from decimal import Decimal
from typing import Any

import httpx

from app.config import Settings
from app.domain.ports import Storage
from app.providers.base import ProviderJob, ProviderRequest, ProviderResult

PROVIDER_NAME = "higgsfield"


def classify(status_code: int, detail: str = "") -> bool:
    """HTTP 錯誤是否可重試。"""
    raise NotImplementedError


def parse_cost(body: Mapping[str, Any]) -> Decimal | None:
    raise NotImplementedError


def map_status(body: Mapping[str, Any]) -> ProviderResult:
    """Higgsfield 狀態回應 → 內部 ProviderResult。"""
    raise NotImplementedError


def compose_args(prompt: str, image_urls: list[str]) -> dict[str, Any]:
    raise NotImplementedError


def i2v_args(image_url: str, prompt: str, duration: int) -> dict[str, Any]:
    raise NotImplementedError


class RedactSecrets(logging.Filter):
    """把日誌中出現的秘密字串替換成 ***。"""

    def __init__(self, secrets: Iterable[str]) -> None:
        super().__init__()
        self.secrets = [s for s in secrets if s]

    def filter(self, record: logging.LogRecord) -> bool:
        raise NotImplementedError


def install_redaction(secret: str) -> None:
    raise NotImplementedError


class HiggsfieldProvider:
    def __init__(self, settings: Settings, storage: Storage, http: httpx.AsyncClient | None = None) -> None:
        self.settings = settings
        self.storage = storage
        self.http = http

    async def compose(self, req: ProviderRequest) -> ProviderJob:
        raise NotImplementedError

    async def image_to_video(self, req: ProviderRequest) -> ProviderJob:
        raise NotImplementedError

    async def fetch_result(self, job: ProviderJob) -> ProviderResult:
        raise NotImplementedError

    async def download(self, result: ProviderResult) -> tuple[bytes, str]:
        raise NotImplementedError
