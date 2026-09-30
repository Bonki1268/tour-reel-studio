"""S10 測試共用：預錄的 Claude 回應、品牌語氣「親切台味」且含 3 張實景照的企劃情境。"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.config import Settings
from app.creative.base import PlanContext
from app.creative.claude import ClaudeReply
from app.domain.ports import BrandProfile, ScenePhoto

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "claude"

ANCHOR_CARD = {
    "name": "梅子阿伯",
    "anchor_zh": "六十歲的梅農阿伯，黝黑皮膚、笑容憨厚，戴草帽、穿藍色工作服與雨鞋",
    "anchor_en": "a 60-year-old Taiwanese plum farmer with tanned skin and a kind smile, "
                 "wearing a straw hat, blue work clothes and rubber boots",
}
PHOTOS = (
    ("ph_01", "梅園入口：木造拱門與石板路，晨霧中的梅樹"),
    ("ph_02", "採梅步道：兩側結滿青梅的梅樹與竹籃"),
    ("ph_03", "梅子醋工坊：一排排玻璃甕與木製長桌"),
)
TEST_MODEL = "claude-test-model"


def fixture_text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def fixture_json(name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(fixture_text(name))
    return data


def plan_context(tone: str = "親切台味", photo_count: int = 3, anchor_card: Any = None) -> PlanContext:
    brand = BrandProfile(
        project_id="p1",
        selling_points=["親手採青梅", {"title": "古法梅子醋", "years": 3}],
        tone=tone,
        info={"name": "阿伯梅園", "address": "南投縣信義鄉", "hours": "每日 09:00–17:00"},
    )
    photos = [ScenePhoto(id=pid, project_id="p1", image_key=f"projects/p1/scenes/{pid}.jpg",
                         width=1080, height=1920, description=desc)
              for pid, desc in PHOTOS[:photo_count]]
    return PlanContext(brand=brand, topic="清晨採梅體驗",
                       anchor_card=ANCHOR_CARD if anchor_card is None else anchor_card, scene_photos=photos)


def engine_settings(**kw: Any) -> Settings:
    return Settings(claude_model=TEST_MODEL, **kw)


@dataclass
class RecordedClaude:
    """依序回傳預錄回應；記錄每次收到的請求。回應可以是文字、ClaudeReply 或要拋出的例外。"""

    replies: list[str | ClaudeReply | BaseException]
    requests: list[dict[str, Any]] = field(default_factory=list)

    async def complete(
        self, *, system: str, messages: list[dict[str, str]], schema: dict[str, Any]
    ) -> ClaudeReply:
        self.requests.append({"system": system, "messages": [dict(m) for m in messages], "schema": schema})
        reply = self.replies[min(len(self.requests), len(self.replies)) - 1]
        if isinstance(reply, BaseException):
            raise reply
        if isinstance(reply, ClaudeReply):
            return reply
        return ClaudeReply(text=reply, stop_reason="end_turn")
