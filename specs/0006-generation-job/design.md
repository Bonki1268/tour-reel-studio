# 生成工作與重試：設計

> 對應規格：spec.md（版本 v1）。本檔由 Claude Code 撰寫，隨規格核准一併審閱。

## 設計概要

```
backend/app/
├─ domain/
│  ├─ generation.py    JobStatus、轉換表、重試與逾時判斷（純邏輯）
│  ├─ ports.py         新增 Storage Protocol；GenerationJobRepository.update／get_by_key；ShotRepository.update_take
│  └─ cost.py          Budget.release(job_id)（新增）
├─ providers/
│  ├─ base.py          ImageProvider、VideoProvider、ProviderRequest、ProviderJob、ProviderResult、ProviderError
│  └─ fake.py          FakeProvider（腳本化行為＋呼叫紀錄）
├─ storage/
│  ├─ objects.py       MemoryStorage（Storage 的記憶體實作）
│  ├─ memory_repos.py、sql_repos.py   新增的 repository 方法
└─ jobs/
   └─ generation.py    run_generation_job(...)
```

### 領域：生成工作狀態（`app/domain/generation.py`）

```python
class JobStatus(StrEnum):
    QUEUED, SUBMITTED, RUNNING, SUCCEEDED, STORED, FAILED, FAILED_FINAL

TRANSITIONS = {
    QUEUED: {SUBMITTED, FAILED},   # 送出時供應商即拒絕 → FAILED（實作時補上）
    SUBMITTED: {RUNNING, SUCCEEDED, FAILED}, RUNNING: {SUCCEEDED, FAILED},
    SUCCEEDED: {STORED, FAILED}, FAILED: {FAILED_FINAL},
}
MAX_ATTEMPTS = 2

def advance(job: GenerationJob, to: JobStatus, *, error: str | None = None) -> None   # 不合法 → InvalidJobTransition
def should_retry(attempt: int, error: ProviderError | TimeoutError) -> bool            # attempt < 2 且可重試
def timed_out(submitted_at: datetime, now: datetime, timeout_s: float) -> bool
```

- 失敗的嘗試：`FAILED`；若 `should_retry` 為真 → 建立 `attempt + 1` 的新工作；否則該筆轉為 `FAILED_FINAL`。
- `GenerationJob` 新增 `submitted_at: datetime | None`（資料表同步新增欄位，遷移 `0002`）。

### 供應商介面（`app/providers/base.py`，架構書 §5.5）

```python
@dataclass(frozen=True)
class ProviderRequest:
    model: str; input: Mapping[str, JSON]; provider_idempotency_key: str

@dataclass(frozen=True)
class ProviderJob:
    provider: str; model: str; external_id: str; estimated_cost: Decimal | None

@dataclass(frozen=True)
class ProviderResult:
    state: Literal["running", "succeeded", "failed"]
    url: str | None = None; actual_cost: Decimal | None = None; error: ProviderError | None = None

class ProviderError(Exception):
    retryable: bool

class ImageProvider(Protocol):
    async def compose(self, req: ProviderRequest) -> ProviderJob
class VideoProvider(Protocol):
    async def image_to_video(self, req: ProviderRequest) -> ProviderJob
class ResultSource(Protocol):
    async def fetch_result(self, job: ProviderJob) -> ProviderResult
    async def download(self, result: ProviderResult) -> tuple[bytes, str]   # 內容、content type
```

`FakeProvider` 同時實作以上三者，建構參數：
`outcomes: list["succeed" | "fail" | "fail_non_retryable" | "never"]`（依送出次數取用，最後一項重複）、`running_polls: int`（成功前回報 running 的次數）、`actual_cost`、`content`；並記錄 `submissions: list[ProviderRequest]`、`fetches: list[str]`。

### 工作執行（`app/jobs/generation.py`）

```python
@dataclass
class GenerationContext:
    repos: Repositories; storage: Storage
    image_provider: ImageProvider; video_provider: VideoProvider; results: ResultSource
    budget: Budget; cost_table: CostTable; settings: Settings
    clock: Callable[[], datetime] = utc_now; sleep: Callable[[float], Awaitable[None]] = asyncio.sleep

@dataclass(frozen=True)
class JobSpec:
    video: VideoRecord; shot: Shot; take: ShotTake; kind: JobKind
    approval: Approval; approved_input: object; input_snapshot: Mapping[str, JSON]

async def run_generation_job(ctx: GenerationContext, spec: JobSpec) -> GenerationJob   # 回傳最後一次嘗試
```

