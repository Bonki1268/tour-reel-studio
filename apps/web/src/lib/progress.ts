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
  | { type: "event"; event: ProgressEvent & { at?: string; status?: string } }
  | { type: "connection"; state: "open" | "lost" };

export const initialState: ProgressState = {
  status: "generating",
  shots: {},
  previewUrl: null,
  costCap: null,
  spent: "0",
  connection: "open",
};

/** 快照：鏡頭版本的 status 後端不更新，改以影片段／關鍵幀是否已存入判斷；需要處理時未完成的鏡頭視為失敗。 */
export function fromSnapshot(video: VideoOut, connection: "open" | "lost" = "open"): ProgressState {
  const shots: Record<number, ShotProgress> = {};
  for (const shot of video.shots) {
    const take = shot.take;
    let state: ShotState = take?.clip_key ? "done" : take?.keyframe_key ? "running" : "waiting";
    if (state !== "done" && video.status === "needs_attention") state = "failed";
    shots[shot.shot_no] = { state, at: null, reason: null, regenCost: String(shot.regen_cost ?? "0") };
  }
  return {
    status: video.status,
    shots,
    previewUrl: video.preview_url ?? null,
    costCap: video.cost_cap === null || video.cost_cap === undefined ? null : String(video.cost_cap),
    spent: String(video.spent),
    connection,
  };
}

const STATUS_EVENTS: Record<string, string> = {
  needs_attention: "needs_attention",
  render_started: "rendering",
  review_ready: "review",
  render_failed: "needs_attention",
};

function shotEvent(state: ProgressState, event: ProgressEvent & { at?: string }): ProgressState {
  const no = event.shot_no;
  if (typeof no !== "number") return state;
  const current = state.shots[no] ?? { state: "waiting" as ShotState, at: null, reason: null, regenCost: "0" };
  const at = event.at ?? null;
  // 亂序保護：同一鏡較舊（或相同時間）的事件忽略
  if (at && current.at && at <= current.at) return state;
  const next: Record<string, ShotState> = { shot_started: "running", shot_done: "done", shot_failed: "failed" };
  const reason = event.type === "shot_failed" ? String(event.data?.reason ?? "生成失敗") : null;
  return {
    ...state,
    shots: { ...state.shots, [no]: { ...current, state: next[event.type], at: at ?? current.at, reason } },
  };
}

export function reduce(state: ProgressState, action: ProgressAction): ProgressState {
  switch (action.type) {
    case "snapshot":
      return fromSnapshot(action.video, "open");
    case "connection":
      return state.connection === action.state ? state : { ...state, connection: action.state };
    case "event": {
      const e = action.event;
      if (e.type === "shot_started" || e.type === "shot_done" || e.type === "shot_failed") return shotEvent(state, e);
      if (e.type === "status") {
        const status = e.status ?? (e.data?.status as string | undefined);
        return status ? { ...state, status } : state;
      }
      if (e.type === "approved") {
        return e.data?.kind === "final" ? { ...state, status: "approved" } : { ...state, status: "generating" };
      }
      const status = STATUS_EVENTS[e.type];
      return status ? { ...state, status } : state;
    }
  }
}
