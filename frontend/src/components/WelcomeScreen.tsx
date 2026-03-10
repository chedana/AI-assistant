type Props = {
  onSuggestionClick: (text: string, routeHint?: Record<string, unknown>) => void;
};

export default function WelcomeScreen({ onSuggestionClick }: Props) {
  const suggestions = [
    {
      label: "Modern 2-bed in Hackney",
      text: "2 bed flat in Hackney under £2,500",
      icon: (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
          <polyline points="9 22 9 12 15 12 15 22" />
        </svg>
      )
    },
    {
      label: "Furnished near King's Cross",
      text: "Furnished 1 bed near King's Cross station",
      icon: (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <rect x="2" y="7" width="20" height="14" rx="2" ry="2" />
          <path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16" />
        </svg>
      )
    },
    {
      label: "Pet-friendly in Brixton",
      text: "Pet-friendly apartment in Brixton with garden",
      icon: (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M10 5.172a4 4 0 0 1 5.656 5.656L10 16.485l-5.657-5.657a4 4 0 0 1 5.657-5.657z" />
        </svg>
      )
    },
    {
      label: "Budget studio Zone 2",
      text: "Studio flat in Zone 2 under £1,400",
      icon: (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="10" />
          <line x1="12" y1="8" x2="12" y2="12" />
          <line x1="12" y1="16" x2="12.01" y2="16" />
        </svg>
      )
    }
  ];

  return (
    <div className="flex h-full flex-col items-center justify-center bg-surface p-6 md:p-12">
      <div className="max-w-2xl text-center">
        <div className="mx-auto mb-8 flex h-20 w-20 items-center justify-center rounded-3xl bg-accent/10 text-accent shadow-2xl shadow-accent/20">
          <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" />
          </svg>
        </div>
        
        <h1 className="text-3xl font-black tracking-tight text-text md:text-5xl">
          Find your next <span className="text-accent">London home.</span>
        </h1>
        <p className="mt-6 text-base font-medium leading-relaxed text-muted md:text-lg">
          OpenClaw is an AI-powered rental search engine. Describe your ideal home in natural language, and I'll find the best matches from thousands of listings.
        </p>

        <div className="mt-12 grid grid-cols-1 gap-3 sm:grid-cols-2">
          {suggestions.map((s) => (
            <button
              key={s.text}
              onClick={() => onSuggestionClick(s.text)}
              className="flex items-center gap-4 rounded-2xl border border-border bg-panel p-4 text-left transition-all hover:border-accent hover:bg-accent/5 hover:shadow-xl hover:shadow-accent/5 active:scale-[0.98]"
            >
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-surface text-accent">
                {s.icon}
              </div>
              <div>
                <div className="text-sm font-bold text-text">{s.label}</div>
                <div className="mt-0.5 line-clamp-1 text-[10px] font-medium uppercase tracking-wider text-muted">
                  Try this query
                </div>
              </div>
            </button>
          ))}
        </div>

        <div className="mt-12 flex items-center justify-center gap-8 border-t border-border/50 pt-8">
          <div className="flex flex-col items-center">
            <span className="text-xl font-black text-text">24k+</span>
            <span className="text-[10px] font-bold uppercase tracking-widest text-muted">Listings</span>
          </div>
          <div className="h-8 w-px bg-border/50" />
          <div className="flex flex-col items-center">
            <span className="text-xl font-black text-text">Live</span>
            <span className="text-[10px] font-bold uppercase tracking-widest text-muted">Market Data</span>
          </div>
          <div className="h-8 w-px bg-border/50" />
          <div className="flex flex-col items-center">
            <span className="text-xl font-black text-text">AI</span>
            <span className="text-[10px] font-bold uppercase tracking-widest text-muted">Powered</span>
          </div>
        </div>
      </div>
    </div>
  );
}
