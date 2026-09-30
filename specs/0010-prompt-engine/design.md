# 企劃產生 PromptEngine：設計

> 對應規格：spec.md（版本 v1）。本檔由 Claude Code 撰寫，隨規格核准一併審閱。

## 設計概要

```
backend/app/creative/
├─ skills/tourism-promo/SKILL.md   題材規則（提示詞的固定部分，以檔案維護）
├─ schema.py        PlanOut／ShotOut（Pydantic）：結構驗證與 JSON Schema 來源
├─ prompt_engine.py PromptEngine：build_prompt、propose_plans、build_shot_prompts、validate_plans
├─ claude.py        ClaudeClient 介面、AnthropicClaudeClient（Anthropic SDK）、ClaudeReply
└─ base.py          （S07）ShotDraft 新增 action_en、camera_en（選填）
backend/tests/fixtures/claude/
├─ valid_plans.json、invalid_json.txt、missing_photo.json、wrong_duration.json …
```

新增依賴：`anthropic`。

### Claude 介面（`app/creative/claude.py`）

```python
@dataclass(frozen=True)
class ClaudeReply:
    text: str                 # 模型輸出的文字（預期為 JSON）
    stop_reason: str | None

class ClaudeClient(Protocol):
    async def complete(self, *, system: str, messages: list[dict[str, str]], schema: dict[str, Any]) -> ClaudeReply

class AnthropicClaudeClient:
    """AsyncAnthropic；messages.stream(...).get_final_message()；
    model=settings.claude_model、max_tokens=16000、output_config={"effort": settings.claude_effort,
    "format": {"type": "json_schema", "schema": schema}}；
    settings.claude_refusal_fallback 時以 client.beta.messages 加上 betas=["server-side-fallback-2026-07-01"]、fallbacks="default"。"""
```

- 測試用 `RecordedClaude(replies: list[str])`：依序回傳 fixture，記錄每次收到的 `system`、`messages`、`schema`。
- API 錯誤（`anthropic.APIError` 家族，SDK 已自動重試）與 `stop_reason == "refusal"` 由 PromptEngine 轉成 `PlanGenerationError`，不進入「無效輸出重試」。

### 結構（`app/creative/schema.py`）

```python
class PlacementOut(BaseModel):  x: float[0,1]；y: float[0,1]；scale: float(0,1]；flip: bool
class ShotOut(BaseModel):  shot_no: 1|2|3；role: "hook"|"feature"|"cta"；duration_s: float>0；scene_photo_id: str；
                           placement: PlacementOut；action；action_en；subtitle；camera；camera_en（皆非空字串）
class PlanOut(BaseModel):  title；concept；tone；shots: list[ShotOut]（恰好 3，shot_no 與 role 依序）；cta
class PlansOut(BaseModel): plans: list[PlanOut]（2～3）
```

`extra="forbid"`；`PlansOut.model_json_schema()` 經過 `additionalProperties: false` 處理後送給 Claude。

### 語意驗證（`validate_plans(plans, ctx) -> list[str]`，回傳錯誤清單）

- 每個企劃 3 鏡長度合計 = 12 秒（容許 ±0.01）
- `scene_photo_id` 都在 `ctx.scene_photos` 中
- 擺放範圍（Pydantic 已檢查，語意層再檢查一次以產生可讀訊息）

### PromptEngine

```python
class PromptEngine:
    name = "prompt"
    def __init__(self, client: ClaudeClient, settings: Settings) -> None   # CLAUDE_MODEL 為空 → ConfigError(("CLAUDE_MODEL",))
    def build_prompt(self, ctx: PlanContext) -> tuple[str, str]           # (system, user)
    async def propose_plans(self, ctx: PlanContext) -> list[PlanDraft]
    async def build_shot_prompts(self, plan: PlanDraft, ctx: PlanContext) -> list[ShotPrompt]
```

- `system`：SKILL.md 的題材規則＋「只輸出符合 Schema 的 JSON」。
- `user`：品牌（語氣、賣點、資訊）、角色錨點卡（JSON 逐項列出）、實景照清單（`- ph_01：描述`）、主題、要求 3 個企劃。
- 重試：第 2 次呼叫在 `messages` 追加上一次的輸出（assistant）與錯誤說明（user：「上一次的輸出無效：…，請修正後重新輸出完整 JSON」）。
- `build_shot_prompts`：
  - 關鍵幀：`{錨點}; {action_en}; setting: {實景照描述}; keep the real background unchanged, match lighting and shadows, photorealistic, vertical 9:16, no text`
  - 影片：`{錨點}. {action_en}. Setting: {實景照描述}. Camera: {camera_en}. Keep the real background…; no on-screen text, no subtitles, no logos.`
  - 錨點：`anchor_card` 中 `anchor_en` 優先，否則以 `key: value` 串接。

