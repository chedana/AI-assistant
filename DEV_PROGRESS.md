# Development Progress — AI Rental Assistant

> **Keeping this file current:** After each commit, append a row to the relevant phase table and update [Current State](#current-state). The default commit target is the `restructure` branch (worktree at `.claude/worktrees/gracious-clarke`).

---

## Project Overview

Multi-turn conversational rental search assistant. Users describe rental requirements in natural language; the system extracts constraints, retrieves listings from a vector database, applies hard filters and soft ranking, and returns grounded explanations.

**Stack:** Python · FastAPI · LangGraph · vLLM (Qwen3-14B) · React + Vite + TypeScript + TailwindCSS · Qdrant · Sentence Transformers

---

## Branches

| Branch | Role | Tip commit |
|--------|------|-----------|
| `restructure` | **Active dev (default commit target)** | `b0f98d8` 2026-02-27 |
| `feature/rental` | Previous dev branch (behind restructure) | `b12fe96` 2026-02-25 |
| `main` | Stable baseline | `7355f5d` 2026-02-24 |
| `codex/initial-modular-structure` | Archived Codex bootstrap | — |

---

## Current State

_Last updated: 2026-02-27 · Branch: `restructure`_

### Architecture

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
    ConstraintTags.tsx  # sticky filter bar; click × sends "remove X filter" via chat
    QuickReplies.tsx    # contextual buttons (Show more / Lower budget / Compare) → inject as user input
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
- **Shortlist UI** — bookmark icon on each listing card (filled/outline driven by `metadata.shortlist.saved_ids`); click injects "save listing N" as chat message; clickable "Saved (N)" badge in header sends "show my shortlist"
- Frontend Phase 1 — component split (10 components, 2 hooks), hand-written markdown renderer, listing cards with preference/penalty tags, sticky constraint filter bar with ×-to-remove, quick-reply buttons, CSS thinking animation, backend metadata SSE event (search_results + constraints + quick_replies + compare_data + shortlist)
- SSE streaming — backend → frontend with stop-generation button
- Session persistence — localStorage + server-side TTL

### Not yet done
- General domain skill (`general_node`) is wired but responses are minimal
- No automated test runner — tests are JSON datasets validated manually
- UI Phase 2 (map view)
- `feature/rental` not yet merged up to `restructure`
- P2-B: location expansion when `prefilter_count == 0` (deferred — requires lat/lon data)
- Cross-session memory (preferences survive server restart)

---

## Session Progress

> Each Claude Code session updates only its own section below after every commit.
> Format: **Done** (append per commit) · **Remaining** (edit in place) · **Deferred** (edit in place).

---

### Session: backend-1 — Orchestration & Search Pipeline
_Covers: `orchestration/`, `agent_graph/`, `agent/`, `skills/`, `core/`_

**Done**
- _(no commits recorded yet — append here with commit hash)_

**Remaining**
- _(list outstanding tasks)_

**Deferred**
- _(items pushed out of scope — add reason)_

---

### Session: backend-2 — API & Infrastructure
_Covers: `backend/api_server.py`, FastAPI endpoints, SSE streaming_

**Done**
- _(no commits recorded yet — append here with commit hash)_

**Remaining**
- _(list outstanding tasks)_

**Deferred**
- _(items pushed out of scope — add reason)_

---

### Session: frontend — UI
_Covers: `frontend/src/` — components, hooks, types, lib_

**Done**
- `627abf9` feat: structured CompareTable UI component for compare intent
- `b0f98d8` feat: shortlist UI — bookmark button on listing cards + header badge

**Remaining**
- UI Phase 2: map view

**Deferred**
- _(items pushed out of scope — add reason)_

---

### Session: data — Data & Embeddings
_Covers: `crawler/`, `artifacts/`, Qdrant collection, embedding scripts_

**Done**
- _(no commits recorded yet — append here with commit hash)_

**Remaining**
- _(list outstanding tasks)_

**Deferred**
- P2-B: location expansion when `prefilter_count == 0` — requires lat/lon data not yet available

---

## Changelog

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
- **Header badge**: clickable "Saved (N)" pill in app header; sends `"show my shortlist"` on click; hidden when count is 0
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

## Stats

| Metric | Value |
|--------|-------|
| Total commits (all branches) | ~128 |
| Project start | 2026-02-17 |
| Latest commit | 2026-02-27 (`b0f98d8`) |
| Days active | 11 |
