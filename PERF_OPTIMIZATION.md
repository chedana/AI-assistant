# Performance Optimization: 52s → 1.2s

## Summary

End-to-end response time for a typical search query ("studio in Shoreditch") was reduced from **~52s to ~1.2s** (43x faster) through 7 optimizations across the LLM calls, execution pipeline, cold start, and streaming layers.

| Query Type | Before | After |
|---|---|---|
| Normal search (e.g. "studio in Shoreditch") | ~52s | **1.2s** |
| Sparse search with relax loop (e.g. "2 bed Hackney under 2000") | ~52s | **~2.2s** |
| Chitchat (e.g. "how are you") | ~10s | **0.69s** |

---

## Optimizations Applied

### 1. Eliminate unnecessary LLM call: domain_router (saved ~2s)

**Problem:** Every request started with an LLM call to `domain_router_node()` to classify the domain (e.g. "Rental" vs other). This single-tenant app only handles rentals, so the call always returned "Rental".

**Fix:** Hardcoded `domain = "Rental"` in `domain_router_node()`, skipping the LLM call entirely.

**Files:** `orchestration/nodes.py`

### 2. Switch routing model: gpt-5-nano → gpt-4o-mini (saved ~7s)

**Problem:** The intent router used `gpt-5-nano`, a reasoning model. It generated 640-700 chain-of-thought tokens internally just to produce a 60-token routing JSON, taking 8.65s per call.

**Fix:** Switched `ROUTER_MODEL` to `gpt-4o-mini`, a non-reasoning model. It produces the same routing JSON in 46 output tokens, taking 1.1-1.4s.

**Key insight:** Reasoning models (gpt-5-nano, o1, etc.) are overkill for classification tasks. They burn tokens on internal reasoning that adds latency without improving accuracy for simple intent routing.

**Files:** `.env`

### 3. Parallel LLM execution: router + refinement_plan (saved ~1.5s)

**Problem:** `route_node` (intent classification) and `refinement_plan` (constraint extraction planning) ran sequentially. Combined: ~2.5s.

**Fix:** Submit `refinement_plan` to a `ThreadPoolExecutor` at the start of `route_node`, run the intent router LLM call, then collect the plan result in `search_node` via `future.result()`. Both LLM calls run concurrently; total time = max(router, plan) ≈ 0.9s.

**Implementation detail:** LangGraph's `GraphState(TypedDict)` silently drops undeclared keys and cannot store `Future` objects. Solution: store the `Future` in a process-level `_SPEC_CACHE` dict and pass only a primitive int key (`_spec_key`) through `GraphState`.

**Files:** `orchestration/nodes.py` (route_node, search_node), `orchestration/state.py` (added `_spec_key` field)

### 4. Compress LLM prompts (saved ~0.3s)

**Problem:** Both the intent router and refinement_plan prompts were verbose, causing unnecessary input token processing and longer output generation.

**Fix:**
- **Refinement_plan prompt:** 798 → 349 input tokens, 113 → 28 output tokens
- **Intent router prompt:** 666 → 316 input tokens, 46 → 16 output tokens

Shorter prompts mean faster LLM inference (fewer tokens to process and generate).

**Files:** `orchestration/refinement_plan.py`, `orchestration/router.py`

### 5. Optimize SSE streaming (saved ~2s)

**Problem:** Backend streamed response text in 8-character chunks with 10ms delays between each. For a typical 300-char response, this meant ~37 chunks × 10ms = ~370ms of pure delay, plus overhead. Measured at ~2.3s total stream time.

**Fix:** Increased chunk size to 32 characters and reduced delay to 5ms. Streaming time dropped to ~0.3s.

**Files:** `backend/api_server.py`

### 6. Eager startup preload (saved ~0.6s on first request)

**Problem:** The sentence-transformer embedder and Qdrant client were initialized lazily on the first user request, adding ~0.6s to the first response.

**Fix:** Added `@app.on_event("startup")` handler that calls `get_runtime()` to load both at app startup.

**Files:** `backend/api_server.py`

