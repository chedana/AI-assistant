import { useEffect, useRef, useState } from "react";
import { streamChat } from "../lib/mockStream";
import type { ChatSession, Message, SessionMetadata } from "../types/chat";
import { createId } from "./useSessions";

function firstLine(content: string): string {
  const line = content.trim().split("\n")[0];
  return line || "New Chat";
}

type UseChatOptions = {
  activeSession: ChatSession | undefined;
  updateSession: (id: string, updater: (s: ChatSession) => ChatSession) => void;
};

export function useChat({ activeSession, updateSession }: UseChatOptions) {
  const [isGenerating, setIsGenerating] = useState(false);
  const [metadata, setMetadata] = useState<SessionMetadata | null>(null);
  const [activeAssistantId, setActiveAssistantId] = useState<string | null>(null);
  // suppressedIds: all assistant message IDs whose text has been replaced by structured
  // UI (listing cards or compare table). Accumulated across paginations so old search
  // text never reappears. Cleared only on session switch.
  const [suppressedIds, setSuppressedIds] = useState<Set<string>>(new Set());
  const abortRef = useRef<AbortController | null>(null);
  const lastSearchSigRef = useRef<string>("");

  useEffect(() => {
    setMetadata(null);
    setActiveAssistantId(null);
    setSuppressedIds(new Set());
    lastSearchSigRef.current = "";
  }, [activeSession?.id]);

  async function sendMessage(input: string, routeHint?: Record<string, unknown>) {
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

    setIsGenerating(true);
    setActiveAssistantId(assistantMessage.id);
    const controller = new AbortController();
    abortRef.current = controller;

    updateSession(activeSession.id, (session) => ({
      ...session,
      title: session.messages.length === 0 ? firstLine(prompt) : session.title,
      updatedAt: Date.now(),
      messages: [...session.messages, userMessage, assistantMessage],
    }));

    try {
      await streamChat(activeSession.id, prompt, {
        signal: controller.signal,
        routeHint,
        onChunk: (chunk) => {
          updateSession(activeSession.id, (session) => {
            const messages = session.messages.map((m) =>
              m.id === assistantMessage.id ? { ...m, content: m.content + chunk } : m,
            );
            return { ...session, updatedAt: Date.now(), messages };
          });
        },
        onMetadata: (meta) => {
          setMetadata(meta);

          const sig = (meta.search_results?.listings ?? []).map((l) => l.url).join(",");
          const hasNewResults = sig !== "" && sig !== lastSearchSigRef.current;
          const hasCompare = (meta.compare_data?.listings?.length ?? 0) >= 2;

          // Add to permanent suppressed set if this message produced structured UI
          if (hasNewResults || hasCompare) {
            lastSearchSigRef.current = sig || lastSearchSigRef.current;
            setSuppressedIds((prev) => new Set([...prev, assistantMessage.id]));
          }
        },
      });
    } catch (error) {
      if (!(error instanceof DOMException) || error.name !== "AbortError") {
        updateSession(activeSession.id, (session) => {
          const messages = session.messages.map((m) =>
            m.id === assistantMessage.id
              ? { ...m, content: `${m.content}\n\n[stream error]` }
              : m,
          );
          return { ...session, updatedAt: Date.now(), messages };
        });
      }
    } finally {
      setIsGenerating(false);
      setActiveAssistantId(null);
      abortRef.current = null;
    }
  }

  // Silent action: calls the backend and updates metadata without adding any
  // messages to the chat session. Used for save/remove/compare shortlist actions.
  async function sendSilentAction(input: string, routeHint?: Record<string, unknown>) {
    if (!activeSession || isGenerating) return;
    const prompt = input.trim();
    if (!prompt) return;

    setIsGenerating(true);
    const controller = new AbortController();
    abortRef.current = controller;

    try {
      await streamChat(activeSession.id, prompt, {
        signal: controller.signal,
        routeHint,
        onChunk: () => {}, // discard streamed text — only metadata matters
        onMetadata: (meta) => {
          setMetadata(meta);
          // Don't suppress anything — no assistant message was added
        },
      });
    } catch (error) {
      if (!(error instanceof DOMException) || error.name !== "AbortError") {
        console.error("[silent action failed]", error);
      }
    } finally {
      setIsGenerating(false);
      abortRef.current = null;
    }
  }

  function stopGenerating() {
    abortRef.current?.abort();
  }

  return { isGenerating, metadata, suppressedIds, activeAssistantId, sendMessage, sendSilentAction, stopGenerating };
}
