import { useState } from "react";
import ChatArea from "./components/ChatArea";
import ChatInput from "./components/ChatInput";
import Sidebar from "./components/Sidebar";
import ShortlistPanel from "./components/ShortlistPanel";
import { useChat } from "./hooks/useChat";
import { useSessions } from "./hooks/useSessions";

export default function App() {
  const {
    sessions,
    activeId,
    activeSession,
    setActiveId,
    updateSession,
    createChat,
    removeChat,
  } = useSessions();

  const { isGenerating, metadata, metadataForId, activeAssistantId, sendMessage, sendSilentAction, stopGenerating } = useChat({
    activeSession,
    updateSession,
  });

  const [shortlistOpen, setShortlistOpen] = useState(false);

  function handleQuickReply(text: string, routeHint?: Record<string, unknown>) {
    void sendMessage(text, routeHint);
  }

  function handleSaveListing(pageIndex: number) {
    void sendSilentAction(`save listing ${pageIndex}`, { intent: "Shortlist", shortlist_action: "add", target_indices: [pageIndex] });
  }

  function handleRemoveFromShortlist(position: number) {
    void sendSilentAction(`remove shortlist ${position}`, { intent: "Shortlist", shortlist_action: "remove" });
  }

  const shortlistCount = metadata?.shortlist?.count ?? 0;
  const shortlistListings = metadata?.shortlist?.listings ?? [];

  // Close panel automatically when shortlist becomes empty
  if (shortlistOpen && shortlistCount === 0) {
    setShortlistOpen(false);
  }

  return (
    <div className="h-screen w-full bg-surface text-text md:flex">
      <Sidebar
        sessions={sessions}
        activeId={activeId}
        isGenerating={isGenerating}
        onSelect={setActiveId}
        onCreate={createChat}
        onRemove={(id) => removeChat(id, isGenerating)}
      />
      <main className="flex h-[65vh] flex-1 flex-col md:h-screen">
        <header className="flex items-center justify-between border-b border-border px-4 py-3 text-sm text-muted">
          <span>AI Assistant</span>
          {shortlistCount > 0 && (
            <button
              type="button"
              onClick={() => setShortlistOpen((o) => !o)}
              className="flex items-center gap-1 rounded-full bg-accent/20 px-2.5 py-0.5 text-xs font-medium text-accent transition-colors hover:bg-accent/30"
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" strokeWidth="2">
                <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z" />
              </svg>
              Saved ({shortlistCount})
            </button>
          )}
        </header>
        <ChatArea
          session={activeSession}
          isGenerating={isGenerating}
          metadata={metadata}
          metadataForId={metadataForId}
          activeAssistantId={activeAssistantId}
          onQuickReply={handleQuickReply}
          onSaveListing={handleSaveListing}
        />
        <ChatInput
          isGenerating={isGenerating}
          onSend={(text) => void sendMessage(text)}
          onStop={stopGenerating}
        />
      </main>
      {shortlistOpen && (
        <ShortlistPanel
          listings={shortlistListings}
          onClose={() => setShortlistOpen(false)}
          onRemove={handleRemoveFromShortlist}
        />
      )}
    </div>
  );
}
