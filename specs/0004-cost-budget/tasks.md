# 成本估算與預算控制：任務

> 每個任務小到能完成一次 red–green–refactor；不得有「完成後端」這類無法驗收的任務。

| 任務 | 前置 | 對應 R／AC | 修改範圍 | 先寫的測試 | 完成證據 |
|---|---|---|---|---|---|
| T-01 | — | R-006／AC-007 | `backend/app/domain/cost.py`（`JobKind`、`CostTable`、`CostTableError`） | `test_r006_invalid_cost_table_files`、`test_r006_load_cost_table_file`、場景 S04-06 | 測試通過 |
| T-02 | T-01 | R-001／AC-001 | `backend/app/domain/cost.py`（`Estimate`、`estimate_video`） | `test_r001_zero_shots_costs_nothing`、`test_r001_reserve_shots_configurable`、場景 S04-01 | 測試通過 |
| T-03 | T-01 | R-002、R-003／AC-002～AC-004 | `backend/app/domain/cost.py`（`Budget.check`、`BudgetExceeded`） | `test_r002_exactly_at_cap_allowed`、`test_r002_parallel_jobs_count_reservations`、`test_r003_one_over_cap_rejected_without_side_effects`、場景 S04-02、S04-03 | 測試通過 |
| T-04 | T-03 | R-004、R-005／AC-005、AC-006 | `backend/app/domain/cost.py`（`CostEntry`、`Budget.record`） | `test_r004_actual_cost_replaces_estimate`、`test_r004_same_job_recorded_once`、場景 S04-04、S04-05 | 測試通過 |
| T-05 | T-02 | R-001 | `backend/app/config.py`（`retry_reserve_shots`）、`.env.example`、`config/cost_table.example.json` | 既有 S01 測試維持通過 | 測試通過 |
| T-06 | T-01～T-05 | 全部 | — | `python3 scripts/tdd.py gate` | 閘門通過（含 S01～S03 回歸）、`mypy app` 無錯誤 |

## 需求追蹤矩陣

| 需求 | 驗收條件 | BDD 場景 | TDD／整合測試 | 實作位置 | 狀態 |
|---|---|---|---|---|---|
| R-001 | AC-001 | `S04-01` | `test_r001_zero_shots_costs_nothing`、`test_r001_reserve_shots_configurable` | `backend/app/domain/cost.py` | TODO |
| R-002 | AC-002、AC-003 | `S04-02` | `test_r002_exactly_at_cap_allowed`、`test_r002_parallel_jobs_count_reservations` | `backend/app/domain/cost.py` | TODO |
| R-003 | AC-004 | `S04-03` | `test_r003_one_over_cap_rejected_without_side_effects` | `backend/app/domain/cost.py` | TODO |
| R-004 | AC-005 | `S04-04` | `test_r004_actual_cost_replaces_estimate`、`test_r004_same_job_recorded_once` | `backend/app/domain/cost.py` | TODO |
| R-005 | AC-006 | `S04-05` | — | `backend/app/domain/cost.py` | TODO |
| R-006 | AC-007 | `S04-06` | `test_r006_invalid_cost_table_files`、`test_r006_load_cost_table_file` | `backend/app/domain/cost.py` | TODO |
