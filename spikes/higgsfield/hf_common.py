"""S00 驗證腳本共用工具：載入金鑰、估價、以 subscribe 送出並記錄耗時與點數。

安全規則：
- HF_KEY 只在執行時從 repo 根目錄的 .env.local 載入，不印出、不寫入紀錄。
- 預設只估價（不產生費用）；必須加上 --yes 才會真正送出生成請求。
- 送出生成的 POST 不自動重試（官方文件：送出不支援冪等鍵，重送可能重複扣點）。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

import higgsfield_client
from higgsfield_client import HiggsfieldClientError
from higgsfield_client.http.retry import create_default_retry_strategy
from higgsfield_client.http.transport import HttpTransport

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
INPUTS = HERE / "inputs"
OUTPUTS = HERE / "outputs"
RUN_LOG = HERE / "results" / "runs.jsonl"

BASE_URL = "https://api.higgsfield.ai"
T2V_MODEL = "bytedance/seedance-2.5/text-to-video"
I2V_MODEL = "bytedance/seedance-2.5/image-to-video"
IMAGE_MODEL = "xai/grok-imagine-image-2.0"

TERMINAL_FAIL = {"failed", "nsfw", "canceled"}
POLL_INTERVAL_S = 2.0
DEFAULT_TIMEOUT_S = 15 * 60


class GenerationFailed(RuntimeError):
    """請求以 failed／nsfw／canceled 結束，或逾時、送出失敗。"""


class _NoPostRetryTransport(HttpTransport):
    """GET（輪詢）照常重試；POST（送出生成、上傳網址）不重試，避免重複扣點。"""

    def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        if method.upper() == "POST":
            response = self._client.request(method, url, **kwargs)
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as e:
                from higgsfield_client.http.error import extract_error_message

                raise HiggsfieldClientError(
                    f"HTTP {response.status_code}: {extract_error_message(response)}"
                ) from e
            return response
        return super().request(method, url, **kwargs)


def load_credentials() -> None:
    """從 .env.local 載入 HF_KEY；只檢查格式，不輸出內容。"""
    load_dotenv(REPO_ROOT / ".env.local", override=False)
    key = os.environ.get("HF_KEY", "")
    if ":" not in key or key.startswith(":") or key.endswith(":"):
        sys.exit("找不到有效的 HF_KEY（格式應為 key-id:key-secret），請確認 repo 根目錄的 .env.local。")


def make_client() -> higgsfield_client.SyncClient:
    client = higgsfield_client.SyncClient()
    # 以不重試 POST 的 transport 取代 SDK 預設值（cached_property 可直接覆寫）
    client.__dict__["_transport"] = _NoPostRetryTransport(
        client._client, create_default_retry_strategy()
    )
    return client


def _auth_headers() -> dict[str, str]:
    return {"Authorization": f"Key {os.environ['HF_KEY']}", "Content-Type": "application/json"}


def estimate(model: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """呼叫官方估價端點（不產生費用），回傳 {'credits': ..., 'usd': ...}。"""
    r = httpx.post(f"{BASE_URL}/estimate/{model}", json=arguments, headers=_auth_headers(), timeout=30)
    if r.status_code >= 400:
        raise GenerationFailed(f"估價失敗 HTTP {r.status_code}: {r.text[:300]}")
    return r.json()


def log_run(record: dict[str, Any]) -> None:
    RUN_LOG.parent.mkdir(parents=True, exist_ok=True)
    with RUN_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _output_url(result: dict[str, Any]) -> str | None:
    if isinstance(result.get("video"), dict):
        return result["video"].get("url")
    images = result.get("images") or []
    return images[0].get("url") if images else None


def run_generation(
    client: higgsfield_client.SyncClient,
    *,
    experiment: str,
    label: str,
    model: str,
    arguments: dict[str, Any],
    est: dict[str, Any] | None,
    timeout_s: float = DEFAULT_TIMEOUT_S,
) -> dict[str, Any]:
    """以 subscribe 送出並等待；非 completed 一律拋出 GenerationFailed，並寫入紀錄。"""
    record: dict[str, Any] = {
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "experiment": experiment,
        "label": label,
        "model": model,
        "arguments": arguments,
        "estimate_credits": (est or {}).get("credits"),
        "estimate_usd": (est or {}).get("usd"),
        "pricing_description": (est or {}).get("pricing_description"),
        "request_id": None,
        "status": None,
        "elapsed_s": None,
        "output_url": None,
        "error": None,
    }
    started = time.monotonic()
    seen: list[str] = []

    def on_enqueue(request_id: str) -> None:
        record["request_id"] = request_id
        print(f"  已送出 request_id={request_id}", flush=True)

    def on_queue_update(status: Any) -> None:
        name = type(status).__name__
        if not seen or seen[-1] != name:
            seen.append(name)
            print(f"  狀態：{name}（{time.monotonic() - started:.0f}s）", flush=True)
        if time.monotonic() - started > timeout_s:
            raise TimeoutError(f"超過 {timeout_s:.0f} 秒仍未完成")
        time.sleep(POLL_INTERVAL_S)  # SDK 預設每 0.5 秒輪詢，放慢以減少負載

    try:
        result = client.subscribe(model, arguments, on_enqueue=on_enqueue, on_queue_update=on_queue_update)
        record["status"] = result.get("status")
        record["output_url"] = _output_url(result)
        record["error"] = result.get("error")
        # 保留回應中任何與成本相關的欄位（文件未定義，若有則記錄）
        extra = {k: v for k, v in result.items() if "credit" in k or "cost" in k}
        if extra:
            record["cost_fields"] = extra
    except (HiggsfieldClientError, TimeoutError, httpx.HTTPError) as e:
        record["status"] = record["status"] or "client_error"
        record["error"] = f"{type(e).__name__}: {e}"
    finally:
        record["elapsed_s"] = round(time.monotonic() - started, 1)
        log_run(record)

    if record["status"] != "completed" or not record["output_url"]:
        reason = record["error"] or "（無錯誤訊息）"
        if record["status"] == "nsfw":
            reason = f"內容審核拒絕（nsfw）{reason}"
        elif record["status"] == "canceled":
            reason = f"請求已取消 {reason}"
        raise GenerationFailed(
            f"[{label}] 失敗：status={record['status']} request_id={record['request_id']} "
            f"耗時={record['elapsed_s']}s — {reason}"
        )
    print(f"  完成（{record['elapsed_s']}s）：{record['output_url']}")
    return record


def download(url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with httpx.stream("GET", url, timeout=120, follow_redirects=True) as r:
        r.raise_for_status()
        with dest.open("wb") as f:
            for chunk in r.iter_bytes():
                f.write(chunk)
    return dest


def base_parser(description: str) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=description)
    p.add_argument("--yes", action="store_true", help="確認產生費用並實際送出；未加時只估價")
    return p


def quote(items: list[tuple[str, str, dict[str, Any]]]) -> list[dict[str, Any]]:
    """對每個 (標籤, 模型, 參數) 估價並列出合計。"""
    ests, total, all_numeric = [], 0.0, True
    for label, model, args in items:
        est = estimate(model, args)
        ests.append(est)
        if est.get("credits") is not None:
            total += float(est["credits"])
            print(f"  估價 {label}: {est['credits']} 點（約 US${est.get('usd')}）")
        else:
            # 部分模型（如 Seedance 2.5）只回傳文字計價說明，不回傳點數
            all_numeric = False
            print(f"  估價 {label}：未回傳點數，計價說明如下\n    {est.get('pricing_description', est)}")
    if all_numeric:
        print(f"  合計預估：{total:g} 點")
    return ests
