# 物件儲存：任務

> 每個任務小到能完成一次 red–green–refactor；不得有「完成後端」這類無法驗收的任務。

| 任務 | 前置 | 對應 R／AC | 修改範圍 | 先寫的測試 | 完成證據 |
|---|---|---|---|---|---|
| T-01 | — | （基礎建設） | `infra/docker-compose.test.yml`（minio）、`backend/pyproject.toml`（boto3）、`app/config.py`、`.env.example` | `docker compose ... up -d --wait` | 三個服務 healthy |
| T-02 | — | R-003／AC-003、AC-004 | `app/storage/keys.py` | 場景 S09-03、`test_r003_all_paths_match_section7`、`test_r003_rejects_*` | 測試通過 |
| T-03 | T-02 | R-003／AC-005 | `app/jobs/generation.py`、`app/jobs/orchestrator.py` | `test_r003_no_hardcoded_paths_in_app` | 測試通過（含 S06、S07 回歸） |
| T-04 | T-01 | R-001、R-002、R-004／AC-001、AC-002、AC-006 | `app/storage/objects.py`、`app/domain/ports.py` | 場景 S09-01、S09-02、S09-04、`test_r001_*`、`test_r002_*` | 測試通過 |
| T-05 | T-04 | R-005／AC-007 | `app/storage/objects.py`、`app/api/services.py` | `test_r005_*` | 測試通過 |
| T-06 | T-01～T-05 | 全部 | — | `python3 scripts/tdd.py gate` | 閘門通過（含 S01～S08 回歸）、`mypy app` 無錯誤 |

## 需求追蹤矩陣

| 需求 | 驗收條件 | BDD 場景 | TDD／整合測試 | 實作位置 | 狀態 |
|---|---|---|---|---|---|
| R-001 | AC-001 | `S09-01` | `test_r001_*` | `backend/app/storage/objects.py` | TODO |
| R-002 | AC-002 | `S09-02` | `test_r002_*` | `backend/app/storage/objects.py` | TODO |
| R-003 | AC-003、AC-004、AC-005 | `S09-03` | `test_r003_*` | `backend/app/storage/keys.py` | TODO |
| R-004 | AC-006 | `S09-04` | — | `backend/app/storage/objects.py` | TODO |
| R-005 | AC-007 | `S09-02` | `test_r005_*` | `backend/app/storage/objects.py`、`backend/app/api/services.py` | TODO |
