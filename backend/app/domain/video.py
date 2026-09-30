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


_S, _E = VideoStatus, VideoEvent

# 轉換表（spec 0002 R-001）；generating → plan_ready 依架構書 §6.3 加入
TRANSITIONS: Mapping[tuple[VideoStatus, VideoEvent], VideoStatus] = MappingProxyType({
    (_S.DRAFT, _E.SUBMIT_TOPIC): _S.PLANNING,
    (_S.PLANNING, _E.PLANS_READY): _S.PLAN_READY,
    (_S.PLANNING, _E.PLANNING_FAILED): _S.FAILED,
    (_S.PLAN_READY, _E.REGENERATE_PLANS): _S.PLANNING,
    (_S.PLAN_READY, _E.APPROVE_PLAN): _S.GENERATING,
    (_S.GENERATING, _E.ALL_SHOTS_DONE): _S.RENDERING,
    (_S.GENERATING, _E.SHOT_FAILED_FINAL): _S.NEEDS_ATTENTION,
    (_S.GENERATING, _E.APPROVAL_INVALIDATED): _S.PLAN_READY,
    (_S.NEEDS_ATTENTION, _E.CONFIRM_REGENERATE): _S.GENERATING,
    (_S.NEEDS_ATTENTION, _E.CONFIRM_RERENDER): _S.RENDERING,
    (_S.RENDERING, _E.RENDER_DONE): _S.REVIEW,
    (_S.RENDERING, _E.RENDER_RETRY): _S.RENDERING,
    (_S.RENDERING, _E.RENDER_FAILED_FINAL): _S.NEEDS_ATTENTION,
    (_S.REVIEW, _E.REGENERATE_SHOT): _S.GENERATING,
    (_S.REVIEW, _E.APPROVE_FINAL): _S.APPROVED,
})

# 終止狀態：轉換表中沒有任何出口
TERMINAL: frozenset[VideoStatus] = frozenset(VideoStatus) - {s for s, _ in TRANSITIONS}


class InvalidTransition(Exception):
    def __init__(self, status: VideoStatus, event: VideoEvent) -> None:
        self.status = status
        self.event = event
        super().__init__(f"影片狀態 {status} 不接受事件 {event}")


def check_transition(status: VideoStatus, event: VideoEvent) -> VideoStatus:
    """不改變影片，只檢查事件是否合法（S08：API 先同步檢查再排入 Worker）。"""
    raise NotImplementedError


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
        """依轉換表轉換並記錄歷程；不合法時拋出 InvalidTransition，狀態與歷程都不變。"""
        new_status = TRANSITIONS.get((self.status, event))
        if new_status is None:
            raise InvalidTransition(self.status, event)
        self.history.append(StatusChange(event, self.status, new_status, self.clock()))
        self.status = new_status
        return new_status

    @property
    def status_trail(self) -> list[VideoStatus]:
        """起始狀態加上每次轉換後的狀態。"""
        if not self.history:
            return [self.status]
        return [self.history[0].from_status, *(c.to_status for c in self.history)]
