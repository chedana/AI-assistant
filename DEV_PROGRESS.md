# Development Progress — AI Rental Assistant

> **Keeping this file current:** After each commit, append a row to the relevant phase table and update [Current State](#current-state). The default commit target is the `restructure` branch (worktree at `.claude/worktrees/gracious-clarke`).

---

## Project Overview

A **renter-advocate platform** — the whole property market is structured to favour agents and landlords (portals are funded by them, UX nudges users to sign up for things they don't need). This product is explicitly on the renter's side, guiding them through the entire rental journey end-to-end.

**Stack:** Python · FastAPI · LangGraph · OpenAI API (GPT-5 Mini) · React + Vite + TypeScript + TailwindCSS · Qdrant Cloud · fastembed (ONNX)

---

## Product Vision — The Full Renter Journey

```
[FIND] → [RESEARCH] → [CONTACT] → [VIEW] → [SIGN] → [RIGHTS]
   1          2            3          4        5          6
```

### Section 1 · FIND _(in progress)_
Surface the right listings before the user knows exactly what they want. Conversational search across multiple portals.

| Item | Status | Notes |
|------|--------|-------|
| Rightmove scraper | ✅ done | Bug: postcode typeahead resolves wrong — must use area names |
| Qdrant Cloud vector search | ✅ done | 9,794 listings (initial); needs refresh with area-name crawl |
| Conversational search + constraints | ✅ done | GPT-5 Mini, LangGraph orchestration |
| OpenRent scraper | ✅ done | `crawler/openrent/` — plain HTTP, 6,539 London listings, full field parity with Rightmove |
| OpenRent merge pipeline | ✅ done | `merge_listings.py` — merges Rightmove+OpenRent; 1,409 enriched, 5,427 OR-only; 31,820 pts in Qdrant |
| Zoopla integration | ❌ future | Broader coverage |
| SpareRoom integration | ❌ future | Rooms / HMO market |
| Geo-radius fallback | ❌ deferred | When location miss → lat/lon radius in Qdrant |
| Multi-source dedup | ❌ future | Same property on 2+ portals → merge |

### Section 2 · RESEARCH _(planned)_
"Is this area right for me?" — neighbourhood intelligence from public APIs.

| Feature | Data source |
|---------|-------------|
| Commute time | TfL Unified API (free, no key) |
| Crime index | data.police.uk API (free) |
| Average rent for area | Our own Qdrant aggregates |
| Schools nearby | Ofsted API |
| Broadband speed | Ofcom postcode checker |
| Flood risk | Environment Agency API |
| Council tax band | Local council open data |
| EPC rating | gov.uk EPC register |

### Section 3 · CONTACT _(planned)_
Help the user send a good first message and not get scammed.

| Feature | Approach |
|---------|----------|
| Draft viewing request email | LLM with listing context |
| Red flag detection | Rule engine on listing text: no DSS, "admin fees", holding deposit required upfront |
| Agent response analyser | Paste reply → flag evasive answers, pressure tactics |
| Holding deposit warnings | Max 1 week rent, refundable if landlord withdraws |

### Section 4 · VIEW _(planned)_
User walks in knowing exactly what to check and ask.

| Feature | Approach |
|---------|----------|
| Legal requirements checklist | Gas cert, EPC, electrical safety, smoke/CO detectors, deposit protection |
| Physical inspection checklist | Damp, boiler age, water pressure, broadband, natural light, storage |
| Questions to ask agent | Generated from listing data gaps |
| In-app notes + photo tags | Per-viewing, linked to listing |
| Post-viewing comparison | Side-by-side across your viewing notes |

### Section 5 · SIGN _(planned — biggest differentiator)_
Renter understands every clause before signing.

| Feature | Approach |
|---------|----------|
| Plain-English summary | LLM reads uploaded tenancy agreement |
| Clause flagging | Non-standard break clauses, excessive landlord access rights, unusual cleaning obligations |
| Legal compliance check | Deposit ≤ 5 weeks? No prohibited fees (Tenant Fees Act 2019)? |
| Deposit protection explainer | Which scheme, how to reclaim |
| Inventory importance | Explain what to check and why it matters |

### Section 6 · RIGHTS _(planned)_
Ongoing tenancy — user knows what they're entitled to.

| Topic | Coverage |
|-------|---------|
| Repairs | Section 11 obligations, 24hr emergency vs reasonable timeframe |
| Deposit disputes | TDS / MyDeposits / DPS adjudication, how to evidence |
| Rent increases | Section 13 procedure, how to challenge at tribunal |
| Eviction | Section 21 abolition (Renters Reform Act 2025), Section 8 grounds |
| Harassment | What counts, how to report |

Implementation: RAG skill over indexed UK tenant law docs (GOV.UK, Shelter guides, Renters Reform Act text).

---

### Build Priority Order

```
1. Fix crawler (area names not postcodes) — unblocks real data
2. OpenRent scraper              — private landlords, major differentiator
3. Red flag detection (Sec 3)   — quick win, reuses existing LLM + listing data
4. Viewing checklist (Sec 4)    — high user value, no new data needed
5. Contract analysis (Sec 5)    — biggest differentiator, LLM-heavy
6. Area research (Sec 2)        — external API integrations
7. Tenant rights RAG (Sec 6)    — legal corpus indexing
```

---

## Branches

| Branch | Role | Tip commit |
|--------|------|-----------|
| `openclaw` | **OpenClaw fork — local-first, OpenAI API + Qdrant Cloud** | (see Phase 18) |
| `restructure` | Previous active dev branch | `f1597ae` 2026-03-01 |
| `feature/rental` | Previous dev branch (behind restructure) | `b12fe96` 2026-02-25 |
| `main` | Stable baseline | `7355f5d` 2026-02-24 |
| `codex/initial-modular-structure` | Archived Codex bootstrap | — |

---

## Current State

_Last updated: 2026-03-11 · Branch: `openclaw` · Tip: see Phase 21_

```
User Input
  → [domain_router_node]     rental vs general conversation
  → [route_node]             intent: Search / AcceptSuggestion / Explain / QA / Page_Nav / DirectReply / Fallback
  → [apply_suggestion_node]  (AcceptSuggestion path) apply pending constraint relaxation
  → [search_node]            Qdrant retrieval + constraint extraction
  → [evaluate_node]          detect empty/sparse results; build pending_suggestion + proactive insight
  → [relax_node]             if sparse: relax bottleneck constraint, loop back to search
  → [skill node]             qa_plan → qa_execute | paginate | direct_reply | fallback
  → [finalize_node]          assemble reply text
  → SSE stream               FastAPI → React frontend
```

### Package layout (restructure)

```
orchestration/          # merged agent/ + agent_graph/ — graph wiring + all nodes
  graph.py              # StateGraph definition with domain_router + rental sub-pipeline
  nodes.py              # all LangGraph node implementations
  evaluate_node.py      # run search + detect empty/sparse result set
  relax_node.py         # constraint relaxation loop
  domain_router.py      # top-level rental vs general classifier
  router.py             # rental intent classifier (search/qa/page_nav/…)
  state.py              # GraphState TypedDict
  merger.py             # constraint merging (patch | replace_all)
  workflow.py           # legacy non-LangGraph fallback

skills/search/          # 19 focused modules (refactored from 2 monolithic files)
  engine.py             # Qdrant vector retrieval (Stage A)
  hard_filter.py        # budget/beds/baths/furnishing/let_type filters (Stage B)
  soft_rank.py          # deposit/freshness/semantic reranking (Stage C)
  signals.py            # penalty signal definitions
  formatter.py          # grounded explanation builder (Stage D)
  extractors.py         # rule engine entry point (delegates to sub-modules)
  constraint_extraction.py  # ~840 lines of extraction rules
  constraint_ops.py     # ~380 lines of constraint merge/validate ops
  location_match.py     # ~590 lines of UK location matching
  text_utils.py         # shared text helpers
  evidence.py           # evidence/grounding helpers
  structured_policy.py  # RULE_FIRST | HYBRID | LLM_FIRST dispatch
  pipeline.py           # end-to-end search pipeline orchestration
  pipeline_service.py   # service wrapper
  state_ops.py          # AgentState read/write helpers
  agentic.py            # agentic search (multi-step)
  handler.py            # legacy thin wrapper (delegates to split modules)

skills/qa/              # Q&A skill (plan + execute)
skills/common/          # shared utilities

core/
  llm_client.py         # dual OpenAI-compat clients (qwen_client, router_client)
  chatbot_config.py     # all system prompts
  settings.py           # 20+ env-driven config values
  database.py           # Qdrant connection
  logger.py

backend/
  api_server.py         # FastAPI SSE endpoint /api/chat

frontend/src/
  App.tsx               # thin layout shell (~50 lines), delegates to hooks + components
  components/
    Sidebar.tsx         # session list + new/delete
    ChatArea.tsx        # messages + listing cards + constraint tags + quick replies
    MessageBubble.tsx   # single message (role label + content or thinking indicator)
    MessageContent.tsx  # user=plain text + URL detection, assistant=markdown rendering
    ChatInput.tsx       # textarea + send/stop buttons
    ThinkingIndicator.tsx  # CSS-only 3-dot pulse animation
    ListingCard.tsx     # structured listing: title, price, bed/bath, address, preference hits (green), penalties (amber), bookmark button
    CompareTable.tsx    # side-by-side comparison table with best-value highlighting
    ConstraintTags.tsx  # sticky filter bar; click × sends explicit clear_fields route_hint (no text parsing)
    QuickReplies.tsx    # contextual buttons (Show more / Lower budget / Compare) → silent actions with assistant acknowledgment
  hooks/
    useSessions.ts      # session CRUD + localStorage sync
    useChat.ts          # sendMessage / stopGenerating / streaming + metadata state
  lib/
    mockStream.ts       # SSE client — parses delta, metadata, error, done events
    markdown.ts         # hand-written MD→HTML (bold, italic, headers, lists, tables, links); zero deps
    storage.ts          # localStorage helpers
  types/
    chat.ts             # Message, ChatSession, ListingData, SearchResultsMeta, ConstraintsMeta, QuickReply, CompareData, ShortlistMeta, SessionMetadata
```

### What's working
- 4-stage search pipeline (retrieval → hard filter → soft rank → grounded explanation)
- Constraint extraction — rule-first engine covering budget, bedrooms, bathrooms, furnishing, let_type, tenancy, location (UK)
- Evaluate + relax loop — detects bottleneck constraint, relaxes it, reports sensitivity to user
- **AcceptSuggestion intent** — when assistant suggests a constraint relaxation, user can say "yes" and the graph applies it and re-runs search automatically (`apply_suggestion_node` → `search`)
- **Explain intent** — user can ask to explain any listing; routes to Stage D grounded explanation on demand
- **Proactive insight** — after every successful search, `evaluate_node` appends an insight (e.g. "raise budget £200 to unlock 12 more listings")
- **Budget headroom signal** — Stage C soft ranking rewards listings that cost well under the stated budget
- **Compare intent** — structured side-by-side listing comparison (markdown table + LLM verdict)
- **AreaCompare intent** — compare rental prices across multiple areas ("Is Hackney cheaper than Peckham?"); per-area Qdrant search + count/min/median/max stats table + LLM verdict; layout optional (note shown when absent)
- **Shortlist/Save intent** — users can save, remove, show, and clear listings by text command; deduplicates by listing_id/url; `metadata.shortlist` (count + saved_ids) sent in every SSE event for frontend card state
- Pagination — page up/down through full result set
- QA skill — answers questions about listed properties
- Domain router — separates Rental from General conversation paths
- Near-miss listings — shown in `ask_user` replies when strict search returns 0; display shows title + reason with actual listing value
- **CompareTable UI** — structured side-by-side comparison table rendered from `metadata.compare_data`; best-value green highlighting, clickable listing links, sticky field column; mutually exclusive with listing cards
- **Shortlist UI** — bookmark icon on each listing card (filled/outline driven by `metadata.shortlist.saved_ids`); click injects "save listing N" as chat message; "Saved (N)" badge in header toggles ShortlistPanel right drawer; drawer shows saved cards with per-item remove button; auto-closes when empty
- **Message suppression** — assistant text bubble for a search turn is hidden once listing cards are shown (tracked via `metadataForId`); `metadataForId` only advances when search results actually change (URL signature), so save/remove actions don't expose the original search text; cards persist across subsequent messages; metadata resets only on session switch
- **No text flash** — while an assistant message is actively streaming (`activeAssistantId`), `MessageBubble` shows ThinkingIndicator instead of partial text; after generation, the message is either hidden by cards or shown in full — no flash either way
- **Silent shortlist actions** — save/remove are `sendSilentAction` calls: backend is updated, metadata (shortlist count/saved_ids/listings) refreshes, but no user or assistant message is added to the chat
- **Bookmark toggles in sidebar** — filled bookmark in `ShortlistPanel` calls `onRemove`; `ListingCard` accepts both `onSave` and `onRemove`; hover turns red when saved to signal destructive action
- **Explicit button actions** — all quick-reply and constraint-removal buttons are fully explicit: no LLM extraction, no user message, no regex parsing. `route_hint` carries `set_constraints` or `clear_fields` directly; `search_node` skips `build_refinement_plan()` when these are present. `sendSilentAction` accepts `actionLabel` → brief assistant acknowledgment appears immediately ("Lowering budget to £1,280/month…", "Removing budget filter…", etc.)
- Frontend Phase 1 — component split (10 components, 2 hooks), hand-written markdown renderer, listing cards with preference/penalty tags, sticky constraint filter bar with ×-to-remove, quick-reply buttons, CSS thinking animation, backend metadata SSE event (search_results + constraints + quick_replies + compare_data + shortlist)
- SSE streaming — backend → frontend with stop-generation button
- Session persistence — localStorage + server-side TTL

### Not yet done
- General domain skill (`general_node`) is wired but responses are minimal
- No automated test runner — tests are JSON datasets validated manually
- UI Phase 2 (map view) ✅ done — see Phase 21
- `feature/rental` not yet merged up to `restructure`
- P2-B: location expansion when `prefilter_count == 0` (deferred — requires lat/lon data)
- Cross-session memory (preferences survive server restart)

---

## Session Progress

> Append a line here after every commit. Tasks live in `TODO.md` — not here.

---

### Phase 21 · Map view, data backfill, listing card improvements (Mar 11)
> Branch: `openclaw` | Commits: `39544ce` → `(current)`

| Hash | Date | Type | Description |
|------|------|------|-------------|
| `39544ce` | 2026-03-11 | feat | Dynamic map search radius + smart geo scroll cap |
| `647c567` | 2026-03-11 | feat | Map geo search exact bounds, image carousel, listing features/description |
| `db41d58` | 2026-03-11 | docs | Update PROJECT.md — Phase 21 tasks marked done |
| `4aefaac` | 2026-03-11 | docs | Add agent ownership boundaries to PROJECT.md |
| `8149ab0` | 2026-03-11 | docs | Mark B-F1 listing detail endpoint as not needed |
| `1f3795b` | 2026-03-11 | fix | Strip `- ` prefix from features; exclude parking/non-residential listings |
| `5a653be` | 2026-03-11 | fix | Optimistic save/unsave UX — instant green toggle, header count, no flash |
| `76213da` | 2026-03-11 | feat | OpenRent scraper — extract_openrent.py + crawl_openrent.py |
| `20e9fbc` | 2026-03-11 | feat | OpenRent merge pipeline + new amenity fields; sync 31,820 pts to Qdrant Cloud |

**Key deliverables this phase:**

- **Qdrant data recovery + cleanup**: Recovered 26,394 listings from local Qdrant after accidental sync deletion. Image backfill completed (23,418 updated). 2,005 dead listings (404/410) removed → **24,389 clean listings**.
- **Map "Search this area"**: Now sends exact viewport bounds (min/max lat/lng, 10% inward shrink). Backend uses bounds directly; skips haversine. `GEO_SCROLL_MAX=15000`.
- **Image carousel** (`ListingCard.tsx`, `ListingDetailDrawer.tsx`): `ImageCarousel` sub-component with arrows, dots, 1/N counter.
- **Features on cards/drawer**: `_features_list()` handles all storage formats (JSON, list, `\n`/`;` strings). Strips `- `, `–`, `•` markers. Filters "ask agent"/"n/a"/"none".
- **Parking excluded**: `apply_hard_filters_with_audit` skips property_type = parking/garage/land/commercial.
- **Agent boundaries**: `PROJECT.md` updated with ownership table — Gemini=frontend only, Claude=backend only. "Do not start autonomously" warning added.
- **Optimistic shortlist UX** (`ListingCard.tsx`, `ListingsPanel.tsx`, `App.tsx`, `useChat.ts`): Save/unsave button turns solid green instantly on click (optimistic local state in `ListingCard`). "Saved Listings (N)" header count updates immediately via optimistic `Set` in `App.tsx` (cleared when server metadata confirms). "Updating" indicator and action button flash suppressed for silent actions — `isSilentAction` flag added to `useChat`, "Updating" dot hidden when true, quick-reply buttons stay rendered (disabled) instead of unmounting.
- **OpenRent scraper** (`crawler/openrent/extract_openrent.py`, `crawler/openrent/crawl_openrent.py`): Full scraper for OpenRent (private landlords, no agent fees). Extracts all standard fields: postcode from `postCode=` URL param, bedrooms/bathrooms from `<ul>` after `<h1>`, features from `Property Details` heading → `<ul>`, stations from `Features` section (`~N min. walk` pattern), lat/lon from `data-lat`/`data-lng` on map widget, images from `imagescdn.openrent.co.uk`. Outputs identical JSONL schema to Rightmove scraper (same `ListingRecord` dataclass). `listing_id = "openrent:{id}"` prevents UUID collision. Parallel HTTP scraping (no Playwright needed). Tested on 5 listings — all fields correct. Run: `python -m crawler.openrent.crawl_openrent` then `sync_qdrant.py --mode sync`.

---

### openclaw — OpenClaw fork setup (2026-03-07)

**Branch:** `openclaw` (forked from `restructure`)
**Python venv:** `/Users/derek/Desktop/LLM_project/openclaw-venv` (Python 3.11)
**Run commands:**
```bash
# Terminal 1 — backend
export $(grep -v '^#' .env | grep -v '^$' | xargs)
/Users/derek/Desktop/LLM_project/openclaw-venv/bin/uvicorn backend.api_server:app --host 0.0.0.0 --port 8000

# Terminal 2 — frontend
cd frontend && npm run dev -- --host 0.0.0.0 --port 5173
```

**What was done:**
- Created `openclaw` branch from `restructure`
- Switched LLM from vLLM/Qwen3-14B (RunPod) → OpenAI API with GPT-5 Mini for both reasoning and routing clients
- Fixed GPT-5 Mini temperature constraint: model only supports default temperature (1); `qwen_chat()` and `qwen_router_chat()` now skip `temperature` param when using GPT-5-class models (`_is_fixed_temp()` helper)
- Set up Qdrant Cloud cluster "openclaw" (GCP europe-west3): `https://725a9b5a-2732-448b-b094-a06577cfe7bd.europe-west3-0.gcp.cloud.qdrant.io`
- `skills/search/engine.py`: dual-mode Qdrant client — uses `RENT_QDRANT_URL` for cloud, falls back to local path
- `core/settings.py`: added `QDRANT_URL` and `QDRANT_API_KEY` from env vars `RENT_QDRANT_URL` / `RENT_QDRANT_API_KEY`
- Migrated 9,794 listings from local Qdrant → Qdrant Cloud (collection `rent_listings`); data covers 35 central London regions (Shoreditch, Mayfair, Paddington, etc.)
- Created `crawler/sync_qdrant.py`: JSONL → Qdrant Cloud ingestion with incremental sync (`--mode full` / `--mode sync`); deterministic UUID5 point IDs from `listing_id`; builds `location_tokens`, `location_station_tokens`, `location_region_tokens`, `location_postcode_tokens`
- Created `crawler/run_sync.sh`: one-command wrapper (crawl + sync)
- Created `requirements-deploy.txt`: CPU-only deps for Render free tier (512MB RAM)
- Created `frontend/vercel.json`: Vercel SPA config with catch-all rewrite
- Created `render.yaml`: Render blueprint with build/start commands and all env var placeholders
- Updated `backend/api_server.py`: defaults to OpenAI API, TTLCache reduced 500→50 for Render RAM
- Updated `run.sh`: defaults to `gpt-5-mini`, added `OPENAI_API_KEY` required check, skips model availability check for `api.openai.com`
- Removed `vllm==0.15.1` from `requirements.txt`
- Added `.env` to `.gitignore` (contains API keys — never commit)
- Updated `CLAUDE.md`: stack, commands (3→2 terminals), config table

**Current working state:**
- Backend starts cleanly: Qdrant Cloud connects (9,794 points), MiniLM embedding model loads, GPT-5 Mini responds
- Chat works: "hi" → chitchat reply; "2 bed in Shoreditch under £3000" → 51 listings, 5 shown with SSE cards + quick replies
- Frontend at `http://localhost:5173` connects to backend at `http://localhost:8000`
- `.env` holds `OPENAI_API_KEY`, `RENT_QDRANT_URL`, `RENT_QDRANT_API_KEY` (do not commit)

**Known limitations of current dataset:**
- Only 35 central London regions scraped (Shoreditch, Mayfair, Vauxhall, Paddington, etc.)
- Outer London (Hackney, Peckham, etc.) returns 0 results — needs crawler run to expand
- Run `crawler/run_sync.sh` twice per week to refresh data

**Next session priorities:**
- Deploy frontend to Vercel (connect repo, set root to `frontend/`)
- Deploy backend to Render (use `render.yaml` blueprint, set env vars in dashboard)
- Run Rightmove crawler to expand dataset beyond central London
- Test full Vercel → Render → Qdrant Cloud production flow

---

### backend-1 — Orchestration & Search Pipeline

- `6ce8ef9` fix: deposit QA returns actual deposit value (0/amount/ask-agent) for single + multi listing — removed `__ASKED__` fail path
- `06ff89f` refactor: QA pipeline — hybrid BM25+embedding retrieval, LLM reasons over evidence; fix B3 classify_qa_scope fallback
- `a61d471` refactor: rename EXTRACT_ALL_SYSTEM → SEARCH_EXTRACT_ALL_SYSTEM; fix QA_EXTRACT_ALL_SYSTEM (drop pipeline fields, fix transit terms, add 8 examples)
- `afde2b4` fix: QA answering prompts — natural language output, multi-topic coverage, 3 examples per prompt
- `191e0f1` fix: replace /focus N CLI references with natural language chat instructions (B4)
- `5f1ddb8` fix: out-of-range index messages — clear range, recovery hint, paginate suggestion (B5)
- `f6d68a3` refactor: remove clarify scope from QA — guard upstream, simplify classify_qa_scope (B7)
- `027b39b` chore: remove dead QA files lookup.py and slot_extractor.py (B8 moot)
- `cfad3d9` docs: update CLAUDE.md — progress tracking section + session identity table
- `da9580b` fix: suppress assistant text bubble when listing cards are shown
- `dae333e` fix: cards persist during generation; S1 tenancy redesign, S3/S4 null-safe rank
- `7fc86f9` fix: search pipeline S5/S6/S8 — dead signals removed, unified normalize, clause boundary fix

---

### backend-2 — API & Infrastructure

- _(no commits recorded yet)_

---

### frontend — UI

- `627abf9` feat: structured CompareTable UI component for compare intent
- `b0f98d8` feat: shortlist UI — bookmark button on listing cards + header badge
- `5122ce3` feat: shortlist side panel — saved listings in a right drawer
- `6bd7cf3` fix: auto-expanding textarea in ChatInput
- `159fbc1` fix: human-friendly constraint tags with correct remove phrases
- `a607f49` feat: shortlist panel, message suppression, auto-expand input, constraint tag labels
- `aef3e62` docs: update DEV_PROGRESS — Phase 15
- `bbb22ac` fix: silent save/remove, no text flash, bookmark removes from shortlist
- `f1597ae` feat: explicit button actions — set_constraints/clear_fields in route_hint, skip extraction, action labels

---

### test — Testing

- _(no commits recorded yet)_

---

### data — Data & Embeddings

- `257a45e` feat: automated crawl pipeline — purge-days, auto_crawl.sh, launchd setup
- `f03dfc7` feat: OpenClaw Discord integration — trigger file + status JSON + WatchPaths + skill

---

## Changelog

### Phase 21 · Map view, data backfill, listing card improvements (Mar 11)
> Branch: `openclaw` | Commits: `39544ce` → (current)

| Hash | Date | Type | Description |
|------|------|------|-------------|
| `39544ce` | 2026-03-11 | feat | Dynamic map search radius + smart geo scroll cap |
| (current) | 2026-03-11 | feat | Exact viewport bounds for geo search; image carousel; features/description on cards |

**Key deliverables this phase:**

- **Qdrant data recovery**: Accidentally ran `sync_qdrant.py --mode sync` with a partial 1,146-listing file — deleted 25,045 listings. Recovered using local Qdrant at `/artifacts/skills/search/data/data/qdrant_local` (9,794 points) and upserted all to cloud. Net result: **26,394 listings** in Qdrant Cloud after new crawl (E3, SW3, SW4, SW5, SW10, E5, N6, N16, SE5, SW19) + image backfill.

- **Image backfill**: `crawler/backfill_images.py` scraped image URLs for all 25,423 listings missing `image_urls`. Result: 23,418 updated, 2,005 failed (listings removed from Rightmove). Dead listings (404/410) subsequently deleted → **24,389 clean listings** remaining.

- **Dead listing cleanup**: Scrolled all Qdrant points, identified 2,005 with no `image_url` (confirmed 404/410 on Rightmove), deleted them.

- **Map "Search this area" — exact viewport bounds** (`skills/search/engine.py`, `frontend/src/components/MapView.tsx`):
  - Previously sent `center + radius_km` (center-to-corner diagonal) → backend recomputed a square bbox that was ~41% larger than the viewport
  - Now frontend sends `min_lat/max_lat/min_lng/max_lng` (exact Leaflet bounding box), shrunk 10% inward so results feel centred
  - Backend uses exact bounds directly in Qdrant filter; skips haversine circle clipping when exact bounds are present
  - `GEO_SCROLL_MAX=15000` cap prevents huge payloads; haversine also skipped when cap hit or radius >20km

- **Image carousel on ListingCard** (`frontend/src/components/ListingCard.tsx`): new `ImageCarousel` sub-component shows all `image_urls` with left/right arrow buttons, dot indicators (up to 8), and `1/N` counter badge. Falls back to single `image_url` or placeholder.

- **Features + description on cards and drawer** (`backend/api_server.py`, `frontend/src/components/ListingDetailDrawer.tsx`):
  - `_features_list()` replaces `str()` conversion for features — handles JSON arrays, Python lists, and `\n`/`;`-separated strings
  - Filters out placeholder values: "ask agent", "n/a", "none"
  - Card shows features (up to 3) if available; falls back to description summary
  - Drawer: Key Features section (all features) first, then Property Description
  - `features` type changed from `string` to `string[]` in `frontend/src/types/chat.ts`

**Data state after this phase:**
- Qdrant Cloud `rent_listings`: **24,389 listings**, all with `image_url`
- Coverage: 35+ London areas including newly crawled E3/SW3/SW4/SW5/SW10/E5/N6/N16/SE5/SW19
- All listings have lat/lon coordinates for map display

---

### Phase 20 · OpenClaw — UX fixes, local hosting, GPT-5 Mini tuning (Mar 8)
> Branch: `openclaw` | Commits: `569e813` → `efabb11`

| Hash | Date | Type | Description |
|------|------|------|-------------|
| `569e813` | 2026-03-08 | fix | E6 district — use "Plaistow, East London" instead of "East Ham" (typeahead mismatch) |
| `e49641f` | 2026-03-08 | debug | Add per-request `[TIMING]` logs to `api_server.py` for bottleneck identification |
| `876fe9f` | 2026-03-08 | fix | Prevent double-click race condition — `isGeneratingRef` for synchronous guard; disable Show more button while loading; add `remaining` count to metadata |
| `efabb11` | 2026-03-08 | fix | Silent actions stream at full speed (200 chars/0ms) — eliminates 2s lag on pagination/shortlist/budget buttons |
| `7bfbf79` | 2026-03-08 | docs | Add Phase 20 to DEV_PROGRESS + backend-1 tasks to TODO |
| `3f13590` | 2026-03-08 | fix | Suppress `need_clarify` for Search intent in both router paths — GPT-5 Mini was asking clarification instead of searching |
| `257a45e` | 2026-03-08 | feat | Automated crawl pipeline — `--purge-days` flag, `auto_crawl.sh`, launchd `setup_automation.sh` |
| `f03dfc7` | 2026-03-08 | feat | OpenClaw Discord integration — trigger/status files, WatchPaths, crawl skill |

**Key deliverables this phase:**

- **Render confirmed too slow**: `[TIMING]` logs showed Render free tier (0.1 vCPU) takes 29–35s per search (router + extraction + Stage D × 5). Same code runs in ~5s locally. Decision: **local Mac hosting** for now (Mac is always-on).

- **Double-click race condition** (`frontend/src/hooks/useChat.ts`): React state `isGenerating` doesn't update synchronously — rapid button clicks could fire multiple simultaneous requests. Added `isGeneratingRef = useRef(false)` as a synchronous guard checked by both `sendMessage` and `sendSilentAction`. Also `disabled={isGenerating}` on the "Show more" button.

- **Silent action streaming delay** (`backend/api_server.py`): Button actions (Show more, Lower budget, Compare) sent text via `sendSilentAction` which discards all chunks — but backend still streamed at 8 chars/10ms (= ~2s latency for 1000+ char replies). Now: requests with `route_hint` stream at 200 chars/chunk with 0ms delay.

- **Card rendering position for silent actions** (`frontend/src/hooks/useChat.ts`): `sendSilentAction` now creates an ack message (e.g. "Lowering budget to £2,800/month…") and moves `metadataForId` to the ack message position when new metadata arrives. Previously cards stayed at the original search message position (scrolled off screen) while ack text appeared below.

- **`remaining` count in metadata** (`backend/api_server.py`, `frontend/src/types/chat.ts`): "Show more results" button now shows actual remaining count (e.g. "Show more results (42 remaining)") computed from `total - shown_so_far`.

- **Crawler re-crawl in progress**: Background crawl running all 182 London area queries (264 districts → 182 unique area names). At time of session end: 10/182 queries done, 682 URLs collected. After completion, run `bash crawler/run_sync.sh sync` to push to Qdrant Cloud.

**Known issues discovered (not yet fixed):**

- **Stale Qdrant data**: Current Qdrant Cloud has 9,794 listings from old crawl — some with corrupted descriptions ("JavaScript is disabled" noscript text), wrong locations (Manchester listings from postcode mismatch), and incorrect prices. Will be replaced once the current re-crawl completes.

---

### Phase 19 · OpenClaw — cloud deployment fixes + lat/lon extraction (Mar 7)
> Branch: `openclaw` | Commits: `635deeb` → `8b323ae`

| Hash | Date | Type | Description |
|------|------|------|-------------|
| `635deeb` | 2026-03-07 | fix | Downgrade react-leaflet v5→v4 (React 18 compat); exclude duplicate `* 2.*` files from tsconfig |
| `002fae0` | 2026-03-07 | fix | run_sync.sh uses venv python; add QWEN_MODEL/ROUTER_MODEL to render.yaml |
| `78d1c5b` | 2026-03-07 | fix | Lazy-load search runtime to avoid OOM on Render 512MB free tier |
| `9399ca1` | 2026-03-07 | fix | Replace PyTorch/sentence-transformers with fastembed (ONNX) — eliminates ~200MB from Render deploy |
| `3260634` | 2026-03-07 | fix | Build location vocab from Qdrant Cloud (scroll) when `RENT_QDRANT_URL` is set |
| `7ff1fa0` | 2026-03-07 | feat | Extract latitude/longitude from Rightmove page JSON; include in JSONL + Qdrant payload |
| `8f7daa6` | 2026-03-07 | fix | fastembed fallback in handler.py, soft_rank.py, internal_helpers.py — no sentence_transformers on Render |
| `8b323ae` | 2026-03-07 | fix | Crawler location resolver: DISTRICT_TO_SEARCH_NAME map (264 districts → area names); postcode codes resolved to wrong STATION^ identifiers |

**Key deliverables this phase:**

- **Frontend on Vercel**: deployed to `https://frontend-delta-red-23.vercel.app`. `VITE_API_BASE=https://openclaw-backend.onrender.com` set on Vercel. `vercel.json` SPA catch-all rewrite. Required: fix react-leaflet v5→v4 (React 18 compat) and tsconfig exclude for stale `* 2.*` duplicate files.

- **Backend on Render** (`render.yaml`, `requirements-deploy.txt`): Replaced CPU PyTorch + sentence-transformers with **fastembed** (ONNX runtime, no PyTorch). Peak RAM drops ~200MB. Added lazy singleton `get_runtime()` so Render can bind port before model loads. Both fixes needed to stay within Render free tier 512MB limit. Note: Render service currently **suspended** — needs manual resume from dashboard.

- **Location vocab on Qdrant Cloud** (`skills/search/location_match.py`): `_build_location_match_index()` now scrolls Qdrant Cloud (when `RENT_QDRANT_URL` is set) to populate station/region vocab instead of reading local SQLite. Fixes region/station name matching for cloud deployments.

- **Lat/lon extraction** (`crawler/extract_one_page.py`, `crawler/sync_qdrant.py`): `extract_lat_lon()` reads latitude/longitude from Rightmove's embedded JSON. Added `latitude`/`longitude` fields to `ListingRecord` dataclass and `PAYLOAD_FIELDS` in sync_qdrant. Tested on single listing — confirmed correct values extracted (e.g. 53.41, -2.21). Future use: geo-radius search when `prefilter_count == 0` (see deferred task in TODO.md).

- **Crawler running**: background crawler (PID 86871) scraping 15 core London districts (E8, E9, N1, N16, SE1, SE5, SE15, SW2, SW4, SW9, W1, W2, NW1, NW3, NW6) — in progress at time of writing. After it finishes, run `bash crawler/run_sync.sh sync` to push new listings to Qdrant Cloud.

- **fastembed fallback** (`handler.py`, `soft_rank.py`, `internal_helpers.py`): All three files that imported `sentence_transformers` now try fastembed first and fall back gracefully. `_embed_texts_cached()` uses `.embed()` (fastembed) or `.encode()` (sentence-transformers) based on `hasattr(embedder, "embed")`. Required for Render deployment where `sentence_transformers`/PyTorch are not installed.

- **Crawler location fix** (`crawler/london_postcodes.py`, `crawler/artifacts/postcode_location_cache.json`): Added `DISTRICT_TO_SEARCH_NAME` dict mapping all 264 London postcode districts to Rightmove typeahead-friendly area names (e.g. `E8 → "Hackney, London"`). Previous crawl produced 752 listings all from Manchester (East Didsbury Station) because Rightmove's tokenizer matched `"E8"` to `STATION^3062`. Rewrote `get_search_queries()` to use area names with deduplication (182 unique queries from 264 districts). Cleared stale cache.

---

### Phase 18 · OpenClaw fork — local OpenAI API + Qdrant Cloud deployment setup (Mar 7)
> Branch: `openclaw` | No new commits (all changes uncommitted, working in branch)

**Key deliverables this phase:**

- **Branch**: `openclaw` forked from `restructure`. All OpenClaw-specific work stays here; `restructure` preserved as-is.

- **LLM switch** (`core/chatbot_config.py`, `core/llm_client.py`, `backend/api_server.py`, `run.sh`): vLLM/Qwen3-14B on RunPod replaced entirely by OpenAI API. Default model for both `qwen_client` (reasoning) and `router_client` (intent classification) is now `gpt-5-mini`. `_is_fixed_temp()` helper skips the `temperature` parameter for GPT-5-class models that only support the default (temperature=1).

- **Qdrant Cloud** (`core/settings.py`, `skills/search/engine.py`): `load_qdrant_client()` now reads `RENT_QDRANT_URL` — if set, connects to Qdrant Cloud; otherwise falls back to local path. Cloud cluster "openclaw" on GCP europe-west3 created and populated with 9,794 listings migrated from local storage.

- **Data sync pipeline** (`crawler/sync_qdrant.py`, `crawler/run_sync.sh`): new JSONL→Qdrant ingestion script with full and incremental sync modes. Deterministic UUID5 point IDs allow safe re-runs. Builds all location token types (`location_tokens`, `location_station_tokens`, `location_region_tokens`, `location_postcode_tokens`). Designed to be run twice per week from the OpenClaw bot machine.

- **Deployment configs** (`requirements-deploy.txt`, `frontend/vercel.json`, `render.yaml`): Render blueprint + Vercel SPA config ready to wire up. CPU-only PyTorch in deploy requirements to fit Render 512MB RAM free tier.

- **Python 3.11 venv** at `/Users/derek/Desktop/LLM_project/openclaw-venv`: all backend deps installed and tested (codebase uses `dict | None` union syntax requiring Python 3.10+; old LLM_chatbot venv was 3.9).

- **Secrets management**: `.env` added to `.gitignore`. Credentials (OpenAI key, Qdrant URL + API key) stored only in `.env`, never committed.

---

### Phase 17 · Explicit button actions — bypass LLM extraction, assistant acknowledgments (Mar 1)
> Branch: `restructure` | 1 commit

| Hash | Date | Type | Description |
|------|------|------|-------------|
| `f1597ae` | 2026-03-01 | feat | Explicit button actions: set_constraints/clear_fields in route_hint, skip extraction, action labels |

**Key deliverables this phase:**
- **Three action types formalised** — button actions are classified as: (1) new search/compare (needs backend data), (2) show more (backend already has data), (3) shortlist save/remove (no LLM). None go through LLM query extraction.
- **Explicit constraint params in route_hint** (`state.py`, `nodes.py`, `api_server.py`): `route_hint` now supports `set_constraints: {field: value}` and `clear_fields: [field, ...]`. `route_node` extracts them into `GraphState.explicit_set_constraints` / `explicit_clear_fields`. `search_node` checks for these first — if present, skips `build_refinement_plan()` entirely and calls `derive_snapshot()` with the explicit params. "Lower budget" quick reply carries `set_constraints: {max_rent_pcm: <80% of current>}`.
- **Constraint tag removal via explicit params** (`ConstraintTags.tsx`, `ChatArea.tsx`, `App.tsx`): `ConstraintTags` now stores `clearFields` (backend field names) and `actionLabel` per constraint key. `onRemove` passes these directly; `App.tsx` builds `route_hint: {intent: Search, clear_fields: [...]}`. No regex matching needed — the correct field is always cleared.
- **Assistant acknowledgment for all button actions** (`useChat.ts`, `App.tsx`): `sendSilentAction` accepts optional `actionLabel`. If set, a brief assistant message is immediately added to the chat before the backend call ("Loading more listings…", "Lowering budget to £1,280/month…", "Comparing listings…", "Removing budget filter…", etc.). No user message is ever shown for button actions.
- **Quick reply fix** (`api_server.py`): "Show more" and "Lower budget" no longer gated on `last_intent != Compare`. "Lower budget" uses specific computed amount (`int(max_rent * 0.8)`). "Compare all" still hides when already in Compare intent.

---

### Phase 16 · Frontend UX fixes — silent actions, no text flash, bookmark remove (Mar 1)
> Branch: `restructure` | 1 commit

| Hash | Date | Type | Description |
|------|------|------|-------------|
| `bbb22ac` | 2026-03-01 | fix | Silent save/remove, no text flash, bookmark removes from shortlist |

**Key fixes this phase:**
- **No text flash on search** (`MessageBubble.tsx`, `useChat.ts`): While a message is actively streaming, `MessageBubble` shows `ThinkingIndicator` instead of partial text (`isActive` prop driven by `activeAssistantId` state). After generation, the message is either hidden by cards (search response) or shown in full (other responses). Zero flash in both cases.
- **Search text no longer reappears after save/remove** (`useChat.ts`): `metadataForId` (the "hide this message" pointer) only advances when the search results URL signature actually changes. Save/remove actions return the same `search_results` in metadata → same signature → hide pointer stays on the original search message.
- **Silent shortlist actions** (`useChat.ts`, `App.tsx`): New `sendSilentAction()` calls the backend and refreshes metadata without adding any user or assistant message to the chat session. Save listing and remove from shortlist are now completely invisible in the conversation.
- **Bookmark click removes from shortlist** (`ListingCard.tsx`, `ShortlistPanel.tsx`): `ListingCard` now accepts `onRemove` prop. In `ShortlistPanel`, the filled bookmark calls `onRemove(idx + 1)`. Bookmark hover turns red when saved to signal it will remove. The separate text "Remove from shortlist" button is removed.

---

### Phase 15 · route_hint optimization + shortlist panel UI (Mar 1)
> Branch: `restructure` | 4 commits

| Hash | Date | Type | Description |
|------|------|------|-------------|
| `159fbc1` | 2026-03-01 | fix | Human-friendly constraint tag labels via FIELD_CONFIG |
| `6bd7cf3` | 2026-03-01 | fix | Auto-expanding textarea in ChatInput |
| `5122ce3` | 2026-03-01 | feat | Shortlist side panel — right-side drawer with saved listing cards |
| `a607f49` | 2026-03-01 | feat | Message suppression (metadataForId), panel toggle, metadata persist fix |
| `aef3e62` | 2026-03-01 | docs | Update DEV_PROGRESS — Phase 15 |

**Key deliverables this phase:**
- **route_hint optimization** (`nodes.py`, `state.py`, `workflow.py`, `api_server.py`, frontend): Quick-reply buttons and listing-action buttons now attach a `route_hint` dict to the request. `domain_router_node` and `route_node` short-circuit immediately when the hint is present — no LLM calls for known intents. Cuts ~2 LLM round-trips per button click.
  - Backend quick replies include hints: `{intent:Page_Nav, page_action:next}`, `{intent:Search}`, `{intent:Compare}`, `{intent:Shortlist, shortlist_action:show}`
  - Frontend `handleSaveListing` / `handleRemoveFromShortlist` send `{intent:Shortlist, shortlist_action:save/remove}`
  - `GraphState.route_hint` field added; `make_graph_state` accepts it as a kwarg
- **Shortlist side panel** (`ShortlistPanel.tsx`): right-side drawer toggled by "Saved (N)" badge in app header; shows saved `ListingCard`s with per-item "Remove" button; auto-closes when shortlist empties
- Shortlist badge moved from Sidebar to app header (always visible, not buried in sidebar); `Sidebar` props simplified (removed `shortlistCount` + `onOpenShortlist`)
- Backend `metadata.shortlist` now includes full `listings` array for the panel to render without a chat round-trip
- Auto-expanding textarea: `ChatInput` grows from 48 px to 160 px as user types
- Human-friendly constraint tag labels: `budget`, `location`, `bedrooms` etc. via `FIELD_CONFIG`; correct NL removal phrases

---

### Phase 14 · Search pipeline fixes — S1/S3–S6/S8 (Mar 1)
> Branch: `restructure` | 2 commits

| Hash | Date | Type | Description |
|------|------|------|-------------|
| `dae333e` | 2026-03-01 | fix | S1/S3/S4 — tenancy filter redesign, rank_stage_c null safety, agentic null guard |
| `7fc86f9` | 2026-03-01 | fix | S5/S6/S8 — remove dead signals, unify normalize, fix clause boundaries |

**Key fixes this phase:**
- **S1 — tenancy filter redesign** (`hard_filter.py`): extracted `_parse_months` from per-row loop to module level; corrected `op` label from `"ge"` to `"lte"` (listing's min tenancy ≤ user's max commitment); renamed check key to `required` (consistent with budget check); rewrote fail message to be human-readable.
- **S3 — null-safe Stage C return** (`soft_rank.py`): `rank_stage_c` now always returns `pd.DataFrame()` instead of `None` when input is empty — consistent type contract for all callers.
- **S4 — null guard in agentic** (`agentic.py`): `len(filtered)` gated behind `filtered is not None` check; `ranked_full` assignment simplified (never None after S3).
- **S5 — dead signal flags removed** (`signals.py`): removed `keyword_fallback_used` dict (always `{...: False}`, never flipped) and three always-empty debug arrays (`keyword_transit_candidates`, `keyword_school_candidates`, `fallback_tokens`) from `semantic_debug`.
- **S6 — unified normalization** (`constraint_ops.py` + callers): `normalize_budget_to_pcm` subsumed into `normalize_constraints` — one entry point handles all constraint normalization. Removed redundant post-merge normalize calls in `pipeline_service.py` and `agentic.py`; removed dead `normalize_budget_to_pcm` field from `ExtractDeps` and its property from `PipelineDeps`.
- **S8 — clause boundary fix** (`constraint_extraction.py`): replaced fragile step-2 loop over `cut_points` (broken when separator start/end coincides with 0 or len(src), producing odd-length list and misaligned pairs) with direct `zip(clause_starts, clause_ends)` over separator match objects.

---

### Phase 13 · QA pipeline rewrite — hybrid retrieval + LLM reasoning (Mar 1)
> Branch: `restructure` | 2 commits

| Hash | Date | Type | Description |
|------|------|------|-------------|
| `06ff89f` | 2026-03-01 | refactor | QA pipeline — hybrid BM25+embedding retrieval, LLM reasons over evidence |
| `6ce8ef9` | 2026-03-01 | fix | Deposit QA returns actual deposit value for single + multi listing |

**Key deliverables this phase:**
- **Deposit QA fix (B1)**: `answer_single_listing_question` and `answer_multi_listing_question` now return the actual deposit value (£0 / £amount / "ask agent") directly. Removed `__ASKED__` sentinel path that was incorrectly failing listings.
- **QA pipeline refactor**: Replaced `structured_lookup` + `semantic_vector_lookup` pre-labelling chain with:
  1. LLM structures question into need categories (`school_terms`, `transit_terms`, `general_semantic_phrases`) via `build_qa_context`
  2. Per-category hybrid retrieval: BM25 (TF-IDF, normalized 0–1) + embedding cosine similarity, combined with `max()` per chunk
  3. Category routing: school → `{schools, description}`, transit → `{stations, description}`, amenity → `{features, description}`
  4. LLM receives raw `listing_fields` + `evidence_by_category` and reasons to produce answer — no pre-labelling
- **B3 fixed**: `classify_qa_scope` fallback now uses `has_focus` / `last_qa_scope` instead of always returning `"clarify"`
- **Removed**: `pandas`, `_pick_decision_label`, `_structured_match_eval`, `_semantic_allowed_fields`, `_has_active_structured_constraints`, `SEMANTIC_HIGH_THRESHOLD`, `SEMANTIC_LOW_THRESHOLD` — 626 lines of pre-labelling code replaced by 266 lines of hybrid retrieval + LLM reasoning

**Architecture note:** `lookup.py` and `slot_extractor.py` remain on disk but are no longer imported by `handler.py`. Structured fast paths for deposit / furnish_type / let_type are preserved.

---

### Phase 12 · Shortlist Compare (Feb 27)
> Branch: `restructure` | 5 commits

| Hash | Date | Type | Description |
|------|------|------|-------------|
| `6d7036e` | 2026-02-27 | fix | Deposit compare formatter handles string values (£1,600, Ask agent) |
| `d34f3be` | 2026-02-27 | fix | NameError use_shortlist → wants_shortlist in compare_node |
| `830258d` | 2026-02-27 | fix | Update empty-shortlist compare message wording |
| `c530102` | 2026-02-27 | fix | Empty shortlist shows correct message immediately (not silent fallthrough) |
| `0fa71e8` | 2026-02-27 | feat | Shortlist compare — "compare my shortlist" uses saved listings |

**Key deliverables this phase:**
- **"compare my shortlist"** / **"compare my saved listings"** → `Compare` intent → `compare_node` uses `agent_state.shortlist` as the source instead of `last_results`
- All saved items are compared (no index selection — shortlist always compares everything)
- Empty shortlist → immediate message: "Your shortlist is empty. You need to have at least two listings to compare."
- Single item → "I need at least 2 listings to compare. Your shortlist only has 1 item."
- Router: 2 new few-shot examples for shortlist-compare queries
- Existing search-result compare behaviour unchanged

**Bug fixes in this phase:**
- `NameError` on `use_shortlist` (renamed to `wants_shortlist` but missed one reference) — crashed every shortlist compare attempt
- Deposit showed "—" in compare table because the field is stored as a string (`"£1,600"`) not a number. Fixed formatter to strip `£`/`,` before parsing; also displays "Ask agent" as-is rather than "—"

**Frontend note:** `AgentState.last_compare_source: Optional[str]` added (`"shortlist"` | `"results"`). Backend `build_metadata()` can use this to emit `compare_data` from `state.shortlist` when it's a shortlist compare, enabling the styled `CompareTable` component. Without this, the markdown table in the text reply renders correctly as-is.

---

### Phase 11 · Bug fixes — table separator row + AreaCompare constraint display (Feb 27)
> Branch: `restructure` | 3 commits

| Hash | Date | Type | Description |
|------|------|------|-------------|
| `7ae665c` | 2026-02-27 | feat | Show active filters line in AreaCompare output |
| `b058c2b` | 2026-02-27 | fix | --- separator row in markdown tables; AreaCompare layout override |

**Key deliverables this phase:**
- **`---` row bug** (`frontend/src/lib/markdown.ts`): separator-skip regex `[\s:-]+` didn't include `|`, so multi-column rows like `| --- | --- | --- |` were rendered as data rows. Fixed by adding `|` to the set → `[\s|:-]+`. Affects both Compare and AreaCompare tables.
- **AreaCompare layout override bug** (`orchestration/nodes.py`): layout extraction from the current user message was gated on `not _has_layout_constraints(base_constraints)`. If a prior search left bedroom constraints in the session (e.g. studios), "for 1b1b" in the current AreaCompare message was silently ignored. Fixed by always extracting from the current turn using `existing_constraints={}`, then merging only `layout_options` if found.
- **AreaCompare filters display** (`orchestration/nodes.py`): added `_describe_base_constraints()` which summarises all active constraints (bedrooms, bathrooms, budget, furnish, let_type, available_from, tenancy, min_size) as a dot-separated string. Every AreaCompare reply now shows a `_Filters: 1-bed · 1-bath · max £2,000/mo_` line directly below the title, or `_Filters: none — all property types..._` when nothing is set. Replaces the previous conditional "Note:" at the bottom.

---

### Phase 10 · Frontend — CompareTable + Shortlist UI (Feb 27)
> Branch: `restructure` | 2 commits

| Hash | Date | Type | Description |
|------|------|------|-------------|
| `b0f98d8` | 2026-02-27 | feat | Shortlist UI — bookmark button on listing cards + clickable "Saved (N)" header badge |
| `627abf9` | 2026-02-27 | feat | Structured CompareTable UI component for compare intent |

**Key deliverables this phase:**
- **CompareTable component** (`CompareTable.tsx`): responsive side-by-side comparison table rendered from `metadata.compare_data`; 8 field rows (price, beds, baths, deposit, available, size, furnished, type); best-value green accent highlighting; clickable listing title links; sticky first column; horizontal scroll on mobile
- Backend: `AgentState.last_intent` field + `build_metadata()` emits `compare_data` when intent is `Compare`; `CompareListingData` / `CompareData` types added to frontend
- Compare table and listing cards are mutually exclusive per turn in `ChatArea`
- **Shortlist UI**: bookmark SVG icon on each `ListingCard` (filled = saved, outline = not); state driven by `metadata.shortlist.saved_ids` set; click injects `"save listing N"` as user chat message (1-based page position)
- **Header badge**: "Saved (N)" pill in app header toggles `ShortlistPanel` open/closed; hidden when count is 0
- `ShortlistMeta` type added to `SessionMetadata`

---

### Phase 9 · Shortlist/Save intent (Feb 27)
> Branch: `restructure` | 1 commit

| Hash | Date | Type | Description |
|------|------|------|-------------|
| `a1ea309` | 2026-02-27 | feat | Shortlist/Save intent — save, show, remove, clear listings by text command |

**Key deliverables this phase:**
- New `Shortlist` intent with `shortlist_action: str` (`add` / `remove` / `show` / `clear`)
- `AgentState.shortlist: List[Dict]` — cross-turn list of saved listing dicts; deduplicates by `listing_id` / `url`
- `shortlist_node` — handles all four actions:
  - `add`: saves by 1-based page position(s) from `last_results` (e.g. "save listing 2"); multiple at once OK
  - `remove`: removes by 1-based shortlist position(s) (e.g. "remove shortlist 1 and 3"); reverse-sorted to preserve indices
  - `show`: renders shortlist as a formatted list, or "empty" message with save instructions
  - `clear`: wipes all saved listings with count confirmation
- `metadata.shortlist` always included in SSE event: `{count: N, saved_ids: [...]}` — lets frontend show filled/empty bookmark icon without an extra API call
- `quick_replies` gains "My shortlist" button when shortlist is non-empty
- AreaCompare fix in same session: layout is now optional — comparison always runs, note added when no bedroom filter applied

**Frontend implementation:** Completed in Phase 10 (`627abf9`, `b0f98d8`).

---

### Phase 8 · AreaCompare intent (Feb 27)
> Branch: `restructure` | 1 commit

| Hash | Date | Type | Description |
|------|------|------|-------------|
| `ba2823b` | 2026-02-27 | feat | AreaCompare intent — geographic area price comparison with pending state |

**Key deliverables this phase:**
- New `AreaCompare` intent: "Is Hackney cheaper than Peckham?", "compare rents in zone 2 vs zone 3"
- `RouteDecision.target_areas: List[str]` extracted from LLM router; `GraphState.target_areas` stored per turn
- `area_compare_node`: per-area `run_search_skill(override_constraints={..., location_keywords=[area]})` → aggregate stats (count, min/median/max price) → markdown table + LLM verdict (2-4 sentences referencing specific figures)
- Like-for-like enforced: requires bedroom layout in constraints; if missing → asks broad layout question + stores `AgentState.pending_area_compare = {"areas": [...]}` for multi-turn resolution
- Pending follow-up: router receives `pending_area_compare_areas` context, routes "2 bed furnished" reply as `AreaCompare` (same pattern as `pending_suggestion` / `AcceptSuggestion`)
- Cap at 4 areas; no dependency on existing listings (independent Qdrant search per area)
- Layout extracted from user message on pending turn via `build_refinement_plan`; does not permanently modify `agent_state.constraints`

---

### Phase 7 · Compare intent + routing refactor (Feb 27)
> Branch: `restructure` | 2 commits

| Hash | Date | Type | Description |
|------|------|------|-------------|
| `1f5147b` | 2026-02-27 | refactor | remove `target_index`, unify all listing references on `target_indices: List[int]` |
| `4026e82` | 2026-02-27 | feat | Compare intent — structured side-by-side listing comparison with table + LLM verdict |

**Key deliverables this phase:**
- New `Compare` intent distinguished from `Explain` (holistic) and `Specific_QA` (attribute question)
  - `"compare listing 1 and 3"` / `"listing 2 vs 4"` → `Compare` → `compare_node`
  - `"which is best?"` → `Explain` → Stage D explanation (unchanged)
  - `"do listing 1 and 2 allow pets?"` → `Specific_QA` with `target_indices=[1,2]` → multi-target QA prose
- `compare_node`: Python-built markdown table of key fields (price, beds, deposit, available, size, furnished, type) + LLM 2-4 sentence verdict; operates on specific indices or all k listings if none given
- Router updated: `target_index` (singular) removed; all listing references now use `target_indices: List[int]` — `[N]` for single, `[N,M]` for multi, `[]` for none
- `qa_execute_node` gains multi-target path: filters `last_results` to specified indices before calling `answer_multi_listing_question`
- Frontend already renders markdown tables via existing `markdown-table` CSS class — no frontend changes needed for core feature; styling polish optional

---

### Phase 6 · AcceptSuggestion, Explain intent, proactive insights, Stage C improvements (Feb 26)
> Branch: `restructure` | 8 commits

| Hash | Date | Type | Description |
|------|------|------|-------------|
| `89ba320` | 2026-02-26 | fix | AcceptSuggestion negative few-shot examples; Explain query reframing; deposit ratio fix |
| `9eabdd2` | 2026-02-26 | feat | budget headroom signal in Stage C ranking — rewards listings priced well under budget |
| `9a0ff82` | 2026-02-26 | feat | Explain intent — on-demand Stage D grounded explanation for a specific listing |
| `a685ace` | 2026-02-26 | feat | proactive result insight appended after every successful search |
| `fa97fb8` | 2026-02-26 | fix | near-miss reasons now show actual listing value (e.g. £2,100/mo) |
| `8bdfd08` | 2026-02-26 | fix | simplify near-miss display to title + reason only |
| `439d08f` | 2026-02-26 | fix | show single clearest suggestion in ask_user reply |
| `e8922c8` | 2026-02-26 | feat | AcceptSuggestion intent — user can accept a suggested relaxation; graph applies it and re-runs search |

**Key deliverables this phase:**
- New graph path: `route → apply_suggestion_node → search` for one-click constraint acceptance
- `pending_suggestion` stored in `AgentState` after every evaluate pass (budget first, then highest-impact minor constraint)
- New `Explain` intent wired into graph; router updated with few-shot examples for both new intents
- `evaluate_node` now appends a proactive insight line to every successful search reply
- Stage C `soft_rank.py` gains a budget headroom scoring term (configurable via `settings.py`)

---

### Phase 5 · Restructure — refactor + relax loop + UI + domain router (Feb 25–26)
> Branch: `restructure` | 34 commits

| Hash | Date | Type | Description |
|------|------|------|-------------|
| `b1b33be` | 2026-02-26 | docs | update CLAUDE.md for restructure branch architecture |
| `a6727ee` | 2026-02-26 | fix | filter out unknown_hard() debug penalties from UI cards |
| `3df3e48` | 2026-02-26 | fix | hide 0 bed/bath when data is missing; fix penalty string splitting |
| `8222f4b` | 2026-02-26 | feat | rewire graph with top-level domain router |
| `74a3976` | 2026-02-26 | feat | add domain_router_node, domain_branch, general_node |
| `0f00db3` | 2026-02-26 | fix | coerce numpy types to native Python in metadata serialization |
| `a411578` | 2026-02-26 | feat | add domain field to GraphState |
| `ccad52e` | 2026-02-26 | feat | add domain_router for top-level skill dispatch |
| `fa81686` | 2026-02-26 | feat | add DOMAIN_ROUTER_SYSTEM and GENERAL_SYSTEM prompts |
| `f98ee95` | 2026-02-26 | fix | convert string fields to arrays in metadata SSE event |
| `7c05015` | 2026-02-26 | feat | show near-miss listings in ask_user replies |
| `81b881b` | 2026-02-26 | feat | phase 1 UI overhaul — component split, markdown, metadata cards |
| `f97b558` | 2026-02-26 | fix | persist original_budget in AgentState across turns |
| `375a5f6` | 2026-02-26 | fix | remove flawed warn-suffix logic from formatter |
| `06dff30` | 2026-02-26 | fix | use full_results for relax trigger, not last_results (current page) |
| `9e3aa8c` | 2026-02-26 | debug | show display/strict/k/threshold counts in output |
| `1d2067b` | 2026-02-26 | fix | use confirmed sensitivity for relax decision |
| `9c8c792` | 2026-02-26 | fix | rewrite sensitivity with confirmed values; trigger budget relax when strict < 2*k |
| `4789598` | 2026-02-26 | fix | use regex to detect unknown_hard fields |
| `80a169d` | 2026-02-26 | fix | use search_full_results for hint threshold, not just current page |
| `86eecd5` | 2026-02-26 | fix | fallback to budget relax when layout is the only bottleneck |
| `4e02b78` | 2026-02-25 | fix | show bedrooms-confirmed results even when bathrooms is null |
| `b97ea29` | 2026-02-25 | fix | restore result display — relax only when strict_results=0 |
| `98918c8` | 2026-02-25 | fix | relax triggers on strict_results < k*2, not total results |
| `591f7f9` | 2026-02-25 | test | add page_nav smoke tests; fix missing re import in nodes.py |
| `5fc9fb6` | 2026-02-25 | feat | sensitivity message with specific values + layout suggestions |
| `b6a8a46` | 2026-02-25 | fix | original_budget field missing + budget relax compounding |
| `2e93d89` | 2026-02-25 | feat | evaluate + relax loop — intelligent empty-result handling |
| `5a8230b` | 2026-02-25 | fix | H8 — validate layout_options in derive_snapshot (LangGraph path) |
| `2387523` | 2026-02-25 | fix | prompt cleanup — remove dead code, add grounding + few-shot examples |
| `be03547` | 2026-02-25 | fix | wave 3 state sync — GraphState cleanup, k-field in snapshot |
| `1d4425c` | 2026-02-25 | fix | wave 2 correctness — cache, input validation, session lock, hash precision |
| `6b1cf39` | 2026-02-25 | fix | wave 1 stability — logging, tenancy filter, timeouts, state rollback, session TTL |
| `0b6f94b` | 2026-02-25 | refactor | split monolithic files → focused modules; merge agent packages into orchestration/ |

---

### Phase 4 · QA debug + pagination (Feb 20–25)
> Branch: `feature/rental` | ~20 commits

| Hash | Date | Type | Description |
|------|------|------|-------------|
| `b12fe96` | 2026-02-25 | docs | commit target is restructure branch |
| `36a0453` | 2026-02-25 | docs | add git convention — no Co-Authored-By in commits |
| `36a10e0` | 2026-02-24 | feat | page down/up (pagination) |
| `4893b5e` | 2026-02-24 | feat | page down/up (pagination) — continued |
| `7355f5d` | 2026-02-24 | chore | merge origin/main into feature/rental |
| `df21008`–`0af4581` | 2026-02-24 | debug | qa debug (6 commits) |
| `f48d07f`–`e8c696b` | 2026-02-23 | debug | qa debug (4 commits) |
| `7848606`–`f8396ae` | 2026-02-21 | debug | qa debug (2 commits) |

---

### Phase 3 · Frontend + LangGraph integration (Feb 20)
> Branch: `feature/rental` | ~12 commits

| Hash | Date | Type | Description |
|------|------|------|-------------|
| `98b9e53` | 2026-02-20 | feat | LangGraph graph wired |
| `f0ccfda` | 2026-02-20 | feat | FastAPI backend API |
| `019c08b`–`fa1d996` | 2026-02-20 | feat | React + Vite frontend (7 commits) |
| `451ad90`–`f6fa0bb` | 2026-02-20 | feat | search pipeline (6 commits) |
| `0e812cd`–`bbdba66` | 2026-02-20 | feat | QA skill (4 commits) |

---

### Phase 2 · Core skills — search, QA, router (Feb 17–19)
> Branch: `feature/rental` | ~25 commits

| Hash | Date | Type | Description |
|------|------|------|-------------|
| `908338b` | 2026-02-19 | chore | merge feature/rental q&a into main |
| `6ada77c`–`be443c6` | 2026-02-19 | feat | budget constraint handling |
| `a949dd4`–`f7c1f95` | 2026-02-19 | feat | QA skill (8 commits) |
| `60c73b4`–`9fe8075` | 2026-02-19 | feat | intent router (3 commits) |
| `268721f`–`da94bab` | 2026-02-19 | chore | pull/push scripts |
| `ef75538` | 2026-02-19 | chore | ignore and untrack cache artifacts |
| `28d93aa`–`93bdf5c` | 2026-02-18 | feat | QA skill development (6 commits) |
| `0685230`–`fc7007c` | 2026-02-18 | feat | router development (2 commits) |
| `30cf1f9`–`29c31c9` | 2026-02-18 | debug | debug sessions (5 commits) |
| `5dfb769`–`29c1bae` | 2026-02-17 | feat | location extraction + path reconstruction |
| `1f6ddb2`–`5ad6201` | 2026-02-17 | debug | early debug (2 commits) |

---

### Phase 1 · Bootstrap (Feb 17)
> Branch: `feature/rental` (from `main`) | ~6 commits

| Hash | Date | Type | Description |
|------|------|------|-------------|
| `108fe18` | 2026-02-17 | chore | isolate search skill artifact paths |
| `67a6f05` | 2026-02-17 | chore | ignore local artifacts; remove large files from tracking |
| `223c4aa` | 2026-02-17 | chore | migrate run scripts + RunPod setup; fix artifact paths |
| `3abbd8a` | 2026-02-17 | chore | merge remote main bootstrap commit |
| `f7d5dff` | 2026-02-17 | feat | bootstrap modular architecture (agent/skills/core) |
| `85379ec` | 2026-02-17 | chore | initial commit |

---

## Phase 22 — OpenRent Crawler (2026-03-11)

| Hash | Date | Type | Description |
|------|------|------|-------------|
| TBD | 2026-03-11 | feat | OpenRent crawler with rate limiting + user agent rotation (6,539 listings scraped) |
| TBD | 2026-03-11 | data | organize local datasets: 26,191 Rightmove + 6,539 OpenRent (not yet synced to Qdrant) |

---

## Stats

| Metric | Value |
|--------|-------|
| Total commits (all branches) | ~140 |
| Project start | 2026-02-17 |
| Latest commit | 2026-03-01 (`f1597ae`, restructure) |
| OpenClaw branch start | 2026-03-07 |
| Days active | 18 |

- `9d35dc3` perf: parallel refinement plan + metadata-first → ~1.4s consistent time-to-cards (backend-2)
- `ef42c1e` perf: shrink router prompt (2-turn history, 120-char truncation) + switch to gpt-4o-mini → stable 1.4–1.6s (backend-2)
