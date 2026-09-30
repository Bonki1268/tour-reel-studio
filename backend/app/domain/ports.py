"""Repository 介面與持久化用的領域資料類別（架構書 §7；spec 0005）。不依賴 SQLAlchemy。"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Protocol

from app.domain.approval import Approval
from app.domain.cost import CostEntry, JobKind
from app.domain.video import Video

JSON = Any  # JSON 相容的值：dict／list／str／int／float／bool／None


@dataclass
class Project:
    id: str
    name: str
    user_id: str | None = None
    output_defaults: dict[str, JSON] = field(default_factory=dict)


@dataclass
class BrandProfile:
    project_id: str
    visual: dict[str, JSON] = field(default_factory=dict)
    selling_points: list[JSON] = field(default_factory=list)
    tone: str = ""
    info: dict[str, JSON] = field(default_factory=dict)
    sources: dict[str, JSON] = field(default_factory=dict)
    confirmed_at: datetime | None = None


@dataclass
class VideoRecord:
    """S02 的 Video（狀態＋歷程）加上 videos 資料表的其他欄位。"""

    id: str
    project_id: str
    mode: str
    topic: str
    video: Video = field(default_factory=Video)
    selected_plan_id: str | None = None
    cost_cap: Decimal | None = None
    timeline: JSON = None


@dataclass
class Shot:
    id: str
    video_id: str
    shot_no: int
    role: str = ""
    duration_s: float = 0.0
    scene_photo_id: str | None = None
    placement: JSON = None
    prompt: JSON = None
    current_take_id: str | None = None


@dataclass
class ShotTake:
    id: str
    shot_id: str
    attempt: int
    keyframe_key: str | None = None
    clip_key: str | None = None
    status: str = "pending"


@dataclass
class GenerationJob:
    id: str
    shot_take_id: str
    idempotency_key: str
    kind: JobKind
    provider: str
    model: str
    input_hash: str
    attempt: int
    status: str = "queued"
    input_snapshot: JSON = None
    external_id: str | None = None
    provider_idempotency_key: str | None = None
    est_cost: Decimal | None = None
    actual_cost: Decimal | None = None
    error: str | None = None


class ProjectRepository(Protocol):
    async def add(self, project: Project, brand: BrandProfile) -> None: ...
    async def get(self, project_id: str) -> tuple[Project, BrandProfile] | None: ...


class VideoRepository(Protocol):
    async def add(self, record: VideoRecord) -> None: ...
    async def get(self, video_id: str) -> VideoRecord | None: ...
    async def save(self, record: VideoRecord) -> None: ...


class ShotRepository(Protocol):
    async def add_shot(self, shot: Shot) -> None: ...
    async def get_shot(self, shot_id: str) -> Shot | None: ...
    async def add_take(
        self, shot_id: str, *, keyframe_key: str | None = None, clip_key: str | None = None,
        status: str = "pending",
    ) -> ShotTake: ...
    async def takes(self, shot_id: str) -> list[ShotTake]: ...


class GenerationJobRepository(Protocol):
    async def create_or_get(self, job: GenerationJob) -> tuple[GenerationJob, bool]: ...
    async def get(self, job_id: str) -> GenerationJob | None: ...
    async def count_by_key(self, idempotency_key: str) -> int: ...


class ApprovalRepository(Protocol):
    async def add(self, video_id: str, approval: Approval) -> None: ...
    async def list(self, video_id: str) -> list[Approval]: ...


class CostEntryRepository(Protocol):
    async def add(self, video_id: str, entry: CostEntry) -> None: ...
    async def list(self, video_id: str) -> list[CostEntry]: ...


@dataclass
class Repositories:
    projects: ProjectRepository
    videos: VideoRepository
    shots: ShotRepository
    jobs: GenerationJobRepository
    approvals: ApprovalRepository
    costs: CostEntryRepository
