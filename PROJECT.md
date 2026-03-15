# OpenClaw — Project Reference & Dev Tracker

> **Who uses this:** Claude.
> This is the single source of truth: living task tracker + full technical reference.
> **Rule:** Mark tasks `✅` when done, `🔄` when in progress. Add bugs as you find them.
> **Branch:** `openclaw`
>
> - **Do not start work autonomously.** Wait for the user to assign a task.

---

## Current App State

| Layer | Status | Notes |
|-------|--------|-------|
| Backend API | ✅ Running | FastAPI · `cd backend && uvicorn api_server:app --host 0.0.0.0 --port 8000` |
| Qdrant Cloud | ✅ Connected | **29,119 listings** (23,592 Rightmove + 6,586 OpenRent, 1,343 merged), `rent_listings` collection |
| Frontend | ✅ Running | Vite · `cd frontend && node node_modules/.bin/vite --host 0.0.0.0 --port 5174` (NOT 5173 — see CLAUDE.md) |
| Search pipeline | ✅ Working | LangGraph + 4-stage pipeline (retrieve → filter → rank → explain) |
| SSE streaming | ✅ Working | delta / metadata / done events |
| Session persistence | ✅ Working | localStorage `openclaw-sessions-v2` |

---

## Immediate Next Priority

```
1. Quick/Deep toggle button (F-F8)               → backend ready, needs frontend UI
2. Session rename (F-F4)                         → double-click to rename
3. Re-crawl Rightmove with area names (B-B2)     → fix location miss rate
```

---

## Data State

| Dataset | Count | Quality | Notes |
|---------|-------|---------|-------|
| Rightmove London | 23,592 | Medium — some location misses | Crawled with postcodes; re-crawl with area names (B-B2) |
| OpenRent London | 6,586 | Good | Full amenity fields: bills, pets, garden, EPC, tenant prefs |
| Merged (both portals) | 1,343 | Good | Rightmove base + OpenRent enrichment; `source_site=rightmove+openrent` |
| Qdrant Cloud total | **29,119** | Clean | All dead (410) listings removed; images backfilled |
| Gallery images | ~29,119 | Good | Rightmove: backfilled via `backfill_images.py`; OpenRent: backfilled via `backfill_openrent_images.py` (5,516 updated, 11 dead) |

---

## Frontend Tasks

### Bugs

| # | Status | Issue | Detail |
|---|--------|-------|--------|
| F-B1 | ✅ Fixed | Match % showed raw `final_score * 100` (e.g. "11%") | Now normalised 70–100% within page, minus 8% per penalty reason |
| F-B2 | ✅ Fixed | Chat accumulates multiple "Loading more listings…" ack messages | Pagination and interactions are now fully silent |
| F-B4 | ✅ Fixed | ListingCard compact mode + bookmark style polish | Smaller bookmark button in compact mode, accent fill when saved |
| F-B5 | ✅ Fixed | Feature items show leading `- ` dash | `_clean()` in `_features_list()` strips `- `, `–`, `•` list markers |
| F-B6 | ✅ Fixed | Parking/garage listings appear in search results | `apply_hard_filters_with_audit` now excludes non-residential property types |
| F-B7 | ✅ Fixed | Skeleton placeholders flash during pagination | Added `!isSilentAction` guard to skeleton render in `ListingsPanel.tsx` |
| F-B8 | ✅ Fixed | OpenRent listings show only 1 photo (logo) | Gallery images backfilled to Qdrant via `backfill_openrent_images.py` (5,516 listings) |

### Polish

| # | Status | Task |
|---|--------|------|
| F-P1 | ✅ Fixed | Title and address identical on most cards — address hidden if matches title |
| F-P2 | ✅ Fixed | "Available ask agent" styled as "Date not provided" |
| F-P3 | ✅ Fixed | No explanation when tags are absent — added "No issues flagged" |
| F-P4 | ✅ Fixed | Floating pagination blocks UI — moved to full-width footer |
| F-P5 | ✅ Fixed | Portrait images stretch cards — enforced `h-64` |
| F-P6 | ✅ Fixed | `<PARA>` tags visible in descriptions — smart regex formatter |

### Features

| # | Agent | Status | Feature | Detail |
|---|-------|--------|---------|--------|
| F-F1 | Claude | ✅ Done | **Map view** | Leaflet map tab, cluster markers, Search this area (exact viewport bounds) |
| F-F2 | Claude | ✅ Done | **Listing detail drawer** | Slide-out with full info, Portal rendering, scroll lock, keyboard focus trap |
| F-F7 | Claude | ✅ Done | **Image carousel** | Left/right arrows, dot indicators, 1/N counter. Features/description on card |
| F-F3 | Claude | ✅ Done | **Mobile bottom nav** | Switch Chat ↔ Results on mobile |
| F-F4 | Claude | 🔴 Open | **Session rename** | Double-click session title to rename |
| F-F5 | Claude | 🔴 Open | **Viewing checklist** | Per-listing checklist panel (legal + physical checks) |
| F-F6 | Claude | 🔴 Open | **Contract upload UI** | File upload → send to contract analysis endpoint |
| F-F8 | Claude | 🔴 Open | **Quick/Deep toggle** | Session-level mode switch; backend already emits `thinking_mode` in metadata |

---

## Backend Tasks

### Bugs

| # | Status | Issue | Detail |
|---|--------|-------|--------|
| B-B1 | ✅ Fixed | `lat`/`lon` not in SSE metadata | Added to `build_metadata()` in `api_server.py` |
| B-B2 | 🔴 Open | Rightmove crawled with postcodes → location miss rate high | Re-crawl `crawl_london.py` using area names |

### Cross-Session Warnings

