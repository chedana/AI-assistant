import ChatArea from "./components/ChatArea";
import ChatInput from "./components/ChatInput";
import Sidebar from "./components/Sidebar";
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

  const { isGenerating, metadata, sendMessage, stopGenerating } = useChat({
    activeSession,
    updateSession,
  });

  function handleQuickReply(text: string) {
    void sendMessage(text);
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
        <header className="border-b border-border px-4 py-3 text-sm text-muted">
          AI Assistant
        </header>
        <ChatArea
          session={activeSession}
          isGenerating={isGenerating}
          metadata={metadata}
          onQuickReply={handleQuickReply}
        />
        <ChatInput
          isGenerating={isGenerating}
          onSend={(text) => void sendMessage(text)}
          onStop={stopGenerating}
        />
      </main>
    </div>
  );
}