### 設定與服務

- `claude_model: str = ""`、`claude_effort: Literal["low","medium","high","xhigh","max"] = "medium"`、`claude_refusal_fallback: bool = True`、`creative_engine: Literal["prompt","fake"] = "prompt"`。
- `build_services`：`prompt` → `PromptEngine(AnthropicClaudeClient(settings), settings)`；`fake` → `FakeCreativeEngine()`。
- `.env.example`：`CLAUDE_MODEL=claude-opus-5-5`（建議值）、`CLAUDE_EFFORT=medium`、`CREATIVE_ENGINE=prompt`。

## 資料模型／狀態轉換變更

無資料表變更；`plans.payload` 多了每鏡的 `action_en`、`camera_en`。

## API 契約（request／response、錯誤碼）

無新端點。企劃失敗沿用 S07／S08：影片 `failed`、事件 `planning_failed`。

## 失敗行為、安全與可觀測性

- `PlanGenerationError(reason)`：reason 只含驗證錯誤或錯誤類型，不含提示詞全文或金鑰。
- 每次呼叫記錄 `usage`（輸入／輸出 token）到日誌，供之後成本分析；不記錄提示詞與回應全文。

## 測試策略

| 需求 | 驗收條件 | 測試層級 | 測試位置 |
|---|---|---|---|
| R-001 | AC-001、AC-002 | BDD（S10-01）＋Unit | `backend/tests/bdd/test_s10_prompt_engine.py`、`backend/tests/unit/test_prompt_engine.py` |
| R-002 | AC-003、AC-004 | BDD（S10-02、S10-04） | 同上 |
| R-003 | AC-005 | BDD（S10-03）＋Unit | 同上 |
| R-004 | AC-006 | BDD（S10-05）＋Unit | 同上 |
| R-005 | AC-007 | BDD（S10-06） | 同上 |

> 實作發現：`anthropic` 1.x 改用 `httpx2`，`respx` 只能攔截 `httpx`，因此 `test_r006_*` 改以 `httpx2.MockTransport` 注入 `AnthropicClaudeClient(http_client=...)` 攔截請求，驗證內容不變（仍不連網）。送給 Claude 的 JSON Schema 以 SDK 的 `anthropic.transform_schema` 產生（加上 `additionalProperties: false`，並把 API 不支援的數值／長度限制移到 description；這些限制仍由 Pydantic 驗證）。S09 的 `test_r005_build_services_uses_s3` 改為指定 `creative_engine="fake"`，因為預設引擎 `prompt` 需要 `CLAUDE_MODEL`；斷言不變。
| R-006 | AC-008 | Unit | `backend/tests/unit/test_prompt_engine.py` |
| — | — | `@external`（不列入閘門） | `backend/tests/external/test_claude_live.py` |

- 預計單元測試（≥ 3，預計約 14）：
  - `test_r001_schema_rejects_missing_field`、`test_r001_schema_rejects_shot_count`、`test_r001_schema_rejects_role_order`
  - `test_r001_semantic_rejects_duration_sum`、`test_r001_semantic_rejects_unknown_photo`、`test_r001_rejects_plan_count`
  - `test_r003_refusal_raises`、`test_r003_api_error_raises`
  - `test_r004_prompt_lists_photos_with_id_and_description`
  - `test_r006_model_and_effort_from_settings`、`test_r006_missing_model_is_config_error`、`test_r006_build_services_selects_engine[prompt|fake]`
  - `test_r006_anthropic_client_request_shape`（以 `respx` 攔截 HTTP，驗證送出的 model、effort、output_config、fallbacks；不連網）

## ADR（影響公開 API、資料遷移、成本、外部供應商或安全性時必填）

- 決定：結構化輸出＋自行驗證＋最多重試一次。
- 替代方案：只靠結構化輸出、不重試；或最多重試多次。
- 取捨：語意規則無法以 Schema 保證，需要重試；限制為 2 次呼叫以控制延遲與費用（每次企劃最多兩次 Claude 呼叫）。
- 決定：生成提示詞以模板組成。
- 取捨：少一次 Claude 呼叫、結果可重現；缺點是提示詞較制式，S19 真實驗收後再評估是否改由 Claude 產生。
