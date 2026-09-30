"""記憶體版 repository（spec 0005 R-006）：供單元測試取代資料庫。

寫入與讀出都深複製，行為與資料庫版一致：呼叫端之後修改物件，不影響已儲存的內容。
"""

from copy import deepcopy
from dataclasses import replace
from typing import TypeVar

from app.domain.approval import Approval
from app.domain.cost import CostEntry
from app.domain.ids import new_id
from app.domain.ports import (
    BrandProfile,
    GenerationJob,
    Project,
    Repositories,
    Shot,
    ShotTake,
    VideoRecord,
)
from app.domain.video import Video

T = TypeVar("T")


def _copy(obj: T) -> T:
    return deepcopy(obj)


class MemoryProjectRepository:
    def __init__(self) -> None:
        self._rows: dict[str, tuple[Project, BrandProfile]] = {}

    async def add(self, project: Project, brand: BrandProfile) -> None:
        self._rows[project.id] = _copy((project, brand))

    async def get(self, project_id: str) -> tuple[Project, BrandProfile] | None:
        return _copy(self._rows.get(project_id))


class MemoryVideoRepository:
    def __init__(self) -> None:
        self._rows: dict[str, VideoRecord] = {}

    def _store(self, record: VideoRecord) -> None:
        # 時鐘是行為而非資料，不保存（與資料庫版相同）
        video = Video(status=record.video.status, history=_copy(record.video.history))
        self._rows[record.id] = replace(_copy(replace(record, video=Video())), video=video)

    async def add(self, record: VideoRecord) -> None:
        self._store(record)

    async def get(self, video_id: str) -> VideoRecord | None:
        return _copy(self._rows.get(video_id))

    async def save(self, record: VideoRecord) -> None:
        self._store(record)


class MemoryShotRepository:
    def __init__(self) -> None:
        self._shots: dict[str, Shot] = {}
        self._takes: dict[str, list[ShotTake]] = {}

    async def add_shot(self, shot: Shot) -> None:
        self._shots[shot.id] = _copy(shot)
        self._takes.setdefault(shot.id, [])

    async def get_shot(self, shot_id: str) -> Shot | None:
        return _copy(self._shots.get(shot_id))

    async def add_take(
        self, shot_id: str, *, keyframe_key: str | None = None, clip_key: str | None = None,
        status: str = "pending",
    ) -> ShotTake:
        takes = self._takes[shot_id]
        take = ShotTake(new_id(), shot_id, len(takes) + 1, keyframe_key, clip_key, status)
        takes.append(take)
        self._shots[shot_id].current_take_id = take.id
        return _copy(take)

    async def takes(self, shot_id: str) -> list[ShotTake]:
        return _copy(self._takes.get(shot_id, []))

    async def update_take(self, take: ShotTake) -> None:
        raise NotImplementedError


class MemoryGenerationJobRepository:
    def __init__(self) -> None:
        self._by_key: dict[str, GenerationJob] = {}

    async def create_or_get(self, job: GenerationJob) -> tuple[GenerationJob, bool]:
        existing = self._by_key.get(job.idempotency_key)
        if existing is not None:
            return _copy(existing), False
        self._by_key[job.idempotency_key] = _copy(job)
        return _copy(job), True

    async def get(self, job_id: str) -> GenerationJob | None:
        return _copy(next((j for j in self._by_key.values() if j.id == job_id), None))

    async def get_by_key(self, idempotency_key: str) -> GenerationJob | None:
        raise NotImplementedError

    async def count_by_key(self, idempotency_key: str) -> int:
        return int(idempotency_key in self._by_key)

    async def update(self, job: GenerationJob) -> None:
        raise NotImplementedError


class MemoryApprovalRepository:
    def __init__(self) -> None:
        self._rows: dict[str, list[Approval]] = {}

    async def add(self, video_id: str, approval: Approval) -> None:
        self._rows.setdefault(video_id, []).append(approval)

    async def list(self, video_id: str) -> list[Approval]:
        return list(self._rows.get(video_id, []))


class MemoryCostEntryRepository:
    def __init__(self) -> None:
        self._rows: dict[str, list[CostEntry]] = {}

    async def add(self, video_id: str, entry: CostEntry) -> None:
        self._rows.setdefault(video_id, []).append(entry)

    async def list(self, video_id: str) -> list[CostEntry]:
        return list(self._rows.get(video_id, []))


def memory_repositories() -> Repositories:
    return Repositories(
        projects=MemoryProjectRepository(),
        videos=MemoryVideoRepository(),
        shots=MemoryShotRepository(),
        jobs=MemoryGenerationJobRepository(),
        approvals=MemoryApprovalRepository(),
        costs=MemoryCostEntryRepository(),
    )
