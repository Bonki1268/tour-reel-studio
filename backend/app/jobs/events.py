"""進度事件（spec 0007、0008）：記憶體版供測試，Redis pub/sub 版讓 API 與 Worker 跨程序傳遞。"""

from collections.abc import AsyncIterator, Mapping
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol


@dataclass(frozen=True)
class ProgressEvent:
    type: str
    video_id: str
    at: datetime
    shot_no: int | None = None
    data: Mapping[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        raise NotImplementedError

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> "ProgressEvent":
        raise NotImplementedError


class EventPublisher(Protocol):
    async def publish(self, event: ProgressEvent) -> None: ...


class EventBus(EventPublisher, Protocol):
    def subscribe(self, video_id: str) -> AbstractAsyncContextManager[AsyncIterator[ProgressEvent]]:
        """進入 context 時即完成訂閱；之後發布的事件都會送到迭代器。"""
        ...


class MemoryEventBus:
    def __init__(self) -> None:
        self.events: list[ProgressEvent] = []

    async def publish(self, event: ProgressEvent) -> None:
        self.events.append(event)

    def subscribe(self, video_id: str) -> AbstractAsyncContextManager[AsyncIterator[ProgressEvent]]:
        raise NotImplementedError


class RedisEventBus:
    """channel：video:{video_id}:events；內容為 ProgressEvent 的 JSON。"""

    def __init__(self, redis_url: str) -> None:
        self.redis_url = redis_url

    async def publish(self, event: ProgressEvent) -> None:
        raise NotImplementedError

    def subscribe(self, video_id: str) -> AbstractAsyncContextManager[AsyncIterator[ProgressEvent]]:
        raise NotImplementedError

    async def close(self) -> None:
        raise NotImplementedError
