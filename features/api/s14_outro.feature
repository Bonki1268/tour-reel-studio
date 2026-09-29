# 架構書 §5.6
@S14
Feature: 片尾卡
  片尾卡由品牌檔案自動產生，包含 Logo、店名、地址與訂位 QR code。

  Background:
    Given 品牌主色為 "#C8553D"、店名為 "梅子農場"、地址為 "台南市楠西區"
    And 訂位網址為 "https://example.com/book"

  Scenario: S14-01 片尾卡使用品牌主色與 Logo
    Given 品牌檔案有 Logo
    When 產生片尾卡
    Then 片尾卡尺寸為 1080×1920
    And 背景主要顏色接近 "#C8553D"
    And 片尾卡包含 Logo

  Scenario: S14-02 QR code 可被解碼
    When 產生片尾卡
    Then 片尾卡上的 QR code 解碼為 "https://example.com/book"

  Scenario: S14-03 缺少 Logo 時以店名文字代替
    Given 品牌檔案沒有 Logo
    When 產生片尾卡
    Then 產生成功且不包含 Logo 圖層

  Scenario: S14-04 片尾卡轉為 3 秒影片段
    When 產生片尾影片段
    Then 影片段長度為 3 ± 0.1 秒
    And 影片段為 1080×1920、30fps
