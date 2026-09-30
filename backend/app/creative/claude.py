"""Claude 呼叫介面（spec 0010）：PromptEngine 只依賴 ClaudeClient，測試以預錄回應注入。"""

from dataclasses import dataclass
from typing import Any, Protocol

from app.config import Settings


@dataclass(frozen=True)
class ClaudeReply:
    text: str  # 模型輸出的文字（預期為 JSON）
    stop_reason: str | None


class ClaudeClient(Protocol):
    async def complete(
        self, *, system: str, messages: list[dict[str, str]], schema: dict[str, Any]
    ) -> ClaudeReply: ...


class AnthropicClaudeClient:
    """以 Anthropic SDK 呼叫 Claude：結構化輸出、effort 與拒絕回應備援都由設定決定。"""

    def __init__(self, settings: Settings, *, http_client: Any = None) -> None:
        raise NotImplementedError

    async def complete(
        self, *, system: str, messages: list[dict[str, str]], schema: dict[str, Any]
    ) -> ClaudeReply:
        raise NotImplementedError
