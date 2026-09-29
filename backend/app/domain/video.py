"""影片狀態機（架構書 §6.1；spec 0002）。純領域邏輯，不依賴資料庫或框架。"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from types import MappingProxyType


class VideoStatus(StrEnum):
    DRAFT = "draft"
    PLANNING = "planning"
    PLAN_READY = "plan_ready"
    GENERATING = "generating"
    NEEDS_ATTENTION = "needs_attention"
    RENDERING = "rendering"
    REVIEW = "review"
    APPROVED = "approved"
    FAILED = "failed"


class VideoEvent(StrEnum):
    SUBMIT_TOPIC = "submit_topic"
    PLANS_READY = "plans_ready"
    PLANNING_FAILED = "planning_failed"
    REGENERATE_PLANS = "regenerate_plans"
    APPROVE_PLAN = "approve_plan"
    ALL_SHOTS_DONE = "all_shots_done"
    SHOT_FAILED_FINAL = "shot_failed_final"
    APPROVAL_INVALIDATED = "approval_invalidated"
    CONFIRM_REGENERATE = "confirm_regenerate"
    CONFIRM_RERENDER = "confirm_rerender"
    RENDER_DONE = "render_done"
    RENDER_RETRY = "render_retry"
    RENDER_FAILED_FINAL = "render_failed_final"
    REGENERATE_SHOT = "regenerate_shot"
    APPROVE_FINAL = "approve_final"


TRANSITIONS: Mapping[tuple[VideoStatus, VideoEvent], VideoStatus] = MappingProxyType({})

TERMINAL: frozenset[VideoStatus] = frozenset()


class InvalidTransition(Exception):
    def __init__(self, status: VideoStatus, event: VideoEvent) -> None:
        self.status = status
        self.event = event
        super().__init__(f"影片狀態 {status} 不接受事件 {event}")


@dataclass(frozen=True)
class StatusChange:
    event: VideoEvent
    from_status: VideoStatus
    to_status: VideoStatus
    at: datetime


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass
class Video:
    status: VideoStatus = VideoStatus.DRAFT
    history: list[StatusChange] = field(default_factory=list)
    clock: Callable[[], datetime] = utc_now

    def apply(self, event: VideoEvent) -> VideoStatus:
        raise NotImplementedError

    @property
    def status_trail(self) -> list[VideoStatus]:
        raise NotImplementedError
