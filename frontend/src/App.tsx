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

  const { isGenerating, metadata, metadataForId, sendMessage, stopGenerating } = useChat({
    activeSession,
    updateSession,
  });

  const [shortlistOpen, setShortlistOpen] = useState(false);

  function handleQuickReply(text: string, routeHint?: Record<string, unknown>) {
    void sendMessage(text, routeHint);
  }

  function handleSaveListing(pageIndex: number) {
    void sendMessage(`save listing ${pageIndex}`, { intent: "Shortlist", shortlist_action: "save" });
  }

  function handleRemoveFromShortlist(position: number) {
    void sendMessage(`remove shortlist ${position}`, { intent: "Shortlist", shortlist_action: "remove" });
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
        shortlistCount={shortlistCount}
        onSelect={setActiveId}
        onCreate={createChat}
        onRemove={(id) => removeChat(id, isGenerating)}
        onOpenShortlist={() => setShortlistOpen(true)}
      />
      <main className="flex h-[65vh] flex-1 flex-col md:h-screen">
        <header className="border-b border-border px-4 py-3 text-sm text-muted">
          AI Assistant
        </header>
        <ChatArea
          session={activeSession}
          isGenerating={isGenerating}
          metadata={metadata}
          metadataForId={metadataForId}
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
