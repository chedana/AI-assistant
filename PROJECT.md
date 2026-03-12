# OpenClaw — Project Reference & Dev Tracker

> **Who uses this:** Claude (backend) and Gemini (frontend).
> This is the single source of truth: living task tracker + full technical reference.
> **Rule:** Mark tasks `✅` when done, `🔄` when in progress. Add bugs as you find them.
> **Branch:** `openclaw`
>
> ⚠️ **IMPORTANT — Agent boundaries:**
> - **Gemini** → only work on tasks in "Frontend Tasks" section. Only edit `frontend/src/` files.
> - **Claude** → only work on tasks in "Backend Tasks" section. Only edit `backend/`, `skills/`, `orchestration/`, `core/`, `crawler/` files.
> - **Do not start work autonomously.** Wait for the user to assign a task.

---

## Current App State

| Layer | Status | Notes |
|-------|--------|-------|
| Backend API | ✅ Running | FastAPI · `venv/bin/uvicorn backend.api_server:app --port 8000` |
| Qdrant Cloud | ✅ Connected | **29,119 listings** (26,191 Rightmove + 6,586 OpenRent, 1,343 merged, 2,599 dead removed), `rent_listings` collection |
| Frontend | ✅ Running | Vite · `cd frontend && npm run dev -- --port 5173` |
| Search pipeline | ✅ Working | LangGraph + 4-stage pipeline (retrieve → filter → rank → explain) |
| SSE streaming | ✅ Working | delta / metadata / done events |
| Session persistence | ✅ Working | localStorage `openclaw-sessions-v2` |

---

## Agent Ownership

> **Rule:** Only work on tasks assigned to your agent. Do not touch the other agent's files.

| Agent | Owns | Files |
|-------|------|-------|
| **Claude** | Backend, data, infrastructure | `backend/`, `skills/`, `orchestration/`, `core/`, `crawler/` |
| **Gemini** | Frontend UI only | `frontend/src/` |

---

## Immediate Next Priority

**Section 1 (FIND) - Complete ✅**
- Rightmove + OpenRent scrapers done
- 29,119 clean listings in Qdrant Cloud
- Conversational search working

**Next: Section 3 - Red Flag Detection** (Quick win, no new data needed)
- Rule engine on listing text
- Detect: "no DSS", upfront fees, no deposit protection
- Flag suspicious patterns in agent responses

**Then: Section 4 - Viewing Checklist**
- Pre-viewing checklist (legal + physical)
- Questions to ask based on listing gaps

**Future: Section 5 - Contract Analysis** (Biggest differentiator)
- Upload tenancy agreement → plain-English summary
- Flag non-standard clauses

---

## Task Queue

### Data & Crawlers
_Owner: Claude · Files: `crawler/`, `artifacts/`_

- [x] Re-crawl OpenRent with new amenity fields (pets, garden, EPC) — **DONE Phase 22**
- [x] Merge Rightmove + OpenRent datasets — **DONE Phase 22**
- [x] Sync to Qdrant Cloud — **DONE Phase 22 (29,119 listings)**
- [ ] **Zoopla scraper** — broader coverage (future)
- [ ] **SpareRoom scraper** — rooms/HMO market (future)

### Backend Features
_Owner: Claude · Files: `backend/`, `skills/`, `orchestration/`, `core/`_

- [ ] **Red flag detection skill** — rule engine + LLM to flag: no DSS, upfront fees, no deposit protection, suspicious patterns
- [ ] **Viewing checklist generator** — legal requirements + physical inspection + questions based on listing gaps
- [ ] **Area research skill** — TfL commute API, crime API, average rent aggregates
- [ ] **Contract analysis skill** — upload PDF → plain-English summary + clause flagging

### Frontend Features
_Owner: Gemini · Files: `frontend/src/`_

- [ ] **Session rename** (F-F4) — double-click session title to rename
- [ ] **Viewing checklist UI** (F-F5) — per-listing checklist panel
- [ ] **Red flag badges** — show warning icons on listings with detected issues
- [ ] **Contract upload UI** — drag-drop PDF, show analysis results

---

## Frontend Tasks (Gemini only — do not modify backend files)

### Bugs

| # | Status | Issue | Detail |
|---|--------|-------|--------|
| F-B1 | ✅ Fixed | Match % showed raw `final_score * 100` (e.g. "11%") | Now normalised 70–100% within page, minus 8% per penalty reason |
| F-B2 | ✅ Fixed | Chat accumulates multiple "Loading more listings…" ack messages | Pagination and interactions are now fully silent. Reusing ack bubbles where necessary. |
| F-B4 | Gemini | ✅ Fixed | ListingCard compact mode + bookmark style polish | Smaller bookmark button in compact mode, accent fill when saved |
| F-B5 | Claude | ✅ Fixed | Feature items show leading `- ` dash | `_clean()` in `_features_list()` strips `- `, `–`, `•` list markers |
| F-B6 | Claude | ✅ Fixed | Parking/garage listings appear in search results | `apply_hard_filters_with_audit` now excludes non-residential property types (parking, garage, land, commercial, office, storage) |

### Polish

| # | Status | Task | Detail |
|---|--------|------|--------|
| F-P1 | ✅ Fixed | Title and address identical on most cards | Address is now hidden if it matches the title exactly. |
| F-P2 | ✅ Fixed | "Available ask agent" looks broken | Styled as "Date not provided" in italic muted text. |
| F-P3 | ✅ Fixed | No explanation when tags are absent | Added "No issues flagged" micro-text. |
| F-P4 | ✅ Fixed | Floating pagination blocks UI | Moved pagination to a full-width footer integrated into the list. |
| F-P5 | ✅ Fixed | Portrait images stretch cards | Enforced `h-64` on card images to ensure consistent layouts. |
| F-P6 | ✅ Fixed | `<PARA>` tags visible in descriptions | Added smart regex formatter to clean scraper artifacts and render proper paragraphs. |

### Features

| # | Agent | Status | Feature | Detail | Needs |
|---|-------|--------|---------|--------|-------|
| F-F1 | Gemini | ✅ Done | **Map view** | Leaflet map tab with cluster markers, popups, Search this area (exact viewport bounds, 10% inward shrink), skipFitBounds after geo search | — |
| F-F2 | Gemini | ✅ Fixed | **Listing detail drawer** | Click card → slide-out with full info. Includes Portal rendering, scroll lock, and keyboard focus trap. | — |
| F-F7 | Gemini | ✅ Done | **Image carousel in card + drawer** | `ImageCarousel` component: left/right arrows, dot indicators, 1/N counter. Features (up to 3) or description shown on card. Drawer: Key Features first, then Property Description. `_features_list()` handles all storage formats + filters "ask agent". | — |
| F-F3 | Gemini | ✅ Fixed | **Mobile bottom nav** | Switch Chat ↔ Results on mobile | Implemented in responsive layout refactor. |
| F-F4 | Gemini | 🔴 Open | **Session rename** | Double-click session title to rename | Frontend only |
| F-F5 | Gemini | 🔴 Open | **Viewing checklist** | Per-listing checklist panel (legal + physical checks) | Roadmap Section 4 |
| F-F6 | Gemini | 🔴 Open | **Contract upload UI** | File upload → send to contract analysis endpoint | Roadmap Section 5 + B-F6 |

---

## Backend Tasks (Claude only — do not modify frontend files)

