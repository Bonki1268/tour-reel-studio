# 架構書 §4、§7（物件儲存路徑規則）
@S09 @integration
Feature: 物件儲存
  所有二進位資產存於 S3 相容儲存；前端以短期預簽名網址直接上傳與播放。

  Scenario: S09-01 上傳並讀回物件
    Given 測試用 MinIO 已啟動
    When 上傳一個 PNG 檔到 "projects/p1/scenes/ph_01.jpg"
    Then 可以讀回相同內容

  Scenario: S09-02 預簽名上傳網址可直接上傳
    Given 取得 "projects/p1/scenes/ph_02.jpg" 的預簽名上傳網址
    When 以 HTTP PUT 將檔案上傳到該網址
    Then 物件存在於儲存中

  Scenario: S09-03 物件路徑符合規則
    When 產生影片 "v1" 第 1 鏡第 2 次版本的關鍵幀路徑
    Then 路徑為 "videos/v1/shots/1/take2/keyframe.png"

  Scenario: S09-04 預簽名網址過期後失效
    Given 取得有效期 1 秒的預簽名下載網址
    When 等待 2 秒後下載
    Then 下載被拒絕
