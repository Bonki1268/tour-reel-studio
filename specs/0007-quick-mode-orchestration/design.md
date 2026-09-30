# 快速模式工作編排：設計

> 對應規格：spec.md（版本 v1）。本檔由 Claude Code 撰寫，隨規格核准一併審閱。

## 設計概要

```
backend/app/
├─ creative/base.py      CreativeEngine、PlanContext、PlanDraft、ShotDraft、ShotPrompt
├─ creative/fake.py      FakeCreativeEngine（固定 3 個企劃，可設定失敗或企劃數）
├─ render/base.py        Renderer、RenderOutput
├─ render/fake.py        FakeRenderer（時間軸 JSON＋空白 mp4）
├─ jobs/events.py        ProgressEvent、EventPublisher、MemoryEventBus
├─ jobs/orchestrator.py  QuickModeOrchestrator
├─ jobs/generation.py    （S06）影片仍在 generating 時才套用 SHOT_FAILED_FINAL
├─ providers/fake.py     （S06）新增 duration_s、outcomes_by_shot
├─ domain/ports.py       Plan、Character、CharacterVersion、ScenePhoto、Render 與其 repository
└─ storage/memory_repos.py、sql_repos.py   新 repository 的兩種實作
```

### 創作引擎（`app/creative/base.py`，架構書 §5.4）

```python
@dataclass(frozen=True)
class PlanContext:
    brand: BrandProfile; topic: str; anchor_card: JSON; scene_photos: list[ScenePhoto]

@dataclass(frozen=True)
class ShotDraft:
    shot_no: int; role: str; duration_s: float; scene_photo_id: str
    placement: dict[str, float | bool]; action: str; subtitle: str; camera: str

@dataclass(frozen=True)
class PlanDraft:
    title: str; concept: str; tone: str; shots: list[ShotDraft]; cta: str

@dataclass(frozen=True)
class ShotPrompt:
    shot_no: int; keyframe_prompt: str; video_prompt: str

class CreativeEngine(Protocol):
    name: str
    async def propose_plans(self, ctx: PlanContext) -> list[PlanDraft]
    async def build_shot_prompts(self, plan: PlanDraft, ctx: PlanContext) -> list[ShotPrompt]
```

`FakeCreativeEngine(plan_count=3, fail=False)`：企劃依 tourism-promo 結構（hook 4 秒／feature 5 秒／cta 3 秒），場景依序使用傳入的實景照；記錄收到的 `PlanContext`。

### 合成器（`app/render/base.py`）

```python
class Renderer(Protocol):
    def build_timeline(self, video: VideoRecord, shots: list[tuple[Shot, ShotTake]]) -> dict[str, JSON]
    async def render(self, timeline: Mapping[str, JSON], storage: Storage, output_key: str) -> None
```

`FakeRenderer`：時間軸含每鏡 `shot_no`、`clip_key`、`start`、`end`、`subtitle`；`render` 寫入 0 位元組的 `video/mp4`。成品路徑依架構書 §7：`videos/{video_id}/renders/{render_id}.mp4`。

### 進度事件（`app/jobs/events.py`）

```python
@dataclass(frozen=True)
class ProgressEvent:
    type: str; video_id: str; at: datetime; shot_no: int | None = None; data: Mapping[str, JSON] = {}

class EventPublisher(Protocol):
    async def publish(self, event: ProgressEvent) -> None

class MemoryEventBus:   # events: list[ProgressEvent]
```

事件類型：`plan_ready`、`planning_failed`、`shot_started`、`shot_done`、`shot_failed`、`render_started`、`review_ready`、`needs_attention`、`approved`。

### 編排（`app/jobs/orchestrator.py`）

```python
@dataclass
class OrchestratorDeps:
    repos: Repositories; storage: Storage; engine: CreativeEngine; renderer: Renderer
    image_provider: ImageProvider; video_provider: VideoProvider; results: ResultSource
    events: EventPublisher; cost_table: CostTable; settings: Settings
    clock: Callable[[], datetime] = utc_now; sleep: Callable[[float], Awaitable[None]] = asyncio.sleep

class QuickModeOrchestrator:
    async def submit_topic(self, project_id: str, topic: str) -> VideoRecord
    async def estimate(self, video_id: str, plan_id: str) -> Estimate
    async def approve_plan(self, video_id: str, plan_id: str, cost_cap: Decimal, approved_by: str,
                           placements: Mapping[int, Mapping[str, JSON]] | None = None) -> Approval
    async def generate(self, video_id: str) -> None
    async def regenerate_shot(self, video_id: str, shot_no: int) -> None
    async def approve_final(self, video_id: str, approved_by: str) -> Approval
```

