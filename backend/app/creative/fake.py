"""FakeCreativeEngine：回傳固定的 tourism-promo 企劃（spec 0007）。"""

from app.creative.base import PlanContext, PlanDraft, ShotPrompt


class FakeCreativeEngine:
    name = "fake"

    def __init__(self, plan_count: int = 3, *, fail: bool = False) -> None:
        self.contexts: list[PlanContext] = []  # 每次 propose_plans 收到的內容
        raise NotImplementedError

    async def propose_plans(self, ctx: PlanContext) -> list[PlanDraft]:
        raise NotImplementedError

    async def build_shot_prompts(self, plan: PlanDraft, ctx: PlanContext) -> list[ShotPrompt]:
        raise NotImplementedError