### Concerns / Coordination
> **🚨 GEMINI NOTE regarding B-F1:** I have temporarily patched `api_server.py` and `candidate_snapshot` to send `description`, `features`, `deposit`, and `property_type` inside the standard `search_results` listing object. This unblocked the frontend summaries and the v1 Detail Drawer. When building `B-F1` (Detail Endpoint), please ensure these fields remain available in the standard search stream, or let me know if we need to switch entirely to fetching them dynamically on click.

### Bugs

| # | Status | Issue | Detail |
|---|--------|-------|--------|
| B-B1 | ✅ Fixed | `lat`/`lon` not in SSE metadata | Added to `build_metadata()` in `api_server.py` — reads `latitude`/`longitude` from Qdrant payload. Also added to `ListingData` TS type. |
| B-B2 | 🔴 Open | Qdrant collection crawled with postcodes | Location miss rate high. Re-crawl `crawl_london.py` using area names |

### Pipeline Improvements

| # | Status | Task | Detail |
|---|--------|------|--------|
| B-P1 | ✅ Fixed | **Geo-radius fallback** | Token miss → geocode via LONDON_REGIONS (97 areas) → 3km haversine radius search. No Qdrant index needed — filters in Python post-recall. |
| B-P2 | 🔴 Open | **Unify listing fields** | `deposit`, `size_sqm`, `furnish_type`, `property_type` are in `compare_data` but not in `search_results` listing objects — causes inconsistency |

### Features

| # | Agent | Status | Feature | Section |
|---|-------|--------|---------|---------|
| B-F1 | Claude | ✅ Not needed | **Listing detail endpoint** — `GET /api/listing/{id}` | All fields (`description`, `features`, `deposit`, `property_type`, `furnish_type`) are already in the SSE metadata stream via `_map_listing()`. Drawer has everything it needs without an extra API call. | 1 |
| B-F2 | Claude | 🔴 Open | **OpenRent scraper** — private landlords, no agent fees (`crawler/openrent.py`) | 1 |
| B-F3 | Claude | 🔴 Open | **Red flag detection** — scan description for: no DSS, admin fees, no deposit protection | 3 |
| B-F4 | Claude | 🔴 Open | **Draft viewing request** — `POST /api/contact/draft`, LLM + listing context | 3 |
| B-F5 | Claude | 🔴 Open | **Commute time** — TfL API: listing lat/lon + workplace → journey time | 2 |
| B-F6 | Claude | 🔴 Open | **Contract analysis** — `POST /api/contract/analyse`, PDF → plain-English summary + clause flags | 5 |
| B-F7 | Claude | 🔴 Open | **Tenant rights RAG** — index GOV.UK + Shelter + Renters Reform Act | 6 |

---

## API Contract

> **Coordination point.** Backend changes a field shape → tell Frontend. Frontend needs a new field → tell Backend.

### SSE Metadata — Listing Object (currently sent)

```typescript
{
  title: string
  url: string
  image_url: string        // cover photo (og:image) — always present
  image_urls: string[]     // full gallery up to 10 × 656x437 JPEG — empty [] until backfill hits this listing
  address: string
  price_pcm: number
  bedrooms: number
  bathrooms: number
  available_from: string
  lat: number | null       // from Qdrant payload (latitude field)
  lon: number | null       // from Qdrant payload (longitude field)
  image_urls?: string[]    // full gallery (up to 10 × 656x437 JPEG); empty until backfill completes
  final_score: number      // raw soft-rank composite (~0.05–0.20); frontend normalises to 70–100%
  penalty_reasons: string[]
  preference_hits: string[]
}
```

### Fields Frontend Needs (not yet in metadata)

*(All required fields are now in metadata. See API contract above.)*

*(Note: `description`, `features`, `deposit`, `property_type`, and `furnish_type` were temporarily added to the standard `ListingData` object in the frontend and `candidate_snapshot` in the backend to unblock the Detail Drawer and Card summaries. These should be formalized in B-P2 and B-F1).*

### SSE Event Types

```
event: delta     data: {"text": "..."}          # streamed text chunks
event: metadata  data: { SessionMetadata }       # structured JSON, sent once
event: done      data: {}                        # stream end
event: error     data: {"message": "..."}        # on failure
```

### Route Hints (frontend → backend)

| Intent | Used for |
|--------|---------|
| `Page_Nav` + `page_action: "next"` | Pagination |
| `Search` + `set_constraints: {...}` | Constraint changes |
| `Search` + `clear_fields: [...]` | Remove a filter |
| `Compare` | Compare current results or shortlist |
| `Shortlist` + `shortlist_action` + `target_indices` | Save/remove listings |

---

## Data State

| Dataset | Count | Quality | Next action |
|---------|-------|---------|------------|
| Rightmove London | 26,191 | Medium — postcodes used, some location misses | Re-crawl with area names |
| Gallery images (`image_urls`) | ✅ Done | 24,389 listings all have `image_url`; 2,005 dead listings (404/410) removed | — |
| OpenRent | 0 | Not started | Build scraper (B-F2) |
| Zoopla | 0 | Not started | Future |

---

## Product Roadmap

```
[FIND] → [RESEARCH] → [CONTACT] → [VIEW] → [SIGN] → [RIGHTS]
   1          2            3          4        5          6
```

| Section | Status | Key features |
|---------|--------|-------------|
| 1 · Find | 🔄 In progress | Search working; OpenRent + geo-radius missing |
| 2 · Research | 🔴 Planned | Commute (TfL), crime (police.uk), avg rent, flood risk, EPC |
| 3 · Contact | 🔴 Planned | Red flag detection, draft viewing email, holding deposit warnings |
| 4 · View | 🔴 Planned | Legal checklist, inspection checklist, agent question generator |
| 5 · Sign | 🔴 Planned | Contract PDF analysis, clause flagging, deposit protection explainer |
| 6 · Rights | 🔴 Planned | RAG over UK tenant law: repairs, eviction, rent increases |

---

## Technical Reference (for Gemini)

> Everything below is a detailed technical reference of the frontend codebase.
> Read this to understand the existing code before making changes.

---

---

## 1. Product Overview

**OpenClaw** is a conversational rental property search app for the London market. Users describe what they want in natural language ("2 bed flat in Hackney under £1,800"), and the AI assistant:

1. Extracts structured constraints (budget, location, bedrooms, etc.)
2. Searches a vector database of ~thousands of rental listings
3. Applies hard filters, then soft-ranks results
4. Returns grounded explanations with structured property cards
5. Supports pagination ("show more"), shortlisting (bookmarks), side-by-side comparison, and constraint refinement via filter chip removal

The experience is split into two panels: **property listings on the left** and a **chat sidebar on the right**.

### Live Deployment

- **Backend:** Python FastAPI on Render
- **Frontend:** React SPA on Vercel

---

## 2. Tech Stack & Build

| Technology | Version | Role |
|------------|---------|------|
| React | 18.3.1 | UI framework |
| TypeScript | 5.6.3 | Type safety (strict mode, ES2020 target) |
| Vite | 5.4.8 | Dev server & bundler |
| TailwindCSS | 3.4.13 | Utility-first styling |
| PostCSS + Autoprefixer | 8.4.47 / 10.4.20 | CSS processing |
| Leaflet + react-leaflet | 1.9.4 / 4.2.1 | Map library (**installed but currently unused**) |

**No other runtime dependencies.** No state libraries (Redux/Zustand/Jotai), no UI component libraries (shadcn, MUI), no routing library.

### package.json

