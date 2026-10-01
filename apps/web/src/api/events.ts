// 影片進度 SSE（GET /videos/{id}/events）；事件名稱即事件類型
export type ProgressEvent = { type: string; video_id?: string; shot_no?: number | null; data?: Record<string, unknown> };

export function subscribeVideo(
  videoId: string,
  handlers: Record<string, (event: ProgressEvent) => void>,
): () => void {
  const source = new EventSource(`/api/videos/${encodeURIComponent(videoId)}/events`);
  for (const [type, handler] of Object.entries(handlers)) {
    source.addEventListener(type, (message) => {
      try {
        handler(JSON.parse((message as MessageEvent<string>).data) as ProgressEvent);
      } catch {
        handler({ type });
      }
    });
  }
  return () => source.close();
}
