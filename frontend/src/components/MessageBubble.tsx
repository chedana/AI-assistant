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
  const showThinking = isGenerating && !isUser && isActive;

  return (
    <div className={`flex w-full flex-col ${isUser ? "items-end" : "items-start"} animate-in fade-in slide-in-from-bottom-2 duration-300`}>
      <div className={`mb-1.5 flex items-center gap-2 px-1 text-[10px] font-bold uppercase tracking-widest text-muted/50`}>
        {!isUser && (
          <div className="flex h-4 w-4 items-center justify-center rounded-sm bg-accent/20 text-accent">
            <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
            </svg>
          </div>
        )}
        {message.role === "assistant" ? "OpenClaw" : "You"}
      </div>
      
      <div
        className={`relative overflow-hidden rounded-2xl px-4 py-3.5 text-sm leading-relaxed shadow-sm transition-all ${
          isUser
            ? "max-w-[85%] whitespace-pre-wrap bg-accent text-surface font-semibold"
            : "max-w-full bg-panel border border-border text-text"
        }`}
      >
        {showThinking ? (
          <div className="flex items-center gap-2 py-1">
             <ThinkingIndicator />
          </div>
        ) : isEmpty ? null : (
          <MessageContent content={message.content} role={message.role} />
        )}
      </div>
    </div>
  );
}