```json
{
  "name": "ai-assistant-frontend",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "@types/leaflet": "^1.9.21",
    "leaflet": "^1.9.4",
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "react-leaflet": "^4.2.1"
  },
  "devDependencies": {
    "@types/react": "^18.3.5",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.2",
    "autoprefixer": "^10.4.20",
    "postcss": "^8.4.47",
    "tailwindcss": "^3.4.13",
    "typescript": "^5.6.3",
    "vite": "^5.4.8"
  }
}
```

### Build Commands

```bash
npm run dev      # Vite dev server, proxies /api to localhost:8000
npm run build    # tsc -b && vite build → outputs to dist/
npm run preview  # preview the production build
```

### Vite Config

- React plugin enabled
- Dev server proxy: `/api/*` → `http://127.0.0.1:8000` (Python FastAPI backend)
- `VITE_API_BASE` env var for production API URL (defaults to `""` = relative paths)

### Deployment (Vercel)

```json
{
  "buildCommand": "npm run build",
  "outputDirectory": "dist",
  "framework": "vite",
  "rewrites": [{ "source": "/(.*)", "destination": "/index.html" }]
}
```

---

## 3. Current Layout & Visual Design

### Color Palette (Dark Theme Only)

| Token | Hex | Usage |
|-------|-----|-------|
| `surface` | `#171717` | Main background, listings panel bg |
| `panel` | `#212121` | Card backgrounds, header bg, sidebar bg |
| `panel-alt` | `#1a1a1a` | Chat sidebar background |
| `border` | `#303030` | All borders throughout |
| `muted` | `#a3a3a3` | Secondary text, labels, placeholders |
| `text` | `#f5f5f5` | Primary text |
| `accent` | `#10a37f` | Brand green — buttons, highlights, best values |
| `accent-dim` | `#0d8868` | Darker accent variant (hover states) |
| Link blue | `#7dd3fc` | All hyperlinks (listing URLs, markdown links) |
| Green tag bg | `bg-green-900/40` | Preference hit badge background |
| Green tag text | `text-green-400` | Preference hit badge text |
| Amber tag bg | `bg-amber-900/40` | Penalty reason badge background |
| Amber tag text | `text-amber-400` | Penalty reason badge text |
| User bubble | `bg-neutral-700` | User message background |
| Assistant bubble | `bg-[#262626]` | Assistant message background |
| Table header | `#2a2a2a` | Markdown table header bg |
| Table alt row | `#1e1e1e` | Markdown table alternating row |
| Table border | `#404040` | Markdown table cell borders |

### Screen Layout (Desktop Only — No Mobile Support)

```
┌──────────────────────────────────────────────────────────────────────┐
│ HEADER (h-12, bg-panel, border-b)                                    │
│ ┌─────────────────────────────────────────────────────┬──────────────┤
│ │ "OpenClaw" (accent, bold, text-lg)                  │ [Saved(N)]   │
│ │ "AI-powered rental search" (muted, text-xs)         │ [☰ hamburger]│
│ └─────────────────────────────────────────────────────┴──────────────┤
│ ┌────────────────────────────────────────────────────────────────────┤
│ │ Filters: [≤£1,800/pcm ✕] [Hackney ✕] [2 beds ✕]  (if active)    │
│ │ (border-t, text-xs chips in bg-neutral-700 rounded-full)          │
│ └────────────────────────────────────────────────────────────────────┤
├──────────────────────────────────────────────┬───────────────────────┤
│                                              │ 💬 AI Assistant       │
│ LISTINGS PANEL (flex-1, bg-surface)          │ (w-[380px], shrink-0) │
│                                              │ (bg-panel-alt)        │
│ ┌───────────────────────────────────┐        │                       │
│ │ "12 properties"    [Lower budget] │        │ ┌───────────────────┐ │
│ │                    [Compare all]  │        │ │ USER              │ │
│ └───────────────────────────────────┘        │ │ ┌───────────────┐ │ │
│                                              │ │ │2 bed in Hack- │ │ │
│ ┌────────────────────────────────────┐       │ │ │ney under 1800 │ │ │
│ │ IMAGE    │ Title (line-clamp-2) 🔖 │       │ │ └───────────────┘ │ │
│ │ 288×192  │ 2 bed · 1 bath · Apr   │       │ │                   │ │
│ │          │ 123 Mare Street, E8     │       │ │ ASSISTANT         │ │
│ │ £1,750   │                         │       │ │ ┌───────────────┐ │ │
│ │ pcm      │ 🟢 pet-friendly        │       │ │ │Found 12 prop- │ │ │
│ │(gradient)│ 🟡 over budget         │       │ │ │erties matching│ │ │
│ └────────────────────────────────────┘       │ │ │your search.   │ │ │
│                                              │ │ └───────────────┘ │ │
│ ┌────────────────────────────────────┐       │ │                   │ │
│ │ IMAGE    │ Another Listing    🔖   │       │ │ [Show more]       │ │
│ │ ...      │ ...                     │       │ │ [Lower budget]    │ │
│ └────────────────────────────────────┘       │ │ [Compare all]     │ │
│                                              │ └───────────────────┘ │
│ ┌────────────────────────────────────┐       ├───────────────────────┤
│ │ Show more results (7 remaining)    │       │ CHAT INPUT            │
│ └────────────────────────────────────┘       │ [textarea    ] [Send] │
│                                              │ (border-t, p-4)       │
└──────────────────────────────────────────────┴───────────────────────┘
```

**Overlay when shortlist is open:**
```
                                           ┌───────────────────┐
                                           │ SHORTLIST PANEL    │
  ████████ dark backdrop ████████████████  │ (w-80, fixed right)│
  ████████ (bg-black/50) ████████████████  │ Saved Listings (2) │
  ████████ click to close ███████████████  │ [Compare shortlist]│
  ██████████████████████████████████████  │ ┌─compact card──┐  │
  ██████████████████████████████████████  │ │ Title    🔖   │  │
  ██████████████████████████████████████  │ │ £1,750 · 2bed │  │
  ██████████████████████████████████████  │ └───────────────┘  │
                                           └───────────────────┘
```

### Key Layout Properties

- **Full screen:** `h-screen w-full` on root, each panel scrolls independently
- **Chat sidebar:** Fixed `w-[380px]`, `shrink-0`, `border-l border-border`
- **Listings panel:** `flex-1`, takes all remaining width
- **Header:** Full-width, `shrink-0`, 48px row + optional filter chip row
- **Shortlist overlay:** `fixed inset-0 z-40` backdrop + `fixed inset-y-0 right-0 z-50` panel
- **No responsive breakpoints** — layout breaks on screens < ~800px

### Typography

- System font stack: `ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif`
- Body text: `text-sm` (14px) with `leading-6`
- Labels: `text-xs` (12px)
- Logo: `text-lg` (18px), `font-bold`
- Heading (welcome): `text-xl` (20px), `font-semibold`

---

## 4. Component Tree & Props

