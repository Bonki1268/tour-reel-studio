"""生成供應商介面（架構書 §5.5；spec 0006）。模型名稱由呼叫端從設定傳入。"""

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal, Protocol


class ProviderError(Exception):
    """供應商回報的錯誤；retryable 為假時不自動重試。"""

    def __init__(self, message: str, *, retryable: bool = True) -> None:
        self.retryable = retryable
        super().__init__(message)


@dataclass(frozen=True)
class ProviderRequest:
    model: str
    input: Mapping[str, Any]
    provider_idempotency_key: str


@dataclass(frozen=True)
class ProviderJob:
    provider: str
    model: str
    external_id: str
    estimated_cost: Decimal | None = None


@dataclass(frozen=True)
class ProviderResult:
    state: Literal["running", "succeeded", "failed"]
    url: str | None = None
    actual_cost: Decimal | None = None
    error: ProviderError | None = None


class ImageProvider(Protocol):
    async def compose(self, req: ProviderRequest) -> ProviderJob: ...


class VideoProvider(Protocol):
    async def image_to_video(self, req: ProviderRequest) -> ProviderJob: ...


class ResultSource(Protocol):
    async def fetch_result(self, job: ProviderJob) -> ProviderResult: ...

    async def download(self, result: ProviderResult) -> tuple[bytes, str]:
        """回傳（內容, content type）。"""
        ...
