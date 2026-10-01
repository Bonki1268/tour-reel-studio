"""資料庫版 repository（spec 0005）。ORM 與領域物件的轉換集中在這裡。"""

from collections.abc import Iterable
from dataclasses import fields
from datetime import datetime
from typing import Any, TypeVar

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.domain.approval import Approval
from app.domain.cost import CostEntry, JobKind
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
from app.domain.video import StatusChange, Video, VideoEvent, VideoStatus
from app.storage.db import session_factory
from app.storage.models import (
    ApiIdempotencyRow,
    ApprovalRow,
    BrandProfileRow,
    CharacterRow,
    CharacterVersionRow,
    CostEntryRow,
    GenerationJobRow,
    PlanRow,
    ProjectRow,
    RenderRow,
    ScenePhotoRow,
    ShotRow,
    ShotTakeRow,
    VideoRow,
)

T = TypeVar("T")
Sessions = async_sessionmaker[AsyncSession]


def _values(obj: object) -> dict[str, Any]:
    """資料類別的欄位值（淺層）；ORM 模型的欄位名稱與資料類別相同。"""
    return {f.name: getattr(obj, f.name) for f in fields(obj)}  # type: ignore[arg-type]


def _from_row(cls: type[T], row: object) -> T:
    return cls(**{f.name: getattr(row, f.name) for f in fields(cls)})  # type: ignore[arg-type]


class SqlProjectRepository:
    def __init__(self, sessions: Sessions) -> None:
        self._sessions = sessions

    async def add(self, project: Project, brand: BrandProfile) -> None:
        async with self._sessions.begin() as s:
            s.add(ProjectRow(**_values(project)))
            await s.flush()
            s.add(BrandProfileRow(**_values(brand)))

    async def get(self, project_id: str) -> tuple[Project, BrandProfile] | None:
        async with self._sessions() as s:
            project = await s.get(ProjectRow, project_id)
            brand = await s.get(BrandProfileRow, project_id)
            if project is None or brand is None:
                return None
            return _from_row(Project, project), _from_row(BrandProfile, brand)

    async def update_brand(self, brand: BrandProfile) -> None:
        async with self._sessions.begin() as s:
            await s.merge(BrandProfileRow(**_values(brand)))


def _history_to_json(history: list[StatusChange]) -> list[dict[str, str]]:
    return [
        {"event": c.event, "from_status": c.from_status, "to_status": c.to_status, "at": c.at.isoformat()}
        for c in history
    ]


def _history_from_json(data: list[dict[str, str]]) -> list[StatusChange]:
    return [
        StatusChange(
            VideoEvent(c["event"]), VideoStatus(c["from_status"]), VideoStatus(c["to_status"]),
            datetime.fromisoformat(c["at"]),
        )
        for c in data
    ]


def _video_columns(record: VideoRecord) -> dict[str, Any]:
    values = _values(record)
    video: Video = values.pop("video")
    values.update(status=video.status, status_history=_history_to_json(video.history))
    return values


class SqlVideoRepository:
    def __init__(self, sessions: Sessions) -> None:
        self._sessions = sessions

    async def add(self, record: VideoRecord) -> None:
        async with self._sessions.begin() as s:
            s.add(VideoRow(**_video_columns(record)))

    async def get(self, video_id: str) -> VideoRecord | None:
        async with self._sessions() as s:
            row = await s.get(VideoRow, video_id)
            if row is None:
                return None
            video = Video(status=VideoStatus(row.status), history=_history_from_json(row.status_history))
            values = {f.name: getattr(row, f.name) for f in fields(VideoRecord) if f.name != "video"}
            return VideoRecord(video=video, **values)

    async def save(self, record: VideoRecord) -> None:
        async with self._sessions.begin() as s:
            await s.merge(VideoRow(**_video_columns(record)))


class SqlShotRepository:
    def __init__(self, sessions: Sessions) -> None:
        self._sessions = sessions

    async def add_shot(self, shot: Shot) -> None:
        async with self._sessions.begin() as s:
            s.add(ShotRow(**_values(shot)))

    async def get_shot(self, shot_id: str) -> Shot | None:
        async with self._sessions() as s:
            row = await s.get(ShotRow, shot_id)
            return None if row is None else _from_row(Shot, row)

    async def add_take(
        self, shot_id: str, *, keyframe_key: str | None = None, clip_key: str | None = None,
        status: str = "pending",
    ) -> ShotTake:
        async with self._sessions.begin() as s:
            # 鎖定鏡頭列，並行重生時 attempt 不會重複
            shot = await s.get_one(ShotRow, shot_id, with_for_update=True)
            last = await s.scalar(select(func.max(ShotTakeRow.attempt)).where(ShotTakeRow.shot_id == shot_id))
            take = ShotTake(new_id(), shot_id, (last or 0) + 1, keyframe_key, clip_key, status)
            s.add(ShotTakeRow(**_values(take)))
            await s.flush()
            shot.current_take_id = take.id
            return take

    async def takes(self, shot_id: str) -> list[ShotTake]:
        async with self._sessions() as s:
            rows = await s.scalars(
                select(ShotTakeRow).where(ShotTakeRow.shot_id == shot_id).order_by(ShotTakeRow.attempt)
            )
            return [_from_row(ShotTake, r) for r in rows]

    async def list_shots(self, video_id: str) -> list[Shot]:
        async with self._sessions() as s:
            query = select(ShotRow).where(ShotRow.video_id == video_id)
            rows = await s.scalars(query.order_by(ShotRow.shot_no))
            return [_from_row(Shot, r) for r in rows]

    async def update_take(self, take: ShotTake) -> None:
        async with self._sessions.begin() as s:
            await s.merge(ShotTakeRow(**_values(take)))

    async def get_take(self, take_id: str) -> ShotTake | None:
        async with self._sessions() as s:
            row = await s.get(ShotTakeRow, take_id)
            return None if row is None else _from_row(ShotTake, row)


