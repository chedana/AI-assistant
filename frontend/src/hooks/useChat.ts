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
  // metadataForId: the message ID where cards/compare are rendered inline (most recent).
  const [metadataForId, setMetadataForId] = useState<string | null>(null);
  // suppressedIds: ALL message IDs that produced structured UI — accumulated so old
  // search text never reappears after pagination or compare.
  const [suppressedIds, setSuppressedIds] = useState<Set<string>>(new Set());
  const abortRef = useRef<AbortController | null>(null);
  const lastSearchSigRef = useRef<string>("");
  const isGeneratingRef = useRef(false);

  const lastAckIdRef = useRef<string | null>(null);

  useEffect(() => {
    setMetadata(null);
    setMetadataForId(null);
    setActiveAssistantId(null);
    setSuppressedIds(new Set());
    lastSearchSigRef.current = "";
    lastAckIdRef.current = null;
  }, [activeSession?.id]);

  async function sendMessage(input: string, routeHint?: Record<string, unknown>) {
    if (!activeSession || isGeneratingRef.current) return;
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

    isGeneratingRef.current = true;
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

          if (hasNewResults || hasCompare) {
            if (hasNewResults) lastSearchSigRef.current = sig;

            // Replace the raw listing dump with a brief summary
            const count = meta.search_results?.total ?? meta.search_results?.listings?.length ?? 0;
            const summary = hasNewResults
              ? `Found ${count} ${count === 1 ? "property" : "properties"} matching your search.`
              : "Comparison ready — see the table on the left.";

            updateSession(activeSession.id, (session) => {
              const messages = session.messages.map((m) =>
                m.id === assistantMessage.id ? { ...m, content: summary } : m,
              );
              return { ...session, messages };
            });

            setSuppressedIds((prev) => new Set([...prev, assistantMessage.id]));
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
      isGeneratingRef.current = false;
      setIsGenerating(false);
      setActiveAssistantId(null);
      abortRef.current = null;
    }
  }

  // Silent action: calls the backend and updates metadata without adding a user
  // message. An optional actionLabel adds a brief assistant acknowledgment so
  // the user knows what is happening (e.g. "Lowering budget to £1,280/month…").
  async function sendSilentAction(input: string, routeHint?: Record<string, unknown>, actionLabel?: string) {
    if (!activeSession || isGeneratingRef.current) return;
    const prompt = input.trim();
    if (!prompt) return;

    // Reuse last ack ID if it's a pagination action to avoid pile-up
    const isPagination = routeHint?.intent === "Page_Nav";
    const canReuse = isPagination && lastAckIdRef.current;
    const ackId = canReuse ? lastAckIdRef.current! : (actionLabel ? createId() : null);
    
    if (actionLabel && ackId) {
      const now = Date.now();
      updateSession(activeSession.id, (session) => {
        const existingIdx = session.messages.findIndex(m => m.id === ackId);
        if (existingIdx !== -1) {
          const messages = [...session.messages];
          messages[existingIdx] = { ...messages[existingIdx], content: actionLabel, createdAt: now };
          return { ...session, updatedAt: now, messages };
        }
        
        const ackMessage: Message = {
          id: ackId,
          role: "assistant",
          content: actionLabel,
          createdAt: now,
        };
        return {
          ...session,
          updatedAt: now,
          messages: [...session.messages, ackMessage],
        };
      });
      lastAckIdRef.current = ackId;
    }

    isGeneratingRef.current = true;
    setIsGenerating(true);
    const controller = new AbortController();
    abortRef.current = controller;

    try {
      await streamChat(activeSession.id, prompt, {
        signal: controller.signal,
        routeHint,
        onChunk: () => {},
        onMetadata: (meta) => {
          setMetadata(meta);

          const hasResults = (meta.search_results?.listings?.length ?? 0) > 0;
          const hasCompare = (meta.compare_data?.listings?.length ?? 0) >= 2;

          if (hasResults || hasCompare) {
            // Move card rendering to the ack message position (or keep current)
            const targetId = ackId ?? metadataForId;
            if (targetId) {
              setSuppressedIds((prev) => new Set([...prev, targetId]));
              setMetadataForId(targetId);
            }
            if (hasResults) {
              lastSearchSigRef.current = (meta.search_results?.listings ?? []).map((l) => l.url).join(",");
            }
          }
        },
      });
    } catch (error) {
      if (!(error instanceof DOMException) || error.name !== "AbortError") {
        console.error("[silent action failed]", error);
      }
    } finally {
      isGeneratingRef.current = false;
      setIsGenerating(false);
      abortRef.current = null;
    }
  }

  function stopGenerating() {
    abortRef.current?.abort();
  }

  return {
    isGenerating,
    metadata,
    suppressedIds,
    metadataForId,
    activeAssistantId,
    sendMessage,
    sendSilentAction,
    stopGenerating,
  };
}
