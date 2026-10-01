# 片尾卡：任務

> 每個任務小到能完成一次 red–green–refactor；不得有「完成後端」這類無法驗收的任務。

| 任務 | 前置 | 對應 R／AC | 修改範圍 | 先寫的測試 | 完成證據 |
|---|---|---|---|---|---|
| T-01 | — | R-004／AC-004 | `app/render/outro.py`（parse_color、text_color） | `test_r004_*` | 測試通過 |
| T-02 | T-01 | R-001／AC-001、R-003／AC-003、R-005／AC-005 | `outro.py`（make_card、fit_text、版面） | `test_r001_*`、`test_r003_*`、`test_r005_*`、場景 S14-01、S14-03 | 測試通過 |
| T-03 | T-02 | R-002／AC-002 | `outro.py`（QR code）、`pyproject.toml`（qrcode、opencv-python-headless dev） | `test_r002_*`、場景 S14-02 | 測試通過 |
| T-04 | T-02 | R-006／AC-006 | `outro.py`（card_to_clip_command）、`app/render/ffmpeg.py`（render_outro） | `test_r006_*`、場景 S14-04 | 測試通過 |
| T-05 | T-04 | R-007／AC-007 | `app/render/base.py`、`fake.py`、`app/jobs/orchestrator.py`、`storage/keys.py`（outro） | `test_r007_*` | 測試通過，S07／S08／S13 回歸通過 |
| T-06 | T-01～T-05 | 全部 | — | `python3 scripts/tdd.py gate` | 閘門通過（含 S01～S13 回歸）、`mypy app` 無錯誤 |

## 需求追蹤矩陣

| 需求 | 驗收條件 | BDD 場景 | TDD／整合測試 | 實作位置 | 狀態 |
|---|---|---|---|---|---|
| R-001 | AC-001 | `S14-01` | `test_r001_*` | `backend/app/render/outro.py` | TODO |
| R-002 | AC-002 | `S14-02` | `test_r002_*` | `backend/app/render/outro.py` | TODO |
| R-003 | AC-003 | `S14-03` | `test_r003_*` | `backend/app/render/outro.py` | TODO |
| R-004 | AC-004 | `S14-01` | `test_r004_*` | `backend/app/render/outro.py` | TODO |
| R-005 | AC-005 | `S14-01` | `test_r005_*` | `backend/app/render/outro.py` | TODO |
| R-006 | AC-006 | `S14-04` | `test_r006_*` | `backend/app/render/outro.py`、`backend/app/render/ffmpeg.py` | TODO |
| R-007 | AC-007 | `S14-04` | `test_r007_*` | `backend/app/jobs/orchestrator.py` | TODO |
