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
    Character,
    CharacterVersion,
    GenerationJob,
    IdempotencyRecord,
    Plan,
    Project,
    Render,
    Repositories,
    ScenePhoto,
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


    async def update_brand(self, brand: BrandProfile) -> None:
        raise NotImplementedError


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

    async def list_shots(self, video_id: str) -> list[Shot]:
        shots = [s for s in self._shots.values() if s.video_id == video_id]
        return _copy(sorted(shots, key=lambda s: s.shot_no))

    async def update_take(self, take: ShotTake) -> None:
        takes = self._takes[take.shot_id]
        index = next(i for i, t in enumerate(takes) if t.id == take.id)
        takes[index] = _copy(take)


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
        return _copy(self._by_key.get(idempotency_key))

    async def count_by_key(self, idempotency_key: str) -> int:
        return int(idempotency_key in self._by_key)

    async def update(self, job: GenerationJob) -> None:
        if self._by_key.get(job.idempotency_key, job).id != job.id:
            raise ValueError(f"冪等鍵 {job.idempotency_key} 已屬於其他工作")
        self._by_key[job.idempotency_key] = _copy(job)


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


class MemoryPlanRepository:
    def __init__(self) -> None:
        self._rows: list[Plan] = []

    async def add(self, plan: Plan) -> None:
        self._rows.append(_copy(plan))

    async def get(self, plan_id: str) -> Plan | None:
        return _copy(next((p for p in self._rows if p.id == plan_id), None))

    async def list(self, video_id: str) -> list[Plan]:
        return _copy([p for p in self._rows if p.video_id == video_id])


class MemoryCharacterRepository:
    def __init__(self) -> None:
        self._characters: list[Character] = []
        self._versions: dict[str, CharacterVersion] = {}

    async def add(self, character: Character, versions: list[CharacterVersion]) -> None:
        self._characters.append(_copy(character))
        self._versions.update({v.id: _copy(v) for v in versions})

    async def locked_version(self, project_id: str) -> CharacterVersion | None:
        for c in self._characters:
            if c.project_id == project_id and c.locked_version_id in self._versions:
                return _copy(self._versions[c.locked_version_id])
        return None


    async def versions(self, project_id: str) -> list[CharacterVersion]:
        raise NotImplementedError

    async def add_version(self, version: CharacterVersion, *, lock: bool = True) -> None:
        raise NotImplementedError


class MemoryScenePhotoRepository:
    def __init__(self) -> None:
        self._rows: list[ScenePhoto] = []

    async def add(self, photo: ScenePhoto) -> None:
        self._rows.append(_copy(photo))

    async def list(self, project_id: str) -> list[ScenePhoto]:
        return _copy([p for p in self._rows if p.project_id == project_id])


class MemoryRenderRepository:
    def __init__(self) -> None:
        self._rows: list[Render] = []

    async def add(self, render: Render) -> None:
        self._rows.append(_copy(render))

    async def list(self, video_id: str) -> list[Render]:
        return _copy([r for r in self._rows if r.video_id == video_id])


class MemoryIdempotencyRepository:
    def __init__(self) -> None:
        self._rows: dict[str, IdempotencyRecord] = {}

    async def get(self, key: str) -> IdempotencyRecord | None:
        return _copy(self._rows.get(key))

    async def save(self, record: IdempotencyRecord) -> bool:
        if record.key in self._rows:
            return False
        self._rows[record.key] = _copy(record)
        return True


def memory_repositories() -> Repositories:
    return Repositories(
        projects=MemoryProjectRepository(),
        videos=MemoryVideoRepository(),
        shots=MemoryShotRepository(),
        jobs=MemoryGenerationJobRepository(),
        approvals=MemoryApprovalRepository(),
        costs=MemoryCostEntryRepository(),
        plans=MemoryPlanRepository(),
        characters=MemoryCharacterRepository(),
        scene_photos=MemoryScenePhotoRepository(),
        renders=MemoryRenderRepository(),
        idempotency=MemoryIdempotencyRepository(),
    )
