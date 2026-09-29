# 架構書 §2.3（構想文件）、§6.3
@S03
Feature: 核准與失效
  花錢的步驟必須經過使用者核准；核准後內容若被修改，核准即失效。

  Scenario: S03-01 核准記錄輸入雜湊與成本上限
    Given 一支狀態為 "plan_ready" 的影片，已選定企劃 "P1"
    When 使用者以成本上限 140 點核准企劃
    Then 產生一筆類型為 "plan" 的核准紀錄
    And 核准紀錄包含企劃與擺放內容的輸入雜湊
    And 核准紀錄的成本上限為 140 點

  Scenario: S03-02 輸入雜湊與欄位順序無關
    Given 兩份內容相同但欄位順序不同的企劃資料
    When 分別計算輸入雜湊
    Then 兩個雜湊相同

  Scenario: S03-03 內容未變時允許送出生成
    Given 企劃 "P1" 已被核准
    When 系統在送出生成工作前重新計算輸入雜湊
    Then 雜湊與核准紀錄一致
    And 允許送出生成工作

  Scenario: S03-04 核准後修改內容使核准失效
    Given 企劃 "P1" 已被核准
    And 第 2 鏡的角色擺放被修改
    When 系統在送出生成工作前重新計算輸入雜湊
    Then 拒絕送出生成工作
    And 影片退回 "plan_ready" 等待重新確認

  Scenario: S03-05 快速模式自動採用的項目被標記
    Given 一支快速模式的影片
    When 系統自動採用建議的腳本
    Then 產生一筆 auto_approved 為 true 的核准紀錄
