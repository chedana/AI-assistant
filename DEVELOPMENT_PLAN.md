# OpenClaw Development Plan

> **Owner:** Lead
> **Created:** 2026-03-30
> **Branch:** `openclaw`
> **Status:** Draft — awaiting review

---

## Overview

5 phases, ordered by impact/effort ratio. Each task has a **Dev Plan**, **Test Plan**, and **Validation Criteria**.

```
Phase 1: Quick Wins               (1-2 days)   — F-F8, B-F5b
Phase 2: Data Quality             (2-3 days)   — B-B2, B-P2
Phase 3: Contact Features         (2 days)     — B-F4
Phase 4: Contract & Viewing       (4-5 days)   — B-F6, F-F6, F-F5
Phase 5: Area Research APIs       (3-4 days)   — crime, flood, EPC, avg rent
```

---

## Phase 1: Quick Wins

### 1.1 F-F8 — Quick/Deep Toggle

**Background:** `AgentState.thinking_mode` exists (`"quick"` default) and is read in `nodes.py`, but is never exposed to the frontend or controllable by the user.

#### Dev Plan

| Layer | File | Change |
|-------|------|--------|
| Backend | `backend/api_server.py` | Add `thinking_mode` to `build_metadata()` output |
| Backend | `backend/api_server.py` | Read `route_hint.thinking_mode` in `/api/chat/stream` and set on `AgentState` |
| Frontend types | `frontend/src/types/chat.ts` | Add `thinking_mode?: "quick" \| "deep"` to `SessionMetadata` |
| Frontend state | `frontend/src/hooks/useChat.ts` | Store `thinkingMode` per-session; pass as `routeHint.thinking_mode` in `sendMessage()` and `sendSilentAction()` |
| Frontend UI | `frontend/src/components/ChatInput.tsx` | Add toggle button (bolt icon = quick, brain icon = deep) left of send button |
| Backend nodes | `orchestration/nodes.py` | When `thinking_mode == "deep"`: use larger model / longer prompts / skip shortcuts in `search_node`, `qa_execute_node` |

**Toggle behavior:**
- Default: `quick` (current behavior)
- `deep`: more thorough explanations, Stage D always enabled, longer QA answers
- Toggle is per-session, persists in `ChatSession` (add `thinkingMode` field to `ChatSession` type)
- Visual: button glows accent color in `deep` mode

#### Test Plan

