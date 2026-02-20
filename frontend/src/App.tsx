import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { streamMockReply } from "./lib/mockStream";
import { loadSessions, saveSessions } from "./lib/storage";
import type { ChatSession, Message } from "./types/chat";

function createId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function makeSession(title = "New Chat"): ChatSession {
  const now = Date.now();
  return {
    id: createId(),
    title,
    createdAt: now,
    updatedAt: now,
    messages: [],
  };
}

function firstLine(content: string): string {
  const line = content.trim().split("\n")[0];
  return line || "New Chat";
}

export default function App() {
  const [sessions, setSessions] = useState<ChatSession[]>(() => {
    const stored = loadSessions();
    if (stored.length > 0) {
      return stored.sort((a, b) => b.updatedAt - a.updatedAt);
    }
    return [makeSession("Welcome")];
  });
  const [activeId, setActiveId] = useState<string>(() => {
    const stored = loadSessions();
    if (stored.length > 0) {
      return stored.sort((a, b) => b.updatedAt - a.updatedAt)[0].id;
    }
    return "";
  });
  const [input, setInput] = useState("");
  const [isGenerating, setIsGenerating] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const endRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!activeId && sessions.length > 0) {
      setActiveId(sessions[0].id);
    }
  }, [activeId, sessions]);

  useEffect(() => {
    saveSessions(sessions);
  }, [sessions]);

  const activeSession = useMemo(
    () => sessions.find((s) => s.id === activeId) ?? sessions[0],
    [activeId, sessions]
  );

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [activeSession?.messages.length, isGenerating]);

  function updateSession(sessionId: string, updater: (s: ChatSession) => ChatSession) {
    setSessions((prev) => {
      const next = prev.map((s) => (s.id === sessionId ? updater(s) : s));
      return next.sort((a, b) => b.updatedAt - a.updatedAt);
    });
  }

  function createChat() {
    const session = makeSession();
    setSessions((prev) => [session, ...prev]);
    setActiveId(session.id);
  }

  function removeChat(sessionId: string) {
    if (isGenerating && sessionId === activeId) return;
    setSessions((prev) => {
      const remaining = prev.filter((s) => s.id !== sessionId);
      if (activeId === sessionId) {
        setActiveId(remaining[0]?.id ?? "");
      }
      return remaining;
    });
  }

  async function sendMessage() {
    if (!activeSession || isGenerating) return;
    const prompt = input.trim();
    if (!prompt) return;

    const now = Date.now();
    const userMessage: Message = {
      id: createId(),
      role: "user",
      content: prompt,
      createdAt: now,
    };
    const assistantMessage: Message = {
      id: createId(),
      role: "assistant",
      content: "",
      createdAt: now + 1,
    };

    setInput("");
    setIsGenerating(true);
    const controller = new AbortController();
    abortRef.current = controller;

    updateSession(activeSession.id, (session) => ({
      ...session,
      title: session.messages.length === 0 ? firstLine(prompt) : session.title,
      updatedAt: Date.now(),
      messages: [...session.messages, userMessage, assistantMessage],
    }));

    try {
      await streamMockReply(activeSession.id, prompt, {
        signal: controller.signal,
        onChunk: (chunk) => {
          updateSession(activeSession.id, (session) => {
            const messages = session.messages.map((m) =>
              m.id === assistantMessage.id ? { ...m, content: m.content + chunk } : m
            );
            return { ...session, updatedAt: Date.now(), messages };
          });
        },
      });
    } catch (error) {
      if (!(error instanceof DOMException) || error.name !== "AbortError") {
        updateSession(activeSession.id, (session) => {
          const messages = session.messages.map((m) =>
            m.id === assistantMessage.id
              ? { ...m, content: `${m.content}\n\n[stream error]` }
              : m
          );
          return { ...session, updatedAt: Date.now(), messages };
        });
      }
    } finally {
      setIsGenerating(false);
      abortRef.current = null;
    }
  }

  function stopGenerating() {
    abortRef.current?.abort();
  }

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void sendMessage();
  }

  return (
    <div className="h-screen w-full bg-surface text-text md:flex">
      <aside className="h-[35vh] border-b border-border bg-panel p-3 md:h-screen md:w-72 md:border-b-0 md:border-r">
        <button
          onClick={createChat}
          className="w-full rounded-lg border border-border px-3 py-2 text-sm hover:bg-neutral-700"
        >
          + New chat
        </button>
        <div className="mt-3 space-y-2 overflow-y-auto pr-1 md:h-[calc(100%-52px)]">
          {sessions.map((session) => (
            <div
              key={session.id}
              className={`group flex items-center gap-2 rounded-lg px-2 py-2 ${
                session.id === activeSession?.id ? "bg-neutral-700" : "hover:bg-neutral-800"
              }`}
            >
              <button
                className="min-w-0 flex-1 truncate text-left text-sm"
                onClick={() => setActiveId(session.id)}
              >
                {session.title}
              </button>
              <button
                className="hidden text-xs text-muted group-hover:block"
                onClick={() => removeChat(session.id)}
                disabled={isGenerating && session.id === activeSession?.id}
                title="Delete chat"
              >
                delete
              </button>
            </div>
          ))}
        </div>
      </aside>

      <main className="flex h-[65vh] flex-1 flex-col md:h-screen">
        <header className="border-b border-border px-4 py-3 text-sm text-muted">
          AI Assistant
        </header>
        <section className="flex-1 overflow-y-auto px-4 py-4">
          <div className="mx-auto max-w-3xl space-y-4">
            {activeSession?.messages.length ? (
              activeSession.messages.map((message) => (
                <article key={message.id} className="w-full">
                  <div className="mb-1 text-xs uppercase tracking-wide text-muted">
                    {message.role}
                  </div>
                  <div
                    className={`whitespace-pre-wrap rounded-xl px-4 py-3 text-sm leading-6 ${
                      message.role === "user"
                        ? "ml-auto max-w-[85%] bg-neutral-700"
                        : "max-w-full bg-[#262626]"
                    }`}
                  >
                    {message.content || (isGenerating ? "..." : "")}
                  </div>
                </article>
              ))
            ) : (
              <div className="pt-16 text-center text-sm text-muted">
                Start a conversation.
              </div>
            )}
            <div ref={endRef} />
          </div>
        </section>

        <footer className="border-t border-border p-4">
          <form onSubmit={onSubmit} className="mx-auto flex max-w-3xl gap-2">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Send a message..."
              className="h-12 flex-1 resize-none rounded-lg border border-border bg-panel px-3 py-3 text-sm outline-none focus:border-neutral-500"
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  void sendMessage();
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
                onClick={stopGenerating}
                className="rounded-lg border border-border px-4 py-2 text-sm hover:bg-neutral-800"
              >
                Stop
              </button>
            )}
          </form>
        </footer>
      </main>
    </div>
  );
}
