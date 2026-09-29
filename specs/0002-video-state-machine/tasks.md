# 影片狀態機：任務

> 每個任務小到能完成一次 red–green–refactor；不得有「完成後端」這類無法驗收的任務。

| 任務 | 前置 | 對應 R／AC | 修改範圍 | 先寫的測試 | 完成證據 |
|---|---|---|---|---|---|
| T-01 | — | R-001／AC-001 | `backend/app/domain/video.py`（列舉、轉換表） | `test_r001_transition_table_matches_spec`、`test_r001_extra_transitions`、場景 S02-01 | 測試通過 |
| T-02 | T-01 | R-002／AC-002、AC-003 | `backend/app/domain/video.py`（`Video.apply`、`InvalidTransition`） | `test_r002_all_undefined_pairs_rejected`、場景 S02-02 | 測試通過 |
| T-03 | T-01 | R-003／AC-004 | `backend/app/domain/video.py`（`TERMINAL`） | `test_r003_terminal_states_have_no_exit`、`test_r003_every_non_terminal_state_has_exit`、場景 S02-03 | 測試通過 |
| T-04 | T-02 | R-004／AC-005 | `backend/app/domain/video.py`（`StatusChange`、歷程、時鐘注入） | `test_r004_history_records_event_and_time`、`test_r004_rejected_event_leaves_no_history`、場景 S02-04 | 測試通過 |
| T-05 | T-01～T-04 | 全部 | — | `python3 scripts/tdd.py gate` | 閘門通過（含 S01 回歸）、`mypy app` 無錯誤 |

## 需求追蹤矩陣

| 需求 | 驗收條件 | BDD 場景 | TDD／整合測試 | 實作位置 | 狀態 |
|---|---|---|---|---|---|
| R-001 | AC-001 | `S02-01` | `test_r001_transition_table_matches_spec`、`test_r001_extra_transitions` | `backend/app/domain/video.py` | TODO |
| R-002 | AC-002、AC-003 | `S02-02` | `test_r002_all_undefined_pairs_rejected` | `backend/app/domain/video.py` | TODO |
| R-003 | AC-004 | `S02-03` | `test_r003_terminal_states_have_no_exit`、`test_r003_every_non_terminal_state_has_exit` | `backend/app/domain/video.py` | TODO |
| R-004 | AC-005 | `S02-04` | `test_r004_history_records_event_and_time`、`test_r004_rejected_event_leaves_no_history` | `backend/app/domain/video.py` | TODO |
