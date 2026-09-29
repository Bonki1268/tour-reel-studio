# 核准與失效：設計

> 對應規格：spec.md（版本 v1）。本檔由 Claude Code 撰寫，隨規格核准一併審閱。

## 設計概要

單一模組 `backend/app/domain/approval.py`，只依賴 S02 的 `app/domain/video.py`：

```python
class ApprovalKind(StrEnum):
    PLAN = "plan"; FINAL = "final"; SCRIPT = "script"; ASSETS = "assets"; KEYFRAMES = "keyframes"

USER_ONLY_KINDS = frozenset({ApprovalKind.PLAN, ApprovalKind.FINAL})   # 不可自動核准

@dataclass(frozen=True)
class Approval:
    kind: ApprovalKind
    input_hash: str
    cost_cap: Decimal | None
    auto_approved: bool
    approved_by: str | None
    approved_at: datetime
    # __post_init__ 驗證 R-006、R-005

class ApprovalError(ValueError): ...          # 核准紀錄本身不合法（R-005、R-006）
class ApprovalInvalidated(Exception):         # 核准後內容被修改（R-004）
    kind: ApprovalKind; approved_hash: str; current_hash: str

def canonical_hash(obj: object) -> str
def plan_approval_input(plan: Mapping[str, object], placements: Sequence[Mapping[str, object]]) -> dict[str, object]
def approve_plan(video: Video, plan, placements, cost_cap: Decimal, approved_by: str) -> Approval
def auto_approve(kind: ApprovalKind, content: object, *, clock=utc_now) -> Approval
def ensure_still_approved(approval: Approval, current_input: object) -> None
def check_before_submit(video: Video, approval: Approval, current_input: object) -> None
```

### `canonical_hash`

1. 先正規化：
   - `dict`：鍵必須是字串，否則 `TypeError`；值遞迴正規化
   - `list`、`tuple`：保持順序，遞迴正規化
   - `float`：NaN／Infinity 拋出 `ValueError`；以 `Decimal(repr(v)).quantize(0.0001, ROUND_HALF_UP)` 四捨五入到 4 位（實作時修訂：內建 `round()` 對 0.12345 這類二進位無法精確表示的值結果不直觀），結果為整數時轉 `int`；`-0.0` 視為 `0`
   - `bool`、`int`、`str`、`None`：原樣
   - `Decimal`：轉為去掉尾端 0 的字串（例如 `Decimal("1.280")` → `"1.28"`）
   - 其他型別：`TypeError`（避免 `str()` 隱含不穩定的表示）
2. `json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)`
3. UTF-8 編碼後取 SHA-256 十六進位小寫

### 企劃核准的輸入

```python
plan_approval_input(plan, placements) == {
    "plan": plan,                                       # 選定企劃的完整內容
    "placements": sorted(placements, key=shot_no),      # 每鏡 {shot_no, x, y, scale, flip}
}
```

擺放依 `shot_no` 排序，所以傳入順序不影響雜湊；但企劃內鏡頭串列的順序仍有意義。

### 流程

- `approve_plan`：先建立並驗證 `Approval`，再 `video.apply(APPROVE_PLAN)`；狀態轉換失敗時拋出 `InvalidTransition`，不回傳核准紀錄。
- `check_before_submit`：呼叫 `ensure_still_approved`；失敗時 `video.apply(APPROVAL_INVALIDATED)` 後重新拋出 `ApprovalInvalidated`。S06 在送出每個生成工作前呼叫它。

## 資料模型／狀態轉換變更

- 新增 `Approval` 值物件，欄位對應架構書 §7 的 `approvals` 表（`id`、`video_id` 由 S05 持久化時加入）。
- 使用 S02 已有的轉換：`plan_ready --approve_plan--> generating`、`generating --approval_invalidated--> plan_ready`，不修改轉換表。

## API 契約（request／response、錯誤碼）

本步驟沒有 HTTP API。S08 把 `ApprovalInvalidated` 對應為 HTTP 409，`ApprovalError` 對應為 422。

## 失敗行為、安全與可觀測性

- `ApprovalInvalidated` 的訊息包含核准類型與兩個雜湊的前 12 字元，方便比對日誌，不包含企劃內容。
- 核准紀錄是不可變的（frozen dataclass）；失效時不修改舊紀錄。

## 測試策略

| 需求 | 驗收條件 | 測試層級 | 測試位置 |
|---|---|---|---|
| R-001 | AC-001 | BDD（S03-01）＋Unit | `backend/tests/bdd/test_s03_approval.py`、`backend/tests/unit/test_approval.py` |
| R-002 | AC-002、AC-003 | BDD（S03-02）＋Unit | 同上 |
| R-003 | AC-004 | BDD（S03-03） | 同上 |
| R-004 | AC-005 | BDD（S03-04）＋Unit | 同上 |
| R-005 | AC-006 | BDD（S03-05）＋Unit | 同上 |
| R-006 | AC-007 | Unit | 同上 |

BDD 的共用資料：企劃 P1 為含 3 鏡的 dict，擺放為 3 筆 `{shot_no, x, y, scale, flip}`；「第 2 鏡的角色擺放被修改」＝把第 2 鏡的 `x` 改為另一個值。

預計單元測試（≥ 3，預計 10）：
- `test_r002_hash_ignores_key_order`（巢狀字典）
- `test_r002_hash_depends_on_list_order`
- `test_r002_float_rounded_to_4_places`
- `test_r002_int_and_integral_float_equal`
- `test_r002_rejects_nan_and_unsupported_types`
- `test_r001_placement_order_does_not_matter`
- `test_r004_rejected_submit_returns_video_to_plan_ready`（`ensure_still_approved` 與 `check_before_submit` 的差異）
- `test_r005_plan_and_final_cannot_be_auto_approved`
- `test_r006_cost_cap_must_be_positive`
- `test_r006_unknown_kind_and_missing_approver_rejected`

## ADR（影響公開 API、資料遷移、成本、外部供應商或安全性時必填）

- 決定：以自訂正規化＋`json.dumps(sort_keys=True)`＋SHA-256 計算輸入雜湊，浮點數固定到小數 4 位。
- 替代方案：(a) 直接對 `json.dumps(sort_keys=True)` 雜湊；(b) 使用 RFC 8785（JCS）函式庫。
- 取捨：(a) 對浮點數的微小差異（例如拖曳後 0.30000000000000004）過度敏感，會造成誤判失效；(b) 標準化程度高但多一個依賴，且仍需自行處理精度。自訂正規化的規則少且可以完整測試。
