import type { ListingData } from "../types/chat";

type Props = {
  listing: ListingData;
};

export default function ListingCard({ listing }: Props) {
  const hasPenalties = listing.penalty_reasons && listing.penalty_reasons.length > 0;
  const hasHits = listing.preference_hits && listing.preference_hits.length > 0;

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
        <span className="shrink-0 rounded bg-accent/20 px-2 py-0.5 text-xs font-semibold text-accent">
          &pound;{listing.price_pcm.toLocaleString()}/pcm
        </span>
      </div>

      <p className="mt-1 text-xs text-muted">
        {listing.bedrooms} bed &middot; {listing.bathrooms} bath
      </p>

      {listing.address && (
        <p className="mt-1 text-xs text-muted">{listing.address}</p>
      )}

      {hasHits && (
        <div className="mt-2 flex flex-wrap gap-1">
          {listing.preference_hits.map((hit) => (
            <span
              key={hit}
              className="rounded bg-green-900/40 px-1.5 py-0.5 text-[11px] text-green-400"
            >
              {hit}
            </span>
          ))}
        </div>
      )}

      {hasPenalties && (
        <div className="mt-2 flex flex-wrap gap-1">
          {listing.penalty_reasons.map((reason) => (
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
