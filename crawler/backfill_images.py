"""
backfill_images.py — Fetch gallery image URLs for existing Qdrant listings.

Scrolls all points, finds those missing image_urls (gallery), fetches the
Rightmove listing page via plain HTTP, extracts all gallery images from
window.PAGE_MODEL, and updates Qdrant payload in-place.

Stores:
  image_url   — cover photo (og:image, kept for backward compat)
  image_urls  — JSON array of up to MAX_IMAGES full-gallery URLs (size656x437)

Usage:
    python3 crawler/backfill_images.py [--concurrency 20] [--dry-run] [--limit N]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import time
from typing import List, Optional, Tuple

import httpx
from qdrant_client import QdrantClient

COLLECTION  = os.environ.get("RENT_QDRANT_COLLECTION", "rent_listings")
MAX_IMAGES  = 10
BATCH_SIZE  = 50

PAGE_MODEL_RE = re.compile(r"window\.PAGE_MODEL\s*=\s*(\{.+?\})\s*;?\s*\n", re.DOTALL)
OG_IMAGE_RE   = re.compile(
    r"""<meta\s+(?:property=['"]\s*og:image['"]\s+content=['"]([^'"]+)['"]"""
    r"""|content=['"]([^'"]+)['"]\s+property=['"]\s*og:image['"])""",
    re.IGNORECASE,
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


def get_client() -> QdrantClient:
    url     = os.environ.get("RENT_QDRANT_URL", "")
    api_key = os.environ.get("RENT_QDRANT_API_KEY", "")
    if url and api_key:
        return QdrantClient(url=url, api_key=api_key)
    path = os.environ.get("RENT_QDRANT_PATH", "")
    return QdrantClient(path=path)


def scroll_missing(client: QdrantClient, limit: Optional[int] = None) -> List[Tuple]:
    """Return [(point_id, url, existing_og_image), ...] for points missing image_urls."""
    missing = []
    offset  = None
    while True:
        points, offset = client.scroll(
            collection_name=COLLECTION,
            limit=500,
            offset=offset,
            with_payload=["url", "image_url", "image_urls"],
            with_vectors=False,
        )
        for p in points:
            pay = p.payload or {}
            # Skip if gallery already backfilled
            if pay.get("image_urls"):
                continue
            url = pay.get("url", "")
            if url:
                missing.append((p.id, url, pay.get("image_url", "")))
        if offset is None:
            break
        if limit and len(missing) >= limit:
            break
    if limit:
        missing = missing[:limit]
    return missing


def extract_gallery(html: str) -> Tuple[List[str], str]:
    """
    Returns (image_urls_list, og_image).
    image_urls_list: up to MAX_IMAGES gallery URLs (size656x437 or full URL).
    og_image: fallback cover photo from og:image meta.
    """
    og_image = ""
    m = OG_IMAGE_RE.search(html)
    if m:
        og_image = m.group(1) or m.group(2) or ""

    image_urls: List[str] = []
    pm = PAGE_MODEL_RE.search(html)
    if pm:
        try:
            data = json.loads(pm.group(1))
            images = data.get("propertyData", {}).get("images", [])
            for img in images[:MAX_IMAGES]:
                # Prefer 656x437 resized; fall back to full URL
                resized = img.get("resizedImageUrls") or {}
                url = (
                    resized.get("size656x437")
                    or resized.get("size476x317")
                    or img.get("url", "")
                )
                if url:
                    image_urls.append(url)
        except Exception:
            pass

    # If gallery extraction failed, at least include og:image
    if not image_urls and og_image:
        image_urls = [og_image]

    return image_urls, og_image


async def fetch_gallery(client_http: httpx.AsyncClient, url: str) -> Tuple[List[str], str]:
    """Fetch listing page and return (image_urls, og_image)."""
    # Strip fragment (e.g. #/?channel=RES_LET) — not needed for HTTP
    clean_url = url.split("#")[0].rstrip("/")
    try:
        resp = await client_http.get(clean_url, follow_redirects=True, timeout=15)
        if resp.status_code == 200:
            return extract_gallery(resp.text)
    except Exception:
        pass
    return [], ""


async def backfill(concurrency: int, dry_run: bool, limit: Optional[int]):
    client = get_client()
    print(f"Connected to Qdrant. Collection: {COLLECTION}")

    missing = scroll_missing(client, limit=limit)
    print(f"Found {len(missing):,} points missing image_urls gallery")
    if not missing:
        print("Nothing to do.")
        return

    if dry_run:
        print("[DRY RUN] Would fetch and update. Sample:")
        for pid, url, _ in missing[:3]:
            print(f"  {pid}  {url}")
        return

    sem     = asyncio.Semaphore(concurrency)
    updated = 0
    failed  = 0
    t0      = time.perf_counter()

    async with httpx.AsyncClient(headers=HEADERS) as http:

        async def process(pid, url, existing_og):
            nonlocal updated, failed
            async with sem:
                image_urls, og_image = await fetch_gallery(http, url)

            if image_urls:
                payload: dict = {"image_urls": json.dumps(image_urls)}
                # Backfill og cover photo too if missing
                if not existing_og and og_image:
                    payload["image_url"] = og_image
                client.set_payload(
                    collection_name=COLLECTION,
                    payload=payload,
                    points=[pid],
                )
                updated += 1
            else:
                failed += 1

            done = updated + failed
            if done % 100 == 0:
                elapsed = time.perf_counter() - t0
                rate    = done / elapsed if elapsed > 0 else 0
                print(
                    f"  {done:,}/{len(missing):,}  "
                    f"ok={updated:,}  fail={failed:,}  {rate:.1f}/s"
                )

        tasks = [process(pid, url, og) for pid, url, og in missing]
        await asyncio.gather(*tasks)

    elapsed = time.perf_counter() - t0
    print(f"\nDone. Updated {updated:,}, failed {failed:,}, took {elapsed:.0f}s")


def main():
    parser = argparse.ArgumentParser(description="Backfill gallery image URLs in Qdrant")
    parser.add_argument("--concurrency", type=int, default=20,
                        help="Concurrent HTTP requests (default 20)")
    parser.add_argument("--limit", type=int, default=None,
                        help="Process only first N missing listings (for testing)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be done without making changes")
    args = parser.parse_args()
    asyncio.run(backfill(args.concurrency, args.dry_run, args.limit))


if __name__ == "__main__":
    main()
