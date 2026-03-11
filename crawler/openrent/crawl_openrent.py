"""
OpenRent London crawler.

Collects all London rental listings from OpenRent and writes a JSONL file
in the same format as the Rightmove crawler output, ready for sync_qdrant.py.

Usage:
    python -m crawler.openrent.crawl_openrent [--workers 8] [--output PATH] [--dry-run]

Output:
    crawler/artifacts/openrent/properties_final.jsonl
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from crawler.openrent.extract_openrent import extract_listing, fetch_listing, HEADERS

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE_URL = "https://www.openrent.co.uk"
SEARCH_URL = "https://www.openrent.co.uk/properties-to-rent/london"
PAGE_SIZE = 20          # OpenRent shows 20 listings per page
MAX_PAGES = 400         # Safety cap (~8,000 listings)
DEFAULT_WORKERS = 8
DELAY_BETWEEN_REQUESTS = 0.5   # seconds between requests per worker
ARTIFACTS_DIR = Path(__file__).resolve().parents[2] / "crawler" / "artifacts" / "openrent"


# ---------------------------------------------------------------------------
# URL collection
# ---------------------------------------------------------------------------

def _collect_urls_page(skip: int, client: httpx.Client) -> list[str]:
    """Fetch one search results page and return listing URLs found."""
    params = {"skip": skip} if skip > 0 else {}
    try:
        resp = client.get(SEARCH_URL, params=params, timeout=20)
        resp.raise_for_status()
    except Exception as e:
        print(f"  [warn] failed to fetch skip={skip}: {e}", file=sys.stderr)
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    urls = []
    for a in soup.find_all("a", href=re.compile(r"^/property-to-rent/")):
        href = a["href"].strip()
        # Only listing detail pages (have a numeric ID at the end)
        if re.search(r"/\d+\s*$", href):
            full_url = BASE_URL + href
            urls.append(full_url)

    return list(dict.fromkeys(urls))  # preserve order, deduplicate


def collect_all_urls(max_pages: int = MAX_PAGES) -> list[str]:
    """Paginate through all OpenRent London results and collect listing URLs."""
    print(f"[openrent] Collecting listing URLs (max {max_pages} pages)…")
    all_urls: list[str] = []
    seen: set[str] = set()

    with httpx.Client(headers=HEADERS, follow_redirects=True) as client:
        # First: find total count from page 1
        try:
            resp = client.get(SEARCH_URL, timeout=20)
            resp.raise_for_status()
            m = re.search(r"(\d[\d,]+)\s*properties?\s*found", resp.text, re.I)
            total = int(m.group(1).replace(",", "")) if m else None
            if total:
                print(f"[openrent] Total properties reported: {total:,}")
                pages = min(max_pages, (total // PAGE_SIZE) + 2)
            else:
                pages = max_pages
        except Exception as e:
            print(f"[openrent] Could not fetch page 1: {e}", file=sys.stderr)
            return []

        for page_idx in range(0, pages):
            skip = page_idx * PAGE_SIZE
            urls = _collect_urls_page(skip, client)
            if not urls:
                print(f"[openrent] No listings at skip={skip}, stopping.")
                break

            new_count = 0
            for url in urls:
                if url not in seen:
                    seen.add(url)
                    all_urls.append(url)
                    new_count += 1

            print(f"  skip={skip:4d} → {len(urls)} listings, {new_count} new | total: {len(all_urls)}")

            if new_count == 0:
                print("[openrent] No new URLs on this page — stopping pagination.")
                break

            time.sleep(DELAY_BETWEEN_REQUESTS)

    print(f"[openrent] Collected {len(all_urls):,} unique listing URLs.")
    return all_urls


# ---------------------------------------------------------------------------
# Detail extraction
# ---------------------------------------------------------------------------

def _scrape_one(url: str) -> Optional[dict]:
    """Fetch and extract a single listing. Returns dict or None on failure."""
    try:
        html = fetch_listing(url)
        rec = extract_listing(html, url)
        d = asdict(rec)
        # Attach image_urls if present (added as __dict__ extra in extractor)
        if hasattr(rec, "__dict__") and "image_urls" in rec.__dict__:
            d["image_urls"] = rec.__dict__["image_urls"]
        # Add discovery_paths (parallel to Rightmove format)
        d["discovery_paths"] = ["openrent:london"]
        return d
    except Exception as e:
        print(f"  [error] {url}: {e}", file=sys.stderr)
        return None


def scrape_listings(
    urls: list[str],
    workers: int = DEFAULT_WORKERS,
    dry_run: bool = False,
) -> list[dict]:
    """Parallel extraction of all listing detail pages."""
    if dry_run:
        print(f"[openrent] DRY RUN — would scrape {len(urls)} listings")
        return []

    print(f"[openrent] Scraping {len(urls):,} listings with {workers} workers…")
    results: list[dict] = []
    failed = 0

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_scrape_one, url): url for url in urls}
        for i, future in enumerate(as_completed(futures), 1):
            rec = future.result()
            if rec:
                results.append(rec)
            else:
                failed += 1
            if i % 50 == 0 or i == len(urls):
                print(f"  scraped {i}/{len(urls)} | ok={len(results)} failed={failed}")

    print(f"[openrent] Done. {len(results):,} successful, {failed} failed.")
    return results


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def write_jsonl(records: list[dict], output_path: Path) -> None:
    """Write records to JSONL file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
    print(f"[openrent] Written {len(records):,} records → {output_path}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Crawl OpenRent London listings")
    parser.add_argument("--workers",  type=int, default=DEFAULT_WORKERS, help="Parallel scrape workers")
    parser.add_argument("--max-pages", type=int, default=MAX_PAGES, help="Max search result pages")
    parser.add_argument("--output",   default=str(ARTIFACTS_DIR / "properties_final.jsonl"))
    parser.add_argument("--urls-only", action="store_true", help="Only collect URLs, don't scrape details")
    parser.add_argument("--dry-run",  action="store_true", help="Collect URLs but skip scraping")
    parser.add_argument("--limit",    type=int, default=0, help="Limit number of listings to scrape (0=all)")
    args = parser.parse_args()

    start = datetime.utcnow()
    output_path = Path(args.output)

    # Step 1: collect URLs
    urls = collect_all_urls(max_pages=args.max_pages)

    if args.urls_only:
        url_file = output_path.parent / "listing_urls.txt"
        url_file.parent.mkdir(parents=True, exist_ok=True)
        url_file.write_text("\n".join(urls))
        print(f"[openrent] URLs written to {url_file}")
        return

    if args.limit:
        urls = urls[: args.limit]
        print(f"[openrent] Limited to {len(urls)} listings (--limit)")

    # Step 2: scrape details
    records = scrape_listings(urls, workers=args.workers, dry_run=args.dry_run)

    # Step 3: write output
    if records:
        write_jsonl(records, output_path)

    elapsed = (datetime.utcnow() - start).total_seconds()
    print(f"[openrent] Total time: {elapsed:.0f}s")


if __name__ == "__main__":
    main()
