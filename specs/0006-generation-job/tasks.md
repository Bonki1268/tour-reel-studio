# 生成工作與重試：任務

> 每個任務小到能完成一次 red–green–refactor；不得有「完成後端」這類無法驗收的任務。

| 任務 | 前置 | 對應 R／AC | 修改範圍 | 先寫的測試 | 完成證據 |
|---|---|---|---|---|---|
| T-01 | — | R-002、R-003、R-004 | `app/domain/generation.py` | `test_r002_max_two_attempts`、`test_r003_non_retryable_not_retried`、`test_r004_timeout_counts_from_submitted`、`test_r001_invalid_job_transition_rejected` | 測試通過 |
| T-02 | — | R-008／AC-011 | `app/domain/ports.py`、`app/storage/{memory_repos,sql_repos,models}.py`、`alembic/versions/0002_*` | `test_r008_job_update_roundtrip[memory|sql]`、`test_r008_take_update_roundtrip[memory|sql]` | 測試通過 |
| T-03 | — | R-001 | `app/providers/{base,fake}.py`、`app/storage/objects.py`、`app/config.py`、`.env.example` | （由 T-04 起的測試使用） | 型別檢查通過 |
| T-04 | T-01～T-03 | R-001、R-007／AC-001、AC-010 | `app/jobs/generation.py` | 場景 S06-01、`test_r007_records_provider_cost_once`、`test_r007_records_table_cost_when_unreported` | 測試通過 |
| T-05 | T-04 | R-002、R-003／AC-002～AC-004 | 同上 | 場景 S06-02、S06-03、`test_r003_non_retryable_goes_failed_final` | 測試通過 |
| T-06 | T-04 | R-004／AC-005 | 同上 | 場景 S06-04、`test_r004_queue_time_not_counted` | 測試通過 |
| T-07 | T-04 | R-005／AC-006、AC-007 | 同上 | 場景 S06-05、`test_r005_resume_existing_external_id`、`test_r005_different_input_hash_is_new_job` | 測試通過 |
| T-08 | T-04 | R-006、R-007／AC-008、AC-009、AC-010 | 同上、`app/domain/cost.py`（`Budget.release`） | 場景 S06-06、`test_r007_budget_exceeded_no_submit`、`test_r007_retry_blocked_by_budget`、`test_r007_failed_attempt_releases_reservation` | 測試通過 |
| T-09 | T-01～T-08 | 全部 | — | `python3 scripts/tdd.py gate` | 閘門通過（含 S01～S05 回歸）、`mypy app` 無錯誤 |

## 需求追蹤矩陣

| 需求 | 驗收條件 | BDD 場景 | TDD／整合測試 | 實作位置 | 狀態 |
|---|---|---|---|---|---|
| R-001 | AC-001 | `S06-01` | `test_r001_invalid_job_transition_rejected` | `backend/app/jobs/generation.py` | TODO |
| R-002 | AC-002 | `S06-02` | `test_r002_max_two_attempts` | `backend/app/domain/generation.py` | TODO |
| R-003 | AC-003、AC-004 | `S06-03` | `test_r003_*` | `backend/app/domain/generation.py`、`backend/app/jobs/generation.py` | TODO |
| R-004 | AC-005 | `S06-04` | `test_r004_*` | 同上 | TODO |
| R-005 | AC-006、AC-007 | `S06-05` | `test_r005_*` | `backend/app/jobs/generation.py` | TODO |
| R-006 | AC-008 | `S06-06` | — | `backend/app/jobs/generation.py` | TODO |
| R-007 | AC-009、AC-010 | `S06-06`、`S06-01` | `test_r007_*` | `backend/app/jobs/generation.py`、`backend/app/domain/cost.py` | TODO |
| R-008 | AC-011 | `S06-01` | `test_r008_*` | `backend/app/storage/` | TODO |
