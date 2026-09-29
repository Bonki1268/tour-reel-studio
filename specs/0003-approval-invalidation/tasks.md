# 核准與失效：任務

> 每個任務小到能完成一次 red–green–refactor；不得有「完成後端」這類無法驗收的任務。

| 任務 | 前置 | 對應 R／AC | 修改範圍 | 先寫的測試 | 完成證據 |
|---|---|---|---|---|---|
| T-01 | — | R-002／AC-002、AC-003 | `backend/app/domain/approval.py`（`canonical_hash`） | `test_r002_*`、場景 S03-02 | 測試通過 |
| T-02 | — | R-006／AC-007 | `backend/app/domain/approval.py`（`ApprovalKind`、`Approval` 驗證） | `test_r006_*` | 測試通過 |
| T-03 | T-01、T-02 | R-001／AC-001 | `backend/app/domain/approval.py`（`plan_approval_input`、`approve_plan`） | `test_r001_placement_order_does_not_matter`、場景 S03-01 | 測試通過 |
| T-04 | T-03 | R-003、R-004／AC-004、AC-005 | `backend/app/domain/approval.py`（`ensure_still_approved`、`check_before_submit`） | `test_r004_rejected_submit_returns_video_to_plan_ready`、場景 S03-03、S03-04 | 測試通過 |
| T-05 | T-02 | R-005／AC-006 | `backend/app/domain/approval.py`（`auto_approve`） | `test_r005_plan_and_final_cannot_be_auto_approved`、場景 S03-05 | 測試通過 |
| T-06 | T-01～T-05 | 全部 | — | `python3 scripts/tdd.py gate` | 閘門通過（含 S01、S02 回歸）、`mypy app` 無錯誤 |

## 需求追蹤矩陣

| 需求 | 驗收條件 | BDD 場景 | TDD／整合測試 | 實作位置 | 狀態 |
|---|---|---|---|---|---|
| R-001 | AC-001 | `S03-01` | `test_r001_placement_order_does_not_matter` | `backend/app/domain/approval.py` | 完成 |
| R-002 | AC-002、AC-003 | `S03-02` | `test_r002_hash_ignores_key_order`、`test_r002_hash_depends_on_list_order`、`test_r002_float_rounded_to_4_places`、`test_r002_int_and_integral_float_equal`、`test_r002_rejects_nan_and_unsupported_types` | `backend/app/domain/approval.py` | 完成 |
| R-003 | AC-004 | `S03-03` | — | `backend/app/domain/approval.py` | 完成 |
| R-004 | AC-005 | `S03-04` | `test_r004_rejected_submit_returns_video_to_plan_ready` | `backend/app/domain/approval.py` | 完成 |
| R-005 | AC-006 | `S03-05` | `test_r005_plan_and_final_cannot_be_auto_approved` | `backend/app/domain/approval.py` | 完成 |
| R-006 | AC-007 | `S03-01` | `test_r006_cost_cap_must_be_positive`、`test_r006_unknown_kind_and_missing_approver_rejected` | `backend/app/domain/approval.py` | 完成 |
