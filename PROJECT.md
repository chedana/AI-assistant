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
| Backend API | ✅ Running | FastAPI · `cd backend && uvicorn api_server:app --host 0.0.0.0 --port 8000` |
| Qdrant Cloud | ✅ Connected | **29,119 listings** (23,592 Rightmove + 6,586 OpenRent, 1,343 merged), `rent_listings` collection |
| Frontend | ✅ Running | Vite · `cd frontend && npm run dev -- --host 0.0.0.0 --port 5173` |
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

```
[CLAUDE]  1. Re-crawl Rightmove with area names (B-B2)     → fix location miss rate
[CLAUDE]  2. Red flag detection (B-F3)                     → quick win, no new data
[GEMINI]  1. Session rename (F-F4)                         → double-click to rename
[GEMINI]  2. Viewing checklist UI (F-F5)                   → per-listing checklist panel
```

---

## Data State

| Dataset | Count | Quality | Notes |
|---------|-------|---------|-------|
| Rightmove London | 23,592 | Medium — some location misses | Crawled with postcodes; re-crawl with area names (B-B2) |
| OpenRent London | 6,586 | Good | Full amenity fields: bills, pets, garden, EPC, tenant prefs |
| Merged (both portals) | 1,343 | Good | Rightmove base + OpenRent enrichment; `source_site=rightmove+openrent` |
| Qdrant Cloud total | **29,119** | Clean | All dead (410) listings removed; images backfilled |
| Gallery images | ~29,119 | Partial | OpenRent: 100% in JSONL; Rightmove: backfilled to Qdrant only (re-run `backfill_images.py` after full sync) |

---

## Frontend Tasks (Gemini only — do not modify backend files)

### Bugs

| # | Status | Issue | Detail |
|---|--------|-------|--------|
| F-B1 | ✅ Fixed | Match % showed raw `final_score * 100` (e.g. "11%") | Now normalised 70–100% within page, minus 8% per penalty reason |
| F-B2 | ✅ Fixed | Chat accumulates multiple "Loading more listings…" ack messages | Pagination and interactions are now fully silent |
| F-B4 | ✅ Fixed | ListingCard compact mode + bookmark style polish | Smaller bookmark button in compact mode, accent fill when saved |
| F-B5 | ✅ Fixed | Feature items show leading `- ` dash | `_clean()` in `_features_list()` strips `- `, `–`, `•` list markers |
| F-B6 | ✅ Fixed | Parking/garage listings appear in search results | `apply_hard_filters_with_audit` now excludes non-residential property types |

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
| F-F1 | Gemini | ✅ Done | **Map view** | Leaflet map tab, cluster markers, Search this area (exact viewport bounds) |
| F-F2 | Gemini | ✅ Done | **Listing detail drawer** | Slide-out with full info, Portal rendering, scroll lock, keyboard focus trap |
| F-F7 | Gemini | ✅ Done | **Image carousel** | Left/right arrows, dot indicators, 1/N counter. Features/description on card |
| F-F3 | Gemini | ✅ Done | **Mobile bottom nav** | Switch Chat ↔ Results on mobile |
| F-F4 | Gemini | 🔴 Open | **Session rename** | Double-click session title to rename |
| F-F5 | Gemini | 🔴 Open | **Viewing checklist** | Per-listing checklist panel (legal + physical checks) |
| F-F6 | Gemini | 🔴 Open | **Contract upload UI** | File upload → send to contract analysis endpoint |

---

## Backend Tasks (Claude only — do not modify frontend files)

### Bugs

| # | Status | Issue | Detail |
|---|--------|-------|--------|
| B-B1 | ✅ Fixed | `lat`/`lon` not in SSE metadata | Added to `build_metadata()` in `api_server.py` |
| B-B2 | 🔴 Open | Rightmove crawled with postcodes → location miss rate high | Re-crawl `crawl_london.py` using area names |

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
| B-F3 | Claude | 🔴 Open | **Red flag detection** | Scan description for: no DSS, admin fees, no deposit protection | 3 |
| B-F4 | Claude | 🔴 Open | **Draft viewing request** | `POST /api/contact/draft`, LLM + listing context | 3 |
| B-F5 | Claude | 🔴 Open | **Commute time** | TfL API: listing lat/lon + workplace → journey time | 2 |
| B-F6 | Claude | 🔴 Open | **Contract analysis** | `POST /api/contract/analyse`, PDF → plain-English summary + clause flags | 5 |
| B-F7 | Claude | 🔴 Open | **Tenant rights RAG** | Index GOV.UK + Shelter + Renters Reform Act | 6 |

---

## API Contract

### SSE Metadata — Listing Object

```typescript
{
  title: string
  url: string
  image_url: string        // cover photo
  image_urls: string[]     // full gallery up to 10 × 656x437 JPEG
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
| 2 · Research | 🔴 Planned | Commute (TfL), crime (police.uk), avg rent, flood risk, EPC |
| 3 · Contact | 🔴 Planned | Red flag detection, draft viewing email, holding deposit warnings |
| 4 · View | 🔴 Planned | Legal checklist, inspection checklist, agent question generator |
| 5 · Sign | 🔴 Planned | Contract PDF analysis, clause flagging, deposit protection explainer |
| 6 · Rights | 🔴 Planned | RAG over UK tenant law: repairs, eviction, rent increases |
