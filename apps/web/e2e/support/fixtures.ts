import { test as base } from "playwright-bdd";
import { MockApi } from "./mockApi";
import { ProgressMock } from "./progressMock";

export const test = base.extend<{ api: MockApi; progress: ProgressMock }>({
  // 第二個參數不命名為 use，避免被 React Hooks 規則誤判
  api: async ({}, provide) => {
    await provide(new MockApi());
  },
  progress: async ({}, provide) => {
    await provide(new ProgressMock());
  },
});
