"""例外 → HTTP 狀態碼與錯誤內容（spec 0008 R-005）。錯誤內容不含堆疊、金鑰或供應商網址。"""

from typing import Any

from app.domain.approval import ApprovalInvalidated
from app.domain.cost import BudgetExceeded
from app.domain.video import InvalidTransition
from app.jobs.orchestrator import NotFound


class InvalidState(Exception):
    """目前狀態不允許此操作（例如非 approved 時下載）。"""


class IdempotencyConflict(Exception):
    """同一個 Idempotency-Key 的請求內容不同。"""


class CostCapTooLow(Exception):
    """成本上限低於企劃的預估成本。"""


HANDLED = (InvalidTransition, InvalidState, ApprovalInvalidated, BudgetExceeded, NotFound,
           IdempotencyConflict, CostCapTooLow)


def error_response(exc: Exception) -> tuple[int, dict[str, Any]]:
    """回傳（狀態碼, 內容）；內容至少含 code 與繁體中文 message。"""
    if isinstance(exc, InvalidTransition):
        return 409, {"code": "invalid_state", "message": f"影片目前為 {exc.status}，不能執行此操作"}
    if isinstance(exc, InvalidState):
        return 409, {"code": "invalid_state", "message": str(exc)}
    if isinstance(exc, ApprovalInvalidated):
        return 409, {"code": "approval_invalidated", "message": "企劃核准後內容已變更，請重新確認企劃與成本"}
    if isinstance(exc, BudgetExceeded):
        return 409, {
            "code": "budget_exceeded", "message": "此操作會超出核准的成本上限，請重新確認",
            "requires_reconfirmation": True,
            "cap": str(exc.cap), "committed": str(exc.committed), "requested": str(exc.requested),
        }
    if isinstance(exc, NotFound):
        return 404, {"code": "not_found", "message": str(exc)}
    if isinstance(exc, IdempotencyConflict):
        return 422, {"code": "idempotency_conflict", "message": str(exc)}
    if isinstance(exc, CostCapTooLow):
        return 422, {"code": "cost_cap_too_low", "message": str(exc)}
    return 500, {"code": "internal_error", "message": "伺服器發生錯誤，請稍後再試"}
