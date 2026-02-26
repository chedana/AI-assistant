import { useEffect, useMemo, useState } from "react";
import { loadSessions, saveSessions } from "../lib/storage";
import type { ChatSession } from "../types/chat";

function createId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function makeSession(title = "New Chat"): ChatSession {
  const now = Date.now();
  return { id: createId(), title, createdAt: now, updatedAt: now, messages: [] };
}

export function useSessions() {
  const [sessions, setSessions] = useState<ChatSession[]>(() => {
    const stored = loadSessions();
    return stored.length > 0
      ? stored.sort((a, b) => b.updatedAt - a.updatedAt)
      : [makeSession("Welcome")];
  });

  const [activeId, setActiveId] = useState<string>(() => {
    const stored = loadSessions();
    return stored.length > 0
      ? stored.sort((a, b) => b.updatedAt - a.updatedAt)[0].id
      : "";
  });

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
    [activeId, sessions],
  );

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

  function removeChat(sessionId: string, isGenerating: boolean) {
    if (isGenerating && sessionId === activeId) return;
    setSessions((prev) => {
      const remaining = prev.filter((s) => s.id !== sessionId);
      if (activeId === sessionId) {
        setActiveId(remaining[0]?.id ?? "");
      }
      return remaining;
    });
  }

  return {
    sessions,
    activeId,
    activeSession,
    setActiveId,
    updateSession,
    createChat,
    removeChat,
  };
}

export { createId };
