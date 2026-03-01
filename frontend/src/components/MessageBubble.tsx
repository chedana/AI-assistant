import type { Message } from "../types/chat";
import MessageContent from "./MessageContent";
import ThinkingIndicator from "./ThinkingIndicator";

type Props = {
  message: Message;
  isGenerating: boolean;
  isActive?: boolean;
};

export default function MessageBubble({ message, isGenerating, isActive }: Props) {
  const isUser = message.role === "user";
  const isEmpty = !message.content;
  // While this message is actively being streamed, show ThinkingIndicator instead
  // of the partial text. This prevents search response text from flashing before
  // the listing cards arrive. After streaming ends the message is either hidden
  // (cards replace it) or shown in full (non-search responses).
  const showThinking = isGenerating && (isEmpty || (!isUser && isActive));

  return (
    <article className="w-full">
      <div className="mb-1 text-xs uppercase tracking-wide text-muted">
        {message.role}
      </div>
      <div
        className={`rounded-xl px-4 py-3 text-sm leading-6 ${
          isUser
            ? "ml-auto max-w-[85%] whitespace-pre-wrap bg-neutral-700"
            : "max-w-full bg-[#262626]"
        }`}
      >
        {showThinking ? (
          <ThinkingIndicator />
        ) : isEmpty ? null : (
          <MessageContent content={message.content} role={message.role} />
        )}
      </div>
    </article>
  );
}
