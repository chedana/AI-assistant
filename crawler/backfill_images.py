"""
backfill_images.py — Fetch og:image URLs for existing Qdrant listings.

Scrolls all points, finds those missing image_url, fetches the listing page
via plain HTTP, extracts og:image, and updates the Qdrant payload in-place.

Usage:
    python3 crawler/backfill_images.py [--concurrency 20] [--dry-run]
"""
from __future__ import annotations

import argparse
import asyncio
import os
import re
import time
from typing import List, Tuple

import httpx
from qdrant_client import QdrantClient

COLLECTION = os.environ.get("RENT_QDRANT_COLLECTION", "rent_listings")
OG_IMAGE_RE = re.compile(r"""<meta\s+(?:property=['"]\s*og:image['"]\s+content=['"]([^'"]+)['"]|content=['"]([^'"]+)['"]\s+property=['"]\s*og:image['"])""", re.IGNORECASE)
BATCH_SIZE = 50


def get_client() -> QdrantClient:
    url = os.environ.get("RENT_QDRANT_URL", "")
    api_key = os.environ.get("RENT_QDRANT_API_KEY", "")
    if url and api_key:
        return QdrantClient(url=url, api_key=api_key)
    path = os.environ.get("RENT_QDRANT_PATH", "")
    return QdrantClient(path=path)


def scroll_missing(client: QdrantClient) -> List[Tuple]:
    """Return [(point_id, url), ...] for points missing image_url."""
    missing = []
    offset = None
    while True:
        points, offset = client.scroll(
            collection_name=COLLECTION, limit=500, offset=offset,
            with_payload=["url", "image_url"], with_vectors=False,
        )
        for p in points:
            pay = p.payload or {}
            if not pay.get("image_url"):
                url = pay.get("url", "")
                if url:
                    missing.append((p.id, url))
        if offset is None:
            break
    return missing


def extract_og_image(html: str) -> str:
    m = OG_IMAGE_RE.search(html)
    if m:
        return m.group(1) or m.group(2) or ""
    return ""


async def fetch_image_url(client_http: httpx.AsyncClient, url: str) -> str:
    try:
        resp = await client_http.get(url, follow_redirects=True, timeout=15)
        if resp.status_code == 200:
            return extract_og_image(resp.text)
    except Exception:
        pass
    return ""


async def backfill(concurrency: int, dry_run: bool):
    client = get_client()
    print(f"Connected to Qdrant. Collection: {COLLECTION}")

    missing = scroll_missing(client)
    print(f"Found {len(missing):,} points missing image_url")
    if not missing:
        return

    if dry_run:
        print("[DRY RUN] Would fetch and update. Exiting.")
        return

    sem = asyncio.Semaphore(concurrency)
    updated = 0
    failed = 0
    t0 = time.perf_counter()

    async with httpx.AsyncClient(
        headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"},
    ) as http:

        async def process(pid, url):
            nonlocal updated, failed
            async with sem:
                img = await fetch_image_url(http, url)
            if img:
                client.set_payload(
                    collection_name=COLLECTION,
                    payload={"image_url": img},
                    points=[pid],
                )
                updated += 1
            else:
                failed += 1
            done = updated + failed
            if done % 200 == 0:
                elapsed = time.perf_counter() - t0
                rate = done / elapsed if elapsed > 0 else 0
                print(f"  {done:,}/{len(missing):,}  ok={updated:,}  fail={failed:,}  {rate:.0f}/s")

        tasks = [process(pid, url) for pid, url in missing]
        await asyncio.gather(*tasks)

    elapsed = time.perf_counter() - t0
    print(f"\nDone. Updated {updated:,}, failed {failed:,}, took {elapsed:.0f}s")


def main():
    parser = argparse.ArgumentParser(description="Backfill image URLs in Qdrant")
    parser.add_argument("--concurrency", type=int, default=20)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    asyncio.run(backfill(args.concurrency, args.dry_run))


if __name__ == "__main__":
    main()
