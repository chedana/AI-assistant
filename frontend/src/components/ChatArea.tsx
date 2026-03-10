import { useEffect, useRef } from "react";
import type { ChatSession, QuickReply } from "../types/chat";
import MessageBubble from "./MessageBubble";
import QuickReplies from "./QuickReplies";

type Props = {
  session: ChatSession | undefined;
  isGenerating: boolean;
  activeAssistantId: string | null;
  quickReplies: QuickReply[] | undefined;
  onQuickReply: (text: string, routeHint?: Record<string, unknown>) => void;
};

export default function ChatArea({
  session,
  isGenerating,
  activeAssistantId,
  quickReplies,
  onQuickReply,
}: Props) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [session?.messages.length, isGenerating]);

  const showQuickReplies = !isGenerating && quickReplies && quickReplies.length > 0;

  return (
    <div className="relative flex flex-1 flex-col overflow-hidden bg-panel-alt/30">
      <div 
        ref={scrollRef}
        className="flex-1 overflow-y-auto scroll-smooth p-4 md:p-6"
      >
        <div className="mx-auto flex max-w-3xl flex-col gap-6">
          {session?.messages.length ? (
            <>
              {session.messages.map((message) => (
                <MessageBubble
                  key={message.id}
                  message={message}
                  isGenerating={isGenerating}
                  isActive={message.id === activeAssistantId}
                />
              ))}
              
              {showQuickReplies && (
                <div className="pt-2 animate-in fade-in slide-in-from-bottom-2 duration-500">
                  <div className="mb-3 text-[10px] font-bold uppercase tracking-widest text-muted/50">
                    Suggestions
                  </div>
                  <QuickReplies replies={quickReplies!} onSelect={onQuickReply} />
                </div>
              )}
            </>
          ) : (
            <div className="flex flex-col items-center justify-center py-20 text-center">
              <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-white/5 text-muted">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
                </svg>
              </div>
              <h3 className="text-sm font-bold text-text">Start a Conversation</h3>
              <p className="mt-2 max-w-[200px] text-xs leading-relaxed text-muted">
                Describe the property you're looking for to begin your search.
              </p>
            </div>
          )}
          <div ref={endRef} className="h-4 shrink-0" />
        </div>
      </div>
    </div>
  );
}
