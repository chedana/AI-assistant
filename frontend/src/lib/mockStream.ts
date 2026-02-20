type StreamOptions = {
  signal: AbortSignal;
  onChunk: (chunk: string) => void;
};

function wait(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export async function streamMockReply(
  prompt: string,
  options: StreamOptions
): Promise<void> {
  const text = buildReply(prompt);
  const chunks = text.match(/.{1,8}/g) ?? [];

  for (const chunk of chunks) {
    if (options.signal.aborted) {
      throw new DOMException("Aborted", "AbortError");
    }
    await wait(40 + Math.floor(Math.random() * 40));
    options.onChunk(chunk);
  }
}

function buildReply(prompt: string): string {
  const clean = prompt.trim();
  if (!clean) return "请先输入你的问题。";

  return [
    `我收到了：${clean}`,
    "",
    "这是一个 mock 流式回复。你后续接入真实接口时，只需要替换 streamMockReply。",
    "如果你愿意，我下一步可以把它改成调用你的后端 `/api/chat/stream` 并保留同样的 UI 逻辑。",
  ].join("\n");
}
