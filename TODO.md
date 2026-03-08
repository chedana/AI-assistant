# TODO

> Tasks assigned by the lead session. Each session works through their section top-to-bottom.
> **When a task is done:** remove it from here and add a line to your session's Done section in `DEV_PROGRESS.md`.
> **When a task is deferred:** move it to the Deferred section below with a one-phrase reason.
> **Product vision:** see `DEV_PROGRESS.md` → "Product Vision — The Full Renter Journey" for the full roadmap.

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

- [ ] UI Phase 2: map view (listing pins; lat/lon now available from scraper)

---

## test — Testing
_Covers: `test/`, manual test datasets, any automated test scripts_

_No tasks assigned yet._

---

## data — Data & Embeddings
_Covers: `crawler/`, `artifacts/`, Qdrant collection, embedding scripts_

- [ ] **Automate crawl + sync pipeline** — full plan at `.claude/plans/prancy-conjuring-torvalds.md`. Three deliverables:
  1. **`crawler/sync_qdrant.py`** — add `--purge-days N` flag + `purge_stale()` function (delete listings with `scraped_at` older than N days). After `sync_incremental()` ~line 388. Make `--mode` optional when `--purge-days` is provided.
  2. **`crawler/auto_crawl.sh`** (NEW) — sources `.env`, runs crawl → sync → purge → cleanup old runs, logs to `crawler/artifacts/crawl_automation.log` with 10MB rotation. Each step independent (one failure doesn't block the rest).
  3. **`crawler/setup_automation.sh`** (NEW) — `install` creates launchd plist at `~/Library/LaunchAgents/com.openclaw.crawl.plist` (Mon+Thu 3am), loads it. `uninstall` removes. `status` shows state + last 10 log lines.
  - **Test:** `bash crawler/auto_crawl.sh` end-to-end, then `bash crawler/setup_automation.sh install`, then `launchctl kickstart gui/$(id -u)/com.openclaw.crawl`
  - **Watch for:** Playwright browser path in launchd context — may need `PLAYWRIGHT_BROWSERS_PATH` in plist env vars
- [ ] **Re-crawl London with fixed scraper** — run `crawl_london.py` then `sync_qdrant.py --mode sync` to populate Qdrant Cloud with real London listings. (May be handled by the automation above once installed.)
- [ ] **Add OpenRent scraper** — private landlords, no agent fees. New `crawler/openrent.py`. Priority: Section 1 of product roadmap.

---

## Product Roadmap — Next Sections
_See full details in `DEV_PROGRESS.md` → Product Vision_

- [ ] **Section 3: Red flag detection** — rule engine on listing text (no DSS, upfront fees, no deposit protection). Quick win using existing LLM + listing data.
- [ ] **Section 4: Viewing checklist** — pre-viewing checklist (legal requirements + physical inspection + questions to ask). No new data needed.
- [ ] **Section 5: Contract analysis** — upload tenancy agreement → plain-English summary + clause flagging. Biggest differentiator.
- [ ] **Section 2: Area research** — commute (TfL API), crime (police API), average rents. Requires external API integrations.
- [ ] **Section 6: Tenant rights RAG** — index GOV.UK + Shelter guides + Renters Reform Act. Requires legal corpus pipeline.

---

## Deferred

| Task | Session | Reason |
|------|---------|--------|
| P2-B: location expansion when `prefilter_count == 0` | backend-1 | lat/lon now scraped — needs radius search logic in engine.py + Qdrant geo payload index |
