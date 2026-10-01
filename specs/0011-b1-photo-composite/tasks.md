# B1 照片合成：任務

> 每個任務小到能完成一次 red–green–refactor；不得有「完成後端」這類無法驗收的任務。

| 任務 | 前置 | 對應 R／AC | 修改範圍 | 先寫的測試 | 完成證據 |
|---|---|---|---|---|---|
| T-01 | — | R-005／AC-006 | `backend/app/providers/composite.py`（Placement、PlacementError）、`pyproject.toml`（pillow） | `test_r005_*`、場景 S11-05 | 測試通過 |
| T-02 | T-01 | R-001、R-002／AC-001～AC-003 | `composite.py`（composite、CompositeResult） | `test_r001_*`、`test_r002_*`、場景 S11-01、S11-02 | 測試通過 |
| T-03 | T-02 | R-003／AC-004 | `composite.py`（flip） | 場景 S11-03 | 測試通過 |
| T-04 | T-02 | R-004／AC-005 | `composite.py`（裁切、完全在外、全透明） | `test_r004_*`、場景 S11-04 | 測試通過 |
| T-05 | T-02 | R-006／AC-007 | `composite.py`（ComposeRequest、build_compose_request、提示詞模板） | `test_r006_*`、場景 S11-06 | 測試通過 |
| T-06 | T-01～T-05 | 全部 | — | `python3 scripts/tdd.py gate` | 閘門通過（含 S01～S10 回歸）、`mypy app` 無錯誤 |

## 需求追蹤矩陣

| 需求 | 驗收條件 | BDD 場景 | TDD／整合測試 | 實作位置 | 狀態 |
|---|---|---|---|---|---|
| R-001 | AC-001、AC-002 | `S11-01` | `test_r001_*` | `backend/app/providers/composite.py` | done |
| R-002 | AC-003 | `S11-02` | `test_r002_*` | `backend/app/providers/composite.py` | done |
| R-003 | AC-004 | `S11-03` | — | `backend/app/providers/composite.py` | done |
| R-004 | AC-005 | `S11-04` | `test_r004_*` | `backend/app/providers/composite.py` | done |
| R-005 | AC-006 | `S11-05` | `test_r005_*` | `backend/app/providers/composite.py` | done |
| R-006 | AC-007 | `S11-06` | `test_r006_*` | `backend/app/providers/composite.py` | done |
