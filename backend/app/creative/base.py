"""創作引擎介面（架構書 §5.4；spec 0007）。"""

from dataclasses import dataclass, field
from typing import Any, Protocol

from app.domain.ports import BrandProfile, ScenePhoto


@dataclass(frozen=True)
class PlanContext:
    brand: BrandProfile
    topic: str
    anchor_card: Any
    scene_photos: list[ScenePhoto]


@dataclass(frozen=True)
class ShotDraft:
    shot_no: int
    role: str
    duration_s: float
    scene_photo_id: str
    placement: dict[str, Any]
    action: str
    subtitle: str = ""
    camera: str = ""
    action_en: str = ""  # 英文描述供影片提示詞使用（S10）
    camera_en: str = ""


@dataclass(frozen=True)
class PlanDraft:
    title: str
    concept: str
    tone: str
    shots: list[ShotDraft]
    cta: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ShotPrompt:
    shot_no: int
    keyframe_prompt: str
    video_prompt: str


class CreativeEngine(Protocol):
    name: str

    async def propose_plans(self, ctx: PlanContext) -> list[PlanDraft]: ...

    async def build_shot_prompts(self, plan: PlanDraft, ctx: PlanContext) -> list[ShotPrompt]: ...
