"""SQLAlchemy ORM 模型（架構書 §7；spec 0005）。

§7 以外新增的欄位：videos.status_history、generation_jobs.idempotency_key、cost_entries.source，
以及排序用的 created_at。
"""

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

ID = String(36)
CREDITS = Numeric(12, 4)


class Base(DeclarativeBase):
    pass


def _created_at() -> Mapped[datetime]:
    # clock_timestamp：同一個交易中的多筆資料也有先後順序
    return mapped_column(DateTime(timezone=True), server_default=func.clock_timestamp())


def _fk(target: str, **kw: Any) -> Any:
    return ForeignKey(target, ondelete="CASCADE", **kw)


def _cyclic_fk(target: str, name: str) -> Any:
    """互相參照的外鍵：遷移中於所有資料表建立後才加上（見 0001_initial.DEFERRED_FKS）。"""
    return ForeignKey(target, use_alter=True, name=name, ondelete="SET NULL")


class UserRow(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(ID, primary_key=True)
    email: Mapped[str | None] = mapped_column(String, unique=True)
    name: Mapped[str] = mapped_column(String, default="")


class ProjectRow(Base):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(ID, primary_key=True)
    user_id: Mapped[str | None] = mapped_column(ID, ForeignKey("users.id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(String)
    output_defaults: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = _created_at()


class BrandProfileRow(Base):
    __tablename__ = "brand_profiles"
    project_id: Mapped[str] = mapped_column(ID, _fk("projects.id"), primary_key=True)
    visual: Mapped[dict[str, Any]] = mapped_column(JSONB)
    selling_points: Mapped[list[Any]] = mapped_column(JSONB)
    tone: Mapped[str] = mapped_column(Text)
    info: Mapped[dict[str, Any]] = mapped_column(JSONB)
    sources: Mapped[dict[str, Any]] = mapped_column(JSONB)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CharacterRow(Base):
    __tablename__ = "characters"
    id: Mapped[str] = mapped_column(ID, primary_key=True)
    project_id: Mapped[str] = mapped_column(ID, _fk("projects.id"), index=True)
    name: Mapped[str] = mapped_column(String)
    locked_version_id: Mapped[str | None] = mapped_column(
        ID, _cyclic_fk("character_versions.id", "fk_characters_locked_version_id")
    )


class CharacterVersionRow(Base):
    __tablename__ = "character_versions"
    __table_args__ = (UniqueConstraint("character_id", "version"),)
    id: Mapped[str] = mapped_column(ID, primary_key=True)
    character_id: Mapped[str] = mapped_column(ID, _fk("characters.id"))
    version: Mapped[int] = mapped_column(Integer)
    identity_board_key: Mapped[str | None] = mapped_column(String)
    cutout_key: Mapped[str | None] = mapped_column(String)
    anchor_card: Mapped[Any] = mapped_column(JSONB, nullable=True)
    voice: Mapped[Any] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String)


class ScenePhotoRow(Base):
    __tablename__ = "scene_photos"
    id: Mapped[str] = mapped_column(ID, primary_key=True)
    project_id: Mapped[str] = mapped_column(ID, _fk("projects.id"), index=True)
    image_key: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(Text, default="")
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = _created_at()  # 0003（S07）：依上傳順序列出


class VideoRow(Base):
    __tablename__ = "videos"
    id: Mapped[str] = mapped_column(ID, primary_key=True)
    project_id: Mapped[str] = mapped_column(ID, _fk("projects.id"), index=True)
    mode: Mapped[str] = mapped_column(String)
    topic: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String)
    status_history: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    selected_plan_id: Mapped[str | None] = mapped_column(
        ID, _cyclic_fk("plans.id", "fk_videos_selected_plan_id")
    )
    cost_cap: Mapped[Decimal | None] = mapped_column(CREDITS)
    timeline: Mapped[Any] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = _created_at()


class PlanRow(Base):
    __tablename__ = "plans"
    id: Mapped[str] = mapped_column(ID, primary_key=True)
    video_id: Mapped[str] = mapped_column(ID, _fk("videos.id"), index=True)
    payload: Mapped[Any] = mapped_column(JSONB)
    engine: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = _created_at()


class ShotRow(Base):
    __tablename__ = "shots"
    __table_args__ = (UniqueConstraint("video_id", "shot_no"),)
    id: Mapped[str] = mapped_column(ID, primary_key=True)
    video_id: Mapped[str] = mapped_column(ID, _fk("videos.id"))
    shot_no: Mapped[int] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(String)
    duration_s: Mapped[float] = mapped_column(Float)
    scene_photo_id: Mapped[str | None] = mapped_column(
        ID, ForeignKey("scene_photos.id", ondelete="SET NULL")
    )
    placement: Mapped[Any] = mapped_column(JSONB, nullable=True)
    prompt: Mapped[Any] = mapped_column(JSONB, nullable=True)
    current_take_id: Mapped[str | None] = mapped_column(
        ID, _cyclic_fk("shot_takes.id", "fk_shots_current_take_id")
    )


class ShotTakeRow(Base):
    __tablename__ = "shot_takes"
    __table_args__ = (UniqueConstraint("shot_id", "attempt"),)
    id: Mapped[str] = mapped_column(ID, primary_key=True)
    shot_id: Mapped[str] = mapped_column(ID, _fk("shots.id"))
    attempt: Mapped[int] = mapped_column(Integer)
    keyframe_key: Mapped[str | None] = mapped_column(String)
    clip_key: Mapped[str | None] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)


