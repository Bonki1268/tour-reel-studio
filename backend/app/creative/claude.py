"""Claude 呼叫介面（spec 0010）：PromptEngine 只依賴 ClaudeClient，測試以預錄回應注入。"""

import logging
from dataclasses import dataclass
from typing import Any, Protocol

import anthropic

from app.config import Settings

log = logging.getLogger(__name__)

MAX_TOKENS = 16000
FALLBACK_BETA = "server-side-fallback-2026-07-01"


@dataclass(frozen=True)
class ClaudeReply:
    text: str  # 模型輸出的文字（預期為 JSON）
    stop_reason: str | None


class ClaudeClient(Protocol):
    async def complete(
        self, *, system: str, messages: list[dict[str, str]], schema: dict[str, Any]
    ) -> ClaudeReply: ...


class AnthropicClaudeClient:
    """以 Anthropic SDK 呼叫 Claude：結構化輸出、effort 與拒絕回應備援都由設定決定。

    API 錯誤由 SDK 自動重試後原樣拋出（anthropic.APIError），由 PromptEngine 轉為企劃產生錯誤。
    """

    def __init__(self, settings: Settings, *, http_client: Any = None) -> None:
        key = settings.anthropic_api_key.get_secret_value() if settings.anthropic_api_key else None
        self._client = anthropic.AsyncAnthropic(api_key=key, http_client=http_client)
        self._settings = settings

    async def complete(
        self, *, system: str, messages: list[dict[str, str]], schema: dict[str, Any]
    ) -> ClaudeReply:
        s = self._settings
        params: dict[str, Any] = {
            "model": s.claude_model,
            "max_tokens": MAX_TOKENS,
            "system": system,
            "messages": messages,
            "output_config": {"effort": s.claude_effort, "format": {"type": "json_schema", "schema": schema}},
        }
        message: Any
        if s.claude_refusal_fallback:
            async with self._client.beta.messages.stream(
                **params, betas=[FALLBACK_BETA], fallbacks="default"
            ) as stream:
                message = await stream.get_final_message()
        else:
            async with self._client.messages.stream(**params) as stream:
                message = await stream.get_final_message()
        # 只記錄用量，不記錄提示詞與回應全文
        log.info("claude usage model=%s input_tokens=%s output_tokens=%s stop_reason=%s",
                 message.model, message.usage.input_tokens, message.usage.output_tokens, message.stop_reason)
        text = "".join(block.text for block in message.content if block.type == "text")
        return ClaudeReply(text=text, stop_reason=message.stop_reason)
