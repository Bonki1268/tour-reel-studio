// S15 選題與企劃確認（features/web/s15_plan_confirm.feature）
import { expect, type Page } from "@playwright/test";
import { createBdd } from "playwright-bdd";
import { test } from "../support/fixtures";
import { type MockApi, PROJECT_ID, plans } from "../support/mockApi";

const { Given, When, Then } = createBdd(test);

const topicInput = (page: Page) => page.getByLabel("宣傳主題");
const planCards = (page: Page) => page.getByTestId("plan-card");
const consent = (page: Page) => page.getByLabel(/同意.*成本上限/);
const approveButton = (page: Page) => page.getByRole("button", { name: "核准並開始生成" });

async function generatePlans(page: Page, api: MockApi): Promise<void> {
  await topicInput(page).fill("清晨採梅體驗");
  await page.getByRole("button", { name: "產生企劃" }).click();
  await expect(page.getByText("企劃產生中")).toBeVisible();
  api.emit("plan_ready");
  await expect(planCards(page)).toHaveCount(plans.length);
}

async function selectPlan(page: Page, api: MockApi, n: number): Promise<void> {
  if ((await planCards(page).count()) === 0) await generatePlans(page, api);
  await planCards(page).nth(n - 1).getByRole("button", { name: "選擇此企劃" }).click();
  await expect(page.getByTestId("placement-shot-1").locator("canvas").first()).toBeVisible();
}

/** 核准請求：還沒送出時勾選同意並按下核准。 */
async function approved(page: Page, api: MockApi) {
  if (!api.approve) {
    if (!(await consent(page).isChecked())) await consent(page).check();
    await approveButton(page).click();
    await expect.poll(() => api.approve).toBeTruthy();
  }
  return api.approve!;
}

Given("已開啟 Demo 專案頁面，API 以 mock 回應", async ({ page, api }) => {
  await api.install(page);
  await page.goto(`/projects/${PROJECT_ID}`);
  await expect(page.getByRole("heading", { name: "梅子農場" })).toBeVisible();
});

// S15-01

When("輸入主題 {string} 並送出", async ({ page }, topic: string) => {
  await expect(page.getByRole("button", { name: "產生企劃" })).toBeDisabled();
  await topicInput(page).fill(topic);
  await page.getByRole("button", { name: "產生企劃" }).click();
});

Then("畫面顯示企劃產生中", async ({ page, api }) => {
  await expect(page.getByText("企劃產生中")).toBeVisible();
  expect(api.createBody).toEqual({ topic: "清晨採梅體驗" });
});

Then("收到 {string} 事件後顯示 2 到 3 張企劃卡", async ({ page, api }, event: string) => {
  await expect(planCards(page)).toHaveCount(0);
  api.emit(event);
  await expect(planCards(page)).toHaveCount(plans.length);
  const count = await planCards(page).count();
  expect(count).toBeGreaterThanOrEqual(2);
  expect(count).toBeLessThanOrEqual(3);
});

// S15-02

When("點選品牌賣點 {string}", async ({ page }, label: string) => {
  await page.getByRole("button", { name: label, exact: true }).click();
});

Then("主題輸入框的內容包含 {string}", async ({ page, api }, text: string) => {
  await expect(topicInput(page)).toHaveValue(new RegExp(text));
  expect(api.createBody).toBeUndefined();
  await topicInput(page).fill("清晨採梅");
  await page.getByRole("button", { name: text, exact: true }).click();
  await expect(topicInput(page)).toHaveValue(`清晨採梅、${text}`);
});

// S15-03

Given("企劃已產生", async ({ page, api }) => {
  await generatePlans(page, api);
});

Then("每張企劃卡顯示 3 鏡的摘要", async ({ page }) => {
  for (const card of await planCards(page).all()) {
    await expect(card.getByTestId("shot-summary")).toHaveCount(3);
  }
  await expect(planCards(page).first()).toContainText("向鏡頭揮手");
});

