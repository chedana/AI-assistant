import { useState } from "react";
import type { ChatSession } from "../types/chat";

type Props = {
  sessions: ChatSession[];
  activeId: string;
  isGenerating: boolean;
  onSelect: (id: string) => void;
  onCreate: () => void;
  onRemove: (id: string) => void;
  onRename: (id: string, newTitle: string) => void;
};

export default function Sidebar({
  sessions,
  activeId,
  isGenerating,
  onSelect,
  onCreate,
  onRemove,
  onRename,
}: Props) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingTitle, setEditingTitle] = useState("");

  function startEdit(session: ChatSession) {
    setEditingId(session.id);
    setEditingTitle(session.title);
  }

  function commitEdit() {
    if (!editingId) return;
    const original = sessions.find((s) => s.id === editingId)?.title ?? "";
    onRename(editingId, editingTitle.trim() || original);
    setEditingId(null);
  }

  function cancelEdit() {
    setEditingId(null);
  }

  return (
    <aside className="h-[35vh] border-b border-border bg-panel p-3 md:h-screen md:w-72 md:border-b-0 md:border-r">
      <button
        onClick={onCreate}
        className="w-full rounded-lg border border-border px-3 py-2 text-sm hover:bg-neutral-700"
      >
        + New chat
      </button>
      <div className="mt-3 space-y-2 overflow-y-auto pr-1 md:h-[calc(100%-52px)]">
        {sessions.map((session) => (
          <div
            key={session.id}
            className={`group flex items-center gap-2 rounded-lg px-2 py-2 ${
              session.id === activeId ? "bg-neutral-700" : "hover:bg-neutral-800"
            }`}
          >
            {editingId === session.id ? (
              <input
                autoFocus
                className="min-w-0 flex-1 bg-transparent text-sm outline-none border-b border-accent text-text"
                value={editingTitle}
                onChange={(e) => setEditingTitle(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") { e.preventDefault(); commitEdit(); }
                  if (e.key === "Escape") cancelEdit();
                }}
                onBlur={commitEdit}
                onClick={(e) => e.stopPropagation()}
              />
            ) : (
              <button
                className="min-w-0 flex-1 truncate text-left text-sm"
                onClick={() => onSelect(session.id)}
                onDoubleClick={() => startEdit(session)}
                title="Double-click to rename"
              >
                {session.title}
              </button>
            )}
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
