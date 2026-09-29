# 架構書 §5.5、§6.2
@S06
Feature: 生成工作與重試
  每個生成工作都經過固定的狀態流程，失敗會自動重試一次，而且不會重複扣點。

  Scenario: S06-01 工作成功後轉存結果
    Given FakeProvider 設定為成功
    When 執行一個關鍵幀生成工作
    Then 工作狀態依序為 "queued", "submitted", "running", "succeeded", "stored"
    And 結果已存入物件儲存
    And 工作記錄外部 request ID

  Scenario: S06-02 失敗後自動重試一次
    Given FakeProvider 設定為第 1 次失敗、第 2 次成功
    When 執行一個影片生成工作
    Then 工作最終狀態為 "stored"
    And 工作共送出 2 次

  Scenario: S06-03 重試後仍失敗
    Given FakeProvider 設定為永遠失敗
    When 執行一個影片生成工作
    Then 工作最終狀態為 "failed_final"
    And 工作共送出 2 次
    And 所屬影片狀態變為 "needs_attention"

  Scenario: S06-04 逾時視為失敗並觸發重試
    Given FakeProvider 設定為永不完成
    And 工作逾時設定為 1 秒
    When 執行一個影片生成工作
    Then 工作被判定為逾時失敗並觸發重試

  Scenario: S06-05 重複執行相同工作不重複扣點
    Given 一個已成功並已記帳的工作
    When 以相同冪等鍵再次執行
    Then 不會再次呼叫供應商
    And 成本帳沒有新增紀錄

  Scenario: S06-06 送出前檢查核准與預算
    Given 企劃已核准但第 1 鏡的輸入在核准後被修改
    When 執行第 1 鏡的關鍵幀生成工作
    Then 不會呼叫供應商
    And 影片退回 "plan_ready"