Then("顯示預估點數與成本上限", async ({ page }) => {
  const first = planCards(page).first();
  await expect(first.getByTestId("estimate-total")).toHaveText("30 點");
  await expect(first.getByTestId("estimate-cap")).toHaveText("40 點");
  await expect(planCards(page).nth(1).getByTestId("estimate-cap")).toHaveText("1,234.5 點");
});

// S15-04

Given("已選擇第 {int} 個企劃", async ({ page, api }, n: number) => {
  await selectPlan(page, api, n);
});

When("在第 {int} 鏡的實景照上把角色拖到右下方", async ({ page }, n: number) => {
  const canvas = page.getByTestId(`placement-shot-${n}`).locator("canvas").first();
  // 擺放區在企劃卡下方，先像使用者一樣捲動到可視範圍
  await canvas.scrollIntoViewIfNeeded();
  const box = (await canvas.boundingBox())!;
  const initial = plans[0].payload.shots[n - 1].placement;
  // 從角色身體中段按下（腳底上方 1/4 身高），拖到照片右下方
  const grabX = box.x + initial.x * box.width;
  const grabY = box.y + (initial.y - initial.scale / 4) * box.height;
  await page.mouse.move(grabX, grabY);
  await page.mouse.down();
  await page.mouse.move(grabX + 0.5 * box.width, grabY + 0.25 * box.height, { steps: 12 });
  await page.mouse.up();
});

Then("送出的第 {int} 鏡擺放參數 x 大於 {float}", async ({ page, api }, n: number, value: number) => {
  const { body } = await approved(page, api);
  const placement = (body as { placements: Record<string, { x: number }> }).placements[String(n)];
  expect(placement.x).toBeGreaterThan(value);
  expect(placement.x).toBeLessThanOrEqual(1);
});

Then("送出的第 {int} 鏡擺放參數 y 大於 {float}", async ({ page, api }, n: number, value: number) => {
  const { body } = await approved(page, api);
  const placement = (body as { placements: Record<string, { y: number }> }).placements[String(n)];
  expect(placement.y).toBeGreaterThan(value);
  expect(placement.y).toBeLessThanOrEqual(1);
});

// S15-05

Given("尚未勾選同意成本上限", async ({ page }) => {
  await expect(consent(page)).not.toBeChecked();
});

Then("核准按鈕為停用狀態", async ({ page, api }) => {
  await expect(approveButton(page)).toBeDisabled();
  await consent(page).check();
  await expect(approveButton(page)).toBeEnabled();
  // 改選其他企劃時同意勾選自動取消
  await planCards(page).nth(1).getByRole("button", { name: "選擇此企劃" }).click();
  await expect(consent(page)).not.toBeChecked();
  await expect(approveButton(page)).toBeDisabled();
  expect(api.approve).toBeUndefined();
});

// S15-06

Given("已選擇第 {int} 個企劃並勾選同意成本上限", async ({ page, api }, n: number) => {
  await selectPlan(page, api, n);
  await consent(page).check();
});

When("按下核准", async ({ page, api }) => {
  await approveButton(page).click();
  await expect.poll(() => api.approve).toBeTruthy();
});

Then("approve-plan 請求帶有 Idempotency-Key 標頭", async ({ api }) => {
  expect(api.approve!.headers["idempotency-key"]).toMatch(/^[0-9a-f-]{36}$/);
});

Then("請求內容包含 plan_id、每鏡的擺放參數與 cost_cap", async ({ api }) => {
  const body = api.approve!.body as { plan_id: string; cost_cap: string; placements: Record<string, unknown> };
  expect(body.plan_id).toBe("plan-1");
  expect(body.cost_cap).toBe("40");
  expect(Object.keys(body.placements).sort()).toEqual(["1", "2", "3"]);
  expect(body.placements["3"]).toEqual({ x: 0.6, y: 0.9, scale: 0.45, flip: true });
});

Then("畫面進入生成進度頁", async ({ page }) => {
  await expect(page).toHaveURL(/\/videos\/v1$/);
  await expect(page.getByRole("heading", { name: "生成進度" })).toBeVisible();
});
