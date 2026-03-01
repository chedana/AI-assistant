import type { ChatSession } from "../types/chat";

type Props = {
  sessions: ChatSession[];
  activeId: string;
  isGenerating: boolean;
  shortlistCount: number;
  onSelect: (id: string) => void;
  onCreate: () => void;
  onRemove: (id: string) => void;
  onOpenShortlist: () => void;
};

export default function Sidebar({
  sessions,
  activeId,
  isGenerating,
  shortlistCount,
  onSelect,
  onCreate,
  onRemove,
  onOpenShortlist,
}: Props) {
  return (
    <aside className="h-[35vh] border-b border-border bg-panel p-3 md:h-screen md:w-72 md:border-b-0 md:border-r">
      <div className="flex gap-2">
        <button
          onClick={onCreate}
          className="flex-1 rounded-lg border border-border px-3 py-2 text-sm hover:bg-neutral-700"
        >
          + New chat
        </button>
        {shortlistCount > 0 && (
          <button
            type="button"
            onClick={onOpenShortlist}
            className="flex items-center gap-1 rounded-lg border border-border px-3 py-2 text-xs font-medium text-accent hover:bg-neutral-700"
            title="View saved listings"
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" strokeWidth="2">
              <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z" />
            </svg>
            {shortlistCount}
          </button>
        )}
      </div>
      <div className="mt-3 space-y-2 overflow-y-auto pr-1 md:h-[calc(100%-52px)]">
        {sessions.map((session) => (
          <div
            key={session.id}
            className={`group flex items-center gap-2 rounded-lg px-2 py-2 ${
              session.id === activeId ? "bg-neutral-700" : "hover:bg-neutral-800"
            }`}
          >
            <button
              className="min-w-0 flex-1 truncate text-left text-sm"
              onClick={() => onSelect(session.id)}
            >
              {session.title}
            </button>
            <button
              className="hidden text-xs text-muted group-hover:block"
              onClick={() => onRemove(session.id)}
              disabled={isGenerating && session.id === activeId}
              title="Delete chat"
            >
              delete
            </button>
          </div>
        ))}
      </div>
    </aside>
  );
}
