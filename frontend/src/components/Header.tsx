import { useState, useRef, useEffect } from "react";
import type { ChatSession, ConstraintsMeta } from "../types/chat";
import ConstraintTags from "./ConstraintTags";

type Props = {
  sessions: ChatSession[];
  activeId: string;
  isGenerating: boolean;
  constraints: ConstraintsMeta | undefined;
  shortlistCount: number;
  onSelectSession: (id: string) => void;
  onCreateSession: () => void;
  onRemoveSession: (id: string) => void;
  onRemoveConstraint: (clearFields: string[], actionLabel: string) => void;
  onShortlistToggle: () => void;
};

export default function Header({
  sessions,
  activeId,
  isGenerating,
  constraints,
  shortlistCount,
  onSelectSession,
  onCreateSession,
  onRemoveSession,
  onRemoveConstraint,
  onShortlistToggle,
}: Props) {
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  // Close menu on click outside
  useEffect(() => {
    if (!menuOpen) return;
    function handleClick(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [menuOpen]);

  const hasConstraints = constraints && Object.keys(constraints).length > 0;

  return (
    <header className="shrink-0 border-b border-border bg-panel">
      {/* Row 1: Brand + actions */}
      <div className="flex h-12 items-center justify-between px-4">
        {/* Left: Logo */}
        <div className="flex items-center gap-2">
          <span className="text-lg font-bold text-accent">OpenClaw</span>
          <span className="hidden text-xs text-muted sm:inline">
            AI-powered rental search
          </span>
        </div>

        {/* Right: Actions */}
        <div className="flex items-center gap-2">
          {/* Shortlist badge */}
          {shortlistCount > 0 && (
            <button
              type="button"
              onClick={onShortlistToggle}
              className="flex items-center gap-1 rounded-full bg-accent/15 px-2.5 py-1 text-xs font-medium text-accent transition-colors hover:bg-accent/25"
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" strokeWidth="2">
                <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z" />
              </svg>
              Saved ({shortlistCount})
            </button>
          )}

          {/* Session menu */}
          <div className="relative" ref={menuRef}>
            <button
              type="button"
              onClick={() => setMenuOpen((o) => !o)}
              className="flex items-center gap-1 rounded-lg px-2 py-1.5 text-xs text-muted transition-colors hover:bg-neutral-800 hover:text-text"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                <line x1="3" y1="6" x2="21" y2="6" />
                <line x1="3" y1="12" x2="21" y2="12" />
                <line x1="3" y1="18" x2="21" y2="18" />
              </svg>
            </button>
            {menuOpen && (
              <div className="absolute right-0 top-full z-50 mt-1 w-64 rounded-lg border border-border bg-panel shadow-xl">
                <button
                  type="button"
                  onClick={() => {
                    onCreateSession();
                    setMenuOpen(false);
                  }}
                  className="flex w-full items-center gap-2 border-b border-border px-3 py-2.5 text-xs text-accent hover:bg-neutral-800"
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <line x1="12" y1="5" x2="12" y2="19" />
                    <line x1="5" y1="12" x2="19" y2="12" />
                  </svg>
                  New search
                </button>
                <div className="max-h-60 overflow-y-auto py-1">
                  {sessions.map((s) => (
                    <div
                      key={s.id}
                      className={`group flex items-center justify-between px-3 py-2 text-xs ${
                        s.id === activeId
                          ? "bg-neutral-800 text-text"
                          : "text-muted hover:bg-neutral-800 hover:text-text"
                      }`}
                    >
                      <button
                        type="button"
                        onClick={() => {
                          onSelectSession(s.id);
                          setMenuOpen(false);
                        }}
                        className="min-w-0 flex-1 truncate text-left"
                      >
                        {s.title}
                      </button>
                      <button
                        type="button"
                        onClick={() => onRemoveSession(s.id)}
                        disabled={isGenerating}
                        className="ml-2 hidden shrink-0 text-muted hover:text-red-400 group-hover:inline disabled:opacity-40"
                      >
                        ✕
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Row 2: Active constraint chips */}
      {hasConstraints && (
        <div className="flex flex-wrap items-center gap-2 border-t border-border px-4 py-2">
          <span className="text-xs text-muted">Filters:</span>
          <ConstraintTags
            constraints={constraints!}
            onRemove={onRemoveConstraint}
            inline
          />
        </div>
      )}
    </header>
  );
}
