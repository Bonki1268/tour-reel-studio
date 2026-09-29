# 影片狀態機：設計

> 對應規格：spec.md（版本 v1）。本檔由 Claude Code 撰寫，隨規格核准一併審閱。

## 設計概要

單一模組 `backend/app/domain/video.py`，不依賴資料庫或框架：

```python
class VideoStatus(StrEnum):
    DRAFT = "draft"; PLANNING = "planning"; PLAN_READY = "plan_ready"
    GENERATING = "generating"; NEEDS_ATTENTION = "needs_attention"
    RENDERING = "rendering"; REVIEW = "review"; APPROVED = "approved"; FAILED = "failed"

class VideoEvent(StrEnum):
    SUBMIT_TOPIC = "submit_topic"; PLANS_READY = "plans_ready"; PLANNING_FAILED = "planning_failed"
    REGENERATE_PLANS = "regenerate_plans"; APPROVE_PLAN = "approve_plan"
    ALL_SHOTS_DONE = "all_shots_done"; SHOT_FAILED_FINAL = "shot_failed_final"
    APPROVAL_INVALIDATED = "approval_invalidated"
    CONFIRM_REGENERATE = "confirm_regenerate"; CONFIRM_RERENDER = "confirm_rerender"
    RENDER_DONE = "render_done"; RENDER_RETRY = "render_retry"; RENDER_FAILED_FINAL = "render_failed_final"
    REGENERATE_SHOT = "regenerate_shot"; APPROVE_FINAL = "approve_final"

TRANSITIONS: Mapping[tuple[VideoStatus, VideoEvent], VideoStatus]   # 15 列，即 spec R-001 的表
TERMINAL: frozenset[VideoStatus] = frozenset({APPROVED, FAILED})

class InvalidTransition(Exception):
    status: VideoStatus
    event: VideoEvent

@dataclass(frozen=True)
class StatusChange:
    event: VideoEvent
    from_status: VideoStatus
    to_status: VideoStatus
    at: datetime                     # UTC、時區感知

@dataclass
class Video:
    status: VideoStatus = VideoStatus.DRAFT
    history: list[StatusChange] = field(default_factory=list)
    clock: Callable[[], datetime] = utc_now    # 可注入

    def apply(self, event: VideoEvent) -> VideoStatus: ...
    @property
    def status_trail(self) -> list[VideoStatus]: ...   # 起始狀態＋每筆轉換後的狀態
```

- `apply` 以 `TRANSITIONS.get((status, event))` 查表；查無結果時拋出 `InvalidTransition`，**先檢查再修改**，所以失敗時狀態與歷程都不變。
- `status_trail` 的起始狀態取自第一筆紀錄的 `from_status`；沒有紀錄時為目前狀態。S02-04 以它驗證「draft → planning → plan_ready」。
- `TRANSITIONS` 以 `MappingProxyType` 包裝，避免被其他模組修改。

## 資料模型／狀態轉換變更

新增影片狀態機（spec R-001 的轉換表）。S05 持久化時，`status` 存為字串欄位、`history` 存為 `video_status_changes` 資料表或 JSON 欄位，由 S05 規格決定。

## API 契約（request／response、錯誤碼）

本步驟沒有 HTTP API。S08 會把 `InvalidTransition` 對應為 HTTP 409。

## 失敗行為、安全與可觀測性

- `InvalidTransition` 的訊息列出目前狀態與事件名稱，例如：`影片狀態 generating 不接受事件 approve_plan`。
- 不合法的轉換不留下歷程紀錄；是否另外記錄被拒絕的嘗試留給 S08（API 層日誌）。

## 測試策略

| 需求 | 驗收條件 | 測試層級 | 測試位置 |
|---|---|---|---|
| R-001 | AC-001 | BDD（S02-01，11 列）＋Unit（其餘 4 列） | `backend/tests/bdd/test_s02_video_state.py`、`backend/tests/unit/test_video.py` |
| R-002 | AC-002、AC-003 | BDD（S02-02）＋Unit（窮舉） | 同上 |
| R-003 | AC-004 | BDD（S02-03）＋Unit | 同上 |
| R-004 | AC-005 | BDD（S02-04）＋Unit | 同上 |

預計單元測試（≥ 3，預計 7）：
- `test_r001_transition_table_matches_spec`：`TRANSITIONS` 與 spec 的 15 列完全相同（不多不少）
- `test_r001_extra_transitions`：參數化驗證場景沒有的 4 列
- `test_r002_all_undefined_pairs_rejected`：窮舉 9 × 15 組合，不在表中的都拋出錯誤，且狀態與歷程不變
- `test_r003_terminal_states_have_no_exit`
- `test_r003_every_non_terminal_state_has_exit`
- `test_r004_history_records_event_and_time`：注入固定遞增的時鐘，檢查事件名稱、前後狀態與時間
- `test_r004_rejected_event_leaves_no_history`

BDD 的 `Given 一支狀態為 "<from>" 的影片` 直接以 `Video(status=...)` 建立，不經過前面的轉換。

## ADR（影響公開 API、資料遷移、成本、外部供應商或安全性時必填）

- 決定：在 S02 就加入 `generating --approval_invalidated--> plan_ready`（使用者於 2026-09-30 選擇 spec 待決事項 1 的 A）。
- 替代方案：S02 嚴格照架構書 §6.1 的圖，由 S03 再擴充轉換表。
- 取捨：S02 就加入可以讓狀態機一次完整、之後步驟不必回頭改；缺點是 S02 的行為超出 §6.1 的圖，架構書需要同步更新。
