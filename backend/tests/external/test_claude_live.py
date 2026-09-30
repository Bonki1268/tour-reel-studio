"""真實呼叫 Claude 產生一次企劃（spec 0010 T-07）。

不列入閘門；會產生費用，只在使用者同意並設定 ANTHROPIC_API_KEY、CLAUDE_MODEL 後手動執行：
    cd backend && python -m pytest -m "S10 and external" tests/external/test_claude_live.py
"""

import os

import pytest

from app.config import Settings
from app.creative.claude import AnthropicClaudeClient
from app.creative.prompt_engine import PromptEngine
from tests.claude_support import plan_context

pytestmark = [pytest.mark.S10, pytest.mark.external]


@pytest.fixture
def live_settings() -> Settings:
    key, model = os.environ.get("TRS_LIVE_ANTHROPIC_API_KEY"), os.environ.get("TRS_LIVE_CLAUDE_MODEL")
    if not key or not model:
        pytest.skip("未設定 TRS_LIVE_ANTHROPIC_API_KEY／TRS_LIVE_CLAUDE_MODEL，略過真實 API 測試")
    return Settings(anthropic_api_key=key, claude_model=model)


async def test_r001_live_claude_generates_valid_plans(live_settings: Settings) -> None:
    engine = PromptEngine(AnthropicClaudeClient(live_settings), live_settings)
    ctx = plan_context()

    plans = await engine.propose_plans(ctx)
    prompts = await engine.build_shot_prompts(plans[0], ctx)

    assert 2 <= len(plans) <= 3
    assert [s.role for s in plans[0].shots] == ["hook", "feature", "cta"]
    assert len(prompts) == 3
