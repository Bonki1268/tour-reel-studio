// 進度頁狀態：SSE 事件與 GET /videos/{id} 快照 → 畫面（spec 0016 R-001、R-005）
import type { VideoOut } from "@/api/client";
import type { ProgressEvent } from "@/api/events";

export type ShotState = "waiting" | "running" | "done" | "failed";
export type ShotProgress = { state: ShotState; at: string | null; reason: string | null; regenCost: string };
export type ProgressState = {
  status: string;
  shots: Record<number, ShotProgress>;
  previewUrl: string | null;
  costCap: string | null;
  spent: string;
  connection: "open" | "lost";
};

export type ProgressAction =
  | { type: "snapshot"; video: VideoOut }
  | { type: "event"; event: ProgressEvent & { at?: string } }
  | { type: "connection"; state: "open" | "lost" };

export const initialState: ProgressState = {
  status: "generating",
  shots: {},
  previewUrl: null,
  costCap: null,
  spent: "0",
  connection: "open",
};

export function fromSnapshot(video: VideoOut, connection: "open" | "lost" = "open"): ProgressState {
  throw new Error("not implemented");
}

export function reduce(state: ProgressState, action: ProgressAction): ProgressState {
  throw new Error("not implemented");
}
