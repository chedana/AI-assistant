import { FormEvent, useEffect, useRef, useState } from "react";

type Props = {
  isGenerating: boolean;
  onSend: (text: string) => void;
  onStop: () => void;
};

export default function ChatInput({ isGenerating, onSend, onStop }: Props) {
  const [input, setInput] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-resize: shrink to 1 row, then grow to content height, capped at ~5 rows.
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, [input]);

  function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const text = input.trim();
    if (!text || isGenerating) return;
    setInput("");
    onSend(text);
  }

  return (
    <footer className="border-t border-border p-4">
      <form onSubmit={handleSubmit} className="mx-auto flex max-w-3xl gap-2">
        <textarea
          ref={textareaRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Send a message..."
          rows={1}
          className="max-h-40 min-h-[48px] flex-1 resize-none overflow-y-auto rounded-lg border border-border bg-panel px-3 py-3 text-sm leading-6 outline-none focus:border-neutral-500"
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              const text = input.trim();
              if (text && !isGenerating) {
                setInput("");
                onSend(text);
              }
            }
          }}
        />
        {!isGenerating ? (
          <button
            type="submit"
            className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-black hover:opacity-90"
          >
            Send
          </button>
        ) : (
          <button
            type="button"
            onClick={onStop}
            className="rounded-lg border border-border px-4 py-2 text-sm hover:bg-neutral-800"
          >
            Stop
          </button>
        )}
      </form>
    </footer>
  );
}
