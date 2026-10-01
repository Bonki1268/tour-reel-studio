# 時間軸與影片合成：任務

> 每個任務小到能完成一次 red–green–refactor；不得有「完成後端」這類無法驗收的任務。

| 任務 | 前置 | 對應 R／AC | 修改範圍 | 先寫的測試 | 完成證據 |
|---|---|---|---|---|---|
| T-01 | — | R-001／AC-001、R-005／AC-005 | `app/render/timeline.py`（模型、build_timeline、set_clip_duration） | `test_r001_*`、`test_r005_set_clip_duration_*`、場景 S13-01 | 測試通過 |
| T-02 | T-01 | R-003／AC-003 | `timeline.py`（ass_time、to_ass）、`backend/assets/fonts/`（字型與授權檔） | `test_r003_*`、場景 S13-03 | 測試通過 |
| T-03 | T-01 | R-002／AC-002、R-004／AC-004 | `app/render/ffmpeg.py`（command、執行、probe） | `test_r002_*`、`test_r004_*`、場景 S13-02、S13-04 | 測試通過 |
| T-04 | T-03 | R-005／AC-005、R-006／AC-006 | `ffmpeg.py`（縮圖）、`storage/keys.py`（render_thumb） | 場景 S13-05、S13-06 | 測試通過 |
| T-05 | T-04 | R-006／AC-006、R-007／AC-007 | `app/render/base.py`、`fake.py`、`app/jobs/orchestrator.py`、`config.py`、`api/services.py` | `test_r006_render_record_has_thumb_key`、`test_r007_*` | 測試通過，S07／S08 回歸通過 |
| T-06 | T-01～T-05 | 全部 | — | `python3 scripts/tdd.py gate` | 閘門通過（含 S01～S12 回歸）、`mypy app` 無錯誤 |

## 需求追蹤矩陣

| 需求 | 驗收條件 | BDD 場景 | TDD／整合測試 | 實作位置 | 狀態 |
|---|---|---|---|---|---|
| R-001 | AC-001 | `S13-01` | `test_r001_*` | `backend/app/render/timeline.py` | TODO |
| R-002 | AC-002 | `S13-02` | `test_r002_*` | `backend/app/render/ffmpeg.py` | TODO |
| R-003 | AC-003 | `S13-03` | `test_r003_*` | `backend/app/render/timeline.py` | TODO |
| R-004 | AC-004 | `S13-04` | `test_r004_*` | `backend/app/render/ffmpeg.py` | TODO |
| R-005 | AC-005 | `S13-05` | `test_r005_*` | `backend/app/render/timeline.py`、`backend/app/render/ffmpeg.py` | TODO |
| R-006 | AC-006 | `S13-06` | `test_r006_*` | `backend/app/render/ffmpeg.py`、`backend/app/jobs/orchestrator.py` | TODO |
| R-007 | AC-007 | `S13-02` | `test_r007_*` | `backend/app/jobs/orchestrator.py` | TODO |
