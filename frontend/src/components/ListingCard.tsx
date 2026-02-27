import type { ListingData } from "../types/chat";

type Props = {
  listing: ListingData;
  isSaved?: boolean;
  onSave?: () => void;
};

function toArray(val: string[] | string | undefined): string[] {
  if (Array.isArray(val)) return val;
  if (typeof val === "string" && val.trim()) return [val];
  return [];
}

export default function ListingCard({ listing, isSaved, onSave }: Props) {
  const penalties = toArray(listing.penalty_reasons);
  const hits = toArray(listing.preference_hits);

  return (
    <div className="rounded-lg border border-border bg-panel p-4">
      <div className="flex items-start justify-between gap-2">
        <a
          href={listing.url}
          target="_blank"
          rel="noopener noreferrer"
          className="text-sm font-medium text-[#7dd3fc] underline hover:opacity-80"
        >
          {listing.title}
        </a>
        <div className="flex shrink-0 items-center gap-1.5">
          <span className="rounded bg-accent/20 px-2 py-0.5 text-xs font-semibold text-accent">
            &pound;{listing.price_pcm.toLocaleString()}/pcm
          </span>
          <button
            type="button"
            aria-label={isSaved ? "Saved" : "Save listing"}
            onClick={!isSaved && onSave ? onSave : undefined}
            className={`p-0.5 transition-colors ${isSaved ? "text-accent" : "text-muted hover:text-accent"}`}
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill={isSaved ? "currentColor" : "none"} stroke="currentColor" strokeWidth="2">
              <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z" />
            </svg>
          </button>
        </div>
      </div>

      {(listing.bedrooms > 0 || listing.bathrooms > 0) && (
        <p className="mt-1 text-xs text-muted">
          {[
            listing.bedrooms > 0 && `${listing.bedrooms} bed`,
            listing.bathrooms > 0 && `${listing.bathrooms} bath`,
          ].filter(Boolean).join(" · ")}
        </p>
      )}

      {listing.address && (
        <p className="mt-1 text-xs text-muted">{listing.address}</p>
      )}

      {hits.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {hits.map((hit) => (
            <span
              key={hit}
              className="rounded bg-green-900/40 px-1.5 py-0.5 text-[11px] text-green-400"
            >
              {hit}
            </span>
          ))}
        </div>
      )}

      {penalties.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {penalties.map((reason) => (
            <span
              key={reason}
              className="rounded bg-amber-900/40 px-1.5 py-0.5 text-[11px] text-amber-400"
            >
              {reason}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
