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
  const abortRef = useRef<AbortController | null>(null);

  // Reset metadata when switching sessions, not on every message send.
  useEffect(() => {
    setMetadata(null);
  }, [activeSession?.id]);

  async function sendMessage(input: string) {
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
      abortRef.current = null;
    }
  }

  function stopGenerating() {
    abortRef.current?.abort();
  }

  return { isGenerating, metadata, sendMessage, stopGenerating };
}
