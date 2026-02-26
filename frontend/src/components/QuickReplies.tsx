import type { QuickReply } from "../types/chat";

type Props = {
  replies: QuickReply[];
  onSelect: (text: string) => void;
};

export default function QuickReplies({ replies, onSelect }: Props) {
  if (replies.length === 0) return null;

  return (
    <div className="flex flex-wrap gap-2 pt-2">
      {replies.map((reply) => (
        <button
          key={reply.text}
          onClick={() => onSelect(reply.text)}
          className="rounded-lg border border-border px-3 py-1.5 text-xs text-muted hover:bg-neutral-700 hover:text-text"
        >
          {reply.label}
        </button>
      ))}
    </div>
  );
}
