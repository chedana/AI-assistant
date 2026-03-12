import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type { ListingData } from "../types/chat";
import { useScrollLock } from "../hooks/useScrollLock";
import { useFocusTrap } from "../hooks/useFocusTrap";

type Props = {
  listing: ListingData | null;
  onClose: () => void;
};

function toArray(val: string[] | string | undefined): string[] {
  const clean = (s: string) => {
    return s.trim().replace(/^[-•*+]\s*/, '').trim();
  };
  if (Array.isArray(val)) return val.map(clean).filter(Boolean);
  if (typeof val === "string" && val.trim()) {
    // Try JSON parse first (backend sends proper JSON arrays now)
    if (val.startsWith("[")) {
      try { const p = JSON.parse(val); if (Array.isArray(p)) return p.map(s => clean(String(s))).filter(Boolean); } catch {}
    }
    return val.split(/[;\n]+/).map(clean).filter(Boolean);
  }
  return [];
}

export default function ListingDetailDrawer({ listing, onClose }: Props) {
  const drawerRef = useRef<HTMLDivElement>(null);
  const [currentImageIndex, setCurrentImageIndex] = useState(0);
  
  useScrollLock(!!listing);
  useFocusTrap(drawerRef, !!listing);

  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleEsc);
    return () => window.removeEventListener("keydown", handleEsc);
  }, [onClose]);

  useEffect(() => {
    setCurrentImageIndex(0);
  }, [listing?.url]);

  if (!listing) return null;

  const images = listing.image_urls && listing.image_urls.length > 0 
    ? listing.image_urls 
    : (listing.image_url ? [listing.image_url] : []);
  const hasMultipleImages = images.length > 1;

  const handlePrevImage = (e: React.MouseEvent) => {
    e.stopPropagation();
    setCurrentImageIndex((prev) => (prev - 1 + images.length) % images.length);
  };

  const handleNextImage = (e: React.MouseEvent) => {
    e.stopPropagation();
    setCurrentImageIndex((prev) => (prev + 1) % images.length);
  };

  const isNegative = (f: string) => /^no\s+/i.test(f) || /not\s+accepted/i.test(f) || /not\s+allowed/i.test(f);
  const allFeatures = toArray(listing.features).filter(f => !["ask agent", "n/a", "none"].includes(f.toLowerCase().trim()));
  const features = allFeatures.filter(f => !isNegative(f));
  const restrictions = allFeatures.filter(f => isNegative(f));
  const penalties = toArray(listing.penalty_reasons);
  const hits = toArray(listing.preference_hits);
  const flags = toArray(listing.red_flags);
  const weeklyPrice = Math.round((listing.price_pcm * 12) / 52);

  const formatDeposit = (dep?: number) => {
    if (!dep) return "Ask agent";
    return `£${dep.toLocaleString()}`;
  };

  const formatFurnishing = (furn?: string) => {
    if (!furn) return "Unknown";
    return furn.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase());
  };

  const formatDescription = (desc?: string) => {
    if (!desc) return null;
    // First, replace <PARA> with newlines
    let text = desc.replace(/<PARA>/gi, "\n");
    
    // Split into lines, trim them, and filter out empty ones
    const lines = text.split("\n").map(l => l.trim()).filter(Boolean);
    
    // Heuristic: If a line is very short (e.g., just "E" or "Council" or "Tax:"), 
    // it was probably part of a broken list. We join it with the previous line if it looks broken.
    const mergedLines: string[] = [];
    for (const line of lines) {
      if (mergedLines.length === 0) {
        mergedLines.push(line);
        continue;
      }
      
      const prevLine = mergedLines[mergedLines.length - 1];
      
      // If the current line is short OR the previous line ended with a colon/dash, 
      // or the previous line was also short, join them with a space.
      if (line.length < 15 || prevLine.length < 15 || prevLine.match(/[:\-]\s*$/)) {
        mergedLines[mergedLines.length - 1] = `${prevLine} ${line}`.trim();
      } else {
        // Otherwise, it's a real paragraph break
        mergedLines.push(line);
      }
    }
    
    return mergedLines.join("\n\n");
  };

  return createPortal(
    <>
      {/* Backdrop (Stops at chat panel edge on desktop) */}
      <div 
        className="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm transition-opacity md:right-[420px]" 
        onClick={onClose}
      />

      {/* Drawer (Slides from the right edge of the listings panel, next to chat) */}
      <div 
        ref={drawerRef}
        role="dialog"
        aria-modal="true"
        className="fixed inset-y-0 right-0 z-50 flex w-full flex-col bg-surface shadow-2xl transition-transform duration-300 md:w-[600px] md:right-[420px] border-l border-border animate-in slide-in-from-right"
      >
        
        {/* Close Button (Floating) */}
        <button
          onClick={onClose}
          className="absolute right-4 top-4 z-50 flex h-10 w-10 items-center justify-center rounded-full bg-black/50 text-white backdrop-blur-md transition-colors hover:bg-black/80"
        >
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>

        <div className="flex-1 overflow-y-auto custom-scrollbar">
          {/* Hero Image */}
          <div className="group relative h-64 w-full shrink-0 bg-panel md:h-80">
            {images.length > 0 ? (
              <img
                src={images[currentImageIndex]}
                alt={`${listing.title} - Image ${currentImageIndex + 1}`}
                className="h-full w-full object-cover transition-opacity duration-300"
              />
            ) : (
              <div className="flex h-full items-center justify-center text-white/10">
                <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1">
                  <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
                </svg>
              </div>
            )}
            
            <div className="absolute inset-0 bg-gradient-to-t from-surface via-transparent to-transparent pointer-events-none" />

            {hasMultipleImages && (
              <>
                <button
                  onClick={handlePrevImage}
                  className="absolute left-4 top-1/2 -translate-y-1/2 flex h-10 w-10 items-center justify-center rounded-full bg-black/40 text-white opacity-0 backdrop-blur-md transition-all hover:bg-black/60 group-hover:opacity-100"
                >
                  <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <polyline points="15 18 9 12 15 6" />
                  </svg>
                </button>
                <button
                  onClick={handleNextImage}
                  className="absolute right-4 top-1/2 -translate-y-1/2 flex h-10 w-10 items-center justify-center rounded-full bg-black/40 text-white opacity-0 backdrop-blur-md transition-all hover:bg-black/60 group-hover:opacity-100"
                >
                  <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <polyline points="9 18 15 12 9 6" />
                  </svg>
                </button>
                <div className="absolute bottom-4 left-1/2 -translate-x-1/2 rounded-full bg-black/50 px-3 py-1 text-xs font-semibold text-white backdrop-blur-md">
                  {currentImageIndex + 1} / {images.length}
                </div>
              </>
            )}
          </div>

          {/* Content Body */}
          <div className="px-6 pb-24 pt-4">
            {/* Title & Address */}
            <div className="mb-6">
              <h2 className="text-2xl font-black tracking-tight text-text md:text-3xl">
                {listing.title}
              </h2>
              {listing.address && listing.address.toLowerCase() !== listing.title.toLowerCase() && (
                <p className="mt-2 text-sm font-medium text-muted">
                  {listing.address}
                </p>
              )}
            </div>

            {/* Price & Primary CTA (Sticky-like feel at top of content) */}
            <div className="mb-8 flex items-end justify-between rounded-2xl border border-border bg-panel p-5 shadow-sm">
              <div className="flex flex-col">
                <div className="flex items-baseline gap-1.5">
                  <span className="text-3xl font-black text-text">£{listing.price_pcm.toLocaleString()}</span>
                  <span className="text-sm font-medium text-muted">pcm</span>
                </div>
                <span className="text-xs font-bold uppercase tracking-wider text-accent">
                  £{weeklyPrice} pw
                </span>
              </div>
              <div className="flex gap-2">
                <a
                  href={listing.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-2 rounded-xl bg-accent px-5 py-3 text-sm font-bold text-surface transition-all hover:bg-accent-dim active:scale-95"
                >
                  {listing.openrent_url ? "Rightmove" : listing.url?.includes("openrent") ? "OpenRent" : listing.url?.includes("rightmove") ? "Rightmove" : "View Listing"}
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
                    <polyline points="15 3 21 3 21 9" />
                    <line x1="10" y1="14" x2="21" y2="3" />
                  </svg>
                </a>
                {listing.openrent_url && (
                  <a
                    href={listing.openrent_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center gap-2 rounded-xl bg-emerald-600 px-5 py-3 text-sm font-bold text-white transition-all hover:bg-emerald-700 active:scale-95"
                  >
                    OpenRent
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
                      <polyline points="15 3 21 3 21 9" />
                      <line x1="10" y1="14" x2="21" y2="3" />
                    </svg>
                  </a>
                )}
              </div>
            </div>

            {/* Core Metrics Grid */}
            <div className="mb-8 grid grid-cols-2 gap-4 md:grid-cols-3">
              <div className="flex flex-col rounded-xl border border-border bg-panel/50 p-4">
                <span className="text-[10px] font-bold uppercase tracking-widest text-muted">Property Type</span>
                <span className="mt-1 text-sm font-semibold text-text">{listing.property_type || "Unknown"}</span>
              </div>
              <div className="flex flex-col rounded-xl border border-border bg-panel/50 p-4">
                <span className="text-[10px] font-bold uppercase tracking-widest text-muted">Bedrooms</span>
                <span className="mt-1 text-sm font-semibold text-text">{listing.bedrooms}</span>
              </div>
              <div className="flex flex-col rounded-xl border border-border bg-panel/50 p-4">
                <span className="text-[10px] font-bold uppercase tracking-widest text-muted">Bathrooms</span>
                <span className="mt-1 text-sm font-semibold text-text">{listing.bathrooms}</span>
              </div>
              <div className="flex flex-col rounded-xl border border-border bg-panel/50 p-4">
                <span className="text-[10px] font-bold uppercase tracking-widest text-muted">Furnishing</span>
                <span className="mt-1 text-sm font-semibold text-text">{formatFurnishing(listing.furnish_type)}</span>
              </div>
              <div className="flex flex-col rounded-xl border border-border bg-panel/50 p-4">
                <span className="text-[10px] font-bold uppercase tracking-widest text-muted">Deposit</span>
                <span className="mt-1 text-sm font-semibold text-text">{formatDeposit(listing.deposit)}</span>
              </div>
              <div className="flex flex-col rounded-xl border border-border bg-panel/50 p-4">
                <span className="text-[10px] font-bold uppercase tracking-widest text-muted">Available From</span>
                <span className="mt-1 text-sm font-semibold text-text">{listing.available_from || "Ask agent"}</span>
              </div>
            </div>

            {/* AI Match Analysis */}
            <div className="mb-8 rounded-2xl border border-border bg-panel p-5">
              <h3 className="mb-4 text-xs font-bold uppercase tracking-widest text-muted">AI Match Analysis</h3>
              
              <div className="space-y-4">
                {hits.length > 0 && (
                  <div>
                    <h4 className="mb-2 text-[10px] font-bold uppercase tracking-widest text-accent">Hits</h4>
                    <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                      {hits.map((hit, i) => (
                        <li key={i} className="flex items-center gap-2 text-sm text-text">
                          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" className="text-accent shrink-0">
                            <polyline points="20 6 9 17 4 12" />
                          </svg>
                          {hit}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                
                {penalties.length > 0 && (
                  <div className={hits.length > 0 ? "pt-4 border-t border-border/50" : ""}>
                    <h4 className="mb-2 text-[10px] font-bold uppercase tracking-widest text-amber-400">Penalties</h4>
                    <ul className="space-y-2">
                      {penalties.map((pen, i) => (
                        <li key={i} className="flex items-start gap-2 text-sm text-text">
                          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" className="mt-0.5 text-amber-400 shrink-0">
                            <line x1="18" y1="6" x2="6" y2="18" />
                            <line x1="6" y1="6" x2="18" y2="18" />
                          </svg>
                          {pen}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {flags.length > 0 && (
                  <div className={(hits.length > 0 || penalties.length > 0) ? "pt-4 border-t border-border/50" : ""}>
                    <h4 className="mb-2 text-[10px] font-bold uppercase tracking-widest text-red-400">Red Flags</h4>
                    <ul className="space-y-2">
                      {flags.map((flag, i) => (
                        <li key={i} className="flex items-start gap-2 text-sm text-text">
                          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" className="mt-0.5 text-red-400 shrink-0">
                            <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" /><line x1="12" y1="9" x2="12" y2="13" /><line x1="12" y1="17" x2="12.01" y2="17" />
                          </svg>
                          {flag}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {hits.length === 0 && penalties.length === 0 && flags.length === 0 && (
                  <p className="text-sm text-muted">No specific hits or penalties flagged for this property.</p>
                )}
              </div>
            </div>

            {/* Key Features */}
            {features.length > 0 && (
              <div className="mb-8">
                <h3 className="mb-4 text-xs font-bold uppercase tracking-widest text-muted">Key Features</h3>
                <ul className="grid grid-cols-1 gap-y-2 gap-x-4 sm:grid-cols-2">
                  {features.map((feat, i) => (
                    <li key={i} className="flex items-start gap-2 text-sm text-text">
                      <div className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-accent/50" />
                      <span className="leading-snug">{feat}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Restrictions */}
            {restrictions.length > 0 && (
              <div className="mb-8">
                <h3 className="mb-4 text-xs font-bold uppercase tracking-widest text-muted">Restrictions</h3>
                <ul className="grid grid-cols-1 gap-y-2 gap-x-4 sm:grid-cols-2">
                  {restrictions.map((r, i) => (
                    <li key={i} className="flex items-start gap-2 text-sm text-amber-400/80">
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" className="mt-0.5 shrink-0">
                        <line x1="18" y1="6" x2="6" y2="18" />
                        <line x1="6" y1="6" x2="18" y2="18" />
                      </svg>
                      <span className="leading-snug">{r}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Description */}
            {listing.description && (
              <div>
                <h3 className="mb-4 text-xs font-bold uppercase tracking-widest text-muted">Property Description</h3>
                <div className="whitespace-pre-wrap text-sm leading-relaxed text-text/90">
                  {formatDescription(listing.description)}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </>,
    document.body
  );
}
