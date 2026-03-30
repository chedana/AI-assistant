import { useState, useRef, useEffect } from "react";
import { createPortal } from "react-dom";
import { VIEWING_CHECKLIST } from "../data/viewingChecklist";
import { useViewingChecklist } from "../hooks/useViewingChecklist";
import { useScrollLock } from "../hooks/useScrollLock";
import { useFocusTrap } from "../hooks/useFocusTrap";

type Props = {
  listingUrl: string;
  onClose: () => void;
};

export default function ViewingChecklist({ listingUrl, onClose }: Props) {
  const panelRef = useRef<HTMLDivElement>(null);
  const { toggle, isChecked, checkedCount, totalCount, totalChecked, totalItems } =
    useViewingChecklist(listingUrl);

  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});

  useScrollLock(true);
  useFocusTrap(panelRef, true);

  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleEsc);
    return () => window.removeEventListener("keydown", handleEsc);
  }, [onClose]);

  const toggleCollapse = (title: string) => {
    setCollapsed((prev) => ({ ...prev, [title]: !prev[title] }));
  };

  const progressPct = totalItems > 0 ? Math.round((totalChecked / totalItems) * 100) : 0;

  return createPortal(
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm transition-opacity"
        onClick={onClose}
      />

      {/* Panel — slides from right */}
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        className="fixed inset-y-0 right-0 z-50 flex w-full flex-col bg-surface shadow-2xl transition-transform duration-300 md:w-[480px] border-l border-border animate-in slide-in-from-right"
      >
        {/* Header */}
        <div className="flex shrink-0 items-center justify-between border-b border-border px-6 py-4">
          <div className="flex items-center gap-3">
            <svg
              width="20"
              height="20"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              className="text-accent"
            >
              <path d="M9 11l3 3L22 4" />
              <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" />
            </svg>
            <div>
              <h2 className="text-sm font-bold tracking-tight text-text">Viewing Checklist</h2>
              <p className="text-[10px] font-medium text-muted">
                {totalChecked}/{totalItems} completed
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="flex h-10 w-10 items-center justify-center rounded-xl border border-border bg-surface text-muted transition-colors hover:border-accent hover:text-accent"
          >
            <svg
              width="20"
              height="20"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        {/* Overall progress bar */}
        <div className="shrink-0 px-6 py-3 border-b border-border">
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-[10px] font-bold uppercase tracking-widest text-muted">
              Overall Progress
            </span>
            <span className="text-[10px] font-bold text-accent">{progressPct}%</span>
          </div>
          <div className="h-2 w-full overflow-hidden rounded-full bg-panel">
            <div
              className="h-full rounded-full bg-accent transition-all duration-300"
              style={{ width: `${progressPct}%` }}
            />
          </div>
        </div>

        {/* Scrollable checklist content */}
        <div className="flex-1 overflow-y-auto custom-scrollbar px-6 py-4">
          <div className="space-y-4">
            {VIEWING_CHECKLIST.map((category) => {
              const checked = checkedCount(category.title);
              const total = totalCount(category.title);
              const isCollapsed = collapsed[category.title] ?? false;
              const allDone = checked === total;

              return (
                <div
                  key={category.title}
                  className="rounded-xl border border-border bg-panel overflow-hidden"
                >
                  {/* Category header — clickable to collapse */}
                  <button
                    onClick={() => toggleCollapse(category.title)}
                    className="flex w-full items-center justify-between px-4 py-3 text-left transition-colors hover:bg-surface/50"
                  >
                    <div className="flex items-center gap-2">
                      <svg
                        width="14"
                        height="14"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="2.5"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        className={`transition-transform ${isCollapsed ? "-rotate-90" : ""}`}
                      >
                        <polyline points="6 9 12 15 18 9" />
                      </svg>
                      <span className="text-xs font-bold tracking-tight text-text">
                        {category.title}
                      </span>
                    </div>
                    <span
                      className={`text-[10px] font-bold ${
                        allDone ? "text-accent" : "text-muted"
                      }`}
                    >
                      {checked}/{total}
                    </span>
                  </button>

                  {/* Items */}
                  {!isCollapsed && (
                    <div className="border-t border-border/50 px-2 py-2">
                      {category.items.map((item) => {
                        const itemChecked = isChecked(item.id);
                        return (
                          <button
                            key={item.id}
                            onClick={() => toggle(item.id)}
                            className="flex w-full items-start gap-3 rounded-lg px-2 py-2.5 text-left transition-colors hover:bg-surface/50"
                            style={{ minHeight: "44px" }}
                          >
                            {/* Custom checkbox */}
                            <div
                              className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-md border-2 transition-all duration-200 ${
                                itemChecked
                                  ? "border-accent bg-accent"
                                  : "border-border bg-surface hover:border-accent/50"
                              }`}
                            >
                              {itemChecked && (
                                <svg
                                  width="12"
                                  height="12"
                                  viewBox="0 0 24 24"
                                  fill="none"
                                  stroke="white"
                                  strokeWidth="3"
                                  strokeLinecap="round"
                                  strokeLinejoin="round"
                                >
                                  <polyline points="20 6 9 17 4 12" />
                                </svg>
                              )}
                            </div>
                            <span
                              className={`text-xs leading-snug transition-colors ${
                                itemChecked ? "text-muted line-through" : "text-text"
                              }`}
                            >
                              {item.label}
                            </span>
                          </button>
                        );
                      })}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </>,
    document.body,
  );
}
