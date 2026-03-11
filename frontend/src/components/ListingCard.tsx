import { useState } from "react";
import type { ListingData } from "../types/chat";

type Props = {
  listing: ListingData;
  isSaved?: boolean;
  compact?: boolean;
  displayScore?: number;  // 0–100, pre-normalized by parent
  onSave?: () => void;
  onRemove?: () => void;
  onClick?: () => void;
};

function toArray(val: string[] | string | undefined): string[] {
  const clean = (s: string) => {
    return s.trim().replace(/^[-•*+]\s*/, '').trim();
  };
  if (Array.isArray(val)) return val.map(clean).filter(Boolean);
  if (typeof val === "string" && val.trim()) return val.split(/[;\n]+/).map(clean).filter(Boolean);
  return [];
}

function ImageCarousel({ images, title, price, weeklyPrice }: { images: string[]; title: string; price: number; weeklyPrice: number }) {
  const [idx, setIdx] = useState(0);
  const prev = (e: React.MouseEvent) => { e.stopPropagation(); setIdx(i => (i - 1 + images.length) % images.length); };
  const next = (e: React.MouseEvent) => { e.stopPropagation(); setIdx(i => (i + 1) % images.length); };
  return (
    <div className="relative h-64 w-72 shrink-0 overflow-hidden bg-white/5 md:w-80 lg:w-96">
      {images.length > 0 ? (
        <img key={idx} src={images[idx]} alt={title}
          className="h-full w-full object-cover transition-transform duration-500 group-hover:scale-105" loading="lazy" />
      ) : (
        <div className="flex h-full w-full items-center justify-center text-white/10">
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" /></svg>
        </div>
      )}
      {images.length > 1 && (
        <>
          <button onClick={prev} className="absolute left-2 top-1/2 -translate-y-1/2 z-10 bg-black/50 hover:bg-black/75 text-white rounded-full w-7 h-7 flex items-center justify-center transition-colors">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><polyline points="15 18 9 12 15 6"/></svg>
          </button>
          <button onClick={next} className="absolute right-2 top-1/2 -translate-y-1/2 z-10 bg-black/50 hover:bg-black/75 text-white rounded-full w-7 h-7 flex items-center justify-center transition-colors">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><polyline points="9 18 15 12 9 6"/></svg>
          </button>
          <div className="absolute bottom-14 left-1/2 -translate-x-1/2 flex gap-1 z-10">
            {images.slice(0, 8).map((_, i) => (
              <button key={i} onClick={(e) => { e.stopPropagation(); setIdx(i); }}
                className={`w-1.5 h-1.5 rounded-full transition-colors ${i === idx ? 'bg-white' : 'bg-white/40'}`} />
            ))}
          </div>
          <span className="absolute top-2 right-2 z-10 bg-black/60 text-white/80 text-[10px] font-bold px-2 py-0.5 rounded-full">{idx + 1}/{images.length}</span>
        </>
      )}
      <div className="absolute inset-0 bg-gradient-to-t from-black/95 via-black/20 to-transparent pointer-events-none" />
      <div className="absolute bottom-4 left-4">
        <div className="flex flex-col">
          <div className="flex items-baseline gap-1">
            <span className="text-2xl font-black text-white">£{price.toLocaleString()}</span>
            <span className="text-xs font-medium text-white/60">pcm</span>
          </div>
          <span className="text-[10px] font-bold text-white/40 uppercase tracking-wider">£{weeklyPrice} pw</span>
        </div>
      </div>
    </div>
  );
}