流程（每次嘗試）：
1. `create_or_get`（冪等鍵 = `idempotency_key(video, shot_no, kind, canonical_hash(input_snapshot), attempt)`）。既有且 `STORED` → 直接回傳；既有且有 `external_id` → 跳到第 5 步。
2. `check_before_submit(video, approval, approved_input)` → 失效時記錄錯誤、保存影片並重新拋出。
3. `budget.check(job.id, 單價表預估)` → 超出時記錄錯誤並重新拋出。
4. 送出（keyframe → `compose`，video → `image_to_video`）；記錄 `external_id`、`submitted_at` → `SUBMITTED`。
5. 輪詢 `fetch_result`，間隔 `GENERATION_POLL_INTERVAL_S`；`running` → `RUNNING`；超過 `GENERATION_TIMEOUT_S` → 逾時失敗。
6. `succeeded` → `SUCCEEDED` → `download` → `storage.put(§7 路徑)` → `update_take` → `STORED` → `budget.record` → 成本帳新增。
7. 失敗 → `FAILED` → `budget.release(job.id)` → 可重試則下一個 attempt，否則 `FAILED_FINAL` 並對影片套用 `SHOT_FAILED_FINAL`、保存影片。

冪等鍵中的 `input_hash` 為 `canonical_hash({"shot_take_attempt": 鏡頭版本, "input": input_snapshot})`（spec 待決事項 2）。`GenerationContext.provider_name`（預設 `higgsfield`）為送出前的供應商名稱，送出後以 `ProviderJob.provider` 為準。

每一次狀態變更都呼叫 `repos.jobs.update(job)`（R-008）。狀態轉換同時附加到 `job_events: list[tuple[str, JobStatus]]`（供測試與 S08 的 SSE 使用）。

### 設定（`app/config.py`）

`generation_timeout_s: float = 600`、`generation_poll_interval_s: float = 5`（皆 `> 0`）；`.env.example` 同步。

## 資料模型／狀態轉換變更

- 遷移 `0002_generation_job_submitted_at`：`generation_jobs.submitted_at`（timestamptz，可為空）。
- 新增 `JobStatus` 轉換表（上方）。影片狀態只使用 S02 既有的 `SHOT_FAILED_FINAL`、`APPROVAL_INVALIDATED` 事件。

## API 契約（request／response、錯誤碼）

本步驟沒有 HTTP API。`run_generation_job` 對呼叫端拋出的例外：`ApprovalInvalidated`（S03）、`BudgetExceeded`（S04）；其餘失敗以工作狀態 `FAILED_FINAL` 表示，不拋出。

## 失敗行為、安全與可觀測性

- 供應商例外中只保留錯誤類型與訊息，結果網址的查詢參數（可能含簽章）不寫入 `error` 欄位或日誌。
- 逾時後不取消供應商請求（spec 待決事項 8）。
- 下載或轉存失敗視為可重試的失敗。

## 測試策略

| 需求 | 驗收條件 | 測試層級 | 測試位置 |
|---|---|---|---|
| R-001 | AC-001 | BDD（S06-01） | `backend/tests/bdd/test_s06_generation_job.py` |
| R-002 | AC-002 | BDD（S06-02）＋Unit | 同上、`backend/tests/unit/test_generation.py` |
| R-003 | AC-003、AC-004 | BDD（S06-03）＋Unit | 同上 |
| R-004 | AC-005 | BDD（S06-04）＋Unit | 同上 |
| R-005 | AC-006、AC-007 | BDD（S06-05）＋Unit | 同上 |
| R-006 | AC-008 | BDD（S06-06） | 同上 |
| R-007 | AC-009、AC-010 | Unit | `backend/tests/unit/test_generation.py` |
| R-008 | AC-011 | 參數化 repo 測試（memory／sql） | `backend/tests/unit/test_repositories.py`（S06 標記的新測試） |

- 場景與大部分單元測試使用記憶體版 repository、`MemoryStorage`、`FakeProvider`，不需要 Docker。
- 時間：`FakeClock`（`sleep` 只推進時鐘），S06-04 的 1 秒逾時不實際等待。
- 預計單元測試（≥ 3，預計約 16）：
  - 領域：`test_r002_max_two_attempts`、`test_r003_non_retryable_not_retried`、`test_r004_timeout_counts_from_submitted`、`test_r001_invalid_job_transition_rejected`
  - 執行：`test_r003_non_retryable_goes_failed_final`、`test_r004_queue_time_not_counted`、`test_r005_resume_existing_external_id`、`test_r005_different_input_hash_is_new_job`、`test_r007_budget_exceeded_no_submit`、`test_r007_retry_blocked_by_budget`、`test_r007_records_provider_cost_once`、`test_r007_records_table_cost_when_unreported`、`test_r007_failed_attempt_releases_reservation`
  - repository：`test_r008_job_update_roundtrip[memory|sql]`、`test_r008_take_update_roundtrip[memory|sql]`

## ADR（影響公開 API、資料遷移、成本、外部供應商或安全性時必填）

- 決定：每次嘗試是一筆 `generation_jobs` 紀錄（spec 待決事項 1）。
- 替代方案：同一筆紀錄內重試，更新 `attempt` 與 `provider_idempotency_key`。
- 取捨：分筆可保留每次送出的 `external_id`、錯誤與成本以便對帳，且與 S05 的冪等鍵唯一索引一致；代價是查詢「某鏡目前狀態」要取最大 attempt。
- 決定：可注入時鐘與 `sleep`，不使用真實等待。
- 取捨：測試快速且可重現；正式環境使用 `asyncio.sleep` 與 UTC 時鐘。
