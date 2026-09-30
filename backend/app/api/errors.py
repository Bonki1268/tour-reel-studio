"""例外 → HTTP 狀態碼與錯誤內容（spec 0008 R-005）。錯誤內容不含堆疊、金鑰或供應商網址。"""

from typing import Any


class InvalidState(Exception):
    """目前狀態不允許此操作（例如非 approved 時下載）。"""


class IdempotencyConflict(Exception):
    """同一個 Idempotency-Key 的請求內容不同。"""


class CostCapTooLow(Exception):
    """成本上限低於企劃的預估成本。"""


def error_response(exc: Exception) -> tuple[int, dict[str, Any]]:
    """回傳（狀態碼, 內容）；內容至少含 code 與繁體中文 message。"""
    raise NotImplementedError
