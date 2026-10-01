import { describe, expect, it } from "vitest";
import { buildApproveRequest, createApproveSession } from "./approve";

const placements = {
  1: { x: 0.8, y: 0.9, scale: 0.4, flip: false },
  2: { x: 0.3, y: 0.85, scale: 0.5, flip: true },
  3: { x: 0.5, y: 0.9, scale: 0.45, flip: false },
};

describe("[S15] buildApproveRequest", () => {
  it("組出 approve-plan 請求的網址、標頭與內容", () => {
    const req = buildApproveRequest({ videoId: "v1", planId: "p1", costCap: "40", placements, idempotencyKey: "k-1" });
    expect(req.url).toBe("/api/videos/v1/approve-plan");
    expect(req.init.method).toBe("POST");
    expect(req.init.headers["Idempotency-Key"]).toBe("k-1");
    expect(req.init.headers["Content-Type"]).toBe("application/json");
    expect(JSON.parse(req.init.body)).toEqual({ plan_id: "p1", cost_cap: "40", placements });
  });

  it("沒有 Idempotency-Key 時拒絕組裝", () => {
    expect(() => buildApproveRequest({ videoId: "v1", planId: "p1", costCap: "40", placements, idempotencyKey: "" })).toThrow();
  });

  it("同一企劃重送沿用同一個 key，改選企劃產生新 key", () => {
    let n = 0;
    const session = createApproveSession(() => `key-${++n}`);
    expect(session.keyFor("p1")).toBe("key-1");
    expect(session.keyFor("p1")).toBe("key-1");
    expect(session.keyFor("p2")).toBe("key-2");
  });

  it("預設以 crypto.randomUUID 產生 key", () => {
    const key = createApproveSession().keyFor("p1");
    expect(key).toMatch(/^[0-9a-f-]{36}$/);
  });
});
