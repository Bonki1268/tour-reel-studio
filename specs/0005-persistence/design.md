# 資料持久化：設計

> 對應規格：spec.md（版本 v1）。本檔由 Claude Code 撰寫，隨規格核准一併審閱。

## 設計概要

```
infra/docker-compose.test.yml     postgres:16、redis:7（healthcheck，供 --wait 使用；S3 相容儲存留到 S09，spec 待決事項 8）
backend/
├─ alembic.ini
├─ alembic/env.py、alembic/versions/0001_initial.py
└─ app/
   ├─ domain/
   │  ├─ ports.py          repository 介面（Protocol）＋領域資料類別（Project、BrandProfile、Shot、ShotTake、GenerationJob）
   │  └─ ids.py            idempotency_key()、new_id()
   └─ storage/
      ├─ db.py             create_engine(settings)、session factory
      ├─ models.py         SQLAlchemy ORM（14 張資料表）
      ├─ sql_repos.py      資料庫版 repository
      └─ memory_repos.py   記憶體版 repository
```

新增依賴：`sqlalchemy[asyncio]`、`alembic`、`psycopg[binary]`。

### Repository 介面（`app/domain/ports.py`，全部 async）

```python
class ProjectRepository(Protocol):
    async def add(self, project: Project, brand: BrandProfile) -> None
    async def get(self, project_id: str) -> tuple[Project, BrandProfile] | None

class VideoRepository(Protocol):
    async def add(self, video: VideoRecord) -> None
    async def get(self, video_id: str) -> VideoRecord | None
    async def save(self, video: VideoRecord) -> None      # 狀態、狀態歷程、時間軸、成本上限

class ShotRepository(Protocol):
    async def add_shot(self, shot: Shot) -> None
    async def add_take(self, shot_id: str) -> ShotTake      # attempt = 既有最大值 + 1，並設為目前版本
    async def takes(self, shot_id: str) -> list[ShotTake]   # 依 attempt 排序
    async def get_shot(self, shot_id: str) -> Shot | None

class GenerationJobRepository(Protocol):
    async def create_or_get(self, job: GenerationJob) -> tuple[GenerationJob, bool]   # bool：是否新建
    async def get(self, job_id: str) -> GenerationJob | None

class ApprovalRepository(Protocol):
    async def add(self, video_id: str, approval: Approval) -> None
    async def list(self, video_id: str) -> list[Approval]

class CostEntryRepository(Protocol):
    async def add(self, video_id: str, entry: CostEntry) -> None
    async def list(self, video_id: str) -> list[CostEntry]
```

- `VideoRecord` 包裝 S02 的 `Video`（狀態＋歷程）與 §7 的其他欄位（project_id、mode、topic、selected_plan_id、cost_cap、timeline）。
- `GenerationJobRepository.create_or_get` 在資料庫版以 `INSERT … ON CONFLICT (idempotency_key) DO NOTHING RETURNING` 後再查詢，並行呼叫也只會有一筆。
- `ShotRepository.add_take` 在同一個交易中鎖定鏡頭列（`SELECT … FOR UPDATE`）後計算下一個 attempt，避免並行重生產生相同 attempt；`shot_takes` 另設 `(shot_id, attempt)` 唯一索引。

### 冪等鍵（`app/domain/ids.py`）

```python
def idempotency_key(video_id: str, shot_no: int, kind: str, input_hash: str, attempt: int) -> str
    # "v1:1:keyframe:abc:1"；空字串、含 ":"、shot_no／attempt < 1 → ValueError
```

### 資料表（`app/storage/models.py`）

依架構書 §7 的 14 張資料表與欄位，另外：
- `videos.status_history`：JSONB，`[{event, from_status, to_status, at}]`（spec 待決事項 2）
- `generation_jobs.idempotency_key`：唯一索引（spec 待決事項 3）
- `shot_takes`：`(shot_id, attempt)` 唯一索引
- JSON 欄位一律 JSONB；點數欄位（`cost_cap`、`est_cost`、`actual_cost`、`credits`）為 `NUMERIC(12, 4)`
- 主鍵為 UUID 字串（`String(36)`），由 `new_id()` 產生（spec 待決事項 4）
- `shots.current_take_id` 與 `shot_takes.shot_id` 互相參照：`current_take_id` 以 `use_alter=True` 建立外鍵

