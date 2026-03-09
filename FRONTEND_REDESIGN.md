# Frontend Redesign: Chat-Only → Split-Panel Rental Platform

> **Status:** V1 implemented, NOT YET TESTED. Updated 2026-03-08 on `openclaw` branch.
> **Build:** `npm run build` passes with zero TypeScript errors.
> **Next:** Test with backend running, fix any visual/functional issues, then mobile layout.

---

## What Was Built

Rightmove-style layout — listings as the main content area (left), AI chat as a sidebar (right).

```
┌─────────────────────────────────────────────────────────────────┐
│  OpenClaw  [AI-powered rental search]  [Saved(3)] [≡ sessions] │  Header
│  Filters: [budget ×] [location ×] [2 bed ×]                    │  ConstraintTags (inline)
├──────────────────────────────────────────────┬──────────────────┤
│  52 properties          [Lower budget] [Cmp] │ 💬 AI Assistant  │  ResultsHeader + actions
│  ┌──────────────┬──────────────────────────┐ │                  │
│  │              │ Casson Square, SE1       │ │  Chat messages   │
│  │  [Image      │ 2 bed · 1 bath           │ │  stream here     │
│  │  placeholder]│ A stunning flat...       │ │                  │
│  │              │ [near station] [garden]  │ │                  │
│  │  £1,200 pcm  │                    [♡]   │ │  [Quick replies] │
│  └──────────────┴──────────────────────────┘ │                  │
│  ┌──────────────┬──────────────────────────┐ ├──────────────────┤
│  │              │ 55 Upper Ground, SE1     │ │ [Describe what   │
│  │  [Image]     │ 1 bed · 1 bath           │ │  you want...]    │
│  └──────────────┴──────────────────────────┘ │                  │
│  [Show more results (42 remaining)]          │                  │
└──────────────────────────────────────────────┴──────────────────┘
```

---

## Files Changed (all paths relative to `frontend/src/`)

### New files created

| File | Purpose |
|------|---------|
| `components/Header.tsx` | Branded header — logo, session dropdown, shortlist badge, inline constraint chips |
| `components/ListingsPanel.tsx` | Main content area — results count, horizontal listing cards, show more button, compare table, welcome screen, action quick replies |
| `components/WelcomeScreen.tsx` | Empty state — "Find your next rental" heading, 4 clickable example searches |

### Files modified

| File | What changed |
|------|-------------|
| `App.tsx` | **Full rewrite.** Layout: listings left (flex-1), chat right (w-[380px]). Header on top. Shortlist panel as fixed overlay with backdrop. `savedIds` moved here from ChatArea. Sidebar removed. |
| `components/ListingCard.tsx` | **Rightmove-style horizontal card.** Image placeholder left (w-72, gradient bg, house icon, price overlay). Details right (title, specs, address, tags). Save button appears on hover. Added `compact?: boolean` prop for use in ShortlistPanel. |
| `components/ChatArea.tsx` | **Stripped to pure chat.** Removed: CompareTable, ListingCard, ConstraintTags imports. Removed: metadata, suppressedIds, metadataForId props. Removed: all suppression/inline-card logic. Kept: messages, QuickReplies, auto-scroll. |
| `components/MessageBubble.tsx` | **1-line fix.** `showThinking` changed from `isGenerating && (isEmpty \|\| (!isUser && isActive))` to `isGenerating && isActive && isEmpty`. Streaming text now visible (was hidden to prevent flash before inline cards). |
| `components/ConstraintTags.tsx` | Added `inline?: boolean` prop. When `inline=true`: renders chip spans as fragment (no sticky wrapper). Used by Header. |
| `components/ChatInput.tsx` | Removed `max-w-3xl` constraint. Updated placeholder: "Describe what you're looking for..." |
| `components/ShortlistPanel.tsx` | ListingCards now use `compact` prop. |
| `tailwind.config.cjs` | Added colors: `panel-alt: "#1a1a1a"`, `accent-dim: "#0d8868"` |

### Files NOT changed (unchanged)

- `hooks/useChat.ts` — still computes `suppressedIds` / `metadataForId` (harmless, ignored by new components)
- `hooks/useSessions.ts` — no changes needed
- `lib/mockStream.ts`, `lib/markdown.ts`, `lib/storage.ts` — no changes
- `types/chat.ts` — no changes
- `components/CompareTable.tsx` — renders in ListingsPanel now, component itself unchanged
- `components/QuickReplies.tsx` — unchanged, rendered in ChatArea
- `components/MessageContent.tsx`, `ThinkingIndicator.tsx` — unchanged

### Files deprecated

- `components/Sidebar.tsx` — still on disk, no longer imported. Replaced by session dropdown in Header.

---

## Architecture Decisions

1. **Listings LEFT, chat RIGHT** — reversed from original plan. Matches Rightmove layout where results are primary content, chat replaces the map sidebar.

2. **Listings are SEPARATE from chat** — no more inline cards in conversation. ListingsPanel renders from `metadata.search_results`. ChatArea shows only messages + quick replies.

3. **Horizontal listing cards** — image placeholder left (w-72), details right. Price overlaid on image. Save button on hover. Compact mode for ShortlistPanel.

4. **Constraint chips in Header** — using `ConstraintTags inline={true}`. Renders as row 2 of header when constraints exist.

5. **Session dropdown replaces Sidebar** — hamburger menu in header opens absolutely positioned dropdown with session list, new/delete.

6. **Shortlist as fixed overlay** — `fixed inset-y-0 right-0 z-50` with click-outside backdrop (`bg-black/50`).

