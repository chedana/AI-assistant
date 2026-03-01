import type { ListingData } from "../types/chat";
import ListingCard from "./ListingCard";

type Props = {
  listings: ListingData[];
  onClose: () => void;
  onRemove: (position: number) => void;
  onCompare: () => void;
};

export default function ShortlistPanel({ listings, onClose, onRemove, onCompare }: Props) {
  return (
    <div className="flex h-full w-80 shrink-0 flex-col border-l border-border bg-panel">
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <span className="text-sm font-medium text-text">
          Saved Listings ({listings.length})
        </span>
        <button
          type="button"
          onClick={onClose}
          className="text-muted hover:text-text"
          aria-label="Close shortlist"
        >
          ✕
        </button>
      </div>

      {listings.length >= 2 && (
        <div className="border-b border-border px-3 py-2">
          <button
            type="button"
            onClick={onCompare}
            className="w-full rounded-lg bg-accent/20 py-1.5 text-xs font-medium text-accent hover:bg-accent/30 transition-colors"
          >
            Compare shortlist
          </button>
        </div>
      )}

      <div className="flex-1 overflow-y-auto p-3 space-y-3">
        {listings.length === 0 ? (
          <p className="pt-8 text-center text-xs text-muted">
            No saved listings yet.
            <br />
            Click the bookmark on a listing card to save it.
          </p>
        ) : (
          listings.map((listing, idx) => (
            <ListingCard
              key={listing.url || idx}
              listing={listing}
              isSaved
              onRemove={() => onRemove(idx + 1)}
            />
          ))
        )}
      </div>
    </div>
  );
}