def _job_from_row(row: GenerationJobRow) -> GenerationJob:
    job = _from_row(GenerationJob, row)
    job.kind = JobKind(row.kind)
    return job


class SqlGenerationJobRepository:
    def __init__(self, sessions: Sessions) -> None:
        self._sessions = sessions

    async def create_or_get(self, job: GenerationJob) -> tuple[GenerationJob, bool]:
        async with self._sessions.begin() as s:
            inserted = await s.scalar(
                insert(GenerationJobRow)
                .values(**_values(job))
                .on_conflict_do_nothing(index_elements=[GenerationJobRow.idempotency_key])
                .returning(GenerationJobRow.id)
            )
            row = await s.scalar(
                select(GenerationJobRow).where(GenerationJobRow.idempotency_key == job.idempotency_key)
            )
            assert row is not None
            return _job_from_row(row), inserted is not None

    async def get(self, job_id: str) -> GenerationJob | None:
        async with self._sessions() as s:
            row = await s.get(GenerationJobRow, job_id)
            return None if row is None else _job_from_row(row)

    async def count_by_key(self, idempotency_key: str) -> int:
        async with self._sessions() as s:
            n = await s.scalar(
                select(func.count()).where(GenerationJobRow.idempotency_key == idempotency_key)
            )
            return n or 0

    async def get_by_key(self, idempotency_key: str) -> GenerationJob | None:
        async with self._sessions() as s:
            row = await s.scalar(
                select(GenerationJobRow).where(GenerationJobRow.idempotency_key == idempotency_key)
            )
            return None if row is None else _job_from_row(row)

    async def update(self, job: GenerationJob) -> None:
        async with self._sessions.begin() as s:
            await s.merge(GenerationJobRow(**_values(job)))

    async def update_if(self, job: GenerationJob, expected: str) -> bool:
        """單一 UPDATE … WHERE status = :expected：多個行程同時寫入時只有一個成功（spec 0018 R-004）。"""
        async with self._sessions.begin() as s:
            updated = await s.scalar(
                update(GenerationJobRow)
                .where(GenerationJobRow.id == job.id, GenerationJobRow.status == expected)
                .values(**_values(job))
                .returning(GenerationJobRow.id)
            )
            return updated is not None

    async def list_by_status(self, statuses: Iterable[str]) -> list[GenerationJob]:
        async with self._sessions() as s:
            query = select(GenerationJobRow).where(GenerationJobRow.status.in_(list(statuses)))
            rows = await s.scalars(query.order_by(GenerationJobRow.id))
            return [_job_from_row(r) for r in rows]

    async def get_by_provider_key(self, key: str) -> GenerationJob | None:
        async with self._sessions() as s:
            row = await s.scalar(
                select(GenerationJobRow).where(GenerationJobRow.provider_idempotency_key == key)
            )
            return None if row is None else _job_from_row(row)

class SqlApprovalRepository:
    def __init__(self, sessions: Sessions) -> None:
        self._sessions = sessions

    async def add(self, video_id: str, approval: Approval) -> None:
        async with self._sessions.begin() as s:
            s.add(ApprovalRow(id=new_id(), video_id=video_id, **_values(approval)))

    async def list(self, video_id: str) -> list[Approval]:
        async with self._sessions() as s:
            rows = await s.scalars(
                select(ApprovalRow).where(ApprovalRow.video_id == video_id).order_by(ApprovalRow.created_at)
            )
            return [_from_row(Approval, r) for r in rows]


class SqlCostEntryRepository:
    def __init__(self, sessions: Sessions) -> None:
        self._sessions = sessions

    async def add(self, video_id: str, entry: CostEntry) -> None:
        async with self._sessions.begin() as s:
            s.add(CostEntryRow(id=new_id(), video_id=video_id, **_values(entry)))

    async def list(self, video_id: str) -> list[CostEntry]:
        async with self._sessions() as s:
            query = select(CostEntryRow).where(CostEntryRow.video_id == video_id)
            rows = await s.scalars(query.order_by(CostEntryRow.created_at))
            return [_from_row(CostEntry, r) for r in rows]


