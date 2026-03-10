import { useState, useRef, useEffect } from "react";
import type { ChatSession, ConstraintsMeta } from "../types/chat";
import ConstraintTags from "./ConstraintTags";

type Props = {
  sessions: ChatSession[];
  activeId: string;
  isGenerating: boolean;
  constraints: ConstraintsMeta | undefined;
  shortlistCount: number;
  mobileView: "chat" | "results";
  onSelectSession: (id: string) => void;
  onCreateSession: () => void;
  onRemoveSession: (id: string) => void;
  onRemoveConstraint: (fields: string[]) => void;
  onShortlistToggle: () => void;
  onMobileViewToggle: (view: "chat" | "results") => void;
};

export default function Header({
  sessions,
  activeId,
  isGenerating,
  constraints,
  shortlistCount,
  mobileView,
  onSelectSession,
  onCreateSession,
  onRemoveSession,
  onRemoveConstraint,
  onShortlistToggle,
  onMobileViewToggle,
}: Props) {
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setMenuOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const hasConstraints = constraints && Object.keys(constraints).length > 0;

  return (
    <header className="z-30 flex shrink-0 flex-col border-b border-border bg-panel shadow-sm">
      {/* Row 1: Logo, Shortlist, Menu */}
      <div className="flex h-14 items-center justify-between px-4 md:px-6">
        <div className="flex items-center gap-3">
          <div className="flex cursor-pointer items-center gap-2" onClick={() => onMobileViewToggle("chat")}>
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-accent text-surface shadow-lg shadow-accent/20">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" />
              </svg>
            </div>
            <div className="flex flex-col">
              <span className="text-lg font-bold leading-none tracking-tight text-text">OpenClaw</span>
              <span className="hidden text-[10px] font-medium uppercase tracking-widest text-muted sm:inline">AI Rental Search</span>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2 md:gap-4">
          {shortlistCount > 0 && (
            <button
              onClick={onShortlistToggle}
              className="group flex items-center gap-2 rounded-full bg-accent/10 px-3 py-1.5 text-accent transition-all hover:bg-accent/20 active:scale-95"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" stroke="none">
                <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z" />
              </svg>
              <span className="text-xs font-bold">{shortlistCount}</span>
            </button>
          )}

          <div className="relative" ref={menuRef}>
            <button
              onClick={() => setMenuOpen(!menuOpen)}
              className={`flex h-9 w-9 items-center justify-center rounded-lg border border-border text-muted transition-colors hover:bg-surface hover:text-text ${menuOpen ? "bg-surface text-text" : ""}`}
            >
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <line x1="3" y1="12" x2="21" y2="12" />
                <line x1="3" y1="6" x2="21" y2="6" />
                <line x1="3" y1="18" x2="21" y2="18" />
              </svg>
            </button>

            {menuOpen && (
              <div className="absolute right-0 mt-2 w-72 origin-top-right rounded-xl border border-border bg-panel p-2 shadow-2xl ring-1 ring-black ring-opacity-5 focus:outline-none z-50">
                <button
                  onClick={() => {
                    onCreateSession();
                    setMenuOpen(false);
                  }}
                  className="flex w-full items-center gap-3 rounded-lg px-4 py-2.5 text-sm font-semibold text-accent transition-colors hover:bg-accent/10"
                >
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <line x1="12" y1="5" x2="12" y2="19" />
                    <line x1="5" y1="12" x2="19" y2="12" />
                  </svg>
                  New Search
                </button>
                
                <div className="my-1 h-px bg-border" />
                
                <div className="max-h-80 overflow-y-auto">
                  {sessions.map((session) => (
                    <div
                      key={session.id}
                      className="group flex items-center gap-1"
                    >
                      <button
                        onClick={() => {
                          onSelectSession(session.id);
                          setMenuOpen(false);
                        }}
                        className={`flex flex-1 items-center gap-3 rounded-lg px-4 py-2 text-left text-sm transition-colors ${
                          session.id === activeId
                            ? "bg-surface text-text"
                            : "text-muted hover:bg-surface/50 hover:text-text"
                        }`}
                      >
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="shrink-0 opacity-40">
                          <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
                        </svg>
                        <span className="truncate">{session.title}</span>
                      </button>
                      <button
                        disabled={isGenerating}
                        onClick={() => onRemoveSession(session.id)}
                        className="invisible flex h-8 w-8 items-center justify-center rounded-lg text-muted hover:bg-red-900/20 hover:text-red-400 group-hover:visible disabled:opacity-0"
                      >
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <line x1="18" y1="6" x2="6" y2="18" />
                          <line x1="6" y1="6" x2="18" y2="18" />
                        </svg>
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Row 2: Constraints (Filter Chips) */}
      {hasConstraints && (
        <div className="flex items-center gap-3 border-t border-border bg-surface/30 px-4 py-2 md:px-6">
          <span className="text-[10px] font-bold uppercase tracking-widest text-muted">Filters</span>
          <div className="flex flex-1 flex-wrap gap-1.5">
            <ConstraintTags
              constraints={constraints}
              onRemove={onRemoveConstraint}
              inline
            />
          </div>
        </div>
      )}
    </header>
  );
}
