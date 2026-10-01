"use client";

import { appendTopic } from "@/lib/plan";

type Props = {
  topic: string;
  sellingPoints: string[];
  busy: boolean;
  onChange: (topic: string) => void;
  onSubmit: () => void;
};

export default function TopicForm({ topic, sellingPoints, busy, onChange, onSubmit }: Props) {
  return (
    <form
      className="topic-form"
      onSubmit={(e) => {
        e.preventDefault();
        if (topic.trim() && !busy) onSubmit();
      }}
    >
      <label htmlFor="topic">宣傳主題</label>
      <input
        id="topic"
        value={topic}
        maxLength={200}
        placeholder="例如：清晨採梅體驗"
        onChange={(e) => onChange(e.target.value)}
        disabled={busy}
      />
      {sellingPoints.length > 0 && (
        <div className="chips" aria-label="品牌賣點">
          {sellingPoints.map((label) => (
            <button key={label} type="button" disabled={busy} onClick={() => onChange(appendTopic(topic, label))}>
              {label}
            </button>
          ))}
        </div>
      )}
      <button type="submit" className="primary" disabled={busy || !topic.trim()}>
        產生企劃
      </button>
    </form>
  );
}
