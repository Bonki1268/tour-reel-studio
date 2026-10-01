# Demo 可靠性：設計

> 對應規格：spec.md（版本 v1）。本檔由 Claude Code 撰寫，隨規格核准一併審閱。

## 設計概要

```
POST /webhooks/higgsfield?ref&sig ──驗證──▶ jobs.get_by_provider_key(ref) ──▶ queue.enqueue("process_webhook", video_id, job_id) ─▶ 202
                                                                                         │
Worker: process_webhook ──▶ fetch_result(原 request ID) ──succeeded──▶ complete_job()  ◀──┤
Worker: generate_video ──▶ run_generation_job ──▶ _wait 輪詢 ──succeeded──▶ complete_job() ◀┘
                                                                              │
                     jobs.update_if(job, expected=submitted|running → succeeded)  只有一方成功
                       成功：下載 → 轉存 → 更新 take → update_if(succeeded → stored) → 記帳
                       失敗：不處理；輪詢端改為等待工作變成 stored／failed
```

### 條件更新（app/storage）

- `GenerationJobRepository.update_if(job, expected: JobStatus) -> bool`：只有資料庫中的狀態等於 `expected` 時整筆寫入。
  - SQL：`UPDATE generation_jobs SET … WHERE id = :id AND status = :expected RETURNING id`
  - 記憶體：同一個事件迴圈中檢查與寫入之間沒有 `await`，天然原子
- `GenerationJobRepository.list_by_status(statuses) -> list[GenerationJob]`、`get_by_provider_key(key) -> GenerationJob | None`
- `ShotRepository.get_take(take_id) -> ShotTake | None`（由工作反查影片）

### 生成工作（app/jobs/generation.py）

- `_transition` 改用 `update_if(job, expected=原狀態)`；失敗時拋出 `JobTaken`（工作已被其他來源改變），呼叫端重新讀取。
- `complete_job(deps, job, result, *, budget) -> bool`：共用的結果處理。取得處理權（`submitted`／`running` → `succeeded`）才下載、轉存、更新鏡頭版本、`stored`、記帳；回傳是否由本次處理。
  - 鏡頭版本、結果路徑由 `job.shot_take_id` → take → shot → video 反查（webhook 路徑沒有 `JobSpec`）。
  - 記帳：`budget.record(...)`（同一工作只記一次，S04）後寫入 `costs`。
  - 轉存失敗：`succeeded → failed`（可重試），由輪詢端的重試規則處理。
- `_wait` 每次輪詢先重新讀取工作：`stored` → 同步本地預算（讀回成本帳中該工作的紀錄、釋放預留）後視為完成；`failed` → 視為本次嘗試失敗（不再重寫狀態）；`succeeded` → 他方轉存中，繼續等待（仍受逾時限制）。

### Webhook（app/api/routes/webhooks.py、app/jobs/worker.py）

- 端點：簽章無效 401；簽章有效一律 202 `{"accepted": true}`（S12 R-005 的回應不變）。`ref` 對應到未結束（`submitted`／`running`／`succeeded`）的工作時排入 `process_webhook(video_id, job_id)`；對應不到或工作已結束（`stored`／`failed`／`failed_final`）時不排入、不做任何變更。`succeeded` 代表另一個來源轉存中，webhook 仍會處理，由條件更新確保只轉存一次。
- `process_webhook`：重新讀取工作，已結束時回傳 `skipped`；`fetch_result(ProviderJob(原 request ID))`；`succeeded` → `complete_job`（預算以該影片目前的成本帳建立）；`running`／`failed` → 不處理（失敗與重試只由輪詢端決定）。

### 恢復（app/jobs/recovery.py）

- `recover(services) -> RecoveryReport`：
  1. `list_by_status([submitted, running, succeeded])`
  2. `submitted`／`running` 且未逾時 → 接續；逾時 → `update_if(→ failed, error="timeout: …")`；`succeeded` → `update_if(→ failed, error="interrupted: 轉存途中中斷")`
  3. 反查所屬影片；狀態為 `generating` 的影片各排入一次 `generate_video`（S07 的 `generate` 對已 `stored` 的工作直接回傳、對已送出的工作以原 request ID 繼續查詢、對已失敗的第 1 次嘗試進行第 2 次）
- arq `on_startup` 在建立服務後呼叫 `recover`。

