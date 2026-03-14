import { useMemo, useEffect, useRef, useState } from "react";
import type { SessionMetadata, QuickReply, ListingData } from "../types/chat";
import CompareTable from "./CompareTable";
import ListingCard from "./ListingCard";
import ListingDetailDrawer from "./ListingDetailDrawer";
import WelcomeScreen from "./WelcomeScreen";
import MapView from "./MapView";

type Props = {
  metadata: SessionMetadata | null;
  isGenerating: boolean;
  isSilentAction: boolean;
  savedIds: Set<string>;
  quickReplies: QuickReply[] | undefined;
  viewMode: "list" | "map";
  onViewModeToggle: (mode: "list" | "map") => void;
  onSaveListing: (pageIndex: number, url: string) => void;
  onRemoveListing: (pageIndex: number, url: string) => void;
  onShowMore: () => void;
  onShowPrev: () => void;
  onQuickReply: (text: string, routeHint?: Record<string, unknown>) => void;
  onSuggestionClick: (text: string, routeHint?: Record<string, unknown>) => void;
};

function ListingSkeleton() {
  return (
    <div className="flex animate-pulse overflow-hidden rounded-xl border border-border bg-panel">
      <div className="h-48 w-72 shrink-0 bg-white/5" />
      <div className="flex flex-1 flex-col gap-3 p-4">
        <div className="h-5 w-3/4 rounded bg-white/5" />
        <div className="h-4 w-1/2 rounded bg-white/5" />
        <div className="mt-auto flex gap-2">
          <div className="h-6 w-16 rounded bg-white/5" />
          <div className="h-6 w-16 rounded bg-white/5" />
        </div>
      </div>
    </div>
  );
}