### 設定

`app/config.py` 新增 `database_url: str = "postgresql+psycopg://trs:trs@localhost:55432/trs"`（與 `infra/docker-compose.test.yml` 的測試資料庫一致；不含真實密碼）。`.env.example` 同步加入 `DATABASE_URL`。

## 資料模型／狀態轉換變更

- 新增架構書 §7 的全部資料表（遷移 `0001_initial`）。
- 不修改 S02～S04 的領域物件；ORM 與領域物件之間的轉換集中在 `sql_repos.py`。

## API 契約（request／response、錯誤碼）

本步驟沒有 HTTP API。

## 失敗行為、安全與可觀測性

- 資料庫連不上時，repository 呼叫拋出 SQLAlchemy 的連線錯誤，不在本步驟包裝（S08 對應為 503）。
- 測試用的資料庫帳密只存在 `infra/docker-compose.test.yml` 與預設的開發連線字串，僅限本機測試容器使用。
- 冪等衝突不是錯誤：`create_or_get` 回傳既有工作與 `created=False`，由呼叫端（S06）決定是否記錄。

## 測試策略

| 需求 | 驗收條件 | 測試層級 | 測試位置 |
|---|---|---|---|
| R-001 | AC-001 | BDD（S05-01，integration） | `backend/tests/bdd/test_s05_persistence.py` |
| R-002 | AC-002 | BDD（S05-02）＋參數化 repo 測試 | 同上、`backend/tests/unit/test_repositories.py` |
| R-003 | AC-003 | BDD（S05-03）＋參數化 repo 測試 | 同上 |
| R-004 | AC-004、AC-005 | BDD（S05-04）＋Unit | 同上、`backend/tests/unit/test_ids.py` |
| R-005 | AC-006 | BDD（S05-05）＋參數化 repo 測試 | 同上 |
| R-006 | AC-007 | 參數化 repo 測試（memory／sql） | `backend/tests/unit/test_repositories.py` |
| R-007 | AC-008 | 參數化 repo 測試 | 同上 |

- 參數化 fixture `repos`：`memory` 參數不需要資料庫；`sql` 參數加上 `pytest.mark.integration`，連到 compose 的 PostgreSQL。
- 整合測試的資料庫隔離：session 範圍內執行一次 `alembic upgrade head`；每個測試結束時 `TRUNCATE … CASCADE` 所有資料表。S05-01 使用獨立的 schema（`search_path`）從零遷移與降版，不影響其他測試。
- `pytest-asyncio` 以 `asyncio_mode = "auto"` 執行 async 測試。
- 預計單元／參數化測試（≥ 2，預計 12，含 memory 與 sql 兩種參數）：
  - `test_r004_idempotency_key_format`、`test_r004_idempotency_key_rejects_invalid_parts`
  - `test_r002_project_and_brand_roundtrip[memory|sql]`
  - `test_r003_takes_are_kept[memory|sql]`
  - `test_r004_create_or_get_returns_existing[memory|sql]`
  - `test_r005_json_types_roundtrip[memory|sql]`（時間軸與擺放）
  - `test_r007_video_history_approvals_costs_roundtrip[memory|sql]`

## ADR（影響公開 API、資料遷移、成本、外部供應商或安全性時必填）

- 決定：SQLAlchemy 2.0 async＋psycopg 3；repository 介面為 async `Protocol`，另提供記憶體版。
- 替代方案：(a) 同步 SQLAlchemy，於 FastAPI 以執行緒池執行；(b) asyncpg 驅動。
- 取捨：API 與 Worker（arq）都是 async，同步存取會佔用執行緒池；asyncpg 無法讓 Alembic 以同一個驅動同步執行遷移，psycopg 3 同時支援同步與非同步。
- 決定：狀態歷程以 JSONB 欄位保存，不新增資料表。
- 替代方案：新增 `video_status_changes` 資料表。
- 取捨：MVP 只需要依影片讀回完整歷程，不需要跨影片查詢；JSONB 較簡單，日後需要查詢時再以遷移拆表。
