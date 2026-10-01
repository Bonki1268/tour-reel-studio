# Demo 種子資料：任務

> 每個任務小到能完成一次 red–green–refactor；不得有「完成後端」這類無法驗收的任務。

| 任務 | 前置 | 對應 R／AC | 修改範圍 | 先寫的測試 | 完成證據 |
|---|---|---|---|---|---|
| T-01 | — | R-007／AC-006 | `app/seed/schema.py` | `test_r007_*` | 測試通過 |
| T-02 | — | R-003／AC-005、R-006／AC-004 | `app/seed/assets.py` | `test_r003_*`、`test_r006_*` | 測試通過 |
| T-03 | — | R-005／AC-003 | `app/seed/firecrawl.py` | `test_r005_*` | 測試通過 |
| T-04 | T-01～T-03 | R-001～R-004／AC-001、AC-002 | `app/seed/run.py`、repository 補充（記憶體＋SQL） | 場景 S17-01、S17-02、`test_r001_*` | 測試通過 |
| T-05 | T-04 | R-005／AC-003、R-006／AC-004 | `run.py`（快取、去背圖） | 場景 S17-03、S17-04 | 測試通過 |
| T-06 | T-05 | — | `seed/demo/`、`seed/cache/`（依待決事項 1 的決定）、`.env.example` | 手動執行 `python -m app.seed.run` | 腳本成功、印出專案 ID |
| T-07 | T-01～T-06 | 全部 | — | `python3 scripts/tdd.py gate` | 閘門通過（含 S01～S16 回歸） |

## 需求追蹤矩陣

| 需求 | 驗收條件 | BDD 場景 | TDD／整合測試 | 實作位置 | 狀態 |
|---|---|---|---|---|---|
| R-001 | AC-001 | `S17-01` | `test_r001_*` | `backend/app/seed/run.py` | done |
| R-002 | AC-001 | `S17-01` | — | `backend/app/seed/run.py` | done |
| R-003 | AC-001、AC-005 | `S17-01` | `test_r003_*` | `backend/app/seed/assets.py` | done |
| R-004 | AC-002 | `S17-02` | `test_r004_*` | `backend/app/seed/run.py` | done |
| R-005 | AC-003 | `S17-03` | `test_r005_*` | `backend/app/seed/firecrawl.py` | done |
| R-006 | AC-004 | `S17-04` | `test_r006_*` | `backend/app/seed/assets.py` | done |
| R-007 | AC-006 | `S17-01` | `test_r007_*` | `backend/app/seed/schema.py` | done |