7. **Quick replies split** — search-action replies (Lower budget, Compare) appear in ListingsPanel results header. All replies also appear in ChatArea below messages.

8. **`useChat.ts` untouched** — suppression state still computed but unused. Clean up in a future PR.

9. **Welcome screen** — clickable example searches call `sendMessage()` directly. Shown when `metadata.search_results` is empty/null.

---

## How to Test

```bash
# Terminal 1 — Backend
cd /Users/derek/Desktop/LLM_project/AI-assistant
export $(grep -v '^#' .env | grep -v '^$' | xargs)
/Users/derek/Desktop/LLM_project/openclaw-venv/bin/uvicorn backend.api_server:app --host 0.0.0.0 --port 8000

# Terminal 2 — Frontend
cd /Users/derek/Desktop/LLM_project/AI-assistant/frontend
npm run dev -- --host 0.0.0.0 --port 5173
```

Open **http://localhost:5173**

### Test checklist

- [ ] Welcome screen shows on first load with 4 example searches
- [ ] Click an example search — listings appear on the left, chat streams on the right
- [ ] Listing cards are horizontal (image placeholder left, details right)
- [ ] Price badge shows overlaid on image area
- [ ] Save button appears on card hover, stays visible when saved
- [ ] Constraint chips appear in header row 2 — click × removes filter
- [ ] "Show more results (N remaining)" button works
- [ ] Shortlist badge appears in header — click opens overlay panel
- [ ] Shortlist panel has backdrop, click outside closes it
- [ ] Session dropdown (hamburger icon): new search, switch sessions, delete
- [ ] Compare table renders in listings panel (not in chat)
- [ ] Chat shows streaming assistant text (not hidden behind thinking dots)
- [ ] Quick replies appear in both chat and listings panel header

---

## Known Issues / TODO for Next Session

### Must fix (likely)
- **Mobile layout not implemented** — currently desktop-only. On narrow screens the chat panel will be cut off. Need tab toggle (Chat | Results) for < 768px.
- **Chat panel might be too narrow (380px)** — long assistant responses may feel cramped. Test and consider widening to 420px.
- **`onRemoveListing` in ListingsPanel** wired to `handleRemoveFromShortlist` — this is shortlist removal by position. On the listing cards in the main panel, this should be `onSave`/`onRemove` toggling. Verify the save/unsave flow works correctly.
- **Quick replies appear in BOTH chat and listings panel** — may be confusing. Consider filtering: only show "Lower budget" / "Compare" in listings header, only show conversational replies in chat.

### Should fix (polish)
- **No real property images** — cards show gradient placeholder with house icon. When crawler stores image URLs, update ListingCard to use `<img>` with fallback.
- **Message bubble styling** — user messages could be right-aligned (iMessage style) for better spatial hierarchy. Currently both user and assistant are left-aligned with different background colors.
- **useChat.ts cleanup** — remove `suppressedIds`, `metadataForId`, `lastSearchSigRef` and related logic since it's no longer used by any component.
- **Sidebar.tsx** — can be deleted from disk (currently just unreferenced).
- **Dark theme depth** — could add more surface level differentiation (3 levels: bg → panel → card) for better visual hierarchy.

### Future features
- **Mobile responsive layout** — tab toggle between Chat and Results at < 768px breakpoint
- **Map view** — Leaflet integration (react-leaflet already in package.json). Toggle between list/map view in listings panel.
- **Listing detail drawer** — click a card → right-side drawer slides over with full details, keeping chat visible
- **Property images from scraper** — Rightmove listing pages have image URLs. Extract in crawler, store in Qdrant payload, render in ListingCard.
- **Sort dropdown** — "Sort by: Newest / Price low-high / Price high-low" in results header

---

## Component Prop Reference

### Header
```ts
{
  sessions: ChatSession[];
  activeId: string;
  isGenerating: boolean;
  constraints: ConstraintsMeta | undefined;
  shortlistCount: number;
  onSelectSession: (id: string) => void;
  onCreateSession: () => void;
  onRemoveSession: (id: string) => void;
  onRemoveConstraint: (clearFields: string[], actionLabel: string) => void;
  onShortlistToggle: () => void;
}
```

### ListingsPanel
```ts
{
  metadata: SessionMetadata | null;
  isGenerating: boolean;
  savedIds: Set<string>;
  quickReplies: QuickReply[] | undefined;
  onSaveListing: (pageIndex: number) => void;
  onRemoveListing: (position: number) => void;
  onShowMore: () => void;
  onQuickReply: (text: string, routeHint?: Record<string, unknown>) => void;
  onSuggestionClick: (text: string) => void;
}
```

### ChatArea (simplified)
```ts
{
  session: ChatSession | undefined;
  isGenerating: boolean;
  activeAssistantId: string | null;
  quickReplies: QuickReply[] | undefined;
  onQuickReply: (text: string, routeHint?: Record<string, unknown>) => void;
}
```

### ListingCard
```ts
{
  listing: ListingData;
  isSaved?: boolean;
  compact?: boolean;   // NEW — compact mode for ShortlistPanel
  onSave?: () => void;
  onRemove?: () => void;
}
```

### WelcomeScreen
```ts
{
  onSuggestionClick: (text: string) => void;
}
```

### ConstraintTags
```ts
{
  constraints: ConstraintsMeta;
  onRemove: (clearFields: string[], actionLabel: string) => void;
  inline?: boolean;   // NEW — renders as fragment, no sticky wrapper
}
```
