// SSE 訂閱＋斷線重連（spec 0016 R-005）：錯誤時關閉連線並依退避時間重建；重連成功後通知呼叫端補回快照。
// 連線收到資料後才結束（例如代理伺服器逾時）時靜默重連；連不上或尚未收到資料就中斷才顯示「連線中斷」。
import { createBackoff } from "@/lib/backoff";
import type { ProgressEvent } from "./events";

export const PROGRESS_EVENTS = [
  "status",
  "shot_started",
  "shot_done",
  "shot_failed",
  "needs_attention",
  "render_started",
  "review_ready",
  "render_failed",
  "approved",
] as const;

type Handlers = {
  onEvent: (event: ProgressEvent) => void;
  onConnection: (state: "open" | "lost") => void;
  onReconnected: () => void;
};

export function subscribeWithReconnect(videoId: string, handlers: Handlers): () => void {
  const backoff = createBackoff();
  let source: EventSource | null = null;
  let timer: ReturnType<typeof setTimeout> | null = null;
  let lost = false;
  let errored = false;
  let closed = false;

  const connect = () => {
    if (closed) return;
    let received = false;
    source = new EventSource(`/api/videos/${encodeURIComponent(videoId)}/events`);
    source.onopen = () => {
      backoff.reset();
      if (lost) {
        lost = false;
        handlers.onConnection("open");
      }
      if (errored) {
        errored = false;
        handlers.onReconnected();
      }
    };
    source.onerror = () => {
      source?.close();
      source = null;
      if (closed) return;
      errored = true;
      if (!received && !lost) {
        lost = true;
        handlers.onConnection("lost");
      }
      timer = setTimeout(connect, backoff.next() * 1000);
    };
    for (const type of PROGRESS_EVENTS) {
      source.addEventListener(type, (message) => {
        received = true;
        try {
          handlers.onEvent(JSON.parse((message as MessageEvent<string>).data) as ProgressEvent);
        } catch {
          handlers.onEvent({ type });
        }
      });
    }
  };

  connect();
  return () => {
    closed = true;
    if (timer) clearTimeout(timer);
    source?.close();
  };
}
