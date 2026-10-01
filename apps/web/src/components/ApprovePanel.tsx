"use client";

import { formatCredits } from "@/lib/format";

type Props = {
  cap: string;
  agreed: boolean;
  busy: boolean;
  error: string | null;
  onAgree: (agreed: boolean) => void;
  onApprove: () => void;
};

export default function ApprovePanel({ cap, agreed, busy, error, onAgree, onApprove }: Props) {
  return (
    <section className="approve">
      <label>
        <input type="checkbox" checked={agreed} disabled={busy} onChange={(e) => onAgree(e.target.checked)} />
        同意本次最高成本上限 {formatCredits(cap)}
      </label>
      <button type="button" className="primary" disabled={!agreed || busy} onClick={onApprove}>
        核准並開始生成
      </button>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
    </section>
  );
}
