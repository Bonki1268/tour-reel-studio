# REST API 與 SSE：任務

> 每個任務小到能完成一次 red–green–refactor；不得有「完成後端」這類無法驗收的任務。

| 任務 | 前置 | 對應 R／AC | 修改範圍 | 先寫的測試 | 完成證據 |
|---|---|---|---|---|---|
| T-01 | — | R-009 | `pyproject.toml`（arq）、`app/config.py`、`.env.example`、`app/jobs/queue.py`、`app/jobs/worker.py` | `test_r009_arq_worker_runs_plan_job` | 測試通過 |
| T-02 | — | R-004 | `app/domain/ports.py`、`app/storage/{models,memory_repos,sql_repos}.py`、`alembic/versions/0004_*` | `test_r009_idempotency_repo_roundtrip[memory|sql]` | 測試通過 |
| T-03 | — | R-006 | `app/jobs/events.py`（subscribe、RedisEventBus） | `test_r009_redis_event_bus_pubsub` | 測試通過 |
| T-04 | — | R-007 | `app/storage/objects.py`（presign_get） | （由 S08-06 使用） | 型別檢查通過 |
| T-05 | T-01 | R-001 | `app/jobs/orchestrator.py`（create_video、propose_plans、regenerate_plans） | S07 回歸 | S07 測試仍通過 |
| T-06 | T-01～T-05 | R-001、R-002／AC-001、AC-002、AC-011 | `app/api/{main,services,schemas,errors}.py`、`routes/projects.py`、`routes/videos.py` | 場景 S08-01、S08-07、`test_r001_topic_validation` | 測試通過 |
| T-07 | T-06 | R-003、R-004／AC-003～AC-005 | `app/api/idempotency.py`、`routes/videos.py` | 場景 S08-02、S08-03、`test_r004_*`、`test_r003_*` | 測試通過 |
| T-08 | T-06 | R-005、R-008／AC-006、AC-007、AC-012 | `app/api/errors.py`、`routes/videos.py` | 場景 S08-04、`test_r005_exception_mapping`、`test_r008_*` | 測試通過 |
| T-09 | T-03、T-06 | R-006／AC-008、AC-009 | `routes/events.py` | 場景 S08-05、`test_r006_*` | 測試通過 |
| T-10 | T-04、T-06 | R-007／AC-010 | `routes/videos.py` | 場景 S08-06 | 測試通過 |
| T-11 | T-01～T-10 | 全部 | — | `python3 scripts/tdd.py gate` | 閘門通過（含 S01～S07 回歸）、`mypy app` 無錯誤 |

## 需求追蹤矩陣

| 需求 | 驗收條件 | BDD 場景 | TDD／整合測試 | 實作位置 | 狀態 |
|---|---|---|---|---|---|
| R-001 | AC-001、AC-002 | `S08-01` | `test_r001_*` | `backend/app/api/routes/videos.py` | TODO |
| R-002 | AC-011 | `S08-07` | — | `backend/app/api/routes/{projects,videos}.py` | TODO |
| R-003 | AC-003、AC-005 | `S08-02`、`S08-03` | `test_r003_*` | `backend/app/api/routes/videos.py` | TODO |
| R-004 | AC-003、AC-004 | `S08-02` | `test_r004_*` | `backend/app/api/idempotency.py` | TODO |
| R-005 | AC-006、AC-007 | `S08-04` | `test_r005_*` | `backend/app/api/errors.py` | TODO |
| R-006 | AC-008、AC-009 | `S08-05` | `test_r006_*` | `backend/app/api/routes/events.py`、`backend/app/jobs/events.py` | TODO |
| R-007 | AC-010 | `S08-06` | — | `backend/app/api/routes/videos.py`、`backend/app/storage/objects.py` | TODO |
| R-008 | AC-012 | `S08-07` | `test_r008_*` | `backend/app/api/routes/videos.py` | TODO |
| R-009 | AC-013 | `S08-05` | `test_r009_*` | `backend/app/jobs/{queue,worker,events}.py` | TODO |