```
App
├── Header
│   ├── Logo + subtitle
│   ├── Shortlist badge button (conditional: count > 0)
│   ├── Session menu (hamburger → dropdown)
│   │   ├── "New search" button
│   │   └── Session list (active highlighted, delete on hover)
│   └── ConstraintTags (inline mode, in filter row)
│
├── ListingsPanel
│   ├── Results header ("N properties" + action quick replies)
│   ├── CompareTable (if compare_data with ≥2 listings)
│   ├── ListingCard × N (full mode, horizontal)
│   ├── "Show more" button (if has_more)
│   └── WelcomeScreen (when no results and not generating)
│
├── Chat sidebar (380px div, not a component)
│   ├── "AI Assistant" label header (icon + text)
│   ├── ChatArea
│   │   ├── MessageBubble × N
│   │   │   ├── Role label (uppercase "USER" / "ASSISTANT")
│   │   │   ├── MessageContent (plain text or markdown)
│   │   │   └── ThinkingIndicator (3 pulsing dots, when streaming)
│   │   └── QuickReplies (buttons after last assistant message)
│   └── ChatInput (textarea + Send/Stop button)
│
└── ShortlistPanel (overlay, conditional on shortlistOpen)
    ├── Header ("Saved Listings (N)" + ✕ close)
    ├── "Compare shortlist" button (≥2 listings)
    └── ListingCard × N (compact mode)
```

---

## 5. Hooks & State Management

**No external state library** — all state is React `useState` + `localStorage`.

### `useSessions()` — Session CRUD + Persistence

```typescript
// Returns:
{
  sessions: ChatSession[];        // sorted by updatedAt desc
  activeId: string;               // currently selected session UUID
  activeSession: ChatSession;     // derived from activeId (fallback: first session)
  setActiveId: (id) => void;
  updateSession: (id, updater: (s) => s) => void;  // functional update, re-sorts
  createChat: () => void;         // new empty session titled "New Chat"
  removeChat: (id, isGenerating) => void;  // no-op if removing active + generating
}
```

- **Storage key:** `"openclaw-sessions-v2"` in localStorage
- **Session shape:** `{ id, title, createdAt, updatedAt, messages[] }`
- Title is set to first line of first user message when session starts
- Sessions auto-sorted by `updatedAt` descending on every update
- Falls back to single "Welcome" session if localStorage empty
- `createId()` uses `crypto.randomUUID()` with `Date.now()+Math.random()` fallback

### `useChat()` — Streaming + Metadata

```typescript
// Input:
{ activeSession: ChatSession, updateSession: (id, updater) => void }

// Returns:
{
  isGenerating: boolean;               // true during SSE stream
  metadata: SessionMetadata | null;    // latest structured data from backend
  suppressedIds: Set<string>;          // message IDs with structured cards (hide raw text)
  metadataForId: string | null;        // message ID where cards should render
  activeAssistantId: string | null;    // currently streaming message ID
  sendMessage: (input: string, routeHint?: object) => Promise<void>;
  sendSilentAction: (input: string, routeHint?: object, actionLabel?: string) => Promise<void>;
  stopGenerating: () => void;
}
```

**Key behaviors:**
- `sendMessage` creates user + empty assistant message, then streams SSE
- On `delta` events: appends text chunk to assistant message content
- On `metadata` event: if search results or compare data arrived, replaces assistant text with brief summary ("Found N properties matching your search." or "Comparison ready — see the table on the left.") and marks message as suppressed
- `sendSilentAction` calls backend without showing user message — used for:
  - Quick reply buttons (show more, lower budget, compare)
  - Constraint chip removal
  - Listing save/remove
  - Optional `actionLabel` creates a brief acknowledgment message (e.g., "Loading more listings…")
- `stopGenerating` aborts the fetch via AbortController
- All state resets when `activeSession.id` changes (session switch)
- **Deduplication:** URL-joined signatures prevent re-rendering identical results
- **Ref guards:** `isGeneratingRef` prevents duplicate sends while generating

---

## 6. Backend API Contract (SSE)

### Endpoint

```
POST /api/chat/stream
Content-Type: application/json

Body: {
  session_id: string,      // UUID
  user_text: string,       // user's message or action text
  route_hint?: {           // optional: pre-classified intent + params
    intent: "Search" | "Page_Nav" | "Compare" | "Shortlist" | "QA" | "Chitchat" | "DirectReply" | "Fallback",
    page_action?: "next",
    set_constraints?: { max_rent_pcm?: number, ... },
    clear_fields?: string[],
    shortlist_action?: "add" | "remove",
    target_indices?: number[],
    ...
  }
}
```

### Response: Server-Sent Events stream

The response is `text/event-stream`. Events are `\n\n` separated, each with `event:` and `data:` lines.

#### Event 1: `delta` — Streamed text chunks
```
event: delta
data: {"text": "Here are"}
```
Text is chunked into 8-character pieces, sent at ~10ms intervals. The frontend appends each chunk to the assistant message.

#### Event 2: `metadata` — Structured JSON (sent once, after text completes)
```
event: metadata
data: { ...full SessionMetadata JSON... }
```
This contains all structured data: search results, constraints, quick replies, compare data, shortlist state.

#### Event 3: `done` — Stream end signal
```
event: done
data: {}
```

#### Event 4: `error` — Error
```
event: error
data: {"message": "Something went wrong"}
```

### Full Metadata Example

```json
{
  "search_results": {
    "listings": [
      {
        "title": "Modern 2 Bed Flat, Mare Street",
        "url": "https://www.openrent.com/property-to-rent/...",
        "image_url": "https://images.openrent.com/...",
        "address": "Mare Street, Hackney, E8 3QE",
        "price_pcm": 1750,
        "bedrooms": 2,
        "bathrooms": 1,
        "available_from": "2026-04-01",
        "final_score": 0.87,
        "penalty_reasons": ["£50 over budget"],
        "preference_hits": ["pet-friendly", "has garden"]
      }
    ],
    "page_index": 0,
    "has_more": true,
    "total": 12,
    "remaining": 7
  },
  "constraints": {
    "budget": "≤£1,800/pcm",
    "location": ["hackney"],
    "bedrooms": [2],
    "furnish_type": "furnished",
    "available_from": "2026-04-01"
  },
  "quick_replies": [
    {
      "label": "Show more",
      "text": "show me more",
      "route_hint": { "intent": "Page_Nav", "page_action": "next" }
    },
    {
      "label": "Lower budget",
      "text": "lower budget to £1440/month",
      "route_hint": { "intent": "Search", "set_constraints": { "max_rent_pcm": 1440 } }
    },
    {
      "label": "Compare all",
      "text": "compare these listings",
      "route_hint": { "intent": "Compare" }
    }
  ],
  "compare_data": {
    "listings": [
      {
        "index": 1,
        "title": "Modern 2 Bed Flat, Mare Street",
        "url": "https://www.openrent.com/...",
        "image_url": "https://images.openrent.com/...",
        "price_pcm": 1750,
        "bedrooms": 2,
        "bathrooms": 1,
        "deposit": 1750,
        "available_from": "2026-04-01",
        "size_sqm": 55,
        "furnish_type": "Furnished",
        "property_type": "Flat"
      }
    ]
  },
  "shortlist": {
    "count": 2,
    "saved_ids": ["https://openrent.com/property-to-rent/abc", "https://openrent.com/property-to-rent/xyz"],
    "listings": [
      {
        "title": "...",
        "url": "...",
        "image_url": "...",
        "address": "...",
        "price_pcm": 1750,
        "bedrooms": 2,
        "bathrooms": 1,
        "available_from": "2026-04-01",
        "final_score": 0.87,
        "penalty_reasons": [],
        "preference_hits": ["pet-friendly"]
      }
    ]
  }
}
```

### How Route Hints Work

The frontend can skip backend intent classification by passing a `route_hint` with the request. This is used for all "silent actions" (no user message bubble shown):

