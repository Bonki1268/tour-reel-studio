"""PromptEngine：以 tourism-promo 模板呼叫 Claude 產生企劃與每鏡生成提示詞（架構書 §5.4；spec 0010）。"""

import json
from pathlib import Path
from typing import Any

import anthropic
from pydantic import ValidationError

from app.config import ConfigError, Settings
from app.creative.base import PlanContext, PlanDraft, ShotDraft, ShotPrompt
from app.creative.claude import ClaudeClient
from app.creative.schema import PlanOut, PlansOut

SKILL_RULES = (Path(__file__).parent / "skills" / "tourism-promo" / "SKILL.md").read_text(encoding="utf-8")
PLAN_REQUEST_COUNT = 3  # 要求 Claude 產生的企劃數；結構接受 2～3 個
MAX_ATTEMPTS = 2  # 第一次＋無效時重試一次
TOTAL_SHOT_SECONDS = 12.0  # 3 鏡合計；片尾卡 3 秒另計
_TOLERANCE = 0.01
_BACKGROUND_KEYFRAME = ("keep the real background unchanged, match lighting and shadows, "
                        "photorealistic, vertical 9:16, no text")
_BACKGROUND_VIDEO = ("Keep the real background, buildings and landmarks exactly as in the first frame; "
                     "consistent natural lighting and shadows; photorealistic; vertical 9:16; "
                     "no on-screen text, no subtitles, no logos.")


class PlanGenerationError(Exception):
    """企劃產生失敗；reason 只含驗證錯誤或錯誤類型，不含提示詞或金鑰。"""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"企劃產生失敗：{reason}")


class InvalidPlanOutput(ValueError):
    """Claude 的輸出不是合法 JSON、不符結構或違反語意規則。"""


def validate_plans(plans: PlansOut, ctx: PlanContext) -> list[str]:
    """語意驗證；回傳錯誤清單（空清單代表有效）。"""
    photo_ids = {p.id for p in ctx.scene_photos}
    errors: list[str] = []
    for i, plan in enumerate(plans.plans, start=1):
        total = sum(s.duration_s for s in plan.shots)
        if abs(total - TOTAL_SHOT_SECONDS) > _TOLERANCE:
            errors.append(f"企劃 {i}：3 鏡長度合計 {total:g} 秒，必須為 {TOTAL_SHOT_SECONDS:g} 秒")
        for s in plan.shots:
            where = f"企劃 {i} 第 {s.shot_no} 鏡"
            if s.scene_photo_id not in photo_ids:
                available = "、".join(sorted(photo_ids))
                errors.append(f"{where}：實景照 {s.scene_photo_id} 不存在，只能使用 {available}")
            p = s.placement
            if not (0 <= p.x <= 1 and 0 <= p.y <= 1 and 0 < p.scale <= 1):
                errors.append(f"{where}：擺放超出範圍（x、y 須介於 0 到 1，scale 須大於 0 且不超過 1）")
    return errors


def _schema_errors(e: ValidationError) -> str:
    # 不使用 str(e)：它會附帶輸入值，訊息冗長
    return "；".join(
        f"{'.'.join(str(part) for part in err['loc']) or '根層級'}：{err['msg']}" for err in e.errors()
    )


def parse_plans(text: str, ctx: PlanContext) -> PlansOut:
    """解析並驗證 Claude 的輸出；無效時拋出 InvalidPlanOutput。"""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise InvalidPlanOutput(f"不是合法 JSON（{e.msg}，第 {e.lineno} 行）") from e
    try:
        plans = PlansOut.model_validate(data)
    except ValidationError as e:
        raise InvalidPlanOutput(f"不符合 JSON Schema：{_schema_errors(e)}") from e
    errors = validate_plans(plans, ctx)
    if errors:
        raise InvalidPlanOutput("；".join(errors))
    return plans


def _to_draft(plan: PlanOut) -> PlanDraft:
    return PlanDraft(
        title=plan.title, concept=plan.concept, tone=plan.tone, cta=plan.cta,
        shots=[
            ShotDraft(shot_no=s.shot_no, role=s.role, duration_s=s.duration_s,
                      scene_photo_id=s.scene_photo_id, placement=s.placement.model_dump(),
                      action=s.action, subtitle=s.subtitle, camera=s.camera,
                      action_en=s.action_en, camera_en=s.camera_en)
            for s in plan.shots
        ],
    )


