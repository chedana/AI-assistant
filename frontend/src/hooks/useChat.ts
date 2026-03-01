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
  const [metadataForId, setMetadataForId] = useState<string | null>(null);
  const [activeAssistantId, setActiveAssistantId] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  // Track the URL signature of the last search results shown as cards.
  // metadataForId only updates when the actual listings change, so saving/removing
  // a listing (which re-sends the same search_results) won't move the hide pointer.
  const lastSearchSigRef = useRef<string>("");

  // Reset metadata when switching sessions, not on every message send.
  useEffect(() => {
    setMetadata(null);
    setMetadataForId(null);
    setActiveAssistantId(null);
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
          // Only update the "hide this message" pointer when search results actually change.
          // This prevents the original search text from reappearing on save/remove actions
          // that return the same search_results in metadata.
          const sig = (meta.search_results?.listings ?? []).map((l) => l.url).join(",");
          if (sig !== lastSearchSigRef.current) {
            lastSearchSigRef.current = sig;
            setMetadataForId(assistantMessage.id);
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
  // messages to the chat session. Used for save/remove shortlist actions.
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
          // Don't touch metadataForId or lastSearchSigRef — keep existing card hide state
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

  return { isGenerating, metadata, metadataForId, activeAssistantId, sendMessage, sendSilentAction, stopGenerating };
}
