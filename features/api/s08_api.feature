# 架構書 §8
@S08
Feature: REST API
  前端透過 REST 與 SSE 操作影片；狀態不符時回應 409，重複核准不會重複扣點。

  Background:
    Given 一個含品牌檔案、1 個已鎖定角色與 3 張實景照的專案

  Scenario: S08-01 建立影片並觸發企劃產生
    When 以主題 "清晨採梅體驗" 呼叫 POST /projects/{id}/videos
    Then 回應狀態碼為 201
    And 影片狀態為 "planning"

  Scenario: S08-02 核准企劃的冪等性
    Given 影片狀態為 "plan_ready"
    When 以相同 Idempotency-Key 呼叫 POST /videos/{id}/approve-plan 兩次
    Then 兩次都回應 202
    And 只建立一組生成工作

  Scenario: S08-03 缺少成本上限時拒絕核准
    Given 影片狀態為 "plan_ready"
    When 呼叫 POST /videos/{id}/approve-plan 但沒有提供 cost_cap
    Then 回應狀態碼為 422

  Scenario: S08-04 狀態不符時回應 409
    Given 影片狀態為 "generating"
    When 呼叫 POST /videos/{id}/plans/regenerate
    Then 回應狀態碼為 409

  Scenario: S08-05 SSE 推送進度
    Given 已訂閱 GET /videos/{id}/events
    When 影片狀態變為 "plan_ready"
    Then 收到事件 "plan_ready"

  Scenario: S08-06 下載成品使用短期預簽名網址
    Given 影片狀態為 "approved"
    When 呼叫 GET /videos/{id}/download
    Then 回應包含有效期不超過 15 分鐘的下載網址

  Scenario: S08-07 取得影片狀態包含企劃、鏡頭與成本
    Given 影片狀態為 "review"
    When 呼叫 GET /videos/{id}
    Then 回應包含 status、plans、shots、cost_cap 與 spent
