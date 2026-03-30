import { FormEvent, useEffect, useRef, useState } from "react";

type Props = {
  isGenerating: boolean;
  thinkingMode: "quick" | "deep";
  onToggleMode: () => void;
  onSend: (text: string) => void;
  onStop: () => void;
};

export default function ChatInput({ isGenerating, thinkingMode, onToggleMode, onSend, onStop }: Props) {
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
    if (!text) return;
    if (isGenerating) {
      onStop();
      return;
    }
    setInput("");
    onSend(text);
  }

  return (
    <div className="border-t border-border bg-panel-alt/50 p-4 backdrop-blur-sm md:p-6">
      <form 
        onSubmit={handleSubmit} 
        className="relative mx-auto flex max-w-4xl items-end gap-3 rounded-2xl border border-border bg-panel p-2 shadow-lg transition-all focus-within:border-accent/50 focus-within:ring-1 focus-within:ring-accent/20"
      >
        <textarea
          ref={textareaRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Describe what you're looking for..."
          rows={1}
          className="flex-1 resize-none bg-transparent px-3 py-3 text-sm leading-relaxed text-text placeholder:text-muted focus:outline-none"
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
        <button
          type="button"
          title={thinkingMode === "quick" ? "Quick mode — click for Deep" : "Deep mode — click for Quick"}
          disabled={isGenerating}
          onClick={onToggleMode}
          className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl transition-all active:scale-95 disabled:opacity-40 disabled:pointer-events-none ${
            thinkingMode === "deep"
              ? "bg-accent/15 text-accent shadow-[0_0_8px_rgba(16,185,129,0.3)]"
              : "bg-transparent text-muted hover:text-text hover:bg-surface"
          }`}
        >
          {thinkingMode === "deep" ? (
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 2l2.4 7.2L22 12l-7.6 2.8L12 22l-2.4-7.2L2 12l7.6-2.8L12 2z" />
            </svg>
          ) : (
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M13 2L3 14h9l-1 10 10-12h-9l1-10z" />
            </svg>
          )}
        </button>
        <button
          type="submit"
          className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl transition-all active:scale-90 ${
            isGenerating
              ? "bg-surface text-text hover:bg-neutral-800"
              : "bg-accent text-surface shadow-lg shadow-accent/20 hover:bg-accent-dim"
          }`}
        >
          {isGenerating ? (
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
              <rect x="6" y="6" width="12" height="12" />
            </svg>
          ) : (
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
              <line x1="22" y1="2" x2="11" y2="13" />
              <polygon points="22 2 15 22 11 13 2 9 22 2" />
            </svg>
          )}
        </button>
      </form>
      <p className="mt-2 text-center text-[10px] font-medium text-muted/50">
        OpenClaw can make mistakes. Verify important property details.
      </p>
    </div>
  );
}
