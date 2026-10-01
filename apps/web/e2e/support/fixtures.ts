import { test as base } from "playwright-bdd";
import { MockApi } from "./mockApi";

export const test = base.extend<{ api: MockApi }>({
  api: async ({}, use) => {
    await use(new MockApi());
  },
});
