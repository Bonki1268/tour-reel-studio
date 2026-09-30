"""進度事件（spec 0007、0008）：記憶體版供測試，Redis pub/sub 版讓 API 與 Worker 跨程序傳遞。"""

import asyncio
import json
from collections.abc import AsyncIterator, Mapping
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

import redis.asyncio as aioredis


@dataclass(frozen=True)
class ProgressEvent:
    type: str
    video_id: str
    at: datetime
    shot_no: int | None = None
    data: Mapping[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {"type": self.type, "video_id": self.video_id, "at": self.at.isoformat(),
                "shot_no": self.shot_no, "data": dict(self.data)}

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> "ProgressEvent":
        return cls(data["type"], data["video_id"], datetime.fromisoformat(data["at"]), data.get("shot_no"),
                   dict(data.get("data") or {}))


class EventPublisher(Protocol):
    async def publish(self, event: ProgressEvent) -> None: ...


class EventBus(EventPublisher, Protocol):
    def subscribe(self, video_id: str) -> AbstractAsyncContextManager[AsyncIterator[ProgressEvent]]:
        """進入 context 時即完成訂閱；之後發布的事件都會送到迭代器。"""
        ...


_Subscriber = tuple[asyncio.AbstractEventLoop, "asyncio.Queue[ProgressEvent]"]


class MemoryEventBus:
    """同一程序內的事件匯流排；訂閱者可在其他執行緒的事件迴圈（例如測試中的 uvicorn）。"""

    def __init__(self) -> None:
        self.events: list[ProgressEvent] = []
        self._subscribers: dict[str, list[_Subscriber]] = {}

    async def publish(self, event: ProgressEvent) -> None:
        self.events.append(event)
        for loop, q in list(self._subscribers.get(event.video_id, [])):
            loop.call_soon_threadsafe(q.put_nowait, event)

    def subscribe(self, video_id: str) -> AbstractAsyncContextManager[AsyncIterator[ProgressEvent]]:
        return self._subscribe(video_id)

    @asynccontextmanager
    async def _subscribe(self, video_id: str) -> AsyncIterator[AsyncIterator[ProgressEvent]]:
        q: asyncio.Queue[ProgressEvent] = asyncio.Queue()
        entry = (asyncio.get_running_loop(), q)
        self._subscribers.setdefault(video_id, []).append(entry)

        async def events() -> AsyncIterator[ProgressEvent]:
            while True:
                yield await q.get()

        try:
            yield events()
        finally:
            self._subscribers[video_id].remove(entry)


def _channel(video_id: str) -> str:
    return f"video:{video_id}:events"


class RedisEventBus:
    """channel：video:{video_id}:events；內容為 ProgressEvent 的 JSON。"""

    def __init__(self, redis_url: str) -> None:
        self._redis: aioredis.Redis = aioredis.Redis.from_url(redis_url)

    async def publish(self, event: ProgressEvent) -> None:
        await self._redis.publish(_channel(event.video_id), json.dumps(event.to_json(), ensure_ascii=False))

    def subscribe(self, video_id: str) -> AbstractAsyncContextManager[AsyncIterator[ProgressEvent]]:
        return self._subscribe(video_id)

    @asynccontextmanager
    async def _subscribe(self, video_id: str) -> AsyncIterator[AsyncIterator[ProgressEvent]]:
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(_channel(video_id))

        async def events() -> AsyncIterator[ProgressEvent]:
            while True:
                msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if msg is not None and msg["type"] == "message":
                    yield ProgressEvent.from_json(json.loads(msg["data"]))

        try:
            yield events()
        finally:
            await pubsub.unsubscribe(_channel(video_id))
            await pubsub.aclose()  # type: ignore[no-untyped-call]  # redis-py 的 PubSub.aclose 沒有型別註記

    async def close(self) -> None:
        await self._redis.aclose()