| Action | user_text sent | route_hint |
|--------|---------------|------------|
| Pagination | `"show me more"` | `{ intent: "Page_Nav", page_action: "next" }` |
| Lower budget | `"lower budget to £1440/month"` | `{ intent: "Search", set_constraints: { max_rent_pcm: 1440 } }` |
| Compare listings | `"compare these listings"` | `{ intent: "Compare" }` |
| Remove constraint | `"clear constraint"` | `{ intent: "Search", clear_fields: ["max_rent_pcm"] }` |
| Save listing | `"save listing 3"` | `{ intent: "Shortlist", shortlist_action: "add", target_indices: [3] }` |
| Remove from shortlist | `"remove shortlist 2"` | `{ intent: "Shortlist", shortlist_action: "remove", target_indices: [2] }` |
| Compare shortlist | `"compare my shortlist"` | `{ intent: "Compare" }` |

### Other Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/healthz` | Health check — `{"ok": true, "sessions": N}` |
| `GET` | `/crawl-status` | Last data crawl status |

---

## 7. Type Definitions

```typescript
// === Messages & Sessions ===

type Role = "user" | "assistant";

type Message = {
  id: string;          // UUID
  role: Role;
  content: string;     // may be empty while streaming
  createdAt: number;   // epoch ms
};

type ChatSession = {
  id: string;          // UUID
  title: string;       // first line of first user message, or "New Chat"
  createdAt: number;
  updatedAt: number;
  messages: Message[];
};

// === Backend Metadata (from SSE metadata event) ===

type ListingData = {
  title: string;             // "Modern 2 Bed Flat, Mare Street"
  url: string;               // full URL to listing page
  image_url: string;         // property photo URL
  address: string;           // "Mare Street, Hackney, E8 3QE"
  price_pcm: number;         // monthly rent in GBP
  bedrooms: number;          // 0 = studio
  bathrooms: number;
  available_from: string;    // ISO date or descriptive string
  final_score: number;       // 0.0–1.0, higher = better match
  penalty_reasons: string[]; // e.g., ["£50 over budget", "no garden"]
  preference_hits: string[]; // e.g., ["pet-friendly", "near station"]
};

type SearchResultsMeta = {
  listings: ListingData[];   // current page of results (typically 5)
  page_index: number;        // 0-based page number
  has_more: boolean;         // more pages available
  total: number;             // total matching properties
  remaining: number;         // total - shown_so_far
};

type ConstraintsMeta = Record<string, unknown>;
// Possible keys and their value types:
//   budget: string ("≤£1,800/pcm")
//   location: string[] (["hackney", "dalston"])
//   bedrooms: number[] ([2] or [1, 2, 3])
//   furnish_type: string | string[] ("furnished")
//   let_type: string ("long_term")
//   available_from: string ("2026-04-01")
//   min_tenancy_months: number (12)

type QuickReply = {
  label: string;                        // button display text
  text: string;                         // message sent to backend
  route_hint?: Record<string, unknown>; // intent shortcut for backend
};

type CompareListingData = {
  index: number;          // 1-based position
  title: string;
  url: string;
  price_pcm: number;
  bedrooms: number;
  bathrooms: number;
  deposit: number;        // may be 0 or null if unknown
  available_from: string;
  size_sqm: number;       // may be 0 if unknown
  furnish_type: string;   // "Furnished", "Unfurnished", "Part Furnished", ""
  property_type: string;  // "Flat", "House", "Studio", ""
};

type CompareData = {
  listings: CompareListingData[];
};

type ShortlistMeta = {
  count: number;
  saved_ids: string[];      // listing URLs used as unique IDs
  listings: ListingData[];  // full listing objects for rendering shortlist panel
};

type SessionMetadata = {
  search_results?: SearchResultsMeta;
  constraints?: ConstraintsMeta;
  quick_replies?: QuickReply[];
  compare_data?: CompareData;
  shortlist?: ShortlistMeta;
};
```

---

## 8. Every Component in Detail

### `App.tsx` — Root Layout Shell (~156 lines)

**Responsibilities:**
- Wires together `useSessions()` and `useChat()` hooks
- Manages `shortlistOpen` boolean state
- Computes `savedIds: Set<string>` from `metadata?.shortlist?.saved_ids`
- Defines all action handlers bridging UI events to backend calls

**Action handler mapping:**

| UI Event | Handler | What it does |
|----------|---------|-------------|
| Quick reply button click | `handleQuickReply(text, routeHint)` | `sendSilentAction` with auto-resolved action label |
| Constraint chip ✕ click | `handleRemoveConstraint(clearFields, label)` | Silent action: `"clear constraint"` + `clear_fields` hint |
| Bookmark click (save) | `handleSaveListing(pageIndex)` | Silent action: shortlist add, 1-indexed |
| Bookmark click (remove) | `handleRemoveFromShortlist(position)` | Silent action: shortlist remove, 1-indexed |
| Welcome example click | `handleSuggestionClick(text)` | `sendMessage(text)` — visible in chat |
| "Show more" button | inline in JSX | `handleQuickReply("show me more", { intent: "Page_Nav", ... })` |
| "Compare shortlist" | inline in ShortlistPanel | `sendSilentAction("compare my shortlist", { intent: "Compare" })` |

**`resolveActionLabel(routeHint)`** generates loading text for silent actions:
- `Page_Nav` → "Loading more listings…"
- `Compare` → "Comparing listings…"
- `Search` with `max_rent_pcm` → "Lowering budget to £X/month…"
- `Search` otherwise → "Refining search…"

**Layout JSX structure:**
```jsx
<div className="flex h-screen w-full flex-col bg-surface text-text">
  <Header ... />
  <div className="flex flex-1 overflow-hidden">
    <ListingsPanel ... />                    {/* flex-1 */}
    <div className="flex w-[380px] shrink-0 flex-col border-l border-border bg-panel-alt">
      <div>💬 AI Assistant label</div>       {/* header bar */}
      <ChatArea ... />                       {/* flex-1 overflow-y-auto */}
      <ChatInput ... />                      {/* footer */}
    </div>
  </div>
  {shortlistOpen && <backdrop + ShortlistPanel />}
</div>
```

---

### `Header.tsx` — Top Bar (~154 lines)

**Two rows:**

**Row 1 (48px, always visible):**
- Left: `"OpenClaw"` in accent green, bold, text-lg + `"AI-powered rental search"` muted subtitle (hidden on small screens via `sm:inline`)
- Right: Shortlist badge (green pill with bookmark icon, only if count > 0) + Hamburger menu button

**Row 2 (conditional, border-t):**
- Shows when `constraints` object has keys
- Contains: `"Filters:"` label + `<ConstraintTags inline />` chips

**Session dropdown menu:**
- Absolute positioned below hamburger, `w-64 rounded-lg border bg-panel shadow-xl z-50`
- "New search" button at top with + icon (accent colored)
- Scrollable session list (`max-h-60 overflow-y-auto`)
- Active session: `bg-neutral-800 text-text`
- Inactive: `text-muted hover:bg-neutral-800 hover:text-text`
- Delete button (✕): `hidden group-hover:inline`, disabled while generating
- Click outside closes menu (mousedown listener)

---

### `ListingsPanel.tsx` — Main Content Area (~122 lines)

**Three states:**

1. **Has results** (`results.listings.length > 0`):
   - Header bar: `"{total} properties"` count + "Updating…" pulse animation if generating
   - Right side of header: Action quick replies filtered to `intent === "Search"` or `"Compare"` only
   - Compare table (if `compare_data.listings.length >= 2`)
   - Listing cards in `space-y-4` vertical stack
   - "Show more results (N remaining)" button at bottom

