# 資料持久化：任務

> 每個任務小到能完成一次 red–green–refactor；不得有「完成後端」這類無法驗收的任務。

| 任務 | 前置 | 對應 R／AC | 修改範圍 | 先寫的測試 | 完成證據 |
|---|---|---|---|---|---|
| T-01 | — | （基礎建設） | `infra/docker-compose.test.yml`、`backend/pyproject.toml`（依賴）、`app/config.py`（`database_url`）、`.env.example` | `docker compose ... up -d --wait` 成功 | 兩個服務 healthy |
| T-02 | — | R-004／AC-005 | `backend/app/domain/ids.py` | `test_r004_idempotency_key_format`、`test_r004_idempotency_key_rejects_invalid_parts` | 測試通過 |
| T-03 | T-01 | R-001／AC-001 | `backend/app/storage/models.py`、`backend/alembic/` | 場景 S05-01 | 測試通過 |
| T-04 | T-03 | R-002、R-006／AC-002、AC-007 | `backend/app/domain/ports.py`、`app/storage/{memory_repos,sql_repos,db}.py`（專案） | `test_r002_project_and_brand_roundtrip[memory|sql]`、場景 S05-02 | 測試通過 |
| T-05 | T-04 | R-003／AC-003 | 同上（鏡頭與版本） | `test_r003_takes_are_kept[memory|sql]`、場景 S05-03 | 測試通過 |
| T-06 | T-02、T-04 | R-004／AC-004 | 同上（生成工作） | `test_r004_create_or_get_returns_existing[memory|sql]`、場景 S05-04 | 測試通過 |
| T-07 | T-04 | R-005、R-007／AC-006、AC-008 | 同上（影片、核准、成本帳） | `test_r005_json_types_roundtrip[memory|sql]`、`test_r007_video_history_approvals_costs_roundtrip[memory|sql]`、場景 S05-05 | 測試通過 |
| T-08 | T-01～T-07 | 全部 | — | `python3 scripts/tdd.py gate` | 閘門通過（含 S01～S04 回歸）、`mypy app` 無錯誤 |

## 需求追蹤矩陣

| 需求 | 驗收條件 | BDD 場景 | TDD／整合測試 | 實作位置 | 狀態 |
|---|---|---|---|---|---|
| R-001 | AC-001 | `S05-01` | — | `backend/app/storage/models.py`、`backend/alembic/` | TODO |
| R-002 | AC-002 | `S05-02` | `test_r002_project_and_brand_roundtrip` | `backend/app/storage/` | TODO |
| R-003 | AC-003 | `S05-03` | `test_r003_takes_are_kept` | `backend/app/storage/` | TODO |
| R-004 | AC-004、AC-005 | `S05-04` | `test_r004_idempotency_key_*`、`test_r004_create_or_get_returns_existing` | `backend/app/domain/ids.py`、`backend/app/storage/` | TODO |
| R-005 | AC-006 | `S05-05` | `test_r005_json_types_roundtrip` | `backend/app/storage/` | TODO |
| R-006 | AC-007 | `S05-02` | 以上參數化測試（memory／sql） | `backend/app/storage/memory_repos.py` | TODO |
| R-007 | AC-008 | `S05-05` | `test_r007_video_history_approvals_costs_roundtrip` | `backend/app/storage/` | TODO |
