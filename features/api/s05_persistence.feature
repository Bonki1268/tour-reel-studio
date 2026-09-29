# 架構書 §7
@S05 @integration
Feature: 資料持久化
  資料寫入 PostgreSQL 後可完整讀回；鏡頭版本全部保留；生成工作不可重複建立。

  Scenario: S05-01 資料庫遷移可從零建立
    Given 一個空的資料庫
    When 執行所有 Alembic 遷移
    Then 架構書 §7 列出的資料表全部存在

  Scenario: S05-02 建立專案與品牌檔案
    Given 一個已遷移的空資料庫
    When 建立專案 "梅子農場" 並寫入品牌檔案
    Then 可以讀回相同的專案與品牌檔案內容

  Scenario: S05-03 重生鏡頭時保留所有版本
    Given 一支影片的第 1 鏡已有 1 個版本
    When 第 1 鏡重生
    Then 第 1 鏡有 2 個版本
    And 目前版本指向第 2 個版本
    And 第 1 個版本仍可讀取

  Scenario: S05-04 生成工作的冪等鍵不可重複
    Given 已存在冪等鍵為 "v1:1:keyframe:abc:1" 的生成工作
    When 再次建立相同冪等鍵的生成工作
    Then 回傳既有的生成工作而非建立新的

  Scenario: S05-05 時間軸 JSON 完整保存
    Given 一支影片有一份時間軸 JSON
    When 儲存後重新讀取
    Then 時間軸 JSON 與原本內容相同