| # | Test | Input | Expected |
|---|------|-------|----------|
| T1 | Default mode | Send any search query | Metadata contains `thinking_mode: "quick"` |
| T2 | Toggle to deep | Click deep toggle, send query | Metadata contains `thinking_mode: "deep"` |
| T3 | Persist across messages | Toggle deep, send 2 messages | Both responses use deep mode |
| T4 | Session switch reset | Toggle deep in A, switch to B | B defaults to quick (or B's own saved mode) |
| T5 | UI state | Toggle deep | Button shows brain icon with accent glow |
| T6 | Deep QA | Toggle deep, ask "is this pet-friendly?" | Longer, more detailed answer than quick mode |

#### Validation Criteria

- [ ] Toggle visible in ChatInput area on both mobile and desktop
- [ ] `thinking_mode` appears in SSE metadata event
- [ ] Backend logs show mode change: `[thinking_mode=deep]`
- [ ] Deep mode produces noticeably more detailed Stage D explanations
- [ ] No regression: quick mode behavior identical to current behavior

---

### 1.2 B-F5b — Merge Commute LLM Call into Router

**Background:** `_try_extract_commute_destination_via_llm()` in `nodes.py:640` fires an extra OpenAI call on every QA question. Most QA is about pets/rent/bedrooms — the commute LLM call is wasted ~90% of the time.

#### Dev Plan

| Step | File | Change |
|------|------|--------|
| 1 | `orchestration/router.py` | Add `commute_destination: Optional[str]` field to `RouteDecision` dataclass |
| 2 | `orchestration/router.py` | Update router prompt: add instruction — "If the user asks about commute/travel/distance to a place, extract the destination name into `commute_destination`. Otherwise leave null." |
| 3 | `orchestration/router.py` | Parse `commute_destination` from LLM response JSON |
| 4 | `orchestration/nodes.py` | In `qa_execute_node()`, read `commute_destination` from `GraphState.route_decision` instead of calling `_try_extract_commute_destination_via_llm()` |
| 5 | `orchestration/nodes.py` | Remove `_try_extract_commute_destination_via_llm()` function |
| 6 | `orchestration/state.py` | Add `commute_destination: Optional[str]` to `GraphState` if not routing through `RouteDecision` |

**Fallback:** If router fails to extract but user message contains commute keywords (regex: `commut|travel|how long|how far|get to|journey`), fall back to a simple regex extraction as last resort (no LLM call).

#### Test Plan

| # | Test | Input | Expected |
|---|------|-------|----------|
| T1 | Commute question | "how long to King's Cross?" | Router returns `intent: Specific_QA, commute_destination: "King's Cross"` |
| T2 | Non-commute QA | "is this pet-friendly?" | Router returns `intent: Specific_QA, commute_destination: null` — NO extra LLM call |
| T3 | Ambiguous | "is it near the station?" | Router may or may not extract; QA handles gracefully |
| T4 | Company name | "how long to Google London?" | Router extracts `"Google London"`; downstream geocodes to station |
| T5 | Latency check | Time 10 QA requests | Average latency drops by ~300-500ms vs current (1 fewer LLM call) |

#### Validation Criteria

- [ ] `_try_extract_commute_destination_via_llm()` is fully removed
- [ ] Only ONE LLM call per QA turn (the router call)
- [ ] Commute QA still works correctly for stations, landmarks, companies
- [ ] Non-commute QA latency measurably lower (no wasted call)
- [ ] No new edge cases where commute detection fails

---

## Phase 2: Data Quality

### 2.1 B-B2 — Re-crawl Rightmove with Area Names

**Background:** Current Rightmove crawl used postcodes (e.g., "E1", "SW1V") for typeahead resolution. Rightmove's typeahead often resolves these to wrong locations. Fix: use full area names (e.g., "Hackney, London", "Brixton, London").

#### Dev Plan

| Step | File | Change |
|------|------|--------|
| 1 | `crawler/rightmove/london_postcodes.py` | Replace postcode list with area-name list (~150 London areas). Format: `"Hackney, London"`, `"Camden, London"`, etc. Source: London borough + neighbourhood names |
| 2 | `crawler/rightmove/crawl_london.py` | Update `resolve_with_typeahead()` to prefer area-name results. Add retry logic if typeahead returns no results |
| 3 | `crawler/rightmove/crawl_london.py` | Clear `postcode_location_cache.json` before re-crawl to force fresh resolution |
| 4 | Run | Execute full crawl: `python crawl_london.py --step all` |
| 5 | Sync | Run `sync_qdrant.py --mode sync` to push new data to Qdrant Cloud |
| 6 | Verify | Compare pre/post: total listings, location coverage, sample query hit rates |

**Area name source list (sample):**
```
Barking, London / Barnet, London / Battersea, London / Bermondsey, London
Bethnal Green, London / Bow, London / Brixton, London / Camberwell, London
Camden, London / Canary Wharf, London / Clapham, London / Croydon, London
Dalston, London / Deptford, London / Ealing, London / Elephant and Castle, London
Finsbury Park, London / Fulham, London / Greenwich, London / Hackney, London
Hammersmith, London / Hampstead, London / Holloway, London / Islington, London
Kennington, London / Kentish Town, London / Kilburn, London / Lewisham, London
... (total ~150 areas covering all 33 boroughs + key neighbourhoods)
```

#### Test Plan

| # | Test | Input | Expected |
|---|------|-------|----------|
| T1 | Typeahead resolution | "Hackney, London" | Returns valid `location_identifier` (not a random postcode's location) |
| T2 | Coverage check | Count unique areas in crawled data | >= 120 London areas represented |
| T3 | Listing count | Total crawled listings | >= 20,000 (comparable to current 23,592) |
| T4 | Search hit rate | Query: "2-bed in Hackney" | Returns listings actually IN Hackney (verify addresses) |
| T5 | Search hit rate | Query: "flat near King's Cross" | Returns listings in King's Cross/Camden area |
| T6 | No regressions | Run all stageA test cases | Pass rate >= current |

#### Validation Criteria

- [ ] Qdrant Cloud collection refreshed with area-name-crawled data
- [ ] Total listing count >= 20,000
- [ ] Location miss rate on 20 sample queries drops from >30% to <10%
- [ ] `discovery_paths` in Qdrant payloads show area names (not postcodes)
- [ ] No duplicate listings (dedup by `listing_id`)

---

### 2.2 B-P2 — Unify Listing Fields

**Background:** Fields like `deposit`, `size_sqm`, `furnish_type`, `property_type` are inconsistent between `search_results` and `compare_data` in the SSE metadata.

#### Dev Plan

| Step | File | Change |
|------|------|--------|
| 1 | `backend/api_server.py` | Audit `_map_listing()` — ensure ALL listing fields are mapped consistently |
| 2 | `backend/api_server.py` | Audit `_map_compare_listing()` — align with `_map_listing()` field names |
| 3 | `frontend/src/types/chat.ts` | Ensure `ListingData` type covers all fields from both code paths |
| 4 | `skills/search/pipeline.py` | Ensure `candidate_snapshot()` includes all fields needed downstream |

**Key fields to unify:**

| Field | search_results | compare_data | Target |
|-------|---------------|--------------|--------|
| `deposit` | number or string | sometimes missing | `deposit?: number \| null` (always number or null) |
| `size_sqm` | sometimes present | often missing | `size_sqm?: number \| null` |
| `furnish_type` | present | sometimes different key | `furnish_type?: string` |
| `property_type` | present | sometimes different key | `property_type?: string` |
| `openrent_url` | present | sometimes "nan" | `openrent_url?: string` (empty string if none) |

#### Test Plan

| # | Test | Input | Expected |
|---|------|-------|----------|
| T1 | Search metadata | Send search query | All listings have consistent field names and types |
| T2 | Compare metadata | "compare 1 and 3" | Compare listings have same fields as search listings |
| T3 | NaN check | Merged listing (rightmove+openrent) | No `"nan"` strings in any field |
| T4 | Missing field | Listing with no deposit info | `deposit: null`, not `deposit: "Ask agent"` in numeric context |

#### Validation Criteria

- [ ] `ListingData` type in frontend matches all backend output fields
- [ ] No `"nan"` or `"NaN"` strings in any SSE metadata
- [ ] Compare table and listing cards render identical data for the same listing
- [ ] No TypeScript errors after type changes

---

## Phase 3: Contact Features

### 3.1 B-F4 — Draft Viewing Request Email

**Background:** User clicks "draft email" on a listing → LLM generates a polite, professional viewing request using listing context.

#### Dev Plan

| Step | File | Change |
|------|------|--------|
| 1 | `backend/api_server.py` | New endpoint: `POST /api/contact/draft` — body: `{session_id, listing_index}` |
| 2 | `backend/api_server.py` | Fetch listing from `AgentState.last_results` by index |
| 3 | `core/chatbot_config.py` | New prompt: `DRAFT_VIEWING_EMAIL_SYSTEM` — instructs LLM to generate viewing request email |
| 4 | `backend/api_server.py` | Call `qwen_client` with listing context (title, address, price, agent name if available) + user profile (name, move-in date, employment if available from conversation) |
| 5 | `backend/api_server.py` | Return `{subject, body, agent_email_hint}` |
| 6 | `frontend/src/types/chat.ts` | Add `DraftEmailResponse` type |
| 7 | `frontend/src/components/ListingCard.tsx` | Add "Draft email" button (envelope icon) — opens modal with editable email |
| 8 | `frontend/src/components/DraftEmailModal.tsx` | New component: shows subject + body in editable textareas + "Copy to clipboard" button |

**Prompt design (DRAFT_VIEWING_EMAIL_SYSTEM):**
```
You are helping a tenant write a viewing request email.
Given the listing details, write a brief, polite email requesting a viewing.
Include: greeting, interest in the property, preferred viewing times (suggest 2-3 slots),
brief mention of the tenant (working professional / couple / etc if known).
Keep it under 150 words. Professional but warm tone.
Do NOT include personal details the user hasn't shared.
```

#### Test Plan

| # | Test | Input | Expected |
|---|------|-------|----------|
| T1 | Basic draft | Click "Draft email" on listing 1 | Modal opens with subject "Viewing request — [address]" and professional body |
| T2 | Listing context | Listing at £1,500/month in Hackney | Email mentions the specific property and location |
| T3 | User profile | User previously said "I'm a nurse" | Email mentions profession if available; omits if not |
| T4 | Copy to clipboard | Click "Copy" button | Email text copied to clipboard; toast confirmation |
| T5 | Edit and copy | User edits the body, clicks copy | Edited version is copied |
| T6 | No listing | Invalid listing index | Error message: "Listing not found" |
| T7 | Loading state | Click draft while generating | Button disabled during generation |

#### Validation Criteria

- [ ] `POST /api/contact/draft` returns valid JSON with `subject` and `body`
- [ ] Email is professional, concise (<150 words), and property-specific
- [ ] No hallucinated details (no fake agent names, no made-up user info)
- [ ] Modal renders correctly on desktop and mobile
- [ ] Copy-to-clipboard works on Chrome, Safari, Firefox

---

## Phase 4: Contract & Viewing

### 4.1 B-F6 — Contract Analysis Endpoint

**Background:** User uploads a tenancy agreement PDF → backend extracts text → LLM produces plain-English summary + clause flags.

#### Dev Plan

| Step | File | Change |
|------|------|--------|
| 1 | `requirements.txt` | Add `pymupdf` (PDF text extraction) |
| 2 | `skills/contract/__init__.py` | New skill module |
| 3 | `skills/contract/extractor.py` | `extract_text(pdf_bytes) -> str` — PyMuPDF extracts text from all pages |
| 4 | `skills/contract/analyser.py` | `analyse_contract(text) -> ContractReport` — LLM call with structured output |
| 5 | `core/chatbot_config.py` | New prompt: `CONTRACT_ANALYSIS_SYSTEM` |
| 6 | `backend/api_server.py` | New endpoint: `POST /api/contract/analyse` — multipart file upload, returns `ContractReport` JSON |

**ContractReport structure:**
```python
@dataclass
class ContractReport:
    summary: str                    # 3-5 sentence plain-English summary
    tenancy_type: str               # AST / fixed-term / rolling
    rent: str                       # amount + frequency
    deposit: str                    # amount + protection scheme if mentioned
    break_clause: str | None        # break terms or "None found"
    notice_period: str              # how much notice to leave
    clauses: list[ClauseFlag]       # flagged unusual clauses
    compliance: list[ComplianceCheck]  # legal compliance checks

@dataclass
class ClauseFlag:
    clause_text: str                # exact quote from contract
    issue: str                      # what's unusual
    severity: str                   # "info" | "warning" | "critical"
    advice: str                     # what to do about it

@dataclass
class ComplianceCheck:
    check: str                      # e.g. "Deposit <= 5 weeks rent"
    status: str                     # "pass" | "fail" | "unknown"
    detail: str                     # explanation
```

**Prompt design (CONTRACT_ANALYSIS_SYSTEM):**
```
You are a UK tenancy law expert helping a renter understand their tenancy agreement.
Given the full text of a tenancy agreement, produce a structured analysis.

CRITICAL CHECKS:
- Deposit must be <= 5 weeks' rent (Tenant Fees Act 2019)
- No prohibited fees (admin, reference, guarantor fees are banned)
- Deposit must be protected in a government scheme within 30 days
- Section 21 notice requirements (if applicable pre-RRA 2025)
- Break clause must be mutual (landlord-only break is a red flag)
- Excessive landlord access rights (>24hr notice is normal; <24hr is a flag)
- Unusual cleaning/decoration obligations at end of tenancy

OUTPUT: JSON matching ContractReport schema.
```

#### Test Plan

| # | Test | Input | Expected |
|---|------|-------|----------|
| T1 | Valid PDF | Upload sample AST agreement (2 pages) | Returns `ContractReport` with all fields populated |
| T2 | Deposit flag | Contract with deposit = 8 weeks rent | `compliance` contains fail: "Deposit exceeds 5 weeks" |
| T3 | Break clause | Contract with landlord-only break clause | `clauses` contains warning about non-mutual break |
| T4 | Clean contract | Standard OpenRent AST (compliant) | All compliance checks pass; minimal clause flags |
| T5 | Large PDF | 20-page contract | Processes within 30 seconds; text truncated if needed |
| T6 | Non-PDF | Upload .docx file | Returns error: "Only PDF files are supported" |
| T7 | Corrupt PDF | Upload empty/corrupt file | Returns error: "Could not extract text from PDF" |
| T8 | No text | Scanned image PDF (no OCR text) | Returns error: "No text found — this may be a scanned document" |

#### Validation Criteria

- [ ] Endpoint accepts multipart file upload up to 10MB
- [ ] Text extraction works on standard UK tenancy agreement PDFs
- [ ] LLM identifies at least 3 of 5 planted issues in a test contract
- [ ] Response time < 30 seconds for a typical 5-page contract
- [ ] No hallucinated clause text (all quotes must exist in the original)
- [ ] Compliance checks cover: deposit amount, prohibited fees, deposit protection, break clause mutuality

---

### 4.2 F-F6 — Contract Upload UI

**Background:** Frontend component for uploading a PDF and displaying the analysis results.

#### Dev Plan

| Step | File | Change |
|------|------|--------|
| 1 | `frontend/src/types/chat.ts` | Add `ContractReport`, `ClauseFlag`, `ComplianceCheck` types |
| 2 | `frontend/src/components/ContractUpload.tsx` | New component: drag-and-drop / file picker → calls `POST /api/contract/analyse` → displays report |
| 3 | `frontend/src/components/ContractReport.tsx` | New component: renders summary, clause flags (color-coded by severity), compliance checklist |
| 4 | `frontend/src/App.tsx` | Add route/tab/button to access contract analysis (e.g., in Header or as a new panel) |

**UI design:**
- Upload area: dashed border, drag-and-drop zone, "Upload tenancy agreement" label
- Loading state: progress bar or spinner with "Analysing contract..."
- Report view:
  - Summary card (top)
  - Key terms row: rent, deposit, tenancy type, notice period, break clause
  - Clause flags: expandable list, color-coded (green=info, amber=warning, red=critical)
  - Compliance checklist: checkmarks/crosses with explanations

#### Test Plan

| # | Test | Input | Expected |
|---|------|-------|----------|
| T1 | File picker | Click upload area | Native file picker opens, filtered to PDF |
| T2 | Drag and drop | Drag PDF onto upload zone | File accepted, upload starts |
| T3 | Loading state | Upload large PDF | Spinner shows; UI not blocked |
| T4 | Report render | Successful analysis | All sections render: summary, terms, clauses, compliance |
| T5 | Critical flag | Contract with prohibited fee | Red flag shown with "critical" badge |
| T6 | Error state | Upload corrupt file | Error message displayed inline (not crash) |
| T7 | Mobile | Use on mobile browser | Upload area and report are responsive |

#### Validation Criteria

- [ ] Drag-and-drop works on Chrome, Safari, Firefox (desktop)
- [ ] File picker works on mobile browsers
- [ ] Report renders all sections without overflow or truncation
- [ ] Severity colors match: info=green, warning=amber, critical=red
- [ ] "Upload another" button available after viewing report

---

### 4.3 F-F5 — Viewing Checklist

**Background:** Per-listing checklist: legal requirements + physical inspection items + questions to ask. No backend endpoint needed — checklist is static content rendered client-side.

#### Dev Plan

| Step | File | Change |
|------|------|--------|
| 1 | `frontend/src/data/viewingChecklist.ts` | New file: static checklist data (legal, physical, questions) |
| 2 | `frontend/src/components/ViewingChecklist.tsx` | New component: renders checklist with toggleable checkboxes, grouped by category |
| 3 | `frontend/src/components/ListingCard.tsx` | Add "Viewing checklist" button (clipboard icon) |
| 4 | `frontend/src/hooks/useViewingChecklists.ts` | Hook: stores checkbox state per listing URL in localStorage |

**Checklist content:**

```typescript
const VIEWING_CHECKLIST = {
  legal: [
    { id: "gas_cert", label: "Gas safety certificate (annual, must be provided before move-in)" },
    { id: "epc", label: "Energy Performance Certificate (minimum E rating)" },
    { id: "electrical", label: "Electrical safety report (EICR, valid 5 years)" },
    { id: "smoke_co", label: "Smoke alarms on every floor + CO detector if gas appliances" },
    { id: "deposit_scheme", label: "Ask which deposit protection scheme they use" },
    { id: "how_to_rent", label: "Must receive 'How to Rent' guide before signing" },
    { id: "landlord_identity", label: "Confirm landlord name and contact (not just agent)" },
  ],
  physical: [
    { id: "damp_mould", label: "Check walls, ceilings, window frames for damp or mould" },
    { id: "boiler", label: "Check boiler age and last service date" },
    { id: "water_pressure", label: "Run taps and shower — check water pressure" },
    { id: "windows", label: "Open/close all windows — check seals and locks" },
    { id: "electrics", label: "Test light switches and plug sockets in each room" },
    { id: "broadband", label: "Check mobile signal and ask about broadband speed" },
    { id: "natural_light", label: "Note natural light levels (visit at different times if possible)" },
    { id: "storage", label: "Check cupboard and storage space" },
    { id: "noise", label: "Listen for traffic, neighbours, building noise" },
    { id: "heating", label: "Check radiators in each room — ask about heating bills" },
  ],
  questions: [
    { id: "q_bills", label: "Are any bills included in the rent?" },
    { id: "q_tenancy_length", label: "What is the minimum tenancy length?" },
    { id: "q_rent_increase", label: "How and when can the rent be increased?" },
    { id: "q_maintenance", label: "How are maintenance requests handled? Response time?" },
    { id: "q_inventory", label: "Will there be a professional inventory check-in?" },
    { id: "q_previous_tenant", label: "Why did the previous tenant leave?" },
    { id: "q_neighbours", label: "Any known issues with neighbours?" },
    { id: "q_works", label: "Are there any planned works or developments nearby?" },
  ]
};
```

#### Test Plan

| # | Test | Input | Expected |
|---|------|-------|----------|
| T1 | Open checklist | Click checklist button on listing | Checklist panel opens with all 3 sections |
| T2 | Check item | Tap checkbox on "Gas safety certificate" | Checkbox fills; state persisted |
| T3 | Persist | Check 3 items, close panel, reopen | 3 items still checked |
| T4 | Per-listing | Check items on listing A, open listing B's checklist | Listing B's checklist is unchecked |
| T5 | Progress | Check 5 of 7 legal items | Header shows "5/7 Legal" progress |
| T6 | Mobile | Open on mobile | Checklist is full-screen overlay, scrollable |

#### Validation Criteria

- [ ] Checklist data is accurate per UK law (Gas Safety Regs, EICR, Tenant Fees Act, Homes Act 2018)
- [ ] Checkbox state persists in localStorage per listing URL
- [ ] Progress indicator per category (e.g., "5/7 Legal")
- [ ] Works on mobile (touch targets >= 44px)
- [ ] No backend dependency — fully client-side

---

## Phase 5: Area Research APIs

### 5.1 Crime Index (data.police.uk)

#### Dev Plan

| Step | File | Change |
|------|------|--------|
| 1 | `skills/research/crime.py` | New module: `get_crime_stats(lat, lon, radius_km=1) -> CrimeStats` |
| 2 | API call | `GET https://data.police.uk/api/crimes-street/all-crime?lat={lat}&lng={lon}&date={YYYY-MM}` |
| 3 | Aggregation | Count by category (burglary, robbery, violence, anti-social, drugs, vehicle crime) for last 3 months |
| 4 | Integration | Call in `build_metadata()` for each listing (cached by postcode prefix, 24hr TTL) |
| 5 | Frontend | Add crime summary badge to `ListingCard` (e.g., "Low crime area" / "Above average crime") |

**Benchmarking:** Compare against London-wide averages to produce relative score (low/medium/high).

#### Test Plan

| # | Test | Expected |
|---|------|----------|
| T1 | API response | Valid JSON array of crimes for E1 area |
| T2 | Aggregation | Correct category counts over 3 months |
| T3 | Caching | Second call for same area hits cache (no API call) |
| T4 | No data | Remote area with no crimes → "No data available" |
| T5 | Rate limit | Respect 15 req/sec limit; retry with backoff |

---

### 5.2 Flood Risk (Environment Agency)

#### Dev Plan

| Step | File | Change |
|------|------|--------|
| 1 | `skills/research/flood.py` | New module: `get_flood_risk(lat, lon) -> FloodRisk` |
| 2 | API call | `GET https://environment.data.gov.uk/flood-monitoring/id/floods?lat={lat}&long={lon}&dist=3` |
| 3 | Alternative | Use gov.uk flood risk API: postcode lookup → risk level (high/medium/low/very low) |
| 4 | Integration | Add to `build_metadata()` per listing (cached by postcode, 7-day TTL) |
| 5 | Frontend | Flood risk badge on ListingCard (icon + level) |

---

### 5.3 EPC Rating (gov.uk)

#### Dev Plan

| Step | File | Change |
|------|------|--------|
| 1 | `skills/research/epc.py` | New module: `get_epc(postcode, address) -> EPCData` |
| 2 | API call | `GET https://epc.opendatacommunities.org/api/v1/domestic/search?postcode={postcode}&address={address}` (requires free API key registration) |
| 3 | Match | Fuzzy-match address to find the right certificate |
| 4 | Extract | Current rating (A-G), potential rating, certificate date |
| 5 | Integration | Add to listing metadata (cached by address, 30-day TTL) |
| 6 | Frontend | EPC badge on ListingCard (color-coded A=green to G=red) |

---

### 5.4 Average Rent Aggregates

#### Dev Plan

| Step | File | Change |
|------|------|--------|
| 1 | `skills/research/rent_stats.py` | New module: `get_area_rent_stats(area_name, bedrooms) -> RentStats` |
| 2 | Query | Aggregate from our own Qdrant data: filter by area + bedrooms → compute median, 25th pct, 75th pct |
| 3 | Integration | Add to `build_metadata()` — show "Area average: £X/month" next to listing price |
| 4 | Frontend | Price context badge on ListingCard: "Below average" / "Average" / "Above average" |

**No external API needed** — we have 29,000+ listings in Qdrant.

---

## End-to-End Validation Plan

After all phases are complete, run the following integration checks:

### Functional Validation

| # | Scenario | Steps | Expected |
|---|----------|-------|----------|
| E1 | New user search | Open fresh session → "Find me a 2-bed in Hackney under £1800" | Returns relevant listings with match scores, commute times, crime/flood badges |
| E2 | Refinement | "I want pet-friendly" → "what about Dalston?" | Constraints update correctly; new results load |
| E3 | Quick/Deep toggle | Switch to deep mode → "tell me more about listing 2" | Detailed explanation with grounded evidence |
| E4 | Viewing prep | Click "Viewing checklist" on a listing | Checklist opens with legal/physical/questions sections |
| E5 | Draft email | Click "Draft email" on listing | Professional email with correct property details |
| E6 | Contract upload | Upload test PDF | Analysis report with flagged clauses and compliance checks |
| E7 | Tenant rights | "Can my landlord enter without notice?" | RAG-powered answer citing relevant legislation |
| E8 | Session management | Create 3 sessions, rename one, switch between them | Each session maintains separate state and history |
| E9 | Mobile | Run E1-E5 on mobile viewport | All features accessible via mobile nav |

### Performance Validation

| Metric | Target | How to measure |
|--------|--------|----------------|
| Search response (quick mode) | < 3s to first listing card | Browser DevTools Network tab |
| Search response (deep mode) | < 6s to first listing card | Browser DevTools |
| QA response | < 2s | Time from send to first token |
| Contract analysis | < 30s for 5-page PDF | API response time |
| Draft email | < 5s | API response time |
| Crime/flood/EPC lookup | < 1s (cached) | Measured in build_metadata |

### Data Validation

| Check | Method | Target |
|-------|--------|--------|
| Listing count in Qdrant | `qdrant.count()` | >= 25,000 |
| Location coverage | Sample 20 London areas, query each | >= 18/20 return results |
| No stale listings | Check 50 random listing URLs | >= 90% still live (not 410) |
| Image availability | Check `image_urls` on 100 listings | >= 95% have at least 1 real image |
| Field completeness | Check `price_pcm`, `bedrooms`, `lat`, `lon` on 100 listings | 100% non-null |

---

## Risk Register

| Risk | Impact | Mitigation |
|------|--------|------------|
| Rightmove blocks re-crawl (rate limiting/IP ban) | High — no fresh data | Use rotating proxies; respect robots.txt; crawl during off-peak |
| Police API rate limit (15 req/sec) | Medium — slow metadata | Aggressive caching by postcode prefix; batch requests |
| EPC API requires registration | Low — delays integration | Register early; fallback to scraping if API denied |
| Contract analysis LLM hallucination | High — legal advice risk | Add disclaimer "This is not legal advice"; verify quotes exist in source |
| PDF text extraction fails (scanned docs) | Medium — user frustration | Detect and show clear error; suggest OCR tool |
| OpenAI API cost increase with deep mode | Medium — cost | Monitor usage; default to quick; show cost indicator to user |

---

## Timeline Estimate

| Phase | Tasks | Calendar days |
|-------|-------|---------------|
| Phase 1 | F-F8 + B-F5b | 1-2 |
| Phase 2 | B-B2 + B-P2 | 2-3 |
| Phase 3 | B-F4 | 2 |
| Phase 4 | B-F6 + F-F6 + F-F5 | 4-5 |
| Phase 5 | Crime + Flood + EPC + Rent stats | 3-4 |
| **Total** | | **~14 days** |

---

## Delivery Validation Checklist

> **Sign-off:** 每个 Phase 交付前，必须通过该 Phase 的全部条目 + "通用"部分。
> Lead 逐项确认后标 `[x]`，全部通过才可合并到 main。

---

### Phase 1 交付验收

**F-F8 Quick/Deep Toggle**

- [ ] 前端：ChatInput 区域可见切换按钮（desktop + mobile）
- [ ] 前端：切换状态在同一会话内持久（刷新后保持）
- [ ] 前端：切换不影响正在进行的生成（disabled during generation）
- [ ] 后端：SSE metadata 中包含 `thinking_mode` 字段
- [ ] 后端：`route_hint.thinking_mode` 正确写入 `AgentState`
- [ ] 效果差异：deep 模式 Stage D 解释 >= 3 句；quick 模式 <= 2 句
- [ ] 回归：quick 模式行为与当前版本完全一致（diff 对比 5 条查询响应）

**B-F5b Commute LLM Merge**

- [ ] `_try_extract_commute_destination_via_llm()` 函数已删除
- [ ] Router prompt 中包含 commute_destination 提取指令
- [ ] `RouteDecision.commute_destination` 字段存在且可 parse
- [ ] 测试："how long to King's Cross" → 正确提取 + TfL 返回通勤时间
- [ ] 测试："is this pet-friendly?" → `commute_destination = null`，无额外 LLM 调用
- [ ] 延迟：10 条非通勤 QA 平均响应时间 < 之前版本（差值 > 200ms）

---

### Phase 2 交付验收

**B-B2 Rightmove Re-crawl**

- [ ] `london_postcodes.py` 已替换为地名列表（>= 120 个 London 地区）
- [ ] `postcode_location_cache.json` 已清空并重新生成
- [ ] Qdrant Cloud `rent_listings` 集合已更新
- [ ] 总房源数 >= 20,000
- [ ] 抽查 20 条："2-bed in [area]" → 返回结果地址确实在该 area 内（>= 18/20 通过）
- [ ] `discovery_paths` payload 包含地名（非邮编代码）
- [ ] 无重复 listing_id（`qdrant.count()` == unique IDs count）

**B-P2 Unify Listing Fields**

- [ ] `_map_listing()` 和 `_map_compare_listing()` 输出字段名完全一致
- [ ] 前端 `ListingData` 类型覆盖所有后端输出字段
- [ ] SSE metadata 中无 `"nan"` / `"NaN"` / `"None"` 字符串
- [ ] Compare 表格和 ListingCard 对同一房源显示一致数据
- [ ] TypeScript 编译通过（`tsc --noEmit` 零错误）

---

### Phase 3 交付验收

**B-F4 Draft Viewing Email**

- [ ] `POST /api/contact/draft` 端点可用（200 响应）
- [ ] 返回 JSON 包含 `subject` 和 `body` 字段
- [ ] 邮件内容包含正确的房源地址和价格
- [ ] 邮件不超过 150 词
- [ ] 邮件不包含用户未提供的个人信息（无 hallucination）
- [ ] 前端：ListingCard 上显示"Draft email"按钮
- [ ] 前端：Modal 正确显示可编辑的 subject + body
- [ ] 前端：Copy to clipboard 在 Chrome / Safari / Firefox 生效
- [ ] 前端：Mobile 上 Modal 全屏显示，可滚动
- [ ] 错误处理：invalid listing index → 友好错误提示（非崩溃）

---

### Phase 4 交付验收

**B-F6 Contract Analysis**

- [ ] `POST /api/contract/analyse` 接受 multipart PDF 上传（<= 10MB）
- [ ] PyMuPDF 正确提取文本（测试 3 份不同格式的 UK AST 合同）
- [ ] 返回 `ContractReport` JSON，所有字段已填充
- [ ] 合规检查覆盖：押金上限、禁止费用、押金保护、break clause 互惠性
- [ ] 测试合同中植入 5 个问题 → LLM 识别 >= 3 个
- [ ] `clause_text` 引用的文本在原文中确实存在（零幻觉引用）
- [ ] 响应时间 < 30 秒（5 页 PDF）
- [ ] 错误处理：非 PDF → "Only PDF files supported"
- [ ] 错误处理：空白/损坏 PDF → "Could not extract text"
- [ ] 错误处理：扫描件（无 OCR 文字）→ "No text found"
- [ ] 页面包含免责声明："This is not legal advice"

**F-F6 Contract Upload UI**

- [ ] 拖拽上传在 Chrome / Safari / Firefox 生效
- [ ] 文件选择器在 mobile 浏览器生效
- [ ] Loading 状态：显示 spinner，UI 不阻塞
- [ ] 报告渲染：summary + key terms + clause flags + compliance checklist 全部可见
- [ ] 严重度颜色：info=绿 / warning=琥珀 / critical=红
- [ ] "Upload another" 按钮可用
- [ ] 无内容溢出或截断

**F-F5 Viewing Checklist**

- [ ] ListingCard 上可见 "Viewing checklist" 按钮
- [ ] Checklist 包含 3 个分类：Legal (7 项) / Physical (10 项) / Questions (8 项)
- [ ] 内容准确：符合 UK Gas Safety Regs / EICR / Tenant Fees Act 2019 / Homes Act 2018
- [ ] Checkbox 状态按 listing URL 独立存储在 localStorage
- [ ] 关闭后重新打开：状态保持
- [ ] 进度指示器：每个分类显示 "N/M" 完成数
- [ ] Mobile：touch target >= 44px，全屏 overlay，可滚动
- [ ] 纯前端：无后端请求

---

### Phase 5 交付验收

**Crime Index**

- [ ] `get_crime_stats()` 返回 3 个月犯罪分类统计
- [ ] 缓存生效：相同 postcode 第二次调用不发 API 请求
- [ ] 遵守 15 req/sec 限速（有 backoff 重试）
- [ ] ListingCard 显示犯罪等级 badge（Low / Medium / High）
- [ ] 无数据时显示 "No data available"（非崩溃）

**Flood Risk**

- [ ] `get_flood_risk()` 返回风险等级（very low / low / medium / high）
- [ ] 缓存生效（7 天 TTL）
- [ ] ListingCard 显示洪水风险 badge

**EPC Rating**

- [ ] EPC API key 已注册且可用
- [ ] 地址模糊匹配准确率 >= 80%（测试 20 条房源）
- [ ] ListingCard 显示 EPC 等级 badge（A-G 色彩编码）
- [ ] 无匹配时显示 "EPC not found"

**Average Rent**

- [ ] Qdrant 聚合查询返回 median / 25th / 75th 百分位
- [ ] ListingCard 显示价格对比 badge（Below avg / Average / Above avg）
- [ ] 分 bedroom 数计算（1-bed 和 3-bed 不混合比较）

---

### 通用验收条目（每个 Phase 必须通过）

**代码质量**

- [ ] TypeScript 编译通过：`cd frontend && npx tsc --noEmit` 零错误
- [ ] Python 无语法错误：`python -m py_compile <changed files>` 全部通过
- [ ] 无 `console.log` / `print()` 调试语句残留（允许 `console.error`）
- [ ] 无 hardcoded secrets（API key / password / token）
- [ ] 新增文件已加入 .gitignore（如有临时/缓存文件）

**安全**

- [ ] 文件上传（如有）：仅接受白名单 MIME type（application/pdf）
- [ ] 文件上传大小限制 <= 10MB
- [ ] 用户输入不直接拼接到 shell 命令或 SQL（无注入风险）
- [ ] SSE metadata 不泄露后端路径 / 内部错误堆栈
- [ ] 合同内容不发送到第三方（仅通过 OpenAI API 处理）

**浏览器兼容性**

- [ ] Chrome >= 90 ✓
- [ ] Safari >= 15 ✓
- [ ] Firefox >= 90 ✓
- [ ] Mobile Safari (iOS 15+) ✓
- [ ] Chrome Android ✓

**响应式 / 移动端**

- [ ] 所有新 UI 在 375px 宽度（iPhone SE）上可用
- [ ] 所有新 Modal / Overlay 在 mobile 上全屏
- [ ] Touch target >= 44px（Apple HIG 标准）
- [ ] 无水平溢出滚动

**性能**

- [ ] 搜索响应（quick 模式）< 3 秒
- [ ] 搜索响应（deep 模式）< 6 秒
- [ ] QA 响应 < 2 秒
- [ ] 前端首屏加载 < 2 秒（production build）
- [ ] 无内存泄漏（切换 10 次会话后 JS heap 不持续增长）

**错误处理**

- [ ] 后端 500 错误 → 前端显示友好提示（非白屏）
- [ ] 网络断开 → 显示 "Connection lost"（非无限 loading）
- [ ] API 超时 → 30 秒后自动断开并提示重试
- [ ] 所有 async 操作有 try/catch（无 unhandled promise rejection）

**部署就绪**

- [ ] 所有新 env vars 已记录在 `core/settings.py` 和 `CLAUDE.md`
- [ ] `requirements.txt` 已更新（如有新依赖）
- [ ] `frontend/package.json` 已更新（如有新依赖）
- [ ] Production build 成功：`cd frontend && npm run build`
- [ ] Git 状态干净：`git status` 无未提交更改
- [ ] 已 push 到 `origin/openclaw` 和 `origin/main`

---

*Document ends. Review and approve before starting Phase 1.*
