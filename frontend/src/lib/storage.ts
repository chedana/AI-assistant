import type { ChatSession } from "../types/chat";

const KEY = "ai-assistant-chat-sessions-v1";

export function loadSessions(): ChatSession[] {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as ChatSession[];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export function saveSessions(sessions: ChatSession[]): void {
  localStorage.setItem(KEY, JSON.stringify(sessions));
}