export default function ListingCard({ listing, isSaved, compact, displayScore, onSave, onRemove, onClick }: Props) {
  const penalties = toArray(listing.penalty_reasons);
  const hits = toArray(listing.preference_hits);
  
  // F-P1: De-duplicate title and address
  const showAddress = listing.address && listing.address.toLowerCase() !== listing.title.toLowerCase();

  // F-P2: Refined "Available ask agent" styling
  const isAvailableUncertain = listing.available_from?.toLowerCase().includes("ask agent") || !listing.available_from;

  // New Data Points
  const weeklyPrice = Math.round((listing.price_pcm * 12) / 52);
  const propertyFeatures = toArray(listing.features).slice(0, 3);
  
  // Format description: collapse broken <PARA> tags into spaces, otherwise use space.
  // For the card summary, we don't need newlines at all, just a clean string.
  const cleanDescription = listing.description
    ?.replace(/<PARA>/gi, " ")
    .replace(/\s{2,}/g, " ")
    .trim();
  const summary = cleanDescription ? (cleanDescription.length > 140 ? cleanDescription.substring(0, 137) + "..." : cleanDescription) : null;

  // Compact mode: used in ShortlistPanel
  if (compact) {
    return (
      <div 
        onClick={onClick}
        className="group relative overflow-hidden rounded-xl border border-border bg-panel p-3 transition-all hover:border-accent/40 cursor-pointer"
      >
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <a href={listing.url} target="_blank" rel="noopener noreferrer" onClick={(e) => e.stopPropagation()} className="block truncate text-xs font-bold text-text hover:text-accent">
              {listing.title}
            </a>
            <div className="mt-1 flex items-center gap-2 text-[10px] text-muted">
              <span className="font-bold text-accent">£{listing.price_pcm.toLocaleString()}</span>
              <span>·</span>
              <span>{listing.bedrooms} bed</span>
            </div>
          </div>
          <button 
            onClick={(e) => { e.stopPropagation(); isSaved ? onRemove?.() : onSave?.(); }} 
            className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border transition-all duration-200 ${
              isSaved 
                ? "border-accent bg-accent text-white shadow-sm shadow-accent/20" 
                : "border-border bg-surface text-muted hover:border-accent hover:text-accent hover:bg-accent/5"
            }`}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill={isSaved ? "currentColor" : "none"} stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z" />
            </svg>
          </button>
        </div>
      </div>
    );
  }

  return (
    <div 
      onClick={onClick}
      className="group relative flex min-h-[200px] cursor-pointer overflow-hidden rounded-2xl border border-border bg-panel transition-all duration-300 hover:border-accent/40 hover:shadow-2xl hover:shadow-accent/5"
    >
      {/* Match Score Badge */}
      {displayScore != null && (
        <div className="absolute left-3 top-3 z-10">
          <div className={`flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[10px] font-bold shadow-lg backdrop-blur-md ${
            displayScore >= 90 ? "bg-accent/20 text-accent" : "bg-white/10 text-text"
          }`}>
            <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z" />
            </svg>
            {displayScore}% Match
          </div>
        </div>
      )}

      {/* Image Section - Carousel if multiple images */}
      <ImageCarousel
        images={(listing.image_urls && listing.image_urls.length > 0) ? listing.image_urls : listing.image_url ? [listing.image_url] : []}
        title={listing.title}
        price={listing.price_pcm}
        weeklyPrice={weeklyPrice}
      />

      {/* Details Section */}
      <div className="flex min-w-0 flex-1 flex-col p-4 md:p-6">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0 flex-1">
            <a href={listing.url} target="_blank" rel="noopener noreferrer" onClick={(e) => e.stopPropagation()} className="line-clamp-2 text-base font-bold tracking-tight text-text hover:text-accent">
              {listing.title}
            </a>
            {showAddress && <p className="mt-1 truncate text-xs font-medium text-muted">{listing.address}</p>}
          </div>
          <button 
            onClick={(e) => { e.stopPropagation(); isSaved ? onRemove?.() : onSave?.(); }} 
            className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border transition-all duration-200 shadow-sm ${
              isSaved 
                ? "border-accent bg-accent text-white shadow-accent/20" 
                : "border-border bg-surface text-muted hover:border-accent hover:text-accent hover:bg-accent/5"
            }`}
            title={isSaved ? "Remove from shortlist" : "Save to shortlist"}
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill={isSaved ? "currentColor" : "none"} stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z" />
            </svg>
          </button>
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-2 border-y border-border/50 py-3">
          <div className="flex items-center gap-1.5 text-xs font-bold text-text">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" className="text-muted"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" /></svg>
            {listing.bedrooms} {listing.bedrooms === 1 ? 'Bed' : 'Beds'}
            {listing.property_type && <span className="ml-1 opacity-60 font-medium text-[10px] uppercase">({listing.property_type})</span>}
          </div>
          <div className="flex items-center gap-1.5 text-xs font-bold text-text">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" className="text-muted"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" /><circle cx="12" cy="7" r="4" /></svg>
            {listing.bathrooms} {listing.bathrooms === 1 ? 'Bath' : 'Baths'}
          </div>
          <div className={`flex items-center gap-1.5 text-xs font-bold ${isAvailableUncertain ? 'italic text-muted/60' : 'text-text'}`}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" className="text-muted"><rect x="3" y="4" width="18" height="18" rx="2" ry="2" /><line x1="16" y1="2" x2="16" y2="6" /><line x1="8" y1="2" x2="8" y2="6" /><line x1="3" y1="10" x2="21" y2="10" /></svg>
            {isAvailableUncertain ? 'Date not provided' : `Available ${listing.available_from}`}
          </div>
        </div>

        {/* Summary Area - Only renders if data exists */}
        {(propertyFeatures.length > 0 || summary) && (
          <div className="mt-4 flex flex-col gap-2">
            {propertyFeatures.length > 0 ? (
              <div className="flex flex-wrap gap-x-4 gap-y-1">
                {propertyFeatures.map((feat, i) => (
                  <div key={i} className="flex items-center gap-1.5 text-[11px] font-medium text-muted">
                    <div className="h-1 w-1 rounded-full bg-accent/40" />
                    {feat}
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-[11px] leading-relaxed text-muted line-clamp-2">{summary}</p>
            )}
          </div>
        )}

        {/* Tags Section - Always at bottom */}
        <div className="mt-auto flex flex-wrap items-center gap-1.5 pt-4">
          {hits.length > 0 ? hits.map((hit, i) => (
            <span key={i} className="inline-flex items-center gap-1 rounded-lg bg-accent/10 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-accent">
              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><polyline points="20 6 9 17 4 12" /></svg>
              {hit}
            </span>
          )) : penalties.length === 0 && (
            <span className="text-[10px] font-bold uppercase tracking-widest text-muted/40">No issues flagged</span>
          )}
          {penalties.map((pen, i) => (
            <span key={i} className="inline-flex items-center gap-1 rounded-lg bg-amber-900/20 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-amber-400">
              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" /></svg>
              {pen}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