2. **Generating, no results yet:**
   - Centered thinking dots + "Searching properties…" text

3. **No results, not generating:**
   - `<WelcomeScreen />` with examples

---

### `ListingCard.tsx` — Property Card (~153 lines)

#### Full Mode (default, used in ListingsPanel)

Horizontal card layout:
```
┌────────────────┬──────────────────────────────────────┐
│                │ Title (line-clamp-2, links to URL) 🔖│
│    IMAGE       │ 2 bed · 1 bath · Available Apr 2026  │
│   w-72 h-48    │ 123 Mare Street, Hackney, E8 (trunc) │
│   (288×192)    │                                      │
│                │ 🟢 pet-friendly  🟢 near station     │
│  ┌───────┐    │ 🟡 £50 over budget                   │
│  │£1,750 │    │                                      │
│  │ pcm   │    │                                      │
│  └gradient┘   │                                      │
└────────────────┴──────────────────────────────────────┘
```

- **Container:** `group flex overflow-hidden rounded-xl border border-border bg-panel hover:border-neutral-500`
- **Image section:** `relative h-48 w-72 shrink-0 bg-neutral-800`
  - Image: `h-full w-full object-cover`, `loading="lazy"`
  - Fallback: centered house SVG icon in `text-neutral-600`
  - Price overlay: `absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/80 to-transparent`
  - Price: `text-lg font-bold` + `"pcm"` in `text-xs text-muted`
- **Details section:** `flex min-w-0 flex-1 flex-col justify-between p-4`
  - Title: `line-clamp-2 text-sm font-semibold`, links to `listing.url` (opens new tab)
  - Specs: `"N bed · N bath · Available DATE"` in `text-xs text-muted`
  - Address: `truncate text-xs text-muted`
  - Tags: `flex flex-wrap gap-1 mt-3`
    - Green: `rounded bg-green-900/40 px-1.5 py-0.5 text-[11px] text-green-400`
    - Amber: `rounded bg-amber-900/40 px-1.5 py-0.5 text-[11px] text-amber-400`
- **Bookmark button:**
  - Unsaved: `opacity-0 group-hover:opacity-100 text-muted hover:text-accent`
  - Saved: `text-accent hover:bg-red-900/30 hover:text-red-400`
  - SVG: filled when saved, outline when unsaved

**Tags parsing:** `penalty_reasons` and `preference_hits` may arrive as `string[]` or as a single semicolon/newline-joined string. The `toArray()` helper normalizes both formats.

#### Compact Mode (`compact` prop, used in ShortlistPanel)

```
┌──────────────────────────────────┐
│ Title (blue link)            🔖  │
│ £1,750/mo · 2 bed · 1 bath      │
└──────────────────────────────────┘
```

- `rounded-lg border border-border bg-panel p-3`
- Title as blue link (`text-[#7dd3fc]`), bookmark always visible
- Specs joined with ` · ` separator

---

### `WelcomeScreen.tsx` — Empty State (~38 lines)

Centered vertically and horizontally:
- `🏠` emoji at `text-5xl` (48px)
- `"Find your next rental"` heading: `text-xl font-semibold`
- Description: `"Describe what you're looking for in the chat — I'll search thousands of listings and find what matches."`
- 4 example buttons in a `space-y-2` column:
  1. "2 bed flat in Hackney under £1,800"
  2. "Furnished studio near King's Cross"
  3. "3 bed house in Zone 2, pet-friendly"
  4. "Something with a garden in Brixton"
- Button style: `w-full rounded-lg border border-border bg-panel px-4 py-2.5 text-left text-sm text-muted hover:border-neutral-500 hover:text-text`
- Text wrapped in curly quotes: `"…"`

---

### `ChatArea.tsx` — Message List (~56 lines)

- Scrollable: `flex-1 overflow-y-auto`
- Inner padding: `space-y-3 px-4 py-4`
- Auto-scrolls to bottom via `useRef` + `scrollIntoView({ behavior: "smooth" })` on message count or generating state change
- Empty state: `"Describe the rental you're looking for."` centered, muted
- Shows `QuickReplies` after messages when `!isGenerating && quickReplies.length > 0`

---

### `MessageBubble.tsx` — Single Message (~38 lines)

- **Role label:** `text-xs uppercase tracking-wide text-muted` above bubble
- **Bubble:** `rounded-xl px-4 py-3 text-sm leading-6`
  - User: `ml-auto max-w-[85%] whitespace-pre-wrap bg-neutral-700`
  - Assistant: `max-w-full bg-[#262626]`
- **Content logic:**
  - If `isGenerating && isActive` (currently streaming this message): `<ThinkingIndicator />`
  - Else if content not empty: `<MessageContent />`
  - Else: nothing (empty placeholder)

---

### `MessageContent.tsx` — Text Rendering (~54 lines)

- **User messages:** Plain text with URL detection
  - Splits on `https?://` regex
  - URLs become `<a>` tags: `underline text-[#7dd3fc]` opening in new tab
  - Newlines converted to `<br />`

- **Assistant messages:** Custom markdown → HTML
  - Uses `markdownToHtml()` from `lib/markdown.ts`
  - Rendered via `dangerouslySetInnerHTML` in a `<div className="markdown-content">`

---

### `ChatInput.tsx` — Input Bar (~69 lines)

- **Form layout:** `border-t border-border p-4` footer
- **Textarea:**
  - Auto-resizing: sets `height: auto` then `Math.min(scrollHeight, 160)px` on input change
  - Min height: `min-h-[48px]` (1 row), max: `max-h-40` (~5 rows)
  - `resize-none overflow-y-auto rounded-lg border border-border bg-panel px-3 py-3 text-sm leading-6`
  - Focus: `focus:border-neutral-500`
  - Placeholder: "Describe what you're looking for..."
- **Submit triggers:**
  - Enter key (without Shift) — prevents default, submits
  - Shift+Enter — inserts newline
  - Form submit (Send button click)
- **Send button:** `rounded-lg bg-accent px-4 py-2 text-sm font-medium text-black hover:opacity-90`
- **Stop button** (replaces Send while generating): `rounded-lg border border-border px-4 py-2 text-sm hover:bg-neutral-800`

---

### `ConstraintTags.tsx` — Filter Chips (~126 lines)

**Field-specific formatting:**

| Constraint Key | Display Format | Fields Cleared on Remove |
|---------------|----------------|--------------------------|
| `budget` | Raw string (e.g., "≤£1,800/pcm") | `["max_rent_pcm"]` |
| `location` | Comma-joined array (e.g., "hackney, dalston") | `["location_keywords"]` |
| `bedrooms` | Smart: "Studio" (0) / "1 bed" / "2–3 beds" (range) | `["layout_options"]` |
| `furnish_type` | Title-cased, underscores→spaces | `["furnish_type"]` |
| `let_type` | Title-cased | `["let_type"]` |
| `available_from` | "From MMM YYYY" (parsed date) or raw string | `["available_from"]` |
| `min_tenancy_months` | "N month min tenancy" | `["min_tenancy_months"]` |
| (unknown key) | Raw value or joined array | `[key]` |

**Chip rendering:**
- `inline-flex items-center gap-1 rounded-full bg-neutral-700 px-2.5 py-1 text-xs text-text`
- ✕ button: `text-muted hover:text-text`, calls `onRemove(clearFields, actionLabel)`