def _bullet(value: Any) -> str:
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)


def anchor_text(anchor_card: Any) -> str:
    """影片提示詞用的角色錨點：anchor_en 優先，否則以 key: value 串接。"""
    if isinstance(anchor_card, dict):
        if anchor_card.get("anchor_en"):
            return str(anchor_card["anchor_en"])
        return "; ".join(f"{k}: {_bullet(v)}" for k, v in anchor_card.items())
    return "" if anchor_card is None else _bullet(anchor_card)


class PromptEngine:
    name = "prompt"

    def __init__(self, client: ClaudeClient, settings: Settings) -> None:
        if not settings.claude_model.strip():
            raise ConfigError(("CLAUDE_MODEL",))
        self.client = client
        self._schema = anthropic.transform_schema(PlansOut)

    def build_prompt(self, ctx: PlanContext) -> tuple[str, str]:
        """回傳 (system, user)：system 為題材規則，user 為本次專案的品牌、角色、實景照與主題。"""
        brand = ctx.brand
        lines = ["## 店家品牌檔案", f"- 語氣：{brand.tone or '未指定'}", "- 賣點："]
        lines += [f"  - {_bullet(point)}" for point in brand.selling_points] or ["  - 未提供"]
        lines += ["- 店家資訊："]
        lines += [f"  - {key}：{_bullet(value)}" for key, value in brand.info.items()] or ["  - 未提供"]
        lines += [
            "",
            "## 角色（已定妝，身份錨點不可變動）",
            json.dumps(ctx.anchor_card, ensure_ascii=False, indent=2),
            "",
            "## 可用實景照（每鏡只能從中選一張，填入 scene_photo_id）",
            *[f"- {p.id}：{p.description or '（無描述）'}" for p in ctx.scene_photos],
            "",
            "## 本支影片主題",
            ctx.topic,
            "",
            f"請產生 {PLAN_REQUEST_COUNT} 個企劃，除了 action_en、camera_en 以外一律以繁體中文撰寫。",
        ]
        return SKILL_RULES, "\n".join(lines)

    async def propose_plans(self, ctx: PlanContext) -> list[PlanDraft]:
        system, user = self.build_prompt(ctx)
        messages = [{"role": "user", "content": user}]
        reason = ""
        for _ in range(MAX_ATTEMPTS):
            try:
                reply = await self.client.complete(system=system, messages=messages, schema=self._schema)
            except anthropic.APIError as e:
                raise PlanGenerationError(f"Claude API 錯誤（{type(e).__name__}）") from e
            if reply.stop_reason == "refusal":
                raise PlanGenerationError("Claude 拒絕回應（refusal）")
            try:
                return [_to_draft(plan) for plan in parse_plans(reply.text, ctx).plans]
            except InvalidPlanOutput as e:
                reason = str(e)
                if reply.stop_reason == "max_tokens":
                    reason = f"輸出超過長度上限被截斷；{reason}"
            retry = f"上一次的輸出無效：{reason}。請修正後重新輸出完整 JSON。"
            if reply.text.strip():
                messages = [*messages, {"role": "assistant", "content": reply.text}]
            messages = [*messages, {"role": "user", "content": retry}]
        raise PlanGenerationError(f"連續 {MAX_ATTEMPTS} 次輸出無效：{reason}")

    async def build_shot_prompts(self, plan: PlanDraft, ctx: PlanContext) -> list[ShotPrompt]:
        """依 S00 驗證過的模板組成每鏡提示詞（角色錨點＋動作＋場景＋運鏡＋保留實景背景、無文字）。"""
        scenes = {p.id: p.description for p in ctx.scene_photos}
        anchor = anchor_text(ctx.anchor_card)
        prompts = []
        for s in plan.shots:
            action, camera = s.action_en or s.action, s.camera_en or s.camera
            scene = scenes.get(s.scene_photo_id, "")
            prompts.append(ShotPrompt(
                shot_no=s.shot_no,
                keyframe_prompt=f"{anchor}; {action}; setting: {scene}; {_BACKGROUND_KEYFRAME}",
                video_prompt=f"{anchor}. {action}. Setting: {scene}. Camera: {camera}. {_BACKGROUND_VIDEO}",
            ))
        return prompts
