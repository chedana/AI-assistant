# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Multi-turn conversational rental search assistant. Users describe rental requirements in natural language; the system extracts constraints, retrieves listings from a vector database, applies hard filters and soft ranking, and returns grounded explanations with structured UI cards.

**Key technologies:** Python (FastAPI, LangGraph, OpenAI API), React + Vite + TypeScript + TailwindCSS, Qdrant, Sentence Transformers.

---

## Commands

### IMPORTANT: Port Conflicts

Another user (`claudesubscription`) runs a **stale** copy of the frontend on port **5173** from `/Users/claudesubscription/Desktop/LLM_project/AI-assistant/frontend/`. That is **old code** — do NOT use it.

Always start our frontend on **port 5174** to avoid conflicts:

```bash
cd frontend && node node_modules/.bin/vite --host 0.0.0.0 --port 5174
```

Before starting any server, check existing processes with `lsof -i :<port>` and `ps aux | grep vite` to avoid connecting to stale instances.

### Backend + Frontend
```bash
# Terminal 1: FastAPI backend
# Must set LLM proxy + Qdrant Cloud env vars (see Configuration section)
cd backend && uvicorn api_server:app --host 0.0.0.0 --port 8000

# Terminal 2: Frontend dev server (port 5174, NOT 5173)
cd frontend && node node_modules/.bin/vite --host 0.0.0.0 --port 5174
```

### Frontend build
```bash
cd frontend && npm run build    # production build (runs tsc -b && vite build)
npm run preview                 # preview production build
```

### CLI mode (no web UI)
```bash
./run.sh          # sets env vars, checks model availability, runs python3 main.py
python3 main.py   # interactive CLI with /exit, /reset, /state, /focus N commands
```

### Tests
No automated test runner. Test datasets are validated manually:
- `test/stageA/` — location extraction
- `test/stageB/stageB_hard_filter_update_summary.json` — hard-filter state transitions (run sequentially, not isolated)
- `test/stageC/stageC_cases.json` — ranking quality

---

## Architecture

### Orchestration Graph (LangGraph)

Built in `orchestration/graph.py`. Entry point: `orchestration/workflow.py:process_turn()`.

```
[route_node] → intent classification (Search / QA / Page_Nav / Chitchat / DirectReply / Fallback)
    ├→ [search_node] → [evaluate_node] ─── "done" ───→ [finalize_node]
    │                       │
    │                       ├── "ask_user" ──────────────→ [finalize_node]
    │                       └── "relax" → [relax_node] ⟲ search_node (max 2×)
    │
    ├→ [qa_plan_node] → [qa_execute_node] → [finalize_node]
    ├→ [paginate_node] → [finalize_node]
    ├→ [chitchat_node] → [finalize_node]
    ├→ [direct_reply_node] → [finalize_node]
    └→ [fallback_node] → [finalize_node]
```

A legacy non-LangGraph fallback (`_legacy_process_turn`) exists in `orchestration/workflow.py` if LangGraph fails to import.

### Search Pipeline (4 Stages)

| Stage | Module | What it does |
|-------|--------|-------------|
| A: Retrieval | `skills/search/engine.py` | Location extraction → Qdrant vector search (default 1000 recall) |
| B: Hard Filter | `skills/search/hard_filter.py` | Budget, bedrooms, bathrooms, furnishing, let_type, tenancy |
| C: Soft Rank | `skills/search/soft_rank.py` | Deposit, freshness, unknown-field penalties, semantic preference reranking |
| D: Explain | `skills/search/formatter.py` | Grounded summary + risk flags per listing |

Orchestrated by `skills/search/agentic.py` → `pipeline.py` → `pipeline_service.py`.

### Evaluate → Relax Loop

`orchestration/evaluate_node.py` diagnoses sparse results and decides: "done" (enough results), "relax" (auto-loosen safe constraints), or "ask_user" (location miss / layout bottleneck). `orchestration/relax_node.py` applies relaxation (budget +15/25%, remove furnish/let_type, shift available_from +14d, reduce min_size_sqm 10%).

### Two-Layer State

- **`GraphState`** (per-turn TypedDict) — routing decisions, reply text, QA scratch-pad, relax tracking. Lives only for one `process_turn()` call.
- **`AgentState`** (cross-turn dataclass) — constraints, user_profile, last_results, search_full_results, page_index, has_more, snapshot_history, focus listing. Persists in server-side `SESSIONS` dict.

Constraint merging (`orchestration/merger.py`) supports `patch` vs `replace_all` scopes, with independent `replace | append | keep` modes for location and layout.

### SSE Protocol (Backend → Frontend)

`backend/api_server.py` streams three event types:
1. **`delta`** — text chunks (8 chars, 10ms interval)
2. **`metadata`** — structured JSON after text completes: `{search_results, constraints, quick_replies}`
3. **`done`** — signals stream end

`build_metadata()` extracts listings, active constraints, and contextual quick-reply suggestions from AgentState. Note: search result fields like `penalty_reasons` and `preference_hits` are stored as semicolon-joined strings in the pipeline — `_to_list()` normalizes them to arrays for JSON serialization. Numeric fields may be numpy types — `_num()` coerces to native Python.

