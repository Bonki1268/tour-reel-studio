"""API request／response（spec 0008）。點數以 Decimal 表示，JSON 中為字串。"""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Topic = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class TopicIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    topic: Topic


class PlacementIn(BaseModel):
    """角色擺放：以照片座標的比例值 0–1 表示（架構書 §5.3）。"""

    model_config = ConfigDict(extra="forbid")
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    scale: float = Field(gt=0)
    flip: bool = False


class ApprovePlanIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    plan_id: str
    cost_cap: Decimal = Field(gt=0)
    placements: dict[int, PlacementIn] | None = None


class RegenerateIn(BaseModel):
    """重生單鏡；cost_cap 為使用者同意提高後的成本上限（spec 0016 R-007）。"""

    model_config = ConfigDict(extra="forbid")
    cost_cap: Decimal | None = Field(default=None, gt=0)


class EstimateOut(BaseModel):
    total: Decimal
    reserve: Decimal
    cap: Decimal


class PlanOut(BaseModel):
    id: str
    payload: dict[str, Any]
    estimate: EstimateOut


class TakeOut(BaseModel):
    attempt: int
    status: str
    keyframe_key: str | None
    clip_key: str | None


class ShotOut(BaseModel):
    shot_no: int
    role: str
    duration_s: float
    placement: dict[str, Any] | None
    take: TakeOut | None
    regen_cost: Decimal = Decimal(0)  # 該鏡完整重生（關鍵幀＋影片）的預估點數（spec 0016 R-007）


class VideoOut(BaseModel):
    id: str
    project_id: str
    status: str
    topic: str
    plans: list[PlanOut]
    selected_plan_id: str | None
    shots: list[ShotOut]
    cost_cap: Decimal | None
    spent: Decimal
    preview_url: str | None = None
    fallback_url: str | None = None  # 保底成品（S18）：生成超過展示門檻時才有值


class DownloadOut(BaseModel):
    url: str
    expires_at: datetime


class CharacterOut(BaseModel):
    """鎖定的角色版本；cutout_url 為去背圖的預簽名網址（spec 0015 R-007）。"""

    id: str
    version: int
    anchor_card: Any = None
    cutout_url: str | None = None


class ScenePhotoOut(BaseModel):
    id: str
    image_key: str
    width: int
    height: int
    description: str = ""
    url: str | None = None


class BrandOut(BaseModel):
    visual: dict[str, Any]
    selling_points: list[Any]
    tone: str | None = None
    info: dict[str, Any]


class ProjectOut(BaseModel):
    id: str
    name: str
    brand: BrandOut
    character: CharacterOut | None
    scene_photos: list[ScenePhotoOut]
