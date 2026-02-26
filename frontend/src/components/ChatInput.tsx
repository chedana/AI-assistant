import { FormEvent, useState } from "react";

type Props = {
  isGenerating: boolean;
  onSend: (text: string) => void;
  onStop: () => void;
};

export default function ChatInput({ isGenerating, onSend, onStop }: Props) {
  const [input, setInput] = useState("");

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
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Send a message..."
          className="h-12 flex-1 resize-none rounded-lg border border-border bg-panel px-3 py-3 text-sm outline-none focus:border-neutral-500"
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
