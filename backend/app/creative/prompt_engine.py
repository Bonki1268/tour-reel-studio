"""PromptEngine：以 tourism-promo 模板呼叫 Claude 產生企劃與每鏡生成提示詞（架構書 §5.4；spec 0010）。"""

from app.config import Settings
from app.creative.base import PlanContext, PlanDraft, ShotPrompt
from app.creative.claude import ClaudeClient
from app.creative.schema import PlansOut


class PlanGenerationError(Exception):
    """企劃產生失敗；reason 只含驗證錯誤或錯誤類型，不含提示詞或金鑰。"""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"企劃產生失敗：{reason}")


class InvalidPlanOutput(ValueError):
    """Claude 的輸出不是合法 JSON、不符結構或違反語意規則。"""


def validate_plans(plans: PlansOut, ctx: PlanContext) -> list[str]:
    """語意驗證；回傳錯誤清單（空清單代表有效）。"""
    raise NotImplementedError


def parse_plans(text: str, ctx: PlanContext) -> PlansOut:
    """解析並驗證 Claude 的輸出；無效時拋出 InvalidPlanOutput。"""
    raise NotImplementedError


class PromptEngine:
    name = "prompt"

    def __init__(self, client: ClaudeClient, settings: Settings) -> None:
        raise NotImplementedError

    def build_prompt(self, ctx: PlanContext) -> tuple[str, str]:
        raise NotImplementedError

    async def propose_plans(self, ctx: PlanContext) -> list[PlanDraft]:
        raise NotImplementedError

    async def build_shot_prompts(self, plan: PlanDraft, ctx: PlanContext) -> list[ShotPrompt]:
        raise NotImplementedError
