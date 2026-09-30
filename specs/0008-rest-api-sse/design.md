# REST API 與 SSE：設計

> 對應規格：spec.md（版本 v1）。本檔由 Claude Code 撰寫，隨規格核准一併審閱。

## 設計概要

```
backend/app/
├─ api/
│  ├─ main.py          create_app(settings, services=None)：掛載路由、例外處理
│  ├─ services.py      AppServices：repos、storage、queue、events、orchestrator、idempotency（依設定建立）
│  ├─ schemas.py       Pydantic request／response
│  ├─ errors.py        例外 → HTTP 狀態碼與錯誤內容
│  ├─ idempotency.py   Idempotency-Key 處理
│  └─ routes/{projects,videos,events}.py
├─ jobs/
│  ├─ queue.py         JobQueue、MemoryJobQueue、ArqJobQueue
│  ├─ worker.py        arq WorkerSettings 與工作函式（plan_video、generate_video、regenerate_plans、regenerate_shot）
│  ├─ events.py        （S07）MemoryEventBus 新增 subscribe；新增 RedisEventBus
│  └─ orchestrator.py  （S07）create_video、propose_plans、regenerate_plans
├─ storage/objects.py  MemoryStorage.presign_get
└─ domain/ports.py     Storage.presign_get；IdempotencyRecord 與 IdempotencyRepository
```

新增依賴：`arq`、`redis`（arq 已依賴）、`sse-starlette` 不使用（以 `StreamingResponse` 自行輸出 SSE 格式）。

實作時的調整：
- SSE 串流放在 `app/api/sse.py`（`format_sse`、`sse_stream`），端點與其他影片端點同在 `routes/videos.py`；依賴注入放在 `app/api/deps.py`（`Services`，未注入時第一次使用才依設定建立）。
- 核准者固定為 `DEMO_USER = "demo"`（MVP 單一 Demo 帳號）。
- S07 的 `KeyError` 改為 `NotFound(KeyError)`，既有呼叫端不受影響。
- Worker 工作遇到可預期的業務例外（核准失效、超出預算、企劃失敗、狀態不符）時發布 `job_failed` 事件後結束，不讓 arq 重試；其他例外照常拋出。
- 新增設定 `sse_keepalive_s`（預設 15 秒；測試使用較短的值）。

### 工作佇列（`app/jobs/queue.py`）

```python
class JobQueue(Protocol):
    async def enqueue(self, name: str, **kwargs: JSON) -> None

class MemoryJobQueue:   # jobs: list[tuple[str, dict]]；run_all(worker) 依序執行（測試用）
class ArqJobQueue:      # arq.create_pool(RedisSettings.from_dsn(settings.redis_url))
```

工作名稱：`plan_video(video_id)`、`generate_video(video_id)`、`regenerate_plans(video_id)`、`regenerate_shot(video_id, shot_no)`。工作函式在 `worker.py`，由 `AppServices.orchestrator` 執行；記憶體佇列與 arq 共用同一組函式。

### 事件（`app/jobs/events.py`）

```python
class EventSubscriber(Protocol):
    def subscribe(self, video_id: str) -> AsyncIterator[ProgressEvent]

class MemoryEventBus:   # publish 同時送到該影片的訂閱者佇列
class RedisEventBus:    # channel = f"video:{video_id}:events"；JSON 序列化
```

### 端點與回應（`app/api/schemas.py` 節錄）

| 端點 | 成功 | request | response |
|---|---|---|---|
| `GET /projects/{id}` | 200 | — | `{id, name, brand, character: {id, version, anchor_card}, scene_photos: [...]}` |
| `POST /projects/{id}/videos` | 201 | `{topic: str(1..200)}` | `VideoOut` |
| `GET /videos/{id}` | 200 | — | `VideoOut` |
| `POST /videos/{id}/plans/regenerate` | 202 | — | `VideoOut` |
| `POST /videos/{id}/approve-plan` | 202 | `{plan_id, cost_cap: Decimal>0, placements?: {shot_no: {x,y∈[0,1], scale>0, flip}}}`＋`Idempotency-Key` | `VideoOut` |
| `POST /videos/{id}/shots/{no}/regenerate` | 202 | — | `VideoOut` |
| `POST /videos/{id}/approve` | 200 | — | `VideoOut` |
| `GET /videos/{id}/download` | 200 | — | `{url, expires_at}` |
| `GET /videos/{id}/events` | 200 | — | `text/event-stream` |

`VideoOut`：`{id, project_id, status, topic, plans: [{id, payload, estimate: {total, reserve, cap}}], selected_plan_id, shots: [{shot_no, role, duration_s, placement, take: {attempt, status, keyframe_key, clip_key}}], cost_cap, spent, preview_url?}`。點數以字串輸出（Decimal 不經浮點數）。

### 錯誤（`app/api/errors.py`）

| 例外 | 狀態碼 | `code` |
|---|---|---|
| `InvalidTransition` | 409 | `invalid_state` |
| `ApprovalInvalidated` | 409 | `approval_invalidated` |
| `BudgetExceeded` | 409 | `budget_exceeded`（另含 `requires_reconfirmation: true`、`cap`、`committed`、`requested`） |
| `NotFound`（取代 S07 的 `KeyError`） | 404 | `not_found` |
| `RequestValidationError`、`IdempotencyConflict`、`CostCapTooLow` | 422 | `validation_error`、`idempotency_conflict`、`cost_cap_too_low` |

