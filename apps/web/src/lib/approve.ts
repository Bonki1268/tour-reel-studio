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
  throw new Error("not implemented");
}

/** 同一企劃重送沿用同一個 Idempotency-Key；改選企劃時產生新的。 */
export function createApproveSession(newKey: () => string = () => crypto.randomUUID()): {
  keyFor(planId: string): string;
} {
  throw new Error("not implemented");
}
