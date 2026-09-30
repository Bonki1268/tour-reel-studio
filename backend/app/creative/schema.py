"""企劃輸出結構（spec 0010）：Claude 回應的結構驗證與送給 Claude 的 JSON Schema 來源。"""

from typing import Literal

from pydantic import BaseModel


class PlacementOut(BaseModel):
    x: float
    y: float
    scale: float
    flip: bool


class ShotOut(BaseModel):
    shot_no: int
    role: Literal["hook", "feature", "cta"]
    duration_s: float
    scene_photo_id: str
    placement: PlacementOut
    action: str
    action_en: str
    subtitle: str
    camera: str
    camera_en: str


class PlanOut(BaseModel):
    title: str
    concept: str
    tone: str
    shots: list[ShotOut]
    cta: str


class PlansOut(BaseModel):
    plans: list[PlanOut]
