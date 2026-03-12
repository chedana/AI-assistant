# OpenRent Re-Crawl Task — Session Handoff

## Context

This session needs to re-crawl OpenRent listings using the improved two-step workflow that separates URL collection from detail scraping. This allows resuming from failures without re-paginating.

## Required Reading

1. **CLAUDE.md** — project overview, architecture, commands, git conventions (auto-loaded)
2. **TODO.md** — the re-crawl task with the two-step --urls-only / --from-file workflow
3. **DEV_PROGRESS.md** — current state of the data pipeline
4. **crawler/openrent/crawl_openrent.py** — the crawler with the new flags
5. **crawler/openrent/extract_openrent.py** — the extractor (to understand/fix any scraping bugs)
6. **crawler/openrent/merge_listings.py** — the merge pipeline to run after crawl
7. **crawler/sync_qdrant.py** — the sync pipeline to run last

## Task: Re-Crawl OpenRent

### Two-Step Workflow

**Step 1: Collect URLs only** (fast, ~10 min)
```bash
python -m crawler.openrent.crawl_openrent --urls-only
```
- Saves to: `crawler/artifacts/openrent/listing_urls.txt`
- No detail scraping, just pagination
- Can be interrupted and restarted safely

**Step 2: Scrape details from saved URLs**
```bash
python -m crawler.openrent.crawl_openrent --from-file crawler/artifacts/openrent/listing_urls.txt
```
- Reads URLs from file (skips pagination)
- Scrapes all listing details with rate limiting
- Outputs: `crawler/artifacts/openrent/properties_final.jsonl`
- If this fails due to scraping bugs, fix `extract_openrent.py` and re-run (URLs already saved)

**Step 3: Merge with Rightmove**
```bash
python -m crawler.openrent.merge_listings
```
- Merges OpenRent + Rightmove datasets
- Deduplicates cross-portal matches
- Outputs: `crawler/artifacts/merged/properties_merged.jsonl`

**Step 4: Sync to Qdrant Cloud**
```bash
python crawler/sync_qdrant.py --mode full --source crawler/artifacts/merged/properties_merged.jsonl
```
- Drops and recreates collection
- Embeds all listings
- Pushes to Qdrant Cloud

## Current State

- **Qdrant Cloud**: 31,820 listings (merged Rightmove + OpenRent from previous crawl)
- **Local data**: 26,191 Rightmove + 6,539 OpenRent (old, not yet merged with new workflow)
- **Goal**: Fresh crawl with latest OpenRent data using the new two-step workflow

## Rate Limiting Strategy

The crawler already has:
- User agent rotation (5 different browsers/OSes)
- Exponential backoff (10s → 160s on 429 errors)
- 3s delay between search pages
- 2s delay between detail requests
- 2 workers (reduced from 8)

If you still hit 429s, increase `DELAY_BETWEEN_PAGES` and `DELAY_BETWEEN_REQUESTS` in `crawl_openrent.py`.

## Debugging Scraping Failures

If Step 2 fails with extraction errors:
1. Check the error output for the failing URL
2. Test manually: `python -m crawler.openrent.extract_openrent --url <URL>`
3. Fix the bug in `extract_openrent.py`
4. Re-run Step 2 with `--from-file` (no need to re-collect URLs)

## Git Workflow

After completing the crawl and sync:
1. Update `DEV_PROGRESS.md` with commit hashes
2. Update `PROJECT.md` with new listing count
3. Commit: `git commit -m "data: re-crawl OpenRent with <N> listings"`
4. Push: `git push origin openclaw`

**Important**: Do NOT commit the large JSONL files unless explicitly requested.

## Environment

- Branch: `openclaw`
- Python: 3.9+
- Required env vars: `RENT_QDRANT_URL`, `RENT_QDRANT_API_KEY` (already set)

## Questions?

Read the files listed above first. The code is well-documented with inline comments explaining the extraction logic and rate limiting strategy.
