import { useMemo } from "react";
import type { SessionMetadata, QuickReply } from "../types/chat";
import CompareTable from "./CompareTable";
import ListingCard from "./ListingCard";
import WelcomeScreen from "./WelcomeScreen";

type Props = {
  metadata: SessionMetadata | null;
  isGenerating: boolean;
  savedIds: Set<string>;
  quickReplies: QuickReply[] | undefined;
  onSaveListing: (pageIndex: number) => void;
  onRemoveListing: (position: number) => void;
  onShowMore: () => void;
  onQuickReply: (text: string, routeHint?: Record<string, unknown>) => void;
  onSuggestionClick: (text: string) => void;
};

export default function ListingsPanel({
  metadata,
  isGenerating,
  savedIds,
  quickReplies,
  onSaveListing,
  onRemoveListing,
  onShowMore,
  onQuickReply,
  onSuggestionClick,
}: Props) {
  const results = metadata?.search_results;
  const compare = metadata?.compare_data;
  const hasResults = results && results.listings.length > 0;
  const hasCompare = compare && compare.listings.length >= 2;

  // Filter quick replies to only show search-relevant ones in the listings panel
  const actionReplies = useMemo(() => {
    if (!quickReplies || isGenerating) return [];
    return quickReplies.filter((r) => {
      const intent = r.route_hint?.intent as string | undefined;
      return intent === "Search" || intent === "Compare";
    });
  }, [quickReplies, isGenerating]);

  return (
    <section className="flex h-full flex-1 flex-col overflow-hidden bg-surface">
      {/* Results header */}
      {hasResults && (
        <div className="flex shrink-0 items-center justify-between border-b border-border px-5 py-3">
          <div className="flex items-center gap-3">
            <span className="text-sm font-medium text-text">
              {results.total} {results.total === 1 ? "property" : "properties"}
            </span>
            {isGenerating && (
              <span className="animate-pulse text-xs text-muted">
                Updating…
              </span>
            )}
          </div>
          {/* Action quick replies (Lower budget, Compare, etc.) */}
          {actionReplies.length > 0 && (
            <div className="flex gap-2">
              {actionReplies.map((reply) => (
                <button
                  key={reply.text}
                  onClick={() => onQuickReply(reply.text, reply.route_hint)}
                  className="rounded-lg border border-border px-3 py-1 text-xs text-muted transition-colors hover:border-neutral-500 hover:text-text"
                >
                  {reply.label}
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Scrollable content */}
      <div className="flex-1 overflow-y-auto">
        {hasCompare && (
          <div className="border-b border-border p-5">
            <CompareTable data={compare!} />
          </div>
        )}

        {hasResults ? (
          <div className="space-y-4 p-5">
            {results.listings.map((listing, idx) => (
              <ListingCard
                key={listing.url || idx}
                listing={listing}
                isSaved={savedIds.has(listing.url)}
                onSave={() => onSaveListing(idx + 1)}
                onRemove={() => onRemoveListing(idx + 1)}
              />
            ))}

            {/* Show more */}
            {results.has_more && (
              <button
                disabled={isGenerating}
                onClick={onShowMore}
                className="w-full rounded-xl border border-border py-3 text-sm text-muted transition-colors hover:border-neutral-500 hover:text-text disabled:cursor-not-allowed disabled:opacity-40"
              >
                Show more results ({results.remaining} remaining)
              </button>
            )}
          </div>
        ) : isGenerating ? (
          <div className="flex h-full flex-col items-center justify-center gap-3 text-muted">
            <div className="flex gap-1.5">
              <span className="thinking-dot" />
              <span className="thinking-dot" style={{ animationDelay: "0.2s" }} />
              <span className="thinking-dot" style={{ animationDelay: "0.4s" }} />
            </div>
            <span className="text-sm">Searching properties…</span>
          </div>
        ) : (
          <WelcomeScreen onSuggestionClick={onSuggestionClick} />
        )}
      </div>
    </section>
  );
}
