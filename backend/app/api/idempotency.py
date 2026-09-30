"""Idempotency-Key：同鍵同內容回傳第一次的回應，同鍵不同內容 → 422（spec 0008 R-004）。"""

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi.responses import JSONResponse

from app.api.errors import IdempotencyConflict
from app.api.services import AppServices
from app.domain.approval import canonical_hash
from app.domain.ports import IdempotencyRecord


async def idempotent(
    services: AppServices, key: str, request_body: dict[str, Any], status_code: int,
    action: Callable[[], Awaitable[dict[str, Any]]],
) -> JSONResponse:
    """只保存成功的回應；失敗（例外）時不保存，可用同一個鍵重試。"""
    request_hash = canonical_hash(request_body)
    existing = await services.repos.idempotency.get(key)
    if existing is None:
        body = await action()
        if await services.repos.idempotency.save(IdempotencyRecord(key, request_hash, status_code, body)):
            return JSONResponse(body, status_code)
        existing = await services.repos.idempotency.get(key)  # 並行的同鍵請求已先保存
        assert existing is not None
    if existing.request_hash != request_hash:
        raise IdempotencyConflict("此 Idempotency-Key 已用於內容不同的請求")
    return JSONResponse(existing.body, existing.status_code)
