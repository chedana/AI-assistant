#!/usr/bin/env python3
"""
Backfill gallery images for OpenRent-only listings in Qdrant Cloud.

The original crawl stored only a logo URL in image_urls. This script:
1. Scrolls all OpenRent-only points from Qdrant
2. Fetches each listing page
3. Extracts gallery images from the HTML (Swiper carousel)
4. Updates the Qdrant point payload with real image_urls

Usage:
    python3 backfill_openrent_images.py [--dry-run] [--limit N]
"""
import argparse
import json
import os
import random
import re
import time
from typing import List

import httpx
from bs4 import BeautifulSoup
from qdrant_client import QdrantClient

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
QDRANT_URL = os.environ.get(
    "RENT_QDRANT_URL",
    "https://725a9b5a-2732-448b-b094-a06577cfe7bd.europe-west3-0.gcp.cloud.qdrant.io",
)
QDRANT_API_KEY = os.environ.get(
    "RENT_QDRANT_API_KEY",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhY2Nlc3MiOiJtIn0.SXmYVOqGgBvuGR-I60m7U4wKUT2zQ-eopChFhO3iVns",
)
COLLECTION = os.environ.get("RENT_QDRANT_COLLECTION", "rent_listings")
MAX_IMAGES = 10
REQUEST_DELAY = 0.5  # seconds between requests

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]

# ---------------------------------------------------------------------------
# Image extraction (standalone — no dependency on extract_openrent.py)
# ---------------------------------------------------------------------------
def extract_gallery(html: str) -> List[str]:
    """Extract gallery image URLs from OpenRent listing HTML."""
    soup = BeautifulSoup(html, "html.parser")
    images: list[str] = []
    seen: set[str] = set()

    def add(url: str) -> None:
        if not url or url in seen:
            return
        if url.startswith("//"):
            url = "https:" + url
        if "imagescdn.openrent" not in url.lower():
            return
        if "staticmapphoto" in url.lower():
            return
        seen.add(url)
        images.append(url)

    # Strategy 1: og:image meta
    og = soup.find("meta", property="og:image")
    if og and og.get("content"):
        add(og["content"])

    # Strategy 2: img tags with imagescdn src
    for img in soup.find_all("img", src=re.compile(r"imagescdn\.openrent", re.I)):
        add(img["src"])

    # Strategy 3: data-src (lazy-loaded)
    for img in soup.find_all("img", attrs={"data-src": re.compile(r"imagescdn\.openrent", re.I)}):
        add(img["data-src"])

    # Strategy 4: anchor hrefs (lightbox full-size)
    for a in soup.find_all("a", href=re.compile(r"imagescdn\.openrent", re.I)):
        add(a["href"])

    # Strategy 5: inline JS
    for script in soup.find_all("script"):
        text = script.get_text()
        if "imagescdn" in text:
            urls = re.findall(
                r'(?:https:)?//imagescdn\.openrent\.co\.uk/listings/[^\s\'"]+',
                text,
            )
            for u in urls:
                add(u)

    # Filter thumbnails, prefer full-size
    full = [u for u in images if "_homepage" not in u and "_thumb" not in u]
    return (full if full else images)[:MAX_IMAGES]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Backfill OpenRent gallery images")
    parser.add_argument("--dry-run", action="store_true", help="Don't update Qdrant")
    parser.add_argument("--limit", type=int, default=0, help="Max listings to process (0=all)")
    args = parser.parse_args()

    print(f"[backfill] Connecting to Qdrant: {QDRANT_URL}")
    qd = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)
    info = qd.get_collection(COLLECTION)
    print(f"[backfill] Collection {COLLECTION}: {info.points_count} points")

    # Scroll through ALL points, filter OpenRent-only client-side
    targets = []
    offset = None
    batch_size = 100
    while True:
        pts, offset = qd.scroll(
            COLLECTION,
            limit=batch_size,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        for p in pts:
            src = p.payload.get("source_site", "")
            if src == "openrent":
                raw = p.payload.get("image_urls")
                has_real_gallery = False
                if raw:
                    try:
                        parsed = json.loads(raw) if isinstance(raw, str) else raw
                    except (json.JSONDecodeError, TypeError):
                        parsed = []
                    has_real_gallery = any("imagescdn" in u for u in (parsed or []))
                if not has_real_gallery:
                    url = p.payload.get("url", "")
                    if url and "openrent.co.uk" in url:
                        targets.append((p.id, url))
        if offset is None:
            break
        print(f"  scanned... {len(targets)} targets so far", end="\r")

    print(f"\n[backfill] Found {len(targets)} OpenRent listings needing gallery backfill")
    if args.limit:
        targets = targets[: args.limit]
        print(f"[backfill] Limited to {len(targets)}")

    if not targets:
        print("[backfill] Nothing to do.")
        return

    http = httpx.Client(
        headers={"User-Agent": random.choice(USER_AGENTS)},
        follow_redirects=True,
        timeout=30,
    )

    updated = 0
    failed = 0
    skipped = 0

    for i, (point_id, listing_url) in enumerate(targets):
        try:
            resp = http.get(listing_url)
            if resp.status_code == 410:
                print(f"  [{i+1}/{len(targets)}] GONE (410): {listing_url}")
                skipped += 1
                continue
            resp.raise_for_status()

            gallery = extract_gallery(resp.text)
            if not gallery:
                print(f"  [{i+1}/{len(targets)}] no images: {listing_url}")
                skipped += 1
                continue

            if args.dry_run:
                print(f"  [{i+1}/{len(targets)}] DRY RUN: {len(gallery)} imgs — {listing_url}")
            else:
                qd.set_payload(
                    collection_name=COLLECTION,
                    payload={"image_urls": gallery},
                    points=[point_id],
                )
                print(f"  [{i+1}/{len(targets)}] OK {len(gallery)} imgs — {listing_url}")
            updated += 1

        except Exception as e:
            print(f"  [{i+1}/{len(targets)}] ERROR: {e} — {listing_url}")
            failed += 1

        time.sleep(REQUEST_DELAY)

    http.close()
    print(f"\n[backfill] Done: {updated} updated, {skipped} skipped, {failed} failed")


if __name__ == "__main__":
    main()
