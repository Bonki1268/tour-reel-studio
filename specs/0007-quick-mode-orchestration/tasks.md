# 快速模式工作編排：任務

> 每個任務小到能完成一次 red–green–refactor；不得有「完成後端」這類無法驗收的任務。

| 任務 | 前置 | 對應 R／AC | 修改範圍 | 先寫的測試 | 完成證據 |
|---|---|---|---|---|---|
| T-01 | — | R-008／AC-010 | `app/domain/ports.py`、`app/storage/{memory_repos,sql_repos}.py` | `test_r008_*[memory|sql]` | 測試通過 |
| T-02 | — | R-004 | `app/jobs/events.py` | `test_r004_event_has_type_video_id_shot_no_at` | 測試通過 |
| T-03 | — | R-001、R-003 | `app/creative/{base,fake}.py`、`app/render/{base,fake}.py`、`app/providers/fake.py` | （由 T-04 起的測試使用） | 型別檢查通過 |
| T-04 | T-01～T-03 | R-001／AC-001、AC-002 | `app/jobs/orchestrator.py`（submit_topic） | 場景 S07-01 前半、`test_r001_*` | 測試通過 |
| T-05 | T-04 | R-002、R-003、R-007／AC-003、AC-009 | 同上（approve_plan、generate、render、approve_final） | 場景 S07-01、S07-06、`test_r002_*` | 測試通過 |
| T-06 | T-05 | R-003／AC-004 | 同上 | 場景 S07-02 | 測試通過（3 秒內） |
| T-07 | T-05 | R-004／AC-005 | 同上 | 場景 S07-03 | 測試通過 |
| T-08 | T-05 | R-005／AC-006、AC-007 | 同上、`app/jobs/generation.py` | 場景 S07-04、`test_r005_*` | 測試通過 |
| T-09 | T-05 | R-006／AC-008 | 同上（regenerate_shot） | 場景 S07-05、`test_r006_*` | 測試通過 |
| T-10 | T-01～T-09 | 全部 | — | `python3 scripts/tdd.py gate` | 閘門通過（含 S01～S06 回歸）、`mypy app` 無錯誤 |

## 需求追蹤矩陣

| 需求 | 驗收條件 | BDD 場景 | TDD／整合測試 | 實作位置 | 狀態 |
|---|---|---|---|---|---|
| R-001 | AC-001、AC-002 | `S07-01` | `test_r001_*` | `backend/app/jobs/orchestrator.py`、`backend/app/creative/` | 完成 |
| R-002 | AC-003 | `S07-01` | `test_r002_*` | `backend/app/jobs/orchestrator.py` | 完成 |
| R-003 | AC-003、AC-004 | `S07-01`、`S07-02` | — | `backend/app/jobs/orchestrator.py`、`backend/app/render/` | 完成 |
| R-004 | AC-005 | `S07-03` | `test_r004_*` | `backend/app/jobs/events.py` | 完成 |
| R-005 | AC-006、AC-007 | `S07-04` | `test_r005_*` | `backend/app/jobs/orchestrator.py`、`backend/app/jobs/generation.py` | 完成 |
| R-006 | AC-008 | `S07-05` | `test_r006_*` | `backend/app/jobs/orchestrator.py` | 完成 |
| R-007 | AC-009 | `S07-06` | `test_r007_final_approval_hashes_latest_timeline` | `backend/app/jobs/orchestrator.py` | 完成 |
| R-008 | AC-010 | `S07-01` | `test_r008_*`（含 `test_r008_list_shots_sorted_by_shot_no`） | `backend/app/storage/` | 完成 |
