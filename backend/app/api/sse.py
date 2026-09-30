"""SSE 進度串流（spec 0008 R-006）。"""

from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

from app.api.services import AppServices


def format_sse(event_type: str, data: dict[str, Any]) -> str:
    """`event: <type>`、`data: <JSON>`，以空行結束。"""
    raise NotImplementedError


async def sse_stream(
    services: AppServices, video_id: str, is_disconnected: Callable[[], Awaitable[bool]]
) -> AsyncIterator[str]:
    """先訂閱，再送出目前狀態（status 事件），之後轉送每個進度事件；定期送出 keep-alive 註解行。"""
    raise NotImplementedError
    yield ""  # pragma: no cover
