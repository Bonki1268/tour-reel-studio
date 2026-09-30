"""SSE 進度串流（spec 0008 R-006）。"""

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

from app.api.services import AppServices
from app.jobs.events import ProgressEvent
from app.jobs.orchestrator import NotFound


def format_sse(event_type: str, data: dict[str, Any]) -> str:
    """`event: <type>`、`data: <JSON>`，以空行結束。"""
    return f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def sse_stream(
    services: AppServices, video_id: str, is_disconnected: Callable[[], Awaitable[bool]]
) -> AsyncIterator[str]:
    """先訂閱，再送出目前狀態（status 事件），之後轉送每個進度事件；定期送出 keep-alive 註解行。"""
    async with services.events.subscribe(video_id) as events:
        video = await services.repos.videos.get(video_id)
        if video is None:
            raise NotFound(f"影片不存在：{video_id}")
        yield format_sse("status", {"type": "status", "video_id": video_id, "status": video.video.status,
                                    "at": services.clock().isoformat()})
        pending: asyncio.Future[ProgressEvent] | None = None
        try:
            while not await is_disconnected():
                if pending is None:
                    pending = asyncio.ensure_future(anext(events))
                done, _ = await asyncio.wait({pending}, timeout=services.settings.sse_keepalive_s)
                if done:
                    event = pending.result()
                    pending = None
                    yield format_sse(event.type, event.to_json())
                else:
                    yield ": keep-alive\n\n"
        finally:
            if pending is not None:
                pending.cancel()
