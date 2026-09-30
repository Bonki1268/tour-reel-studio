"""進度事件（spec 0007）：記憶體版供測試，Redis 版在 S08 加入。"""

from collections.abc import Mapping
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


class EventPublisher(Protocol):
    async def publish(self, event: ProgressEvent) -> None: ...


class MemoryEventBus:
    def __init__(self) -> None:
        self.events: list[ProgressEvent] = []

    async def publish(self, event: ProgressEvent) -> None:
        self.events.append(event)
