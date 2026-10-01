"use client";

import { formatCredits } from "@/lib/format";

type Props = {
  shotNo: number;
  remaining: number | null;
  cost: string;
  newCap: string;
  busy: boolean;
  onConfirm: () => void;
  onCancel: () => void;
};

/** 重生超出剩餘預算時要求再次確認（spec 0016 R-004）。 */
export default function RegenDialog({ shotNo, remaining, cost, newCap, busy, onConfirm, onCancel }: Props) {
  return (
    <div className="backdrop">
      <div role="dialog" aria-modal="true" aria-labelledby="regen-title" className="dialog">
        <h2 id="regen-title">第 {shotNo} 鏡重生會超出預算</h2>
        <dl>
          <dt>剩餘預算</dt>
          <dd>{remaining === null ? "—" : formatCredits(remaining)}</dd>
          <dt>重生所需</dt>
          <dd>{formatCredits(cost)}</dd>
          <dt>新的成本上限</dt>
          <dd>{formatCredits(newCap)}</dd>
        </dl>
        <div className="actions">
          <button type="button" onClick={onCancel} disabled={busy}>
            取消
          </button>
          <button type="button" className="primary" onClick={onConfirm} disabled={busy}>
            同意提高上限並重生
          </button>
        </div>
      </div>
    </div>
  );
}
