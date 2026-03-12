import type { SessionMetadata } from "../types/chat";

type StreamOptions = {
  signal: AbortSignal;
  routeHint?: Record<string, unknown>;
  onChunk: (chunk: string) => void;
  onMetadata?: (meta: SessionMetadata) => void;
};

const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "";

export async function streamChat(
  sessionId: string,
  userText: string,
  options: StreamOptions,
): Promise<void> {
  const response = await fetch(`${API_BASE}/api/chat/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    signal: options.signal,
    body: JSON.stringify({
      session_id: sessionId,
      user_text: userText,
      ...(options.routeHint ? { route_hint: options.routeHint } : {}),
    }),
  });

  if (!response.ok || !response.body) {
    throw new Error(`Request failed: ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const events = buffer.split("\n\n");
    buffer = events.pop() ?? "";

    for (const eventText of events) {
      let eventName = "message";
      let dataLine = "";
      for (const line of eventText.split("\n")) {
        if (line.startsWith("event:")) {
          eventName = line.slice(6).trim();
        } else if (line.startsWith("data:")) {
          dataLine = line.slice(5).trim();
        }
      }
      if (!dataLine) continue;

      if (eventName === "delta") {
        const data = JSON.parse(dataLine) as { text?: string };
        if (data.text) {
          options.onChunk(data.text);
        }
      } else if (eventName === "metadata") {
        const data = JSON.parse(dataLine) as SessionMetadata;
        options.onMetadata?.(data);
      } else if (eventName === "error") {
        const data = JSON.parse(dataLine) as { message?: string };
        throw new Error(data.message ?? "Stream error");
      } else if (eventName === "done") {
        return;
      }
    }
  }
}
