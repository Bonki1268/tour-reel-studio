# Higgsfield adapter：任務

> 每個任務小到能完成一次 red–green–refactor；不得有「完成後端」這類無法驗收的任務。

| 任務 | 前置 | 對應 R／AC | 修改範圍 | 先寫的測試 | 完成證據 |
|---|---|---|---|---|---|
| T-01 | — | R-003／AC-003、R-006／AC-006 | `app/providers/higgsfield.py`（map_status、parse_cost、classify） | `test_r003_*`、`test_r006_classify*` | 測試通過 |
| T-02 | T-01 | R-001／AC-001、R-002／AC-002 | `higgsfield.py`（上傳、compose、image_to_video、參數）、`config.py`、`tests/conftest.py` | `test_r001_*`、`test_r002_*`、場景 S12-01、S12-02、S12-06 | 測試通過 |
| T-03 | T-02 | R-003／AC-003、R-004／AC-004 | `higgsfield.py`（fetch_result、download） | 場景 S12-03、S12-04 | 測試通過 |
| T-04 | — | R-005／AC-005 | `app/providers/webhook.py`、`app/api/routes/webhooks.py`、`main.py` | `test_r005_*`、場景 S12-05 | 測試通過 |
| T-05 | T-02 | R-007／AC-007 | `higgsfield.py`（RedactSecrets、錯誤訊息） | `test_r006_error_message_excludes_key`、場景 S12-07 | 測試通過 |
| T-06 | T-02 | R-008／AC-008 | `app/jobs/orchestrator.py`、`app/storage/keys.py`（mask）、`app/api/services.py`（選用 adapter） | `test_r008_*` | 測試通過，S07 回歸通過 |
| T-07 | T-01～T-06 | 全部 | `tests/external/test_higgsfield_live.py`（S12-08，不執行） | `python3 scripts/tdd.py gate` | 閘門通過（含 S01～S11 回歸）、`mypy app` 無錯誤 |

## 需求追蹤矩陣

| 需求 | 驗收條件 | BDD 場景 | TDD／整合測試 | 實作位置 | 狀態 |
|---|---|---|---|---|---|
| R-001 | AC-001 | `S12-01` | `test_r001_*` | `backend/app/providers/higgsfield.py` | done |
| R-002 | AC-002 | `S12-02` | `test_r002_*` | `backend/app/providers/higgsfield.py` | done |
| R-003 | AC-003 | `S12-03` | `test_r003_*` | `backend/app/providers/higgsfield.py` | done |
| R-004 | AC-004 | `S12-04` | — | `backend/app/providers/higgsfield.py` | done |
| R-005 | AC-005 | `S12-05` | `test_r005_*` | `backend/app/providers/webhook.py`、`backend/app/api/routes/webhooks.py` | done |
| R-006 | AC-006 | `S12-06` | `test_r006_*` | `backend/app/providers/higgsfield.py` | done |
| R-007 | AC-007 | `S12-07` | `test_r006_error_message_excludes_key`、`test_r007_*` | `backend/app/providers/higgsfield.py` | done |
| R-008 | AC-008 | `S12-02` | `test_r008_*` | `backend/app/jobs/orchestrator.py` | done |
