"""FakeCreativeEngine：回傳固定的 tourism-promo 企劃（spec 0007）。"""

from app.creative.base import PlanContext, PlanDraft, ShotDraft, ShotPrompt

# tourism-promo 固定結構（架構書 §5.4）：鏡頭、功能、長度、動作、字幕、運鏡
_SHOTS = (
    (1, "hook", 4.0, "角色轉身向鏡頭揮手", "早安！梅子熟了喔", "緩慢推進"),
    (2, "feature", 5.0, "角色示範採摘梅子", "親手採最新鮮", "跟拍"),
    (3, "cta", 3.0, "角色邀請遊客前來", "週末見！", "固定鏡頭"),
)


class FakeCreativeEngine:
    name = "fake"

    def __init__(self, plan_count: int = 3, *, fail: bool = False) -> None:
        self.contexts: list[PlanContext] = []  # 每次 propose_plans 收到的內容
        self.plan_count = plan_count
        self.fail = fail

    async def propose_plans(self, ctx: PlanContext) -> list[PlanDraft]:
        self.contexts.append(ctx)
        if self.fail:
            raise RuntimeError("假創作引擎：企劃產生失敗")
        photos = ctx.scene_photos
        return [
            PlanDraft(
                title=f"{ctx.topic}（方案 {n}）",
                concept=f"角色帶遊客體驗{ctx.topic}",
                tone="溫馨家庭",
                shots=[
                    ShotDraft(
                        shot_no=no, role=role, duration_s=dur,
                        scene_photo_id=photos[(no - 1) % len(photos)].id,
                        placement={"x": 0.62, "y": 0.88, "scale": 0.45, "flip": False},
                        action=action, subtitle=subtitle, camera=camera,
                    )
                    for no, role, dur, action, subtitle, camera in _SHOTS
                ],
                cta="私訊訂位",
            )
            for n in range(1, self.plan_count + 1)
        ]

    async def build_shot_prompts(self, plan: PlanDraft, ctx: PlanContext) -> list[ShotPrompt]:
        return [
            ShotPrompt(s.shot_no, f"{s.action}，實景 {s.scene_photo_id}", f"{s.camera}：{s.action}")
            for s in plan.shots
        ]
