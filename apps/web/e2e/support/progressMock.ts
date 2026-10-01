// 進度頁的 API mock（spec 0016）：影片快照與 SSE 事件同步更新；每次 SSE 連線送出排隊中的事件後結束，
// 或由步驟主動中斷（route.abort）以模擬斷線
import type { BrowserContext, Page, Request, Route } from "@playwright/test";

export const VIDEO_ID = "v1";
export const PREVIEW_URL = "https://storage.test/videos/v1/renders/r1.mp4?X-Amz-Signature=preview";
export const DOWNLOAD_URL = "https://storage.test/videos/v1/renders/r1.mp4?X-Amz-Signature=download";

type Shot = { shot_no: number; keyframe: boolean; clip: boolean; regen_cost: string };
type SseEvent = { type: string; shot_no?: number | null; data?: Record<string, unknown> };

export class ProgressMock {
  status = "generating";
  costCap = "140";
  spent = "60";
  previewUrl: string | null = null;
  shots: Shot[] = [1, 2, 3].map((n) => ({ shot_no: n, keyframe: false, clip: false, regen_cost: "35" }));
  connections = 0;
  videoGets = 0;
  regenerate: { shotNo: number; body: unknown }[] = [];
  approveCalls = 0;
  private queue: SseEvent[] = [];
  private waiting: (() => void) | null = null;
  private drop: (() => void) | null = null;
  private seconds = 0;

  async install(page: Page, context: BrowserContext): Promise<void> {
    await context.route("https://storage.test/**", (route) =>
      route.fulfill({ contentType: "video/mp4", body: Buffer.from("fake-mp4") }),
    );
    await page.route("**/api/**", (route, request) => this.handle(route, request));
  }

  /** 送出事件並同步更新快照（重連後的 GET 會看到一致的狀態）。 */
  push(...events: SseEvent[]): void {
    for (const e of events) this.apply(e);
    this.queue.push(...events);
    this.waiting?.();
  }

  /** 中斷目前的 SSE 連線。 */
  disconnect(): void {
    this.drop?.();
  }

  private apply(e: SseEvent): void {
    const shot = this.shots.find((s) => s.shot_no === e.shot_no);
    if (e.type === "shot_started" && shot) shot.keyframe = true;
    if (e.type === "shot_done" && shot) Object.assign(shot, { keyframe: true, clip: true });
    if (e.type === "needs_attention" || e.type === "render_failed") this.status = "needs_attention";
    if (e.type === "render_started") this.status = "rendering";
    if (e.type === "review_ready") {
      this.status = "review";
      this.previewUrl = PREVIEW_URL;
    }
  }

  video() {
    return {
      id: VIDEO_ID,
      project_id: "demo",
      status: this.status,
      topic: "清晨採梅體驗",
      plans: [],
      selected_plan_id: "plan-1",
      shots: this.shots.map((s) => ({
        shot_no: s.shot_no,
        role: ["hook", "feature", "cta"][s.shot_no - 1],
        duration_s: [4, 5, 3][s.shot_no - 1],
        placement: null,
        regen_cost: s.regen_cost,
        take: { attempt: 1, status: "pending", keyframe_key: s.keyframe ? `k${s.shot_no}` : null,
          clip_key: s.clip ? `c${s.shot_no}` : null },
      })),
      cost_cap: this.costCap,
      spent: this.spent,
      preview_url: this.previewUrl,
    };
  }

  private sse(events: SseEvent[]): string {
    return events
      .map((e) => {
        this.seconds += 1;
        const at = new Date(Date.UTC(2026, 9, 1, 9, 0, this.seconds)).toISOString();
        const body = { type: e.type, video_id: VIDEO_ID, at, shot_no: e.shot_no ?? null, data: e.data ?? {} };
        return `event: ${e.type}\ndata: ${JSON.stringify(body)}\n\n`;
      })
      .join("");
  }

  private async handle(route: Route, request: Request): Promise<void> {
    const path = new URL(request.url()).pathname.replace(/^\/api/, "");
    const method = request.method();
    if (method === "GET" && path === `/videos/${VIDEO_ID}`) {
      this.videoGets += 1;
      return route.fulfill({ json: this.video() });
    }
    if (method === "GET" && path === `/videos/${VIDEO_ID}/events`) {
      this.connections += 1;
      const outcome = await new Promise<"events" | "drop">((resolve) => {
        if (this.queue.length) return resolve("events");
        this.waiting = () => resolve("events");
        this.drop = () => resolve("drop");
      });
      this.waiting = this.drop = null;
      if (outcome === "drop") return route.abort("connectionreset");
      const events = this.queue.splice(0);
      return route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        body: this.sse([{ type: "status", data: { status: this.status } }, ...events]),
      });
    }
    const regen = path.match(new RegExp(`^/videos/${VIDEO_ID}/shots/(\\d+)/regenerate$`));
    if (method === "POST" && regen) {
      const body = request.postData() ? request.postDataJSON() : null;
      this.regenerate.push({ shotNo: Number(regen[1]), body });
      if (body?.cost_cap) this.costCap = String(body.cost_cap);
      this.status = "generating";
      return route.fulfill({ status: 202, json: this.video() });
    }
    if (method === "POST" && path === `/videos/${VIDEO_ID}/approve`) {
      this.approveCalls += 1;
      this.status = "approved";
      return route.fulfill({ json: this.video() });
    }
    if (method === "GET" && path === `/videos/${VIDEO_ID}/download`) {
      return route.fulfill({ json: { url: DOWNLOAD_URL, expires_at: "2026-10-01T10:00:00Z" } });
    }
    return route.fulfill({ status: 404, json: { code: "not_found", message: `mock 沒有 ${method} ${path}` } });
  }
}
