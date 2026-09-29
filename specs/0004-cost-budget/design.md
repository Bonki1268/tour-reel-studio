# 成本估算與預算控制：設計

> 對應規格：spec.md（版本 v1）。本檔由 Claude Code 撰寫，隨規格核准一併審閱。
> 點數以 `Decimal` 表示（spec 待決事項 1，使用者於 2026-09-30 決定）。

## 設計概要

單一模組 `backend/app/domain/cost.py`：

```python
class JobKind(StrEnum):
    KEYFRAME = "keyframe"
    VIDEO = "video"

class CostTableError(ValueError): ...

@dataclass(frozen=True)
class CostTable:
    prices: Mapping[tuple[JobKind, str], Decimal]      # (種類, 模型) → 點數
    @classmethod
    def load(cls, path: Path) -> "CostTable"            # 檔案錯誤 → CostTableError
    @classmethod
    def from_rows(cls, rows: Iterable[Mapping[str, object]]) -> "CostTable"
    def price(self, kind: JobKind, model: str) -> Decimal   # 缺少 → CostTableError（訊息含模型名稱）

@dataclass(frozen=True)
class Estimate:
    total: Decimal          # 本次生成預估
    reserve: Decimal        # 已預留的單鏡重生額度
    cap: Decimal            # 最高成本上限 = total + reserve

def estimate_video(table, shot_count: int, image_model: str, video_model: str,
                   reserve_shots: int = 1) -> Estimate

class BudgetExceeded(Exception):
    requires_reconfirmation = True          # 訊息：「超出預算上限」
    cap: Decimal; committed: Decimal; requested: Decimal

@dataclass(frozen=True)
class CostEntry:
    job_id: str
    credits: Decimal
    source: Literal["provider", "table"]

@dataclass
class Budget:
    cap: Decimal
    entries: list[CostEntry]
    reserved: dict[str, Decimal]            # job_id → 預估（已通過檢查、尚未記帳）
    @property
    def spent(self) -> Decimal
    def check(self, job_id: str, estimate: Decimal) -> None     # 通過即計入 reserved；否則 BudgetExceeded
    def record(self, job_id: str, kind: JobKind, model: str,
               actual: Decimal | None, table: CostTable) -> CostEntry | None   # 重複 → None
```

- 開發計畫的 `Budget.check(next_cost)` 加上 `job_id`，才能追蹤預留並在記帳時釋放（spec 待決事項 4）。
- 成本帳（開發計畫的 `CostLedger`）就是 `Budget.entries`；S05 持久化時對應 `cost_entries` 表。
- 單鏡完整重生成本＝該鏡關鍵幀單價＋影片單價。MVP 每鏡使用相同模型，因此「最大值」等於任一鏡；函式仍以最大值計算，保留日後每鏡不同模型的可能。

### 單價表檔案格式（`COST_TABLE`）

```json
{
  "unit": "credits",
  "prices": [
    {"kind": "keyframe", "model": "xai/grok-imagine-image-2.0", "credits": "1.28"},
    {"kind": "video", "model": "bytedance/seedance-2.5/image-to-video", "credits": "0"}
  ]
}
```

- 以 `json.loads(..., parse_float=Decimal)` 讀取；`credits` 可以是字串或數字，一律轉為 `Decimal`。
- 錯誤：檔案不存在、非 JSON、缺少 `prices` 或欄位、未知 `kind`、負數或非數字 `credits`、重複的（種類、模型）→ `CostTableError`，訊息包含檔案路徑與原因。

### 設定

- `app/config.py`：新增 `retry_reserve_shots: int = 1`（環境變數 `RETRY_RESERVE_SHOTS`，必須 ≥ 0），移除 `retry_reserve_ratio`；`.env.example` 同步更新（spec 待決事項 3）。
- 新增 `config/cost_table.example.json`（影片單價為佔位值，需使用者自行填入）。

## 資料模型／狀態轉換變更

- 新增 `CostEntry`（對應架構書 §7 的 `cost_entries`，`video_id`、`created_at` 由 S05 加入）。
- 不修改影片狀態機（spec 待決事項 2）。

## API 契約（request／response、錯誤碼）

本步驟沒有 HTTP API。S08 回應中的 `cost_cap` 與 `spent` 來自 `Budget`。

## 失敗行為、安全與可觀測性

- `BudgetExceeded` 訊息固定以「超出預算上限」開頭，後面附上限、已承諾（已花費＋預留）與此工作預估。
- 拒絕時不改變 `entries` 與 `reserved`。
- 實際成本超過預估時照實記帳（spec 待決事項 6）。

## 測試策略

| 需求 | 驗收條件 | 測試層級 | 測試位置 |
|---|---|---|---|
| R-001 | AC-001 | BDD（S04-01）＋Unit | `backend/tests/bdd/test_s04_cost.py`、`backend/tests/unit/test_cost.py` |
| R-002 | AC-002、AC-003 | BDD（S04-02）＋Unit | 同上 |
| R-003 | AC-004 | BDD（S04-03）＋Unit | 同上 |
| R-004 | AC-005 | BDD（S04-04）＋Unit | 同上 |
| R-005 | AC-006 | BDD（S04-05） | 同上 |
| R-006 | AC-007 | BDD（S04-06）＋Unit | 同上、`tmp_path` 寫入錯誤的單價表檔案 |

BDD 的 Background 以 `CostTable.from_rows` 建立單價表；「已花費 N 點」以一筆來源為單價表的既有紀錄表示。

預計單元測試（≥ 3，預計 9）：
- `test_r001_zero_shots_costs_nothing`
- `test_r001_reserve_shots_configurable`（預留 0 鏡與 2 鏡）
- `test_r002_exactly_at_cap_allowed`
- `test_r002_parallel_jobs_count_reservations`
- `test_r003_one_over_cap_rejected_without_side_effects`
- `test_r004_actual_cost_replaces_estimate`（實際 28、預估 30，已花費以 28 計；預留釋放）
- `test_r004_same_job_recorded_once`
- `test_r006_invalid_cost_table_files`（參數化：不存在、非 JSON、缺欄位、未知種類、負數、重複）
- `test_r006_load_cost_table_file`（正確檔案可載入，含小數單價 1.28）

## ADR（影響公開 API、資料遷移、成本、外部供應商或安全性時必填）

- 決定：預算檢查把「已通過檢查、尚未記帳」的工作預估計入預留（spec 待決事項 4，使用者於 2026-09-30 同意）。
- 替代方案：照 §6.4 字面，只比較「已花費＋此工作預估」。
- 取捨：只看已花費在 3 鏡平行送出時會同時通過，合計可能超出使用者核准的上限，違反「花錢一定要使用者同意」。預留多一個欄位與釋放時機，但能保證承諾金額永不超過上限（除了實際扣點高於預估的情況）。