class SqlPlanRepository:
    def __init__(self, sessions: Sessions) -> None:
        self._sessions = sessions

    async def add(self, plan: Plan) -> None:
        async with self._sessions.begin() as s:
            s.add(PlanRow(**_values(plan)))

    async def get(self, plan_id: str) -> Plan | None:
        async with self._sessions() as s:
            row = await s.get(PlanRow, plan_id)
            return None if row is None else _from_row(Plan, row)

    async def list(self, video_id: str) -> list[Plan]:
        async with self._sessions() as s:
            query = select(PlanRow).where(PlanRow.video_id == video_id)
            rows = await s.scalars(query.order_by(PlanRow.created_at))
            return [_from_row(Plan, r) for r in rows]


class SqlCharacterRepository:
    def __init__(self, sessions: Sessions) -> None:
        self._sessions = sessions

    async def add(self, character: Character, versions: list[CharacterVersion]) -> None:
        async with self._sessions.begin() as s:
            # 角色與版本互相參照：先寫入角色（未鎖定），再寫入版本，最後設定鎖定版本
            row = CharacterRow(**{**_values(character), "locked_version_id": None})
            s.add(row)
            await s.flush()
            s.add_all(CharacterVersionRow(**_values(v)) for v in versions)
            await s.flush()
            row.locked_version_id = character.locked_version_id

    async def locked_version(self, project_id: str) -> CharacterVersion | None:
        async with self._sessions() as s:
            row = await s.scalar(
                select(CharacterVersionRow)
                .join(CharacterRow, CharacterRow.locked_version_id == CharacterVersionRow.id)
                .where(CharacterRow.project_id == project_id)
            )
            return None if row is None else _from_row(CharacterVersion, row)

    async def versions(self, project_id: str) -> list[CharacterVersion]:
        async with self._sessions() as s:
            rows = await s.scalars(
                select(CharacterVersionRow)
                .join(CharacterRow, CharacterRow.id == CharacterVersionRow.character_id)
                .where(CharacterRow.project_id == project_id)
                .order_by(CharacterVersionRow.character_id, CharacterVersionRow.version)
            )
            return [_from_row(CharacterVersion, r) for r in rows]

    async def add_version(self, version: CharacterVersion, *, lock: bool = True) -> None:
        async with self._sessions.begin() as s:
            character = await s.get_one(CharacterRow, version.character_id, with_for_update=True)
            s.add(CharacterVersionRow(**_values(version)))
            await s.flush()
            if lock:
                character.locked_version_id = version.id


class SqlScenePhotoRepository:
    def __init__(self, sessions: Sessions) -> None:
        self._sessions = sessions

    async def add(self, photo: ScenePhoto) -> None:
        async with self._sessions.begin() as s:
            s.add(ScenePhotoRow(**_values(photo)))

    async def list(self, project_id: str) -> list[ScenePhoto]:
        async with self._sessions() as s:
            query = select(ScenePhotoRow).where(ScenePhotoRow.project_id == project_id)
            rows = await s.scalars(query.order_by(ScenePhotoRow.created_at))
            return [_from_row(ScenePhoto, r) for r in rows]


class SqlRenderRepository:
    def __init__(self, sessions: Sessions) -> None:
        self._sessions = sessions

    async def add(self, render: Render) -> None:
        async with self._sessions.begin() as s:
            s.add(RenderRow(**_values(render)))

    async def list(self, video_id: str) -> list[Render]:
        async with self._sessions() as s:
            query = select(RenderRow).where(RenderRow.video_id == video_id)
            rows = await s.scalars(query.order_by(RenderRow.created_at))
            return [_from_row(Render, r) for r in rows]


class SqlIdempotencyRepository:
    def __init__(self, sessions: Sessions) -> None:
        self._sessions = sessions

    async def get(self, key: str) -> IdempotencyRecord | None:
        async with self._sessions() as s:
            row = await s.get(ApiIdempotencyRow, key)
            return None if row is None else _from_row(IdempotencyRecord, row)

    async def save(self, record: IdempotencyRecord) -> bool:
        async with self._sessions.begin() as s:
            inserted = await s.scalar(
                insert(ApiIdempotencyRow)
                .values(**_values(record))
                .on_conflict_do_nothing(index_elements=[ApiIdempotencyRow.key])
                .returning(ApiIdempotencyRow.key)
            )
            return inserted is not None


def sql_repositories(engine: AsyncEngine) -> Repositories:
    sessions = session_factory(engine)
    return Repositories(
        projects=SqlProjectRepository(sessions),
        videos=SqlVideoRepository(sessions),
        shots=SqlShotRepository(sessions),
        jobs=SqlGenerationJobRepository(sessions),
        approvals=SqlApprovalRepository(sessions),
        costs=SqlCostEntryRepository(sessions),
        plans=SqlPlanRepository(sessions),
        characters=SqlCharacterRepository(sessions),
        scene_photos=SqlScenePhotoRepository(sessions),
        renders=SqlRenderRepository(sessions),
        idempotency=SqlIdempotencyRepository(sessions),
    )
