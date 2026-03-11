import { useMemo, useState } from "react";
import ChatArea from "./components/ChatArea";
import ChatInput from "./components/ChatInput";
import Header from "./components/Header";
import ListingsPanel from "./components/ListingsPanel";
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

  const {
    isGenerating,
    metadata,
    activeAssistantId,
    sendMessage,
    sendSilentAction,
    stopGenerating,
  } = useChat({ activeSession, updateSession });

  const [shortlistOpen, setShortlistOpen] = useState(false);
  const [mobileView, setMobileView] = useState<"chat" | "results">("chat");
  const [viewMode, setViewMode] = useState<"list" | "map">("list");

  // Auto-switch to results on search completion (if on mobile chat)
  const lastMetadataRef = useState(metadata);
  if (metadata !== lastMetadataRef[0]) {
    if (metadata?.search_results?.listings?.length && mobileView === "chat") {
      setMobileView("results");
    }
    lastMetadataRef[1](metadata);
  }

  const savedIds = useMemo(
    () => new Set(metadata?.shortlist?.saved_ids ?? []),
    [metadata?.shortlist?.saved_ids],
  );

  const shortlistCount = metadata?.shortlist?.count ?? 0;
  const shortlistListings = metadata?.shortlist?.listings ?? [];

  // Close panel automatically when shortlist becomes empty
  if (shortlistOpen && shortlistCount === 0) {
    setShortlistOpen(false);
  }

  // --- Action handlers ---

  function handleQuickReply(text: string, routeHint?: Record<string, unknown>) {
    void sendSilentAction(text, routeHint);
  }

  function handleRemoveConstraint(clearFields: string[]) {
    void sendSilentAction("clear constraint", { intent: "Search", clear_fields: clearFields });
  }

  function handleSaveListing(pageIndex: number) {
    void sendSilentAction(`save listing ${pageIndex}`, { intent: "Shortlist", shortlist_action: "add", target_indices: [pageIndex] });
  }

  function handleRemoveListingFromResults(pageIndex: number, url: string) {
    const savedIdsArr = metadata?.shortlist?.saved_ids ?? [];
    const position = savedIdsArr.indexOf(url) + 1;
    if (position > 0) {
      handleRemoveFromShortlist(position);
    }
  }

  function handleRemoveFromShortlist(position: number) {
    void sendSilentAction(`remove shortlist ${position}`, { intent: "Shortlist", shortlist_action: "remove", target_indices: [position] });
  }

  function handleSuggestionClick(text: string, routeHint?: Record<string, unknown>) {
    void sendSilentAction(text, routeHint);
  }

  return (
    <div className="flex h-screen w-full flex-col bg-surface text-text antialiased">
      {/* Header: full width */}
      <Header
        sessions={sessions}
        activeId={activeId}
        isGenerating={isGenerating}
        constraints={metadata?.constraints}
        shortlistCount={shortlistCount}
        onSelectSession={setActiveId}
        onCreateSession={createChat}
        onRemoveSession={(id) => removeChat(id, isGenerating)}
        onRemoveConstraint={handleRemoveConstraint}
        onShortlistToggle={() => setShortlistOpen((o) => !o)}
        mobileView={mobileView}
        onMobileViewToggle={(v) => setMobileView(v)}
      />

      {/* Main content: responsive layout */}
      <div className="flex flex-1 overflow-hidden">
        {/* Listings panel — main content (visible on desktop or if results tab selected on mobile) */}
        <div className={`flex flex-1 overflow-hidden transition-all duration-300 ${mobileView === "chat" ? "hidden md:flex" : "flex"}`}>
          <ListingsPanel
            metadata={metadata}
            isGenerating={isGenerating}
            savedIds={savedIds}
            quickReplies={metadata?.quick_replies}
            viewMode={viewMode}
            onViewModeToggle={setViewMode}
            onSaveListing={handleSaveListing}
            onRemoveListing={handleRemoveListingFromResults}
            onShowMore={() => sendSilentAction("show me more", { intent: "Page_Nav", page_action: "next" })}
            onShowPrev={() => sendSilentAction("go back", { intent: "Page_Nav", page_action: "prev" })}
            onQuickReply={handleQuickReply}
            onSuggestionClick={handleSuggestionClick}
          />
        </div>

        {/* Chat panel — right sidebar (visible on desktop or if chat tab selected on mobile) */}
        <div className={`flex w-full md:w-[420px] shrink-0 flex-col border-l border-border bg-panel-alt transition-all duration-300 ${mobileView === "results" ? "hidden md:flex" : "flex"}`}>
          <div className="hidden items-center border-b border-border px-5 py-3 md:flex">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="mr-3 text-accent">
              <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
            </svg>
            <span className="text-sm font-semibold tracking-tight text-text">OpenClaw Assistant</span>
          </div>
          <ChatArea
            session={activeSession}
            isGenerating={isGenerating}
            activeAssistantId={activeAssistantId}
            quickReplies={metadata?.quick_replies}
            onQuickReply={handleQuickReply}
          />
          <ChatInput
            isGenerating={isGenerating}
            onSend={(text) => void sendMessage(text)}
            onStop={stopGenerating}
          />
        </div>
      </div>

      {/* Mobile Navigation Bar */}
      <div className="flex border-t border-border bg-panel md:hidden">
        <button
          onClick={() => setMobileView("chat")}
          className={`flex-1 flex flex-col items-center justify-center py-2 text-[10px] ${mobileView === "chat" ? "text-accent" : "text-muted"}`}
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
          </svg>
          Chat
        </button>
        <button
          onClick={() => setMobileView("results")}
          className={`flex-1 flex flex-col items-center justify-center py-2 text-[10px] ${mobileView === "results" ? "text-accent" : "text-muted"}`}
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
            <polyline points="9 22 9 12 15 12 15 22" />
          </svg>
          Results
        </button>
      </div>

      {/* Shortlist overlay */}
      {shortlistOpen && (
        <>
          <div
            className="fixed inset-0 z-40 bg-black/50"
            onClick={() => setShortlistOpen(false)}
          />
          <div className="fixed inset-y-0 right-0 z-50 shadow-2xl">
            <ShortlistPanel
              listings={shortlistListings}
              onClose={() => setShortlistOpen(false)}
              onRemove={handleRemoveFromShortlist}
              onCompare={() => {
                setShortlistOpen(false);
                void sendSilentAction("compare my shortlist", { intent: "Compare" });
              }}
            />
          </div>
        </>
      )}
    </div>
  );
}