class GenerationJobRow(Base):
    __tablename__ = "generation_jobs"
    id: Mapped[str] = mapped_column(ID, primary_key=True)
    shot_take_id: Mapped[str] = mapped_column(ID, _fk("shot_takes.id"), index=True)
    idempotency_key: Mapped[str] = mapped_column(String, unique=True)
    kind: Mapped[str] = mapped_column(String)
    provider: Mapped[str] = mapped_column(String)
    model: Mapped[str] = mapped_column(String)
    external_id: Mapped[str | None] = mapped_column(String)
    provider_idempotency_key: Mapped[str | None] = mapped_column(String)
    input_snapshot: Mapped[Any] = mapped_column(JSONB, nullable=True)
    input_hash: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)
    attempt: Mapped[int] = mapped_column(Integer)
    est_cost: Mapped[Decimal | None] = mapped_column(CREDITS)
    actual_cost: Mapped[Decimal | None] = mapped_column(CREDITS)
    error: Mapped[str | None] = mapped_column(Text)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # 0002（S06）
    created_at: Mapped[datetime] = _created_at()


class ApprovalRow(Base):
    __tablename__ = "approvals"
    id: Mapped[str] = mapped_column(ID, primary_key=True)
    video_id: Mapped[str] = mapped_column(ID, _fk("videos.id"), index=True)
    kind: Mapped[str] = mapped_column(String)
    input_hash: Mapped[str] = mapped_column(String)
    cost_cap: Mapped[Decimal | None] = mapped_column(CREDITS)
    auto_approved: Mapped[bool] = mapped_column(Boolean)
    approved_by: Mapped[str | None] = mapped_column(String)
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created_at()


class CostEntryRow(Base):
    __tablename__ = "cost_entries"
    id: Mapped[str] = mapped_column(ID, primary_key=True)
    video_id: Mapped[str] = mapped_column(ID, _fk("videos.id"), index=True)
    # S04 的 CostEntry.job_id 是任意字串，不設外鍵（S06 串接生成工作時再決定）
    job_id: Mapped[str] = mapped_column(String)
    credits: Mapped[Decimal] = mapped_column(CREDITS)
    source: Mapped[str] = mapped_column(String)  # provider｜table（S04 CostEntry.source）
    created_at: Mapped[datetime] = _created_at()


class RenderRow(Base):
    __tablename__ = "renders"
    id: Mapped[str] = mapped_column(ID, primary_key=True)
    video_id: Mapped[str] = mapped_column(ID, _fk("videos.id"), index=True)
    aspect_ratio: Mapped[str] = mapped_column(String)
    subtitle_lang: Mapped[str | None] = mapped_column(String)
    mp4_key: Mapped[str] = mapped_column(String)
    thumb_key: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = _created_at()


class ApiIdempotencyRow(Base):
    """API 冪等鍵與第一次成功的回應（0004；S08）。"""

    __tablename__ = "api_idempotency"
    key: Mapped[str] = mapped_column(String, primary_key=True)
    request_hash: Mapped[str] = mapped_column(String)
    status_code: Mapped[int] = mapped_column(Integer)
    body: Mapped[Any] = mapped_column(JSONB)
    created_at: Mapped[datetime] = _created_at()