### 7. Pre-compute location match index (saved ~9s on first request)

**Problem:** The location fuzzy-match system (`_build_location_match_index()`) scans every point in Qdrant to build a vocabulary of location names, slugs, and compact keys. This took ~9s on the first request, then was cached in-process. Every app restart paid this cost again on the first user query.

**Investigation:** Instrumented the search pipeline and isolated the bottleneck to `normalize_constraints()` → `_correct_location_keyword()` → `_get_location_match_index()` → `_build_location_match_index()`. The function itself is correct; the cost is from scrolling all Qdrant points and deserializing payloads.

**Fix:** Pre-compute the index to `artifacts/skills/search/data/location_index.json` after each Qdrant sync. At app startup, load from the JSON file (~ms). Falls back to building from Qdrant if the file doesn't exist.

**Files:** `skills/search/location_match.py` (added `rebuild_location_index()`, modified `_get_location_match_index()`), `crawler/sync_qdrant.py` (calls `rebuild_location_index()` after sync/purge), `backend/api_server.py` (removed warmup call)

---

## Final Time Budget (warm state, no relax)

```
max(router ~0.8s, refinement ~0.9s) = 0.9s   (parallel LLM calls)
qdrant_search                       = 0.2s
hard_filter + soft_rank             = 0.02s
evaluate_node                       = 0.01s
streaming                           = 0.3s
───────────────────────────────────────────
Total                               ≈ 1.2-1.5s
```

The LLM calls (router + refinement_plan) are now the dominant cost at ~0.9s. Further reduction would require faster models or eliminating one of the calls.

---

## Architecture: Parallel Execution Pattern

```
route_node:
  1. Submit refinement_plan to ThreadPoolExecutor → Future
  2. Store Future in process-level _SPEC_CACHE dict (NOT in LangGraph state)
  3. Store primitive int key (_spec_key) in GraphState
  4. Run intent_router LLM call concurrently
  5. Return routing decision

search_node:
  1. Pop _spec_key from state
  2. Pop Future from _SPEC_CACHE
  3. Call future.result() (usually instant — plan already finished during router)
  4. Use plan result to build constraints
  5. Call run_search_skill
```

---

## Model Configuration

```
QWEN_MODEL=gpt-4.1-mini     # reasoning/extraction (refinement_plan, QA, explain)
ROUTER_MODEL=gpt-4o-mini     # intent routing (fast, non-reasoning)
```

Do NOT use reasoning models (gpt-5-nano, o1, etc.) for routing — they generate hundreds of internal chain-of-thought tokens for a task that needs 16 output tokens.

---

## Future Optimization Opportunities

### Inverted index for location fuzzy matching (LOW priority)

The current fuzzy matcher in `expand_location_keyword_candidates()` does a brute-force scan over all entries × all aliases, computing edit distance and subsequence similarity for each. With ~500-1000 aliases this is fast (~ms), but if the vocabulary grows significantly (e.g. expanding beyond London), an n-gram inverted index would reduce the search space:

- **At index build time:** For each alias compact key (e.g. "shoreditch"), generate character n-grams ("sho", "hor", "ore", ...) and map each n-gram to a set of alias IDs.
- **At query time:** Look up the query's n-grams in the inverted index to get candidate aliases, then only score those few candidates with edit distance instead of scanning all aliases.

Not needed at current scale (~hundreds of London locations), but worth implementing if the system expands to multiple cities or thousands of locations.

### Reduce relax loop overhead (LOW priority)

When search results are sparse, `evaluate_node` triggers a relax loop (loosen budget +15%, remove furnish/let_type, etc.) which runs a second full search cycle adding ~1s. After cold start fix, sparse queries take ~2.2s total. Options to reduce:
- Tune `MIN_PAGES` threshold to avoid unnecessary relaxation
- Cache relaxed constraint mappings to skip redundant re-searches

### Precompute embeddings for common locations (NOT RECOMMENDED)

The embedder encodes the search query on every request (~0.05-0.1s). Could cache embeddings for common location names. Savings are marginal and not worth the cache invalidation complexity.