錯誤內容：`{"code": ..., "message": "<繁體中文說明>"}`。

`approve-plan` 在排入工作前先呼叫 `orchestrator.approve_plan`（同步、數十毫秒）；其他需要改變狀態的操作（重新產生企劃、重生單鏡）先在 API 以狀態機檢查事件是否合法，不合法立即 409，合法才排入 Worker。

### 冪等（`app/api/idempotency.py`）

- 資料表 `api_idempotency`（遷移 `0004`）：`key`（主鍵，與端點、影片 ID 組合）、`request_hash`、`status_code`、`body`（JSONB）、`created_at`。
- 流程：查詢 → 存在且雜湊相同 → 回傳保存的回應；雜湊不同 → 422；不存在 → 執行 → 保存回應（僅保存 2xx；失敗的請求可以用同鍵重試）。
- 並行的同鍵請求：以主鍵唯一性保證只有一個寫入成功；另一個回傳已保存的回應。
- repository：`IdempotencyRepository.get(key)`、`save(record) -> bool`（記憶體版與資料庫版）。

### SSE（`app/api/routes/events.py`）

```
event: status
data: {"type":"status","video_id":"…","status":"planning","at":"…"}

event: plan_ready
data: {"type":"plan_ready","video_id":"…","shot_no":null,"at":"…","data":{…}}

```

先訂閱再讀取目前狀態，避免兩者之間發生的事件遺失。每 15 秒送一個註解行（`: keep-alive`）。

### 設定

`redis_url: str = "redis://localhost:56379/0"`（對應測試 compose）、`presign_ttl_s: int = Field(900, gt=0, le=900)`；`.env.example` 同步。

## 資料模型／狀態轉換變更

- 遷移 `0004_api_idempotency`：新增 `api_idempotency` 資料表。
- 影片狀態轉換只使用 S02 既有事件。

## API 契約（request／response、錯誤碼）

見上方「端點與回應」與「錯誤」。

## 失敗行為、安全與可觀測性

- 例外處理器只輸出 `code` 與中文訊息；未預期的例外回應 500 `internal_error`，細節只寫入伺服器日誌。
- 預簽名網址不寫入日誌；有效期上限 15 分鐘由設定驗證。
- Worker 工作失敗（例外）時記錄錯誤並發布 `job_failed` 事件；影片狀態由編排決定。

## 測試策略

| 需求 | 驗收條件 | 測試層級 | 測試位置 |
|---|---|---|---|
| R-001 | AC-001、AC-002 | BDD（S08-01）＋Unit | `backend/tests/bdd/test_s08_api.py`、`backend/tests/unit/test_api.py` |
| R-003、R-004 | AC-003～AC-005 | BDD（S08-02、S08-03）＋Unit | 同上 |
| R-005 | AC-006、AC-007 | BDD（S08-04）＋Unit | 同上 |
| R-006 | AC-008、AC-009 | BDD（S08-05，真實 uvicorn）＋Unit | 同上、`backend/tests/unit/test_sse.py` |
| R-007 | AC-010 | BDD（S08-06） | 同上 |
| R-002、R-008 | AC-011、AC-012 | BDD（S08-07）＋Unit | 同上 |
| R-009 | AC-013 | 整合（Redis） | `backend/tests/unit/test_worker_integration.py` |

- 場景使用 `httpx.AsyncClient(transport=ASGITransport(app))`、記憶體 repository／儲存／佇列／事件匯流排、S07 的假實作；排隊的工作以 `MemoryJobQueue.run_all` 執行（Worker 同步化）。
- 預計單元測試（≥ 2，預計約 14）：
  - `test_r005_exception_mapping[InvalidTransition|ApprovalInvalidated|BudgetExceeded|NotFound]`
  - `test_r004_same_key_different_body_is_422`、`test_r004_missing_key_is_422`、`test_r004_failed_request_not_saved`
  - `test_r006_sse_format`、`test_r006_status_event_first`
  - `test_r001_topic_validation`、`test_r003_cost_cap_below_estimate_is_422`、`test_r003_placement_out_of_range_is_422`
  - `test_r008_regenerate_shot_enqueues`、`test_r008_approve_final`
  - `test_r009_idempotency_repo_roundtrip[memory|sql]`
  - `test_r009_arq_worker_runs_plan_job`（integration）、`test_r009_redis_event_bus_pubsub`（integration）

## ADR（影響公開 API、資料遷移、成本、外部供應商或安全性時必填）

- 決定：冪等鍵保存在 PostgreSQL（`api_idempotency`）。
- 替代方案：Redis（`SET NX` ＋ TTL）。
- 取捨：資料表與核准在同一個持久層，Redis 資料遺失不會導致重複扣點；代價是一個遷移與一張資料表。
- 決定：API 對狀態轉換先做同步檢查，再排入 Worker。
- 取捨：使用者立即得到 409，而不是排入後才在 Worker 失敗、只能從 SSE 得知。