> **⚠️ Session conflict (2026-03-12):** Commit `437b69f` (red flag detection, B-F3) was committed from a worktree while another session had uncommitted changes to the same files (`soft_rank.py`, `ListingCard.tsx`, `ListingDetailDrawer.tsx`, `api_server.py`, `chat.ts`). This caused:
>
> 1. **`openrent_url` NaN bug** — `candidate_snapshot()` in `signals.py` didn't include `source_site`/`openrent_url`, so they were dropped by the pipeline. When re-added, the DataFrame converts `""` to `NaN`; `str(NaN)` → `"nan"` which is truthy in JS → every listing showed two portal buttons. **Fixed** with `_safe_str()` in `api_server.py`.
> 2. **`collection_exists` 403** — Qdrant Cloud read-only keys lack HEAD endpoint permission. **Fixed** with try/except fallback in `engine.py`.
>
> **Rule for future sessions:** If you modify files in `skills/search/`, `backend/`, or `frontend/src/components/`, check `git status` first — another session may have uncommitted changes to the same files. Coordinate via this file.

### Pipeline Improvements

| # | Status | Task | Detail |
|---|--------|------|--------|
| B-P1 | ✅ Fixed | **Geo-radius fallback** | Token miss → geocode via LONDON_REGIONS → 3km haversine radius search |
| B-P2 | 🔴 Open | **Unify listing fields** | `deposit`, `size_sqm`, `furnish_type`, `property_type` inconsistent across search_results vs compare_data |

### Features

| # | Agent | Status | Feature | Section |
|---|-------|--------|---------|---------|
| B-F1 | Claude | ✅ Not needed | **Listing detail endpoint** | All fields already in SSE metadata stream via `_map_listing()` |
| B-F2 | Claude | ✅ Done | **OpenRent scraper** | 6,586 London listings; amenity booleans; merged with Rightmove | 1 |
| B-F3 | Claude | ✅ Done | **Red flag detection** | Regex + boolean scan: No DSS, No pets, No deposit protection, Guarantor required. Image placeholder filter (`_is_real_image`) | 3 |
| B-F8 | Claude | ✅ Done | **Boolean signal system** | Two-tier bool resolution (explicit field → text regex → None); hard filter rejects contradictions; soft rank +0.12 weight for matches; synthetic text injection for semantic compat | 1 |
| B-F9 | Claude | ✅ Done | **Source badges + portal links** | ListingCard/Drawer show Rightmove/OpenRent/Both badge; merged listings get dual buttons; single-source get one button | 1 |
| B-F4 | Claude | 🔴 Open | **Draft viewing request** | `POST /api/contact/draft`, LLM + listing context | 3 |
| B-F5 | Claude | ✅ Done | **Commute time** | TfL Journey API: LLM extracts commute_destination, geocoded via stations.json (721 stations, fuzzy+abbrev) / TfL Place Search / OSM Nominatim; parallel TfL calls in build_metadata (cached 1hr); card shows color-coded time; QA interceptor for "how long to X"; match_pct redesigned as requirement-satisfaction score | 2 |
| B-F5b | Claude | 🔴 Open | **Commute QA: merge LLM call into router** | `_try_extract_commute_destination_via_llm()` fires an extra OpenAI call on every QA question — wasteful since most QA is about pets/rent/bedrooms. Merge commute detection into the existing router prompt so it's one call, not two. | 1 |
| B-F6 | Claude | 🔴 Open | **Contract analysis** | `POST /api/contract/analyse`, PDF → plain-English summary + clause flags | 5 |
| B-F7 | Claude | ✅ Done | **Tenant rights RAG** | Tier 1 (11 curated Markdown files + keyword/LLM topic router) + Tier 2 (Qdrant vector search, 147 chunks, fastembed + cross-encoder rerank); LangGraph `rights` node wired | 6 |

---

## API Contract

### SSE Metadata — Listing Object

```typescript
{
  title: string
  url: string
  image_url: string        // cover photo (logos/placeholders filtered by _is_real_image)
  image_urls: string[]     // full gallery up to 10; logos/maps/placeholders stripped
  address: string
  price_pcm: number
  bedrooms: number
  bathrooms: number
  available_from: string
  lat: number | null
  lon: number | null
  final_score: number      // raw soft-rank composite (~0.05–0.20); frontend normalises to 70–100%
  penalty_reasons: string[]
  preference_hits: string[]
  red_flags: string[]        // e.g. ["No pets", "No DSS", "Guarantor required"]
  source_site: string        // "rightmove" | "openrent" | "rightmove+openrent"
  openrent_url: string       // non-empty only for merged listings
  // Also present: description, features, deposit, property_type, furnish_type
}
```

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

## Product Roadmap

```
[FIND] → [RESEARCH] → [CONTACT] → [VIEW] → [SIGN] → [RIGHTS]
   1          2            3          4        5          6
```

| Section | Status | Key features |
|---------|--------|-------------|
| 1 · Find | ✅ Working | Multi-portal search (Rightmove + OpenRent); conversational constraints; LangGraph orchestration |
| 2 · Research | 🔄 Partial | Commute time (TfL) ✅; crime (police.uk), avg rent, flood risk, EPC 🔴 |
| 3 · Contact | 🔄 Partial | Red flag detection ✅; draft viewing email 🔴, holding deposit warnings 🔴 |
| 4 · View | 🔴 Planned | Legal checklist, inspection checklist, agent question generator |
| 5 · Sign | 🔴 Planned | Contract PDF analysis, clause flagging, deposit protection explainer |
| 6 · Rights | ✅ Working | Tier 1 (curated files + topic router) + Tier 2 (Qdrant vector search); LangGraph `TenantRights` intent wired |
