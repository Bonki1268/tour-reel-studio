# 架構書 §9.3
@S17 @integration
Feature: Demo 專案種子資料
  以腳本建立可重複、可預期的 Demo 專案，現場不依賴外部擷取。

  Scenario: S17-01 種子腳本建立 Demo 專案
    Given 一個已遷移的空資料庫與空的物件儲存
    When 執行種子腳本
    Then 存在一個已確認品牌檔案的專案
    And 專案有 1 個已鎖定的角色，含身份板與去背全身圖
    And 專案有 3 到 5 張附文字描述的實景照

  Scenario: S17-02 重複執行不產生重複資料
    Given 種子腳本已執行過一次
    When 再次執行種子腳本
    Then 專案、角色與實景照的數量不變

  Scenario: S17-03 使用快取的官網擷取結果
    Given Firecrawl 無法連線
    And 存在官網擷取結果的快取檔
    When 執行種子腳本
    Then 種子腳本成功完成

  Scenario: S17-04 角色去背圖具透明背景
    When 執行種子腳本
    Then 角色去背圖為含 alpha 通道的 PNG
    And 圖片四個角落都是完全透明