### 保底成品（app/api/routes/videos.py、app/domain/fallback.py）

- 設定：`DEMO_FALLBACK_VIDEO: str = ""`、`DEMO_FALLBACK_AFTER_S: float = 420`
- 領域函式 `fallback_due(video, now, after_s, has_render) -> bool`：狀態屬於 `generating`／`rendering`／`needs_attention`、沒有成品、且距最後一次轉入 `generating` 已達門檻。
- `video_out`：`fallback_due` 且 `storage.exists(key)` 時回傳 `fallback_url = presign_get(key)`。

## 資料模型／狀態轉換變更

- 無資料表變更、無遷移。S06 的工作狀態轉換表不變。
- `VideoOut` 新增 `fallback_url: str | None`（OpenAPI 與 `apps/web` 的型別需重新產生；前端暫不使用）。

## API 契約（request／response、錯誤碼）

- `POST /webhooks/higgsfield?ref=…&sig=…`：401 `invalid_signature`；202 `{"accepted": true}`。
- `GET /videos/{id}`：新增 `fallback_url`（`string | null`）。

## 失敗行為、安全與可觀測性

- webhook 仍不採用通知內容（避免偽造或重放），只當作「立即查詢」的觸發。
- `process_webhook` 失敗（供應商查詢錯誤）只記錄，不改變工作；輪詢仍會完成。
- 恢復掃描在 Worker 啟動時執行一次；掃描失敗記錄錯誤但不阻止 Worker 啟動。
- 日誌：`job_id`、來源（`poll`／`webhook`／`recovery`）、結果（`processed`／`taken`／`skipped`）。

## 測試策略

| 需求 | 驗收條件 | 測試層級 | 測試位置 |
|---|---|---|---|
| R-001 | AC-001 | BDD（S18-01）：`HiggsfieldProvider`＋`respx` | `backend/tests/bdd/test_s18_reliability.py` |
| R-002 | AC-002 | BDD（S18-02）：同上 | 同上 |
| R-003、R-004 | AC-003 | BDD（S18-03）：`FakeProvider`＋慢速儲存讓兩者交錯 | 同上 |
| R-004 | AC-006 | Unit（記憶體）＋Unit（SQL，測試資料庫） | `backend/tests/unit/test_reliability.py` |
| R-003 | AC-007 | Unit（API＋記憶體佇列） | 同上 |
| R-005 | AC-004 | BDD（S18-04）：第一個 Worker 在送出後中止，第二個 Worker 以相同 repository 啟動 | `test_s18_reliability.py` |
| R-005 | AC-008 | Unit | `test_reliability.py` |
| R-006 | AC-005 | BDD（S18-05）：可控時鐘、`FakeProvider(never → succeed)` | `test_s18_reliability.py` |
| R-006 | AC-009 | Unit | `test_reliability.py` |

- 共用：`tests/reliability_support.py`（以 S08 的 `ApiEnv` 為基礎，加上可替換的供應商與可計數的儲存）。
- 預計單元測試約 14 個（下限 2）：`test_r004_update_if_*`（記憶體、SQL）、`test_r004_complete_job_*`、`test_r003_webhook_*`、`test_r005_recover_*`、`test_r006_fallback_*`。
- 回歸：S06、S07、S08、S12 的測試應不受影響（`_transition` 改為條件更新，單一來源時行為相同）。

## ADR（影響公開 API、資料遷移、成本、外部供應商或安全性時必填）

- 決定：以工作狀態的條件更新（樂觀並行控制）確保結果只處理一次；webhook 只觸發 Worker 立即查詢，不採用通知內容；Worker 啟動時掃描並接續進行中的工作；保底成品由 API 依門檻提供網址。
- 替代方案：(a) Redis 分散式鎖；(b) webhook 直接在 API 行程轉存；(c) 以 Redis pub/sub 喚醒正在輪詢的協程；(d) 成本帳加唯一索引。
- 取捨：條件更新不需額外基礎設施，且 PostgreSQL 保證原子性；(a) 鎖過期與釋放難以測試；(b) 大檔下載會拖慢 API；(c) 需要跨行程訂閱與狀態管理，收益只是省掉一次輪詢查詢；(d) 需要遷移，且條件更新已保證只有一方記帳。代價是所有工作狀態寫入都多一個 `WHERE status` 條件，競爭失敗時需要重新讀取。
