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
    submitted_at: datetime | None = None  # 逾時由此起算（S06）


@dataclass
class Plan:
    id: str
    video_id: str
    payload: JSON
    engine: str


@dataclass
class Character:
    id: str
    project_id: str
    name: str
    locked_version_id: str | None = None


@dataclass
class CharacterVersion:
    id: str
    character_id: str
    version: int
    status: str
    identity_board_key: str | None = None
    cutout_key: str | None = None
    anchor_card: JSON = None
    voice: JSON = None


@dataclass
class ScenePhoto:
    id: str
    project_id: str
    image_key: str
    width: int
    height: int
    description: str = ""


@dataclass
class Render:
    id: str
    video_id: str
    aspect_ratio: str
    mp4_key: str
    subtitle_lang: str | None = None
    thumb_key: str | None = None


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
    async def update_take(self, take: ShotTake) -> None: ...
    async def list_shots(self, video_id: str) -> list[Shot]: ...  # 依 shot_no 排序（S07）


class GenerationJobRepository(Protocol):
    async def create_or_get(self, job: GenerationJob) -> tuple[GenerationJob, bool]: ...
    async def get(self, job_id: str) -> GenerationJob | None: ...
    async def get_by_key(self, idempotency_key: str) -> GenerationJob | None: ...
    async def count_by_key(self, idempotency_key: str) -> int: ...
    async def update(self, job: GenerationJob) -> None: ...


class ApprovalRepository(Protocol):
    async def add(self, video_id: str, approval: Approval) -> None: ...
    async def list(self, video_id: str) -> list[Approval]: ...


class CostEntryRepository(Protocol):
    async def add(self, video_id: str, entry: CostEntry) -> None: ...
    async def list(self, video_id: str) -> list[CostEntry]: ...


class PlanRepository(Protocol):
    async def add(self, plan: Plan) -> None: ...
    async def get(self, plan_id: str) -> Plan | None: ...
    async def list(self, video_id: str) -> list[Plan]: ...  # 依建立順序


class CharacterRepository(Protocol):
    async def add(self, character: Character, versions: list[CharacterVersion]) -> None: ...
    async def locked_version(self, project_id: str) -> CharacterVersion | None: ...


class ScenePhotoRepository(Protocol):
    async def add(self, photo: ScenePhoto) -> None: ...
    async def list(self, project_id: str) -> list[ScenePhoto]: ...  # 依建立順序


class RenderRepository(Protocol):
    async def add(self, render: Render) -> None: ...
    async def list(self, video_id: str) -> list[Render]: ...  # 依建立順序


class Storage(Protocol):
    """物件儲存（S06 定義最小子集；S09 補上預簽網址與 S3 實作）。"""

    async def put(self, key: str, data: bytes, content_type: str) -> None: ...
    async def get(self, key: str) -> bytes: ...
    async def exists(self, key: str) -> bool: ...


@dataclass
class Repositories:
    projects: ProjectRepository
    videos: VideoRepository
    shots: ShotRepository
    jobs: GenerationJobRepository
    approvals: ApprovalRepository
    costs: CostEntryRepository
    plans: PlanRepository
    characters: CharacterRepository
    scene_photos: ScenePhotoRepository
    renders: RenderRepository
