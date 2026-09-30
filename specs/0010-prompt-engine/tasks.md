# 企劃產生 PromptEngine：任務

> 每個任務小到能完成一次 red–green–refactor；不得有「完成後端」這類無法驗收的任務。

| 任務 | 前置 | 對應 R／AC | 修改範圍 | 先寫的測試 | 完成證據 |
|---|---|---|---|---|---|
| T-01 | — | R-001／AC-002 | `app/creative/schema.py`、`app/creative/base.py`（ShotDraft 英文欄位） | `test_r001_schema_*` | 測試通過 |
| T-02 | T-01 | R-001／AC-002 | `app/creative/prompt_engine.py`（validate_plans） | `test_r001_semantic_*`、`test_r001_rejects_plan_count` | 測試通過 |
| T-03 | — | R-004／AC-006 | `app/creative/skills/tourism-promo/SKILL.md`、`prompt_engine.py`（build_prompt） | 場景 S10-05、`test_r004_*` | 測試通過 |
| T-04 | T-01～T-03 | R-001～R-003／AC-001、AC-003～AC-005 | `app/creative/claude.py`、`prompt_engine.py`（propose_plans）、`tests/fixtures/claude/` | 場景 S10-01～S10-04、`test_r003_*` | 測試通過 |
| T-05 | T-04 | R-005／AC-007 | `prompt_engine.py`（build_shot_prompts） | 場景 S10-06 | 測試通過 |
| T-06 | T-04 | R-006／AC-008 | `app/config.py`、`.env.example`、`app/api/services.py`、`claude.py`（AnthropicClaudeClient） | `test_r006_*` | 測試通過 |
| T-07 | T-06 | （external） | `tests/external/test_claude_live.py` | `@external` 測試 | 使用者同意後手動執行 |
| T-08 | T-01～T-06 | 全部 | — | `python3 scripts/tdd.py gate` | 閘門通過（含 S01～S09 回歸）、`mypy app` 無錯誤 |

## 需求追蹤矩陣

| 需求 | 驗收條件 | BDD 場景 | TDD／整合測試 | 實作位置 | 狀態 |
|---|---|---|---|---|---|
| R-001 | AC-001、AC-002 | `S10-01` | `test_r001_*` | `backend/app/creative/{schema,prompt_engine}.py` | TODO |
| R-002 | AC-003、AC-004 | `S10-02`、`S10-04` | — | `backend/app/creative/prompt_engine.py` | TODO |
| R-003 | AC-005 | `S10-03` | `test_r003_*` | `backend/app/creative/prompt_engine.py` | TODO |
| R-004 | AC-006 | `S10-05` | `test_r004_*` | `backend/app/creative/prompt_engine.py`、`skills/tourism-promo/SKILL.md` | TODO |
| R-005 | AC-007 | `S10-06` | — | `backend/app/creative/prompt_engine.py` | TODO |
| R-006 | AC-008 | `S10-05` | `test_r006_*` | `backend/app/creative/claude.py`、`backend/app/api/services.py` | TODO |