- `submit_topic`：建立影片（`mode=quick`）→ `SUBMIT_TOPIC` → `engine.propose_plans` → 保存企劃 → `PLANS_READY`；失敗 → `PLANNING_FAILED`。
- `approve_plan`：以所選企劃與（調整後的）擺放呼叫 S03 `approve_plan`，保存核准；建立 3 個 `Shot`（擺放、提示詞）與第 1 版；寫入 `script`、`assets` 自動核准。
- `generate`：`asyncio.gather` 平行執行每鏡 `_run_shot`；每鏡 `run_generation_job(keyframe)` → 自動核准 `keyframes` → `run_generation_job(video)`。全部 `STORED` → `ALL_SHOTS_DONE` → `_render`；否則發布 `needs_attention`。
- 各鏡共用同一個 `VideoRecord` 與 `Budget`（上限 = 核准的 `cost_cap`，已花費由成本帳載入）；核准比對內容 = 所選企劃＋各鏡目前的擺放。
- `_render`：`RENDER_DONE` 前發布 `render_started`，`build_timeline` → 保存時間軸 → `render` → 新增成品紀錄 → `RENDER_DONE` → `review_ready`。
- `regenerate_shot`：`REGENERATE_SHOT` → 該鏡 `add_take` → 只執行該鏡 → `ALL_SHOTS_DONE` → `_render`。
- `approve_final`：`APPROVE_FINAL`，寫入 `final` 使用者核准，輸入雜湊為最新成品的時間軸。

### 新增 repository（`app/domain/ports.py`）

```python
class PlanRepository:          add(plan: Plan)、list(video_id) -> list[Plan]、get(plan_id)
class CharacterRepository:     add(character, versions)、locked_version(project_id) -> CharacterVersion | None
class ScenePhotoRepository:    add(photo)、list(project_id) -> list[ScenePhoto]
class RenderRepository:        add(render: Render)、list(video_id) -> list[Render]
```

資料類別欄位與架構書 §7 的資料表一致；`Repositories` 新增 `plans`、`characters`、`scene_photos`、`renders`。

## 資料模型／狀態轉換變更

- 不新增資料表；使用 S05 已建立的 `plans`、`characters`、`character_versions`、`scene_photos`、`renders`。
- 實作時補上遷移 `0003_scene_photos_created_at`：`scene_photos` 原本沒有 `created_at`，資料庫版無法保證「依上傳順序列出」實景照（企劃依序使用實景照）。
- 實作時補上 `ShotRepository.list_shots(video_id)`（依 `shot_no` 排序），編排需要列出影片的所有鏡頭。
- 影片狀態轉換只使用 S02 既有事件。

## API 契約（request／response、錯誤碼）

本步驟沒有 HTTP API。例外：`InvalidTransition`（狀態不允許的操作，例如非 `review` 時重生）、`ApprovalInvalidated`、`BudgetExceeded`、`PlanningFailed`（包裝創作引擎錯誤；影片已進入 `failed`）。

## 失敗行為、安全與可觀測性

- 單鏡失敗以 S06 的工作狀態表示，不中斷其他鏡頭（`gather(return_exceptions=True)`；`BudgetExceeded`、`ApprovalInvalidated` 等例外在所有鏡頭結束後重新拋出第一個）。
- 事件的 `data` 只放狀態與路徑，不放供應商網址或金鑰。

## 測試策略

| 需求 | 驗收條件 | 測試層級 | 測試位置 |
|---|---|---|---|
| R-001 | AC-001、AC-002 | BDD（S07-01）＋Unit | `backend/tests/bdd/test_s07_orchestration.py`、`backend/tests/unit/test_orchestrator.py` |
| R-002、R-003 | AC-003 | BDD（S07-01） | 同上 |
| R-003 | AC-004 | BDD（S07-02，真實時間） | 同上 |
| R-004 | AC-005 | BDD（S07-03）＋Unit | 同上 |
| R-005 | AC-006、AC-007 | BDD（S07-04）＋Unit | 同上 |
| R-006 | AC-008 | BDD（S07-05）＋Unit | 同上 |
| R-007 | AC-009 | BDD（S07-06） | 同上 |
| R-008 | AC-010 | 參數化 repo 測試（memory／sql） | `backend/tests/unit/test_repositories_s07.py` |

- 環境：記憶體 repository、`MemoryStorage`、`FakeCreativeEngine`、`FakeProvider`、`FakeRenderer`、`MemoryEventBus`；除 S07-02 外使用假時鐘。
- 預計單元測試（≥ 2，預計約 12）：
  - `test_r004_event_has_type_video_id_shot_no_at`
  - `test_r001_engine_error_marks_failed`、`test_r001_wrong_plan_count_marks_failed`
  - `test_r002_approve_plan_creates_shots_with_adjusted_placement`
  - `test_r005_completed_shots_kept_on_partial_failure`、`test_r005_two_failed_shots_single_needs_attention`
  - `test_r006_regenerate_keeps_other_current_takes`、`test_r006_regenerate_requires_review`
  - `test_r008_plans_roundtrip[memory|sql]`、`test_r008_character_and_photos_roundtrip[memory|sql]`、`test_r008_renders_roundtrip[memory|sql]`

## ADR（影響公開 API、資料遷移、成本、外部供應商或安全性時必填）

- 決定：編排以 `asyncio.gather` 在同一個 Worker 程序內平行處理 3 鏡，而非每鏡一個佇列任務。
- 替代方案：每鏡關鍵幀、影片各為一個 arq 任務，以任務鏈串接。
- 取捨：MVP 每支影片只有 3 鏡，單程序平行即可滿足時間；工作狀態已逐步寫入資料庫（S06），Worker 重啟後以相同冪等鍵重跑 `generate` 即可接續，不會重複扣點。若之後需要跨機器擴充，再拆成任務鏈。
