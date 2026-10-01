# Demo 可靠性：任務

> 每個任務小到能完成一次 red–green–refactor；不得有「完成後端」這類無法驗收的任務。

| 任務 | 前置 | 對應 R／AC | 修改範圍 | 先寫的測試 | 完成證據 |
|---|---|---|---|---|---|
| T-01 | — | R-004／AC-006 | `app/domain/ports.py`、`app/storage/memory_repos.py`、`sql_repos.py`（`update_if`、`list_by_status`、`get_by_provider_key`、`get_take`） | `test_r004_update_if_*` | 測試通過 |
| T-02 | T-01 | R-004／AC-003 | `app/jobs/generation.py`（條件轉換、`complete_job`、輪詢端等待他方結果） | `test_r004_complete_job_*`、場景 S18-03 | 測試通過；S06／S07 回歸通過 |
| T-03 | T-02 | R-003／AC-007 | `app/api/routes/webhooks.py`、`app/jobs/worker.py`（`process_webhook`） | `test_r003_webhook_*` | 測試通過；S12 回歸通過 |
| T-04 | — | R-001、R-002／AC-001、AC-002 | 無預期的產品程式碼變更（驗證既有輪詢路徑） | 場景 S18-01、S18-02 | 測試通過 |
| T-05 | T-02 | R-005／AC-004、AC-008 | `app/jobs/recovery.py`、`worker.py` 的 `on_startup` | `test_r005_recover_*`、場景 S18-04 | 測試通過 |
| T-06 | — | R-006／AC-005、AC-009 | `app/config.py`、`app/domain/fallback.py`、`app/api/schemas.py`、`routes/videos.py`、`.env.example`、OpenAPI 與前端型別 | `test_r006_fallback_*`、場景 S18-05 | 測試通過 |
| T-07 | T-01～T-06 | 全部 | — | `python3 scripts/tdd.py gate` | 閘門通過（含 S01～S17 回歸） |

## 需求追蹤矩陣

| 需求 | 驗收條件 | BDD 場景 | TDD／整合測試 | 實作位置 | 狀態 |
|---|---|---|---|---|---|
| R-001 | AC-001 | `S18-01` | — | `backend/app/jobs/generation.py` | TODO |
| R-002 | AC-002 | `S18-02` | — | `backend/app/jobs/generation.py` | TODO |
| R-003 | AC-003、AC-007 | `S18-03` | `test_r003_*` | `backend/app/api/routes/webhooks.py`、`backend/app/jobs/worker.py` | TODO |
| R-004 | AC-003、AC-006 | `S18-03` | `test_r004_*` | `backend/app/jobs/generation.py`、`backend/app/storage/` | TODO |
| R-005 | AC-004、AC-008 | `S18-04` | `test_r005_*` | `backend/app/jobs/recovery.py` | TODO |
| R-006 | AC-005、AC-009 | `S18-05` | `test_r006_*` | `backend/app/domain/fallback.py`、`backend/app/api/routes/videos.py` | TODO |