**Two modes:**
- `inline` (used in Header): renders chips without wrapper, just fragments
- Standalone: `sticky top-0 z-10 bg-surface/90 backdrop-blur border-b border-border px-4 py-2`

---

### `CompareTable.tsx` — Side-by-Side Comparison (~99 lines)

Renders when `compare_data.listings.length >= 2`.

**Structure:**
```
┌──────────┬────────────┬────────────┬────────────┐
│ Field    │ #1 — Title │ #2 — Title │ #3 — Title │
├──────────┼────────────┼────────────┼────────────┤
│ Price/mo │ £1,750 ★   │ £1,900     │ £2,100     │
│ Beds     │ 2          │ 3 ★        │ 2          │
│ Baths    │ 1          │ 2 ★        │ 1          │
│ Deposit  │ £1,750 ★   │ £1,900     │ £2,100     │
│ Avail.   │ Apr 2026   │ Mar 2026   │ Now        │
│ Size     │ 55 sqm ★   │ 45 sqm     │ 50 sqm    │
│ Furnish  │ Furnished  │ Unfurnished│ Part       │
│ Type     │ Flat       │ House      │ Flat       │
└──────────┴────────────┴────────────┴────────────┘
★ = best value (bold + accent color)
```

**Fields and "best" logic:**

| Field | Format | Best = | Highlighted? |
|-------|--------|--------|-------------|
| Price/mo | `£X,XXX` | min (cheapest) | Yes |
| Beds | N | max | Yes |
| Baths | N | max | Yes |
| Deposit | `£X,XXX` | min (lowest) | Yes |
| Available | date string | — | No |
| Size | `N sqm` | max (biggest) | Yes |
| Furnished | string | — | No |
| Type | string | — | No |

- Best cell: `font-semibold text-accent`
- Normal cell: `text-text`
- Column headers: listing title truncated to 24 chars, linked to URL in blue
- Left column: sticky with `bg-[#262626]`, field labels in `text-xs font-medium text-muted`
- Wrapper: `overflow-x-auto rounded-lg border border-border`
- Touch scrolling: `-webkit-overflow-scrolling: touch`

---

### `ShortlistPanel.tsx` — Saved Listings Overlay (~61 lines)

- **Panel:** `h-full w-80 shrink-0 border-l border-border bg-panel`
- **Header:** "Saved Listings (N)" + ✕ close button
- **Compare button:** Only if ≥2 listings. `w-full rounded-lg bg-accent/20 py-1.5 text-xs font-medium text-accent hover:bg-accent/30`
- **List:** `flex-1 overflow-y-auto p-3 space-y-3` of compact `ListingCard`s
- **Empty state:** "No saved listings yet. Click the bookmark on a listing card to save it."
- **Backdrop:** `fixed inset-0 z-40 bg-black/50`, click to close
- **Panel positioning:** `fixed inset-y-0 right-0 z-50 shadow-2xl`

---

### `QuickReplies.tsx` — Action Buttons (~24 lines)

- `flex flex-wrap gap-2 pt-2`
- Button: `rounded-lg border border-border px-3 py-1.5 text-xs text-muted hover:bg-neutral-700 hover:text-text`
- Click: `onSelect(reply.text, reply.route_hint)`

---

### `ThinkingIndicator.tsx` — Loading Dots (~9 lines)

- `inline-flex items-center gap-1`
- 3 `<span className="thinking-dot">` elements
- CSS: 6px circles, `bg-[#a3a3a3]`, `animation: thinking-pulse 1.2s ease-in-out infinite`
- Staggered: +0.2s, +0.4s delays
- Keyframe: opacity 0.3→1→0.3, scale 0.8→1→0.8

---

### `Sidebar.tsx` — **UNUSED Legacy Component**

Was a responsive sidebar layout (35vh on mobile, full height on md+). Superseded by Header dropdown menu. Can be deleted.

---

## 9. Styling System

### Tailwind Configuration

```javascript
// tailwind.config.cjs
module.exports = {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        surface: "#171717",
        panel: "#212121",
        "panel-alt": "#1a1a1a",
        border: "#303030",
        muted: "#a3a3a3",
        text: "#f5f5f5",
        accent: "#10a37f",
        "accent-dim": "#0d8868",
      },
    },
  },
  plugins: [],
};
```

### Custom CSS (`index.css`)

```css
/* Base */
:root { font-family: ui-sans-serif, -apple-system, ... }
* { box-sizing: border-box; }
html, body, #root { margin: 0; height: 100%; }

/* Thinking indicator */
.thinking-dot { 6px circle, pulse animation 1.2s, staggered 0.2s each }

/* Markdown content */
.markdown-content p { margin: 0.25em 0 }
.markdown-content .markdown-heading { font-weight: 600, margin: 0.75em 0 0.25em }
.markdown-content h3 { font-size: 1.05em }
.markdown-content h4 { font-size: 0.95em }
.markdown-content h5, h6 { font-size: 0.9em }
.markdown-content .markdown-list { padding-left: 1.5em, list-style disc/decimal }
.markdown-content .markdown-table { border-collapse, #404040 borders, alternating #1e1e1e rows }
.markdown-content a { color: #7dd3fc, underlined }
.markdown-content strong { weight 600 }

/* Compare table */
.compare-table-wrapper { touch scrolling }
.compare-table { border-collapse, nowrap cells }
.compare-table thead tr { double bottom border }
```

### Markdown Parser (`lib/markdown.ts`)

Custom hand-written parser supporting:
- **Bold:** `**text**` → `<strong>`
- **Italic:** `*text*` → `<em>` (avoids conflict with bold)
- **Bare URLs:** `https://...` → clickable `<a>` links
- **Inline links:** `[text](url)` → `<a>`
- **Headers:** `# to ####` → `<h3> to <h6>` (shifted +2 to keep sizes small)
- **Unordered lists:** `- item` or `* item` → `<ul class="markdown-list">`
- **Ordered lists:** `1. item` → `<ol class="markdown-list">`
- **Tables:** `| col | col |` → `<table>` with thead/tbody, auto-filters separator rows
- **Blank lines** → paragraph breaks

**Not supported:** Code blocks, images, blockquotes (intentionally excluded as irrelevant to rental context).

---

## 10. Data Flow Walkthrough

### Flow 1: User Sends a Search Query

```
1. User types "2 bed in Hackney under £1,800" → presses Enter
2. ChatInput.onSend(text) → App → sendMessage(text)
3. useChat.sendMessage():
   a. Creates userMessage { role: "user", content: "2 bed in..." }
   b. Creates empty assistantMessage { role: "assistant", content: "" }
   c. Updates session: appends both messages, sets title if first message
   d. Sets isGenerating=true, activeAssistantId=assistantMessage.id
   e. Fetches POST /api/chat/stream { session_id, user_text: "2 bed in..." }
4. Backend processes (0.5–3s) → streams SSE events:
   a. delta: { text: "I found 12 prope..." } × many → onChunk appends to assistant
   b. metadata: { search_results, constraints, quick_replies, shortlist }
   c. done: {}
5. On metadata arrival:
   a. Computes URL signature from listing URLs
   b. If new results: replaces assistant text with "Found 12 properties matching your search."
   c. Adds message ID to suppressedIds (raw listing text hidden)
   d. Sets metadataForId for card rendering target
6. React re-renders:
   a. ListingsPanel: shows listing cards from metadata.search_results
   b. Header: shows constraint chips from metadata.constraints
   c. ChatArea: shows quick reply buttons from metadata.quick_replies
   d. ShortlistPanel: badge updates from metadata.shortlist
7. isGenerating → false, activeAssistantId → null
```

