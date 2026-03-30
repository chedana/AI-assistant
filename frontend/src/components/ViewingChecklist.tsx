import { useState } from "react";
import { viewingChecklist } from "../data/viewingChecklist";
import { useViewingChecklist } from "../hooks/useViewingChecklist";

type Props = {
  listingUrl: string;
  onClose: () => void;
};

export default function ViewingChecklist({ listingUrl, onClose }: Props) {
  const { toggle, isChecked, checkedCount, totalItems, totalChecked } =
    useViewingChecklist(listingUrl);

  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});

  const toggleSection = (title: string) =>
    setCollapsed((prev) => ({ ...prev, [title]: !prev[title] }));

  const progressPct = totalItems > 0 ? Math.round((totalChecked / totalItems) * 100) : 0;

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-end"
      onClick={onClose}
    >
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/50" />

      {/* Panel */}
      <div
        className="relative z-10 flex h-full w-full max-w-md flex-col border-l border-border bg-panel shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-border px-5 py-4">
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
            <span className="text-sm font-bold tracking-tight text-text">
              Viewing Checklist
            </span>
          </div>
          <button
            onClick={onClose}
            className="flex h-8 w-8 items-center justify-center rounded-lg border border-border text-muted transition-colors hover:bg-surface hover:text-text"
          >
            <svg
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        {/* Progress bar */}
        <div className="border-b border-border px-5 py-3">
          <div className="flex items-center justify-between text-[11px] font-bold text-muted">
            <span>
              {totalChecked} of {totalItems} completed
            </span>
            <span className="text-accent">{progressPct}%</span>
          </div>
          <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-surface">
            <div
              className="h-full rounded-full bg-accent transition-all duration-300"
              style={{ width: `${progressPct}%` }}
            />
          </div>
        </div>

        {/* Checklist sections */}
        <div className="flex-1 overflow-y-auto px-5 py-4">
          <div className="space-y-4">
            {viewingChecklist.map((category) => {
              const catChecked = checkedCount(category.title);
              const catTotal = category.items.length;
              const isCollapsed = collapsed[category.title] ?? false;

              return (
                <div key={category.title}>
                  <button
                    onClick={() => toggleSection(category.title)}
                    className="flex w-full items-center justify-between rounded-lg px-2 py-2 transition-colors hover:bg-surface"
                  >
                    <div className="flex items-center gap-2">
                      <svg
                        width="12"
                        height="12"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="3"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        className={`text-muted transition-transform ${isCollapsed ? "" : "rotate-90"}`}
                      >
                        <polyline points="9 18 15 12 9 6" />
                      </svg>
                      <span className="text-xs font-bold uppercase tracking-wider text-text">
                        {category.title}
                      </span>
                    </div>
                    <span
                      className={`text-[10px] font-bold ${
                        catChecked === catTotal ? "text-accent" : "text-muted"
                      }`}
                    >
                      {catChecked}/{catTotal}
                    </span>
                  </button>

                  {!isCollapsed && (
                    <div className="mt-1 space-y-0.5 pl-2">
                      {category.items.map((item) => {
                        const checked = isChecked(item.id);
                        return (
                          <button
                            key={item.id}
                            onClick={() => toggle(item.id)}
                            className="flex w-full items-start gap-3 rounded-lg px-2 py-2 text-left transition-colors hover:bg-surface"
                          >
                            <div
                              className={`mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded border transition-all ${
                                checked
                                  ? "border-accent bg-accent"
                                  : "border-border bg-surface"
                              }`}
                            >
                              {checked && (
                                <svg
                                  width="10"
                                  height="10"
                                  viewBox="0 0 24 24"
                                  fill="none"
                                  stroke="white"
                                  strokeWidth="4"
                                  strokeLinecap="round"
                                  strokeLinejoin="round"
                                >
                                  <polyline points="20 6 9 17 4 12" />
                                </svg>
                              )}
                            </div>
                            <span
                              className={`text-xs leading-relaxed ${
                                checked
                                  ? "text-muted line-through"
                                  : "text-text"
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
    </div>
  );
}
