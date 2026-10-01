"use client";

type Props = {
  status: string;
  previewUrl: string;
  busy: boolean;
  onDownload: () => void;
  onApprove: () => void;
};

/** 成品播放、下載與確認（spec 0016 R-003、R-006）。 */
export default function ResultPanel({ status, previewUrl, busy, onDownload, onApprove }: Props) {
  return (
    <section className="result" aria-label="成品">
      <video src={previewUrl} controls playsInline preload="metadata" />
      <div className="actions">
        <button type="button" onClick={onDownload} disabled={busy}>
          下載
        </button>
        {status === "review" && (
          <button type="button" className="primary" onClick={onApprove} disabled={busy}>
            確認成品
          </button>
        )}
      </div>
      {status === "approved" && <p className="done">已完成</p>}
    </section>
  );
}
