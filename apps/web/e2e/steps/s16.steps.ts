// S16 生成進度與成品確認（features/web/s16_progress_review.feature）
import { expect, type Page } from "@playwright/test";
import { createBdd } from "playwright-bdd";
import { test } from "../support/fixtures";
import { PREVIEW_URL, type ProgressMock, VIDEO_ID } from "../support/progressMock";

const { Given, When, Then } = createBdd(test);

const shotCard = (page: Page, n: number) => page.getByTestId(`shot-${n}`);
const regenButton = (page: Page, n: number) => shotCard(page, n).getByRole("button", { name: /重生/ });

async function reload(page: Page, progress: ProgressMock): Promise<void> {
  const before = progress.videoGets;
  await page.reload();
  await expect.poll(() => progress.videoGets).toBeGreaterThan(before);
}

Given("已開啟一支生成中影片的進度頁，API 以 mock 回應", async ({ page, context, progress }) => {
  await progress.install(page, context);
  await page.goto(`/videos/${VIDEO_ID}`);
  await expect(page.getByRole("heading", { name: "生成進度" })).toBeVisible();
  await expect(shotCard(page, 1)).toBeVisible();
});

// S16-01

When("依序收到第 1、2、3 鏡的 {string} 事件", async ({ progress }, type: string) => {
  for (const n of [1, 2, 3]) progress.push({ type, shot_no: n });
});

Then("3 鏡都顯示為完成", async ({ page }) => {
  for (const n of [1, 2, 3]) await expect(shotCard(page, n)).toContainText("完成");
});

// S16-02

When("收到影片狀態為 {string}、第 {int} 鏡失敗的事件", async ({ progress }, status: string, n: number) => {
  progress.push({ type: "shot_done", shot_no: 1 }, { type: "shot_done", shot_no: 3 });
  progress.push({ type: "shot_failed", shot_no: n, data: { reason: "生成逾時" } }, { type: status });
});

Then("第 {int} 鏡顯示失敗與重生按鈕", async ({ page }, n: number) => {
  await expect(shotCard(page, n)).toContainText("失敗");
  await expect(regenButton(page, n)).toBeVisible();
  for (const other of [1, 2, 3].filter((x) => x !== n)) await expect(regenButton(page, other)).toHaveCount(0);
});

Then("重生按鈕旁顯示所需點數", async ({ page }) => {
  await expect(shotCard(page, 2).getByTestId("regen-cost")).toHaveText("35 點");
});

// S16-03

When("收到 {string} 事件", async ({ progress }, type: string) => {
  progress.push({ type: "shot_done", shot_no: 1 }, { type: "shot_done", shot_no: 2 }, { type: "shot_done", shot_no: 3 });
  progress.push({ type: "render_started" }, { type });
});

Then("畫面顯示可播放的成品", async ({ page }) => {
  const video = page.locator("video");
  await expect(video).toBeVisible();
  await expect(video).toHaveAttribute("src", PREVIEW_URL);
  await expect(video).toHaveAttribute("controls", "");
});

Then("按下下載會開啟預簽名下載網址", async ({ page, context }) => {
  const opened = context.waitForEvent("page");
  await page.getByRole("button", { name: "下載" }).click();
  const tab = await opened;
  expect(tab.url()).toBe(PREVIEW_URL);
});

// S16-04

Given("影片狀態為 {string}，剩餘預算 {int} 點", async ({ page, progress }, status: string, budget: number) => {
  progress.status = status;
  progress.shots.forEach((s) => Object.assign(s, { keyframe: true, clip: true }));
  progress.previewUrl = PREVIEW_URL;
  progress.spent = "120";
  progress.costCap = String(120 + budget);
  await reload(page, progress);
  await expect(page.getByTestId("remaining-budget")).toHaveText(`${budget} 點`);
});

When("對第 {int} 鏡按下重生，所需 {int} 點", async ({ page, progress }, n: number, cost: number) => {
  expect(progress.shots[n - 1].regen_cost).toBe(String(cost));
  await expect(shotCard(page, n).getByTestId("regen-cost")).toHaveText(`${cost} 點`);
  await regenButton(page, n).click();
});

Then("顯示超出預算的確認對話框", async ({ page }) => {
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText("20 點");
  await expect(dialog).toContainText("35 點");
  await expect(dialog).toContainText("155 點");
});

Then("未確認前不送出重生請求", async ({ page, progress }) => {
  await page.waitForTimeout(300);
  expect(progress.regenerate).toEqual([]);
  await page.getByRole("dialog").getByRole("button", { name: "取消" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  expect(progress.regenerate).toEqual([]);
  // 再按一次並確認：帶新的成本上限送出
  await regenButton(page, 3).click();
  await page.getByRole("dialog").getByRole("button", { name: "同意提高上限並重生" }).click();
  await expect.poll(() => progress.regenerate).toEqual([{ shotNo: 3, body: { cost_cap: "155" } }]);
});

// S16-05

When("SSE 連線中斷", async ({ page, progress }) => {
  await expect.poll(() => progress.connections).toBeGreaterThanOrEqual(1);
  // 中斷期間後端已進入成品確認
  progress.status = "review";
  progress.previewUrl = PREVIEW_URL;
  progress.shots.forEach((s) => Object.assign(s, { keyframe: true, clip: true }));
  progress.disconnect();
  await expect(page.getByText("連線中斷")).toBeVisible();
});

Then("前端重新連線", async ({ progress }) => {
  await expect.poll(() => progress.connections, { timeout: 10_000 }).toBeGreaterThanOrEqual(2);
});

Then("重新取得 GET \\/videos\\/\\{id} 的最新狀態", async ({ page, progress }) => {
  await expect.poll(() => progress.videoGets).toBeGreaterThanOrEqual(2);
  await expect(page.locator("video")).toHaveAttribute("src", PREVIEW_URL);
  for (const n of [1, 2, 3]) await expect(shotCard(page, n)).toContainText("完成");
  await expect(page.getByText("連線中斷")).toHaveCount(0);
});

// S16-06

Given("影片狀態為 {string}", async ({ page, progress }, status: string) => {
  progress.status = status;
  progress.shots.forEach((s) => Object.assign(s, { keyframe: true, clip: true }));
  progress.previewUrl = PREVIEW_URL;
  await reload(page, progress);
});

When("按下「確認成品」", async ({ page }) => {
  await page.getByRole("button", { name: "確認成品" }).click();
});

Then("送出 POST \\/videos\\/\\{id}\\/approve", async ({ progress }) => {
  await expect.poll(() => progress.approveCalls).toBe(1);
});

Then("畫面顯示已完成", async ({ page }) => {
  await expect(page.getByText("已完成")).toBeVisible();
  await expect(page.getByRole("button", { name: "確認成品" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "下載" })).toBeVisible();
});
