# TODO

> Tasks assigned by the lead session. Each session works through their section top-to-bottom.
> **When a task is done:** remove it from here and add a line to your session's Done section in `DEV_PROGRESS.md`.
> **When a task is deferred:** move it to the Deferred section below with a one-phrase reason.

---

## backend-1 — Orchestration & Search Pipeline
_Covers: `orchestration/`, `agent_graph/`, `agent/`, `skills/`, `core/`_

_No tasks assigned yet._

---

## backend-2 — API & Infrastructure
_Covers: `backend/api_server.py`, FastAPI endpoints, SSE streaming_

_No tasks assigned yet._

---

## frontend — UI
_Covers: `frontend/src/` — components, hooks, types, lib_

- [ ] UI Phase 2: map view

---

## test — Testing
_Covers: `test/`, manual test datasets, any automated test scripts_

_No tasks assigned yet._

---

## data — Data & Embeddings
_Covers: `crawler/`, `artifacts/`, Qdrant collection, embedding scripts_

_No tasks assigned yet._

---

## Deferred

| Task | Session | Reason |
|------|---------|--------|
| P2-B: location expansion when `prefilter_count == 0` | backend-1 | lat/lon now scraped — needs radius search logic in engine.py + Qdrant geo payload index |