### Frontend Component Structure

`App.tsx` is a thin layout shell (~50 lines). Logic lives in hooks:
- **`hooks/useSessions.ts`** — session CRUD + localStorage persistence
- **`hooks/useChat.ts`** — sendMessage, stopGenerating, streaming + metadata state

Key components:
- **`ChatArea`** — messages + listing cards + constraint tags + quick replies
- **`MessageContent`** — user messages: plain text with URL detection; assistant messages: hand-written Markdown renderer (`lib/markdown.ts`)
- **`ListingCard`** — structured listing display with price, bed/bath, preference hits (green), penalty reasons (amber)
- **`ConstraintTags`** — sticky filter bar; clicking ✕ sends natural language removal via chat
- **`QuickReplies`** — contextual buttons that inject text as user input
- **`ThinkingIndicator`** — CSS-only 3-dot pulse animation

### Dual LLM Clients

`core/llm_client.py` exposes two OpenAI SDK clients (default: OpenAI API):
- **`qwen_client`** — reasoning (extraction, QA, explanation)
- **`router_client`** — intent routing (may point to same or lighter model)

---

## Configuration

All tunable parameters are env vars (see `run.sh` for defaults, `core/settings.py` for full list):

| Var | Default | Purpose |
|-----|---------|---------|
| `OPENAI_API_KEY` | — (required) | OpenAI API key |
| `QWEN_BASE_URL` | `https://api.openai.com/v1` | Reasoning LLM endpoint |
| `QWEN_MODEL` | `gpt-5-mini` | Model name |
| `ROUTER_BASE_URL` | same as QWEN | Routing LLM endpoint |
| `RENT_QDRANT_PATH` | — | Qdrant DB directory |
| `RENT_QDRANT_COLLECTION` | `rent_listings` | Collection name |
| `RENT_RECALL` | `1000` | Vector search recall count |
| `RENT_K` | `5` | Listings per page |
| `RENT_STRUCTURED_POLICY` | `RULE_FIRST` | `RULE_FIRST \| HYBRID \| LLM_FIRST` |
| `RENT_ENABLE_STAGE_D_EXPLAIN` | `1` | Enable Stage D explanation |
| `ROUTER_DEBUG` | `1` | Print routing decisions |

---

## Key Files

| File | Role |
|------|------|
| `orchestration/graph.py` | LangGraph state graph builder |
| `orchestration/workflow.py` | `process_turn()` entry point + legacy fallback |
| `orchestration/nodes.py` | All graph node implementations |
| `orchestration/evaluate_node.py` | Sparsity diagnosis + relax decision |
| `orchestration/state.py` | `GraphState` + `AgentState` + `QuerySnapshot` |
| `orchestration/router.py` | LLM intent classifier with few-shot examples |
| `orchestration/merger.py` | Constraint snapshot merge logic |
| `core/chatbot_config.py` | All LLM system prompts |
| `core/settings.py` | Env-driven config with defaults |
| `skills/search/constraint_extraction.py` | Regex + rule engine for UK rental constraints |
| `skills/search/hard_filter.py` | Stage B hard filtering |
| `skills/search/soft_rank.py` | Stage C soft scoring |
| `backend/api_server.py` | FastAPI SSE streaming + metadata |
| `frontend/src/hooks/useChat.ts` | Chat streaming + metadata state |
| `frontend/src/lib/markdown.ts` | Hand-written Markdown-to-HTML parser |

---

## Design Principles

- **LLM-first for user input understanding.** Whenever a user query needs to be interpreted, classified, or have information extracted from it, use the LLM — not regex. Regex is brittle and can only match patterns you anticipate. The LLM understands intent, handles misspellings, slang, and novel phrasing. Regex may be used only as a last-resort fallback if the LLM call fails, never as the primary path.
- **Rule-based for data processing.** Hard filters, normalization, geocoding lookups, score computation — these operate on structured data, not user language. Rules are appropriate here.

**Rule of thumb:** If it touches raw user text → LLM. If it transforms structured data → rules.

---

## Git Conventions

- Do **not** add `Co-Authored-By` trailers to commit messages.
- Always commit to the **`openclaw`** branch.

---

## Progress Tracking

Two files manage work across sessions:

| File | Purpose |
|------|---------|
| `PROJECT.md` | Living task tracker — current state, open tasks, bugs, roadmap. **Read this to know what to work on.** |
| `DEV_PROGRESS.md` | Append-only commit log — what has been done, per session. |

### After every commit (mandatory)

1. **Update `PROJECT.md`** — mark completed tasks `✅`, update Current App State / Data State if changed.
2. **Append a done line to `DEV_PROGRESS.md`** (format: `` | `<hash>` | <date> | <type> | <description> ``).
3. Commit both:
   ```bash
   git add PROJECT.md DEV_PROGRESS.md
   git commit -m "docs: update PROJECT + DEV_PROGRESS after <short hash>"
   ```
