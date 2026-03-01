import type { ListingData } from "../types/chat";
import ListingCard from "./ListingCard";

type Props = {
  listings: ListingData[];
  onClose: () => void;
  onRemove: (position: number) => void;
};

export default function ShortlistPanel({ listings, onClose, onRemove }: Props) {
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

      <div className="flex-1 overflow-y-auto p-3 space-y-3">
        {listings.length === 0 ? (
          <p className="pt-8 text-center text-xs text-muted">
            No saved listings yet.
            <br />
            Click the bookmark on a listing card to save it.
          </p>
        ) : (
          listings.map((listing, idx) => (
            <div key={listing.url || idx}>
              <ListingCard listing={listing} isSaved />
              <button
                type="button"
                onClick={() => onRemove(idx + 1)}
                className="mt-1 w-full rounded text-xs text-muted hover:text-red-400"
              >
                Remove from shortlist
              </button>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
