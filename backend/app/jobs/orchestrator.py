"""快速模式編排：主題 → 企劃 → 3 鏡平行生成 → 合成 → 成品確認（架構書 §5.2；spec 0007）。"""

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from app.config import Settings
from app.creative.base import CreativeEngine
from app.domain.approval import Approval
from app.domain.cost import CostTable, Estimate
from app.domain.ports import Repositories, Storage, VideoRecord
from app.domain.video import utc_now
from app.jobs.events import EventPublisher
from app.providers.base import ImageProvider, ResultSource, VideoProvider
from app.render.base import Renderer


class PlanningFailed(Exception):
    """創作引擎失敗或企劃數不符；影片已進入 failed。"""

    def __init__(self, video_id: str, reason: str) -> None:
        self.video_id = video_id
        super().__init__(f"影片 {video_id} 企劃失敗：{reason}")


@dataclass
class OrchestratorDeps:
    repos: Repositories
    storage: Storage
    engine: CreativeEngine
    renderer: Renderer
    image_provider: ImageProvider
    video_provider: VideoProvider
    results: ResultSource
    events: EventPublisher
    cost_table: CostTable
    settings: Settings
    clock: Callable[[], datetime] = utc_now
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep


class QuickModeOrchestrator:
    def __init__(self, deps: OrchestratorDeps) -> None:
        self.deps = deps

    async def submit_topic(self, project_id: str, topic: str) -> VideoRecord:
        raise NotImplementedError

    async def estimate(self, video_id: str, plan_id: str) -> Estimate:
        raise NotImplementedError

    async def approve_plan(
        self, video_id: str, plan_id: str, cost_cap: Decimal, approved_by: str,
        placements: Mapping[int, Mapping[str, Any]] | None = None,
    ) -> Approval:
        raise NotImplementedError

    async def generate(self, video_id: str) -> None:
        raise NotImplementedError

    async def regenerate_shot(self, video_id: str, shot_no: int) -> None:
        raise NotImplementedError

    async def approve_final(self, video_id: str, approved_by: str) -> Approval:
        raise NotImplementedError