### Flow 2: User Clicks "Show More" (Pagination)

```
1. ListingsPanel "Show more" button → App.onShowMore()
2. handleQuickReply("show me more", { intent: "Page_Nav", page_action: "next" })
3. sendSilentAction with actionLabel "Loading more listings…"
4. Creates brief ack message: "Loading more listings…" (visible in chat)
5. Backend skips intent classification (route_hint), returns next page
6. Metadata arrives with next 5 listings, updated page_index/remaining
7. ListingsPanel renders new page of cards
```

### Flow 3: Constraint Removal

```
1. User clicks ✕ on "≤£1,800/pcm" chip in Header
2. ConstraintTags.onRemove(["max_rent_pcm"], "Removing budget filter…")
3. App.handleRemoveConstraint → sendSilentAction("clear constraint",
     { intent: "Search", clear_fields: ["max_rent_pcm"] },
     "Removing budget filter…")
4. Ack message appears: "Removing budget filter…"
5. Backend re-runs search without budget constraint
6. New metadata: more results, no budget in constraints
7. UI: budget chip disappears, listings refresh, counts update
```

### Flow 4: Save → Shortlist → Compare

```
1. User hovers ListingCard → bookmark icon appears → clicks
2. onSave() → handleSaveListing(3) → sendSilentAction("save listing 3",
     { intent: "Shortlist", shortlist_action: "add", target_indices: [3] })
3. Backend adds to session shortlist → metadata includes updated shortlist
4. savedIds Set updates → bookmark fills on card, badge appears in Header
5. User clicks "Saved (2)" badge → ShortlistPanel overlay opens
6. User clicks "Compare shortlist" → sendSilentAction("compare my shortlist",
     { intent: "Compare" }) → shortlist closes
7. Backend returns compare_data → CompareTable renders above listings
```

---

## 11. Current UX Pain Points

1. **No mobile/responsive layout** — 380px fixed sidebar breaks on anything under ~800px
2. **Generic "ChatGPT clone" appearance** — dark theme + green accent, nothing says "property search"
3. **No map view** — Leaflet installed but unused; no spatial context for locations
4. **Welcome screen is bare** — just a 🏠 emoji + 4 text buttons
5. **Chat and results feel disconnected** — two separate panels with no visual connection
6. **No listing detail expansion** — must click through to external URL for full details
7. **No loading skeletons** — transitions feel jarring (empty → dots → cards)
8. **`final_score` not shown** — relevance score exists but users can't see it
9. **No sort controls** — results ordered by AI ranking, no manual sort option
10. **Constraint editing limited** — can only remove chips, not edit values (e.g., adjust budget)
11. **Compare table basic** — plain HTML table, hard to read on mobile
12. **Session management minimal** — hamburger dropdown, no search/rename
13. **No keyboard navigation** — no shortcuts for navigating listings or chat

---

## 12. File Inventory

```
frontend/
├── index.html                    # Single HTML entry point, <div id="root">
├── package.json                  # Dependencies & scripts (see section 2)
├── postcss.config.cjs            # PostCSS: tailwind → autoprefixer
├── tailwind.config.cjs           # Custom dark theme colors
├── tsconfig.json                 # TypeScript strict, ES2020, react-jsx
├── tsconfig.node.json            # Node TS config for Vite
├── vercel.json                   # Deployment: build, output, rewrites
├── vite.config.ts                # Vite + React plugin + /api proxy
└── src/
    ├── main.tsx                  # ReactDOM.createRoot + StrictMode
    ├── App.tsx                   # Root layout, hook wiring, action handlers
    ├── index.css                 # Tailwind imports + custom CSS animations
    ├── vite-env.d.ts             # Vite type references
    ├── components/
    │   ├── ChatArea.tsx          # Scrollable message list + quick replies
    │   ├── ChatInput.tsx         # Auto-resize textarea + Send/Stop
    │   ├── CompareTable.tsx      # Side-by-side listing comparison
    │   ├── ConstraintTags.tsx    # Removable filter chips
    │   ├── Header.tsx            # Top bar: logo, badges, session menu, filters
    │   ├── ListingCard.tsx       # Property card (full horizontal + compact)
    │   ├── ListingsPanel.tsx     # Main content: results / welcome / loading
    │   ├── MessageBubble.tsx     # Message wrapper with role label + styling
    │   ├── MessageContent.tsx    # Plain text (user) / markdown (assistant)
    │   ├── QuickReplies.tsx      # Contextual action buttons
    │   ├── ShortlistPanel.tsx    # Saved listings slide-out overlay
    │   ├── Sidebar.tsx           # ⚠️ UNUSED legacy — can be deleted
    │   ├── ThinkingIndicator.tsx # CSS-only 3-dot pulse animation
    │   └── WelcomeScreen.tsx     # Empty state with example queries
    ├── hooks/
    │   ├── useChat.ts            # SSE streaming, metadata state, send/stop
    │   └── useSessions.ts        # Session CRUD, localStorage persistence
    ├── lib/
    │   ├── markdown.ts           # Custom MD→HTML (bold, italic, lists, tables, links)
    │   ├── mockStream.ts         # ⚠️ Name is legacy — this IS the production SSE client
    │   └── storage.ts            # localStorage load/save helpers
    └── types/
        └── chat.ts               # All TypeScript type definitions
```

---

## 13. What We Need From You (Gemini)

### 1. New Layout Proposal
The current layout (listings left + chat right fixed sidebar) is functional but generic. What's the best layout for a conversational search product? Consider:
- Should chat be a sidebar, overlay, bottom sheet, or inline with results?
- How should the layout transition from "landing" to "results" state?
- Can we make the chat feel less like a bolted-on ChatGPT widget?

### 2. Welcome / Landing Screen Redesign
Current: 🏠 emoji + 4 buttons. Needs visual appeal and product communication.

### 3. Visual Design Direction
We have dark theme with `#10a37f` green accent. Should we keep/refine/change this? Need our own identity separate from "ChatGPT clone."

### 4. Component-Level Mockups or Descriptions
For any new/changed components, keeping in mind:
- Must work with the existing SSE streaming protocol (no backend changes)
- React + TailwindCSS (can suggest new Tailwind color tokens)
- The data shapes from the metadata event are fixed
- Leaflet maps are available if you want to incorporate them

### 5. Responsive Design
Currently completely breaks on mobile. Need mobile-first approach:
- Mobile: ~375–428px
- Tablet: ~768px
- Desktop: 1024px+

### 6. Listing Card Redesign
Current: horizontal (image left, details right). Consider:
- Grid layout option?
- Better use of preference_hits (green) and penalty_reasons (amber)?
- How to surface the relevance score visually?

---

## 14. Constraints on the Redesign

- **No backend changes** — all data comes from the SSE stream as described
- **Keep React + TailwindCSS** — no new frameworks
- **Sessions are local** — no user accounts, localStorage only
- **Dark theme preferred** — users browse at all hours
- **Performance** — 5–20 listing cards per page, must scroll smoothly
- **Leaflet maps available** — installed, ready to use if wanted

### Deliverables Format

Either:
- Wireframes / mockups (images or Figma links)
- Detailed written descriptions with Tailwind class suggestions we can implement
- ASCII layouts for structure + color/spacing specs

We will implement whatever you design in React + TailwindCSS ourselves.
