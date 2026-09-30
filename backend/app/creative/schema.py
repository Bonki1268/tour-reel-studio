"""企劃輸出結構（spec 0010）：Claude 回應的結構驗證與送給 Claude 的 JSON Schema 來源。"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]

ROLES = ("hook", "feature", "cta")  # tourism-promo 固定的 3 鏡功能與順序


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PlacementOut(_Strict):
    """角色腳底中心位置（x、y，畫面比例）與身高佔畫面高度的比例。"""

    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    scale: float = Field(gt=0, le=1)
    flip: bool


class ShotOut(_Strict):
    shot_no: Literal[1, 2, 3]
    role: Literal["hook", "feature", "cta"]
    duration_s: float = Field(gt=0)
    scene_photo_id: Text
    placement: PlacementOut
    action: Text = Field(description="角色動作（繁體中文）")
    action_en: Text = Field(description="角色動作（英文，供影片生成）")
    subtitle: Text = Field(description="字幕（繁體中文，12 字以內）")
    camera: Text = Field(description="運鏡（繁體中文，寫明速度與幅度）")
    camera_en: Text = Field(description="運鏡（英文，寫明速度與幅度）")


class PlanOut(_Strict):
    title: Text
    concept: Text
    tone: Text
    shots: list[ShotOut] = Field(min_length=3, max_length=3)
    cta: Text

    @model_validator(mode="after")
    def _shot_order(self) -> "PlanOut":
        if [s.shot_no for s in self.shots] != [1, 2, 3] or tuple(s.role for s in self.shots) != ROLES:
            raise ValueError("3 鏡必須依序為 1 hook、2 feature、3 cta")
        return self


class PlansOut(_Strict):
    plans: list[PlanOut] = Field(min_length=2, max_length=3)