export default function ListingsPanel({
  metadata,
  isGenerating,
  isSilentAction,
  savedIds,
  quickReplies,
  viewMode,
  onViewModeToggle,
  onSaveListing,
  onRemoveListing,
  onShowMore,
  onShowPrev,
  onQuickReply,
  onSuggestionClick,
}: Props) {
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const [selectedListing, setSelectedListing] = useState<ListingData | null>(null);
  const [didGeoSearch, setDidGeoSearch] = useState(false);
  
  const results = metadata?.search_results;
  const compare = metadata?.compare_data;
  const hasResults = results && results.listings.length > 0;
  const hasCompare = compare && compare.listings.length >= 2;

  // Pagination data
  const pageIndex = results?.page_index ?? 0;
  const listingsSig = results?.listings?.map(l => l.url).join(',') ?? '';

  // Scroll to top only on page change or if the result set actually changes
  useEffect(() => {
    if (scrollContainerRef.current && viewMode === "list") {
      scrollContainerRef.current.scrollTo({ top: 0, behavior: "smooth" });
    }
  }, [pageIndex, listingsSig, viewMode]);

  const pageSize = 5; // Standard page size from backend
  const totalResults = results?.total ?? 0;
  const startRange = pageIndex * pageSize + 1;
  const endRange = Math.min(startRange + (results?.listings.length ?? 0) - 1, totalResults);
  const totalPages = Math.ceil(totalResults / pageSize);

  // Use backend-computed match_pct (requirement satisfaction), fallback to 100.
  const normalizedScores = useMemo(() => {
    if (!results?.listings.length) return [];
    return results.listings.map(l => l.match_pct ?? 100);
  }, [results?.listings]);

  // Filter quick replies to only show search-relevant ones in the listings panel
  const actionReplies = useMemo(() => {
    if (!quickReplies) return [];
    return quickReplies.filter((r) => {
      const intent = r.route_hint?.intent as string | undefined;
      return intent === "Search" || intent === "Compare";
    });
  }, [quickReplies]);

  return (
    <>
      <section className="flex h-full flex-1 flex-col overflow-hidden bg-surface">
        {/* Results header */}
        {hasResults && (
          <div className="flex shrink-0 items-center justify-between border-b border-border bg-panel/50 px-5 py-3 backdrop-blur-md">
            <div className="flex items-center gap-4">
              <div className="flex flex-col">
                <span className="text-sm font-bold tracking-tight text-text">
                  {results.total} {results.total === 1 ? "Property" : "Properties"}
                </span>
                <span className="text-[10px] font-medium uppercase tracking-widest text-muted">
                  Search Results
                </span>
              </div>
              
              {/* View Toggle */}
              <div className="ml-2 flex overflow-hidden rounded-lg border border-border bg-surface p-0.5">
                <button
                  onClick={() => onViewModeToggle("list")}
                  className={`flex items-center gap-1.5 px-2.5 py-1 text-[11px] font-bold transition-all ${
                    viewMode === "list" ? "bg-panel text-accent shadow-sm" : "text-muted hover:text-text"
                  }`}
                >
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <line x1="8" y1="6" x2="21" y2="6" /><line x1="8" y1="12" x2="21" y2="12" /><line x1="8" y1="18" x2="21" y2="18" /><line x1="3" y1="6" x2="3.01" y2="6" /><line x1="3" y1="12" x2="3.01" y2="12" /><line x1="3" y1="18" x2="3.01" y2="18" />
                  </svg>
                  List
                </button>
                <button
                  onClick={() => onViewModeToggle("map")}
                  className={`flex items-center gap-1.5 px-2.5 py-1 text-[11px] font-bold transition-all ${
                    viewMode === "map" ? "bg-panel text-accent shadow-sm" : "text-muted hover:text-text"
                  }`}
                >
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <polygon points="1 6 1 22 8 18 16 22 23 18 23 2 16 6 8 2 1 6" /><line x1="8" y1="2" x2="8" y2="18" /><line x1="16" y1="6" x2="16" y2="22" />
                  </svg>
                  Map
                </button>
              </div>
            </div>

            <div className="flex items-center gap-2">
              {isGenerating && !isSilentAction && (
                <div className="mr-2 flex items-center gap-1.5">
                  <div className="h-1.5 w-1.5 animate-bounce rounded-full bg-accent" />
                  <span className="text-[10px] font-bold uppercase tracking-tighter text-accent">Updating</span>
                </div>
              )}
              {/* Action quick replies */}
              <div className="hidden gap-1.5 sm:flex">
                {actionReplies.map((reply) => (
                  <button
                    key={reply.text}
                    onClick={() => onQuickReply(reply.text, reply.route_hint)}
                    disabled={isGenerating}
                    className="rounded-lg border border-border bg-surface px-2.5 py-1 text-[11px] font-bold text-muted transition-all hover:border-neutral-500 hover:text-text disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    {reply.label}
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Content area: Scrollable for list, fixed for map */}
        <div 
          ref={scrollContainerRef}
          className={`flex-1 ${viewMode === "list" ? "overflow-y-auto" : "overflow-hidden"}`}
        >
          {hasCompare && viewMode === "list" && (
            <div className="border-b border-border p-5">
              <CompareTable data={compare!} />
            </div>
          )}

          {hasResults ? (
            viewMode === "list" ? (
              <div className="mx-auto max-w-4xl p-5 md:p-6">
                <div className="space-y-4">
                  {results.listings.map((listing, idx) => (
                    <ListingCard
                      key={listing.url || idx}
                      listing={listing}
                      isSaved={savedIds.has(listing.url)}
                      displayScore={normalizedScores[idx] ?? undefined}
                      onSave={isGenerating ? undefined : () => onSaveListing(idx + 1, listing.url)}
                      onRemove={isGenerating ? undefined : () => onRemoveListing(idx + 1, listing.url)}
                      onClick={() => setSelectedListing(listing)}
                    />
                  ))}

                  {isGenerating && !isSilentAction && (
                    <div className="space-y-4">
                      <ListingSkeleton />
                      <ListingSkeleton />
                    </div>
                  )}
                </div>

                {/* Pagination Bar - Integrated at bottom of list */}
                <div className="mt-8 border-t border-border pt-6 pb-12">
                  <div className="flex items-center justify-between">
                    <button
                      disabled={isGenerating || pageIndex === 0}
                      onClick={onShowPrev}
                      className="flex items-center gap-2 px-4 py-2 text-sm font-bold text-muted transition-all hover:text-accent disabled:cursor-not-allowed disabled:opacity-20"
                    >
                      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                        <line x1="19" y1="12" x2="5" y2="12" />
                        <polyline points="12 19 5 12 12 5" />
                      </svg>
                      Previous
                    </button>
                    
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-medium text-muted">Page</span>
                      <div className="flex h-9 min-w-[40px] items-center justify-center rounded-lg border border-border bg-panel px-3 text-sm font-bold text-text">
                        {pageIndex + 1}
                      </div>
                      <span className="text-xs font-medium text-muted">of {totalPages}</span>
                      <div className="ml-4 h-4 w-px bg-border" />
                      <span className="ml-4 text-xs font-bold text-muted/60">
                        {startRange}–{endRange} of {totalResults}
                      </span>
                    </div>

                    <button
                      disabled={isGenerating || !results.has_more}
                      onClick={onShowMore}
                      className="flex items-center gap-2 px-4 py-2 text-sm font-bold text-muted transition-all hover:text-accent disabled:cursor-not-allowed disabled:opacity-20"
                    >
                      Next
                      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                        <line x1="5" y1="12" x2="19" y2="12" />
                        <polyline points="12 5 19 12 12 19" />
                      </svg>
                    </button>
                  </div>
                </div>
              </div>
            ) : (
              <MapView
                listings={results.all_listings || results.listings}
                onListingClick={setSelectedListing}
                skipFitBounds={didGeoSearch}
                onSearchArea={(geo) => {
                    setDidGeoSearch(true);
                    onSuggestionClick(
                      `Search rentals near this area`,
                      { intent: "Search", set_constraints: { geo_bound: geo }, clear_fields: ["location_keywords"] }
                    );
                }}
              />
            )
          ) : isGenerating && !isSilentAction ? (
            <div className="mx-auto max-w-4xl space-y-4 p-5 md:p-6">
              <ListingSkeleton />
              <ListingSkeleton />
              <ListingSkeleton />
            </div>
          ) : (
            <WelcomeScreen onSuggestionClick={onSuggestionClick} />
          )}
        </div>
      </section>

      {/* Listing Detail Drawer Overlay */}
      <ListingDetailDrawer 
        listing={selectedListing} 
        onClose={() => setSelectedListing(null)} 
      />
    </>
  );
}
