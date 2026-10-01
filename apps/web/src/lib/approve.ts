// 核准請求組裝（spec 0015 R-006）
import type { Placement } from "./placement";

export type ApproveInput = {
  videoId: string;
  planId: string;
  costCap: string;
  placements: Record<number, Placement>;
  idempotencyKey: string;
};

export type ApproveRequest = {
  url: string;
  init: { method: "POST"; headers: Record<string, string>; body: string };
};

export function buildApproveRequest(input: ApproveInput): ApproveRequest {
  if (!input.idempotencyKey) throw new Error("核准請求必須帶 Idempotency-Key");
  return {
    url: `/api/videos/${encodeURIComponent(input.videoId)}/approve-plan`,
    init: {
      method: "POST",
      headers: { "Content-Type": "application/json", "Idempotency-Key": input.idempotencyKey },
      body: JSON.stringify({ plan_id: input.planId, cost_cap: input.costCap, placements: input.placements }),
    },
  };
}

/** 同一企劃重送沿用同一個 Idempotency-Key；改選企劃時產生新的。 */
export function createApproveSession(newKey: () => string = () => crypto.randomUUID()): {
  keyFor(planId: string): string;
} {
  const keys = new Map<string, string>();
  return {
    keyFor(planId) {
      let key = keys.get(planId);
      if (!key) {
        key = newKey();
        keys.set(planId, key);
      }
      return key;
    },
  };
}
