# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Multi-turn conversational rental search assistant. Users describe rental requirements in natural language; the system extracts constraints, retrieves listings from a vector database, applies hard filters and soft ranking, and returns grounded explanations.

**Key technologies:** Python (FastAPI, LangGraph, vLLM), React + Vite + TypeScript + TailwindCSS, Qdrant, Sentence Transformers.

---

## Commands

### Backend
```bash
# Start vLLM inference server (required first, separate terminal)
vllm serve ./Qwen3-14B --port 8002

# Start FastAPI backend
cd backend && uvicorn api_server:app --host 0.0.0.0 --port 8000

# Run Python CLI (interactive agent)
python3 main.py
```

### Frontend
```bash
cd frontend && npm install
npm run dev -- --host 0.0.0.0 --port 5173   # dev server (UI at http://localhost:5173)
npm run build                                  # production build
npm run preview                                # preview build
```

### Full Stack via Script
```bash
./run.sh    # orchestrates environment setup; edit for env vars
```

### Tests
No automated test runner. Tests are JSON datasets validated manually against expected state:
- `test/stageA/` — location extraction
- `test/stageB/stageB_hard_filter_update_summary.json` — hard-filter state transitions (run sequentially, not isolated)
- `test/stageC/stageC_cases.json` — ranking quality

---

## Architecture

### Request Flow

```
User Input
  → [route_node]         LLM intent classification (search / QA / page_nav / chitchat / direct_reply / fallback)
  → [skill node]         Dispatched by intent
  → [finalize_node]      Assemble reply text
  → SSE stream           Backend → Frontend
```

The graph is built in `agent_graph/graph.py` with conditional edges. A legacy non-LangGraph fallback (`_legacy_process_turn`) exists in `agent/workflow.py` for when LangGraph fails to import.

### Search Pipeline (4 Stages)

| Stage | File | What it does |
|-------|------|-------------|
| A: Retrieval | `skills/search/engine.py` | Location extraction → Qdrant vector search (default: 1000 recall) |
| B: Hard Filter | `skills/search/handler.py` | Apply budget, bedrooms, bathrooms, furnishing, let_type, tenancy constraints |
| C: Soft Rank | `skills/search/handler.py` | Deposit, freshness, unknown-field penalties, semantic preference reranking |
| D: Explain | `skills/search/handler.py` | Grounded summary + risk flags per listing |

### Dual LLM Clients

`core/llm_client.py` exposes two OpenAI-compatible clients against vLLM:
- **`qwen_client`** — reasoning (extraction, QA, explanation)
- **`router_client`** — intent routing (may point to same or lighter model)

Both endpoints/models are independently configured via env vars.

### Constraint State

`AgentState` (in `agent/state.py`) persists across turns:
- `constraints` — hard filter dict (budget, bedrooms, layout_options, location_keywords, etc.)
- `user_profile` — semantic soft preferences
- `last_results` / `search_full_results` — current page vs full result set
- `snapshot_history` — MD5-keyed cache of prior searches
- `page_index` / `has_more` — pagination state

Constraint merging logic (`agent/merger.py`) handles two scopes driven by LLM output:
- `patch` — update only specified fields
- `replace_all` — replace entire constraint set

Location and layout each have independent update modes: `replace | append | keep`.

### Key Files

| File | Role |
|------|------|
| `core/chatbot_config.py` | All LLM system prompts (extraction, explanation, router) |
| `core/settings.py` | 20+ env-driven config values with defaults |
| `skills/search/extractors.py` | ~60 KB regex + rule engine for UK rental constraint extraction |
| `skills/search/handler.py` | ~60 KB multi-stage search pipeline implementation |
| `agent_graph/nodes.py` | LangGraph node implementations |
| `agent/router.py` | LLM-based intent classifier with few-shot examples |
| `backend/api_server.py` | FastAPI SSE streaming endpoint (`/api/chat`) |

---

## Configuration

All tunable parameters are env vars (see `run.sh` for defaults and `core/settings.py` for full list):

| Var | Default | Purpose |
|-----|---------|---------|
| `QWEN_BASE_URL` | `http://127.0.0.1:8002/v1` | Reasoning LLM endpoint |
| `QWEN_MODEL` | `./Qwen3-14B` | Model name |
| `ROUTER_BASE_URL` | same as QWEN | Routing LLM endpoint |
| `RENT_QDRANT_PATH` | — | Qdrant DB directory |
| `RENT_QDRANT_COLLECTION` | `rent_listings` | Collection name |
| `RENT_RECALL` | `1000` | Vector search recall count |
| `RENT_K` | `5` | Listings per page |
| `RENT_STRUCTURED_POLICY` | `RULE_FIRST` | `RULE_FIRST \| HYBRID \| LLM_FIRST` |
| `ROUTER_DEBUG` | `0` | Print routing decisions |
| `RENT_STAGEA_TRACE` | `0` | Verbose retrieval trace |
| `RENT_STRUCTURED_DEBUG_PRINT` | `0` | Constraint extraction debug |

---

## Frontend

Vite proxies `/api/*` → `http://127.0.0.1:8000`. Chat sessions persist to localStorage. The UI handles SSE chunked streaming and exposes a stop-generation button.

---

## Git Conventions

- Do **not** add `Co-Authored-By` trailers to commit messages.
- Always commit to the **`restructure`** branch (worktree at `.claude/worktrees/gracious-clarke`).
