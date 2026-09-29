# 架構書 §5.4
@S10
Feature: 企劃產生（PromptEngine）
  以 tourism-promo 模板呼叫 Claude，輸出必須符合固定的 15 秒、3 鏡結構。

  Background:
    Given 使用預錄的 Claude 回應 fixture
    And 一個品牌語氣為 "親切台味"、含 3 張實景照的專案

  Scenario: S10-01 產生符合結構的企劃
    When 以主題 "清晨採梅體驗" 產生企劃
    Then 回傳 2 到 3 個企劃
    And 每個企劃有 3 鏡，功能依序為 "hook", "feature", "cta"
    And 3 鏡長度合計 12 秒
    And 每鏡引用的實景照都存在於專案中
    And 每鏡的擺放參數 x、y、scale 都介於 0 到 1

  Scenario: S10-02 輸出不符 Schema 時重試一次
    Given Claude 第 1 次回傳無效 JSON，第 2 次回傳有效企劃
    When 以主題 "清晨採梅體驗" 產生企劃
    Then 成功回傳企劃
    And 共呼叫 Claude 2 次

  Scenario: S10-03 連續兩次無效時失敗
    Given Claude 連續回傳無效 JSON
    When 以主題 "清晨採梅體驗" 產生企劃
    Then 應拋出企劃產生錯誤

  Scenario: S10-04 引用不存在的實景照視為無效輸出
    Given Claude 第 1 次回傳引用 "ph_99" 的企劃，第 2 次回傳有效企劃
    When 以主題 "清晨採梅體驗" 產生企劃
    Then 成功回傳企劃
    And 共呼叫 Claude 2 次

  Scenario: S10-05 提示詞包含品牌與角色資訊
    When 組出送給 Claude 的提示詞
    Then 提示詞包含品牌語氣 "親切台味"
    And 提示詞包含角色身份錨點
    And 提示詞包含每張實景照的描述
    And 提示詞要求以繁體中文輸出

  Scenario: S10-06 產生每鏡的生成提示詞
    Given 一個已核准的企劃
    When 產生 3 鏡的生成提示詞
    Then 每鏡都有關鍵幀提示詞與影片提示詞
    And 影片提示詞包含鏡頭運動描述
