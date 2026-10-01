import { describe, expect, it } from "vitest";
import type { VideoOut } from "@/api/client";
import { fromSnapshot, initialState, reduce, type ProgressState } from "./progress";

const at = (s: number) => new Date(Date.UTC(2026, 9, 1, 9, 0, s)).toISOString();
const ev = (type: string, shot_no: number | null, seconds: number, data: Record<string, unknown> = {}) =>
  ({ type: "event", event: { type, video_id: "v1", shot_no, at: at(seconds), data } }) as const;

function video(overrides: Partial<VideoOut> = {}): VideoOut {
  const take = (n: number, keyframe: boolean, clip: boolean) => ({
    attempt: 1, status: "pending",
    keyframe_key: keyframe ? `k${n}` : null, clip_key: clip ? `c${n}` : null,
  });
  return {
    id: "v1", project_id: "p1", status: "generating", topic: "t", plans: [], selected_plan_id: "plan-1",
    shots: [
      { shot_no: 1, role: "hook", duration_s: 4, placement: null, take: take(1, true, true), regen_cost: "35" },
      { shot_no: 2, role: "feature", duration_s: 5, placement: null, take: take(2, true, false), regen_cost: "35" },
      { shot_no: 3, role: "cta", duration_s: 3, placement: null, take: take(3, false, false), regen_cost: "35" },
    ],
    cost_cap: "140", spent: "70", preview_url: null,
    ...overrides,
  } as VideoOut;
}

const base = (): ProgressState => fromSnapshot(video());

describe("[S16] progress reducer", () => {
  it("快照：依關鍵幀與影片段判斷鏡頭進度", () => {
    expect(base().shots[1].state).toBe("done");
    expect(base().shots[2].state).toBe("running");
    expect(base().shots[3].state).toBe("waiting");
    expect(base().shots[2].regenCost).toBe("35");
    expect([base().costCap, base().spent, base().status]).toEqual(["140", "70", "generating"]);
  });

  it("needs_attention 快照：尚未完成的鏡頭視為失敗", () => {
    const s = fromSnapshot(video({ status: "needs_attention" }));
    expect([s.shots[1].state, s.shots[2].state, s.shots[3].state]).toEqual(["done", "failed", "failed"]);
  });

  it("依序事件：開始 → 完成", () => {
    let s = reduce(base(), ev("shot_started", 3, 10));
    expect(s.shots[3].state).toBe("running");
    s = reduce(s, ev("shot_done", 3, 20));
    expect(s.shots[3].state).toBe("done");
  });

  it("亂序：較舊的 shot_started 晚到時不會讓完成退回生成中", () => {
    let s = reduce(base(), ev("shot_done", 3, 20));
    s = reduce(s, ev("shot_started", 3, 10));
    expect(s.shots[3].state).toBe("done");
  });

  it("重複事件不改變結果", () => {
    const once = reduce(base(), ev("shot_done", 2, 20));
    expect(reduce(once, ev("shot_done", 2, 20))).toEqual(once);
  });

  it("失敗與重生：新的 shot_started 蓋過失敗與完成", () => {
    let s = reduce(base(), ev("shot_failed", 2, 30, { reason: "timeout" }));
    expect(s.shots[2]).toMatchObject({ state: "failed", reason: "timeout" });
    s = reduce(s, ev("needs_attention", null, 31));
    expect(s.status).toBe("needs_attention");
    s = reduce(s, ev("shot_started", 2, 60));
    expect(s.shots[2]).toMatchObject({ state: "running", reason: null });
    s = reduce(s, ev("shot_started", 1, 61));
    expect(s.shots[1].state).toBe("running");
  });

  it("整體狀態事件", () => {
    let s = reduce(base(), ev("render_started", null, 40));
    expect(s.status).toBe("rendering");
    s = reduce(s, ev("review_ready", null, 50, { render_id: "r1" }));
    expect(s.status).toBe("review");
    s = reduce(s, ev("approved", null, 70, { kind: "final" }));
    expect(s.status).toBe("approved");
    expect(reduce(base(), ev("render_failed", null, 45)).status).toBe("needs_attention");
    expect(reduce(base(), { type: "event", event: { type: "status", status: "review" } as never }).status).toBe("review");
  });

  it("連線狀態與快照覆蓋", () => {
    const lost = reduce(base(), { type: "connection", state: "lost" });
    expect(lost.connection).toBe("lost");
    const restored = reduce(lost, { type: "snapshot", video: video({ status: "review", preview_url: "https://x/p.mp4" }) });
    expect(restored.status).toBe("review");
    expect(restored.previewUrl).toBe("https://x/p.mp4");
    expect(restored.connection).toBe("open");
    expect(initialState.shots).toEqual({});
  });
});
