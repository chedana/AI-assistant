"""
sync_qdrant.py
--------------
Sync crawled Rightmove listings (JSONL) into Qdrant Cloud.

Modes:
  --mode full   Drop + recreate collection, embed + upsert everything.
  --mode sync   Incremental: add new listings, delete removed ones, skip unchanged.

Usage:
  # First time (full rebuild):
  python crawler/sync_qdrant.py --mode full

  # Subsequent runs (incremental):
  python crawler/sync_qdrant.py --mode sync

  # Explicit source file:
  python crawler/sync_qdrant.py --source crawler/artifacts/runs/run_XXX/properties_final.jsonl

Env vars required:
  RENT_QDRANT_URL       Qdrant Cloud cluster URL
  RENT_QDRANT_API_KEY   Qdrant Cloud API key
  RENT_EMBED_MODEL      (optional, default: sentence-transformers/all-MiniLM-L6-v2)
"""

import argparse
import json
import os
import re
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastembed import TextEmbedding
from qdrant_client import QdrantClient, models

# ── Path setup ──────────────────────────────────────────────────
CRAWLER_DIR = Path(__file__).parent.resolve()
PROJECT_ROOT = CRAWLER_DIR.parent.resolve()
sys.path.insert(0, str(CRAWLER_DIR))

from geo_utils import extract_postcode_district, get_regions_for_district

# ── Config ──────────────────────────────────────────────────────
COLLECTION = os.environ.get("RENT_QDRANT_COLLECTION", "rent_listings")
QDRANT_URL = os.environ.get("RENT_QDRANT_URL", "")
QDRANT_API_KEY = os.environ.get("RENT_QDRANT_API_KEY", "")
EMBED_MODEL = os.environ.get("RENT_EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
VECTOR_DIM = 384  # all-MiniLM-L6-v2 output dimension
BATCH_SIZE = 100
# Deterministic namespace for uuid5
_UUID_NS = uuid.UUID("a3b2c1d0-e5f6-7890-abcd-ef1234567890")

# Fields to store in Qdrant payload (everything the search pipeline needs)
PAYLOAD_FIELDS = [
    # Identity
    "listing_id", "url", "source_site", "source", "scraped_at",
    # Media
    "image_url",
    # Location
    "address", "postcode", "postcode_district", "title",
    # Price
    "price_pcm", "price_pw", "price_display",
    # Property
    "bedrooms", "bathrooms", "property_type", "size_sqm", "size_sqft",
    # Terms
    "deposit", "deposit_amount", "available_from", "min_tenancy",
    "let_type", "furnish_type", "council_tax",
    # Text
    "description", "features", "stations", "schools",
    # Coordinates
    "latitude", "longitude",
    # Metadata
    "added_date", "discovery_paths",
    # OpenRent-exclusive / merged fields
    "max_tenants",
    "bills_included", "student_friendly", "families_allowed",
    "pets_allowed", "smokers_allowed", "dss_covers_rent",
    "garden", "parking", "fireplace", "epc_rating", "epc_not_required",
    "online_viewings", "live_in_landlord", "dss_income_accepted",
    "openrent_url",
]

# Payload indexes for location prefiltering
KEYWORD_INDEX_FIELDS = [
    "location_postcode_tokens",
    "location_station_tokens",
    "location_region_tokens",
    "location_tokens",
]


# ══════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════

def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def listing_id_to_uuid(lid: str) -> str:
    """Deterministic UUID from listing_id string."""
    return str(uuid.uuid5(_UUID_NS, lid))


def build_location_tokens(rec: Dict[str, Any]) -> Dict[str, List[str]]:
    """Generate location token lists for Qdrant payload indexing."""
    tokens: Dict[str, List[str]] = {
        "postcode": [], "station": [], "region": [], "all": [],
    }

    # Postcode tokens
    pc = (rec.get("postcode") or "").replace(" ", "").lower()
    district = (rec.get("postcode_district") or "").lower()
    if not district and rec.get("address"):
        d = extract_postcode_district(rec["address"])
        if d:
            district = d.lower()
    if pc:
        tokens["postcode"].append(pc)
    if district:
        tokens["postcode"].append(district)

    # Region tokens (postcode district → mental regions → slugs)
    regions = get_regions_for_district(district.upper()) if district else []
    for r in regions:
        slug = slugify(r)
        tokens["region"].extend([slug, f"{slug}_london"])

    # Station tokens (from stations JSON)
    stations_raw = rec.get("stations") or "[]"
    if isinstance(stations_raw, str):
        try:
            stations_list = json.loads(stations_raw)
        except json.JSONDecodeError:
            stations_list = []
    else:
        stations_list = stations_raw

    for s in (stations_list or []):
        name = s.get("name", "") if isinstance(s, dict) else str(s)
        if not name:
            continue
        slug = slugify(name)
        tokens["station"].append(name.lower())
        if slug:
            tokens["station"].append(slug)
            if not slug.endswith("_station"):
                tokens["station"].append(f"{slug}_station")

    # Deduplicate each category
    for k in tokens:
        tokens[k] = list(dict.fromkeys(x for x in tokens[k] if x))

    # Build catch-all
    tokens["all"] = list(dict.fromkeys(
        tokens["postcode"] + tokens["station"] + tokens["region"]
    ))
    return tokens


def build_embed_text(rec: Dict[str, Any]) -> str:
    """Build text for embedding from listing fields."""
    parts = []
    if rec.get("title"):
        parts.append(str(rec["title"]))
    if rec.get("address"):
        parts.append(str(rec["address"]))
    desc = str(rec.get("description") or "")
    if desc:
        parts.append(desc[:300])
    if rec.get("features"):
        parts.append(str(rec["features"])[:200])

    # Append human-readable amenity tags from OpenRent boolean fields
    amenities = []
    bool_labels = [
        ("pets_allowed",     "pets allowed"),
        ("garden",           "garden"),
        ("parking",          "parking"),
        ("fireplace",        "fireplace"),
        ("bills_included",   "bills included"),
        ("student_friendly", "student friendly"),
        ("families_allowed", "families allowed"),
        ("dss_covers_rent",  "DSS accepted"),
    ]
    for field, label in bool_labels:
        val = rec.get(field)
        if val is True:
            amenities.append(label)
    if amenities:
        parts.append("Amenities: " + ", ".join(amenities))
    if rec.get("epc_rating"):
        parts.append(f"EPC rating {rec['epc_rating']}")

    return " ".join(parts) if parts else "rental listing"


def build_payload(rec: Dict[str, Any], loc_tokens: Dict[str, List[str]]) -> Dict[str, Any]:
    """Build Qdrant payload from JSONL record + location tokens."""
    payload: Dict[str, Any] = {}
    for field in PAYLOAD_FIELDS:
        if field in rec:
            payload[field] = rec[field]

    # Inject location tokens
    payload["location_postcode_tokens"] = loc_tokens["postcode"]
    payload["location_station_tokens"] = loc_tokens["station"]
    payload["location_region_tokens"] = loc_tokens["region"]
    payload["location_tokens"] = loc_tokens["all"]

    return payload


# ══════════════════════════════════════════════════════════════════
# Qdrant operations
# ══════════════════════════════════════════════════════════════════

def connect_qdrant() -> QdrantClient:
    if not QDRANT_URL:
        print("[ERROR] RENT_QDRANT_URL not set.")
        sys.exit(1)
    client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY or None)
    print(f"Connected to Qdrant: {QDRANT_URL}")
    return client


def create_collection(client: QdrantClient):
    """Create collection with vector config + payload indexes."""
    if client.collection_exists(COLLECTION):
        client.delete_collection(COLLECTION)
        print(f"Deleted existing collection: {COLLECTION}")

    client.create_collection(
        collection_name=COLLECTION,
        vectors_config=models.VectorParams(
            size=VECTOR_DIM,
            distance=models.Distance.COSINE,
        ),
    )
    print(f"Created collection: {COLLECTION} (dim={VECTOR_DIM}, cosine)")

    # Create payload indexes for location prefiltering
    for field in KEYWORD_INDEX_FIELDS:
        client.create_payload_index(
            collection_name=COLLECTION,
            field_name=field,
            field_schema=models.PayloadSchemaType.KEYWORD,
        )
        print(f"  Created index: {field}")


def fetch_existing_ids(client: QdrantClient) -> Dict[str, str]:
    """Scroll all points and return {listing_id: point_uuid}."""
    existing: Dict[str, str] = {}
    offset = None
    while True:
        points, offset = client.scroll(
            collection_name=COLLECTION,
            limit=500,
            offset=offset,
            with_payload=["listing_id"],
            with_vectors=False,
        )
        for p in points:
            lid = (p.payload or {}).get("listing_id", "")
            if lid:
                existing[lid] = p.id
        if offset is None:
            break
    return existing


# ══════════════════════════════════════════════════════════════════
# Main sync logic
# ══════════════════════════════════════════════════════════════════

def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    print(f"Loaded {len(records):,} records from {path.name}")
    return records


def find_latest_source() -> Path:
    """Find the latest properties_final.jsonl from crawler runs."""
    runs_dir = CRAWLER_DIR / "artifacts" / "runs"
    if not runs_dir.exists():
        print(f"[ERROR] No runs directory: {runs_dir}")
        sys.exit(1)
    runs = sorted(runs_dir.glob("run_*"))
    if not runs:
        print("[ERROR] No crawl runs found.")
        sys.exit(1)
    latest = runs[-1]
    source = latest / "properties_final.jsonl"
    if not source.exists():
        print(f"[ERROR] {source} not found. Run the crawler first.")
        sys.exit(1)
    print(f"Using latest run: {latest.name}")
    return source


def sync_full(client: QdrantClient, records: List[Dict[str, Any]], embedder: TextEmbedding):
    """Full rebuild: drop collection, recreate, embed + upsert all."""
    create_collection(client)

    # Prepare all embed texts
    embed_texts = [build_embed_text(r) for r in records]

    total = len(records)
    upserted = 0
    for i in range(0, total, BATCH_SIZE):
        batch_recs = records[i:i + BATCH_SIZE]
        batch_texts = embed_texts[i:i + BATCH_SIZE]

        # Batch embed
        vectors = list(embedder.embed(batch_texts))

        points = []
        for rec, vec in zip(batch_recs, vectors):
            lid = rec.get("listing_id", "")
            if not lid:
                continue
            loc_tokens = build_location_tokens(rec)
            payload = build_payload(rec, loc_tokens)
            points.append(models.PointStruct(
                id=listing_id_to_uuid(lid),
                vector=vec.tolist(),
                payload=payload,
            ))

        if points:
            client.upsert(collection_name=COLLECTION, points=points)
            upserted += len(points)
            print(f"  Upserted {upserted:,}/{total:,}", end="\r")

    print(f"\nFull sync complete: {upserted:,} points upserted")


def sync_incremental(client: QdrantClient, records: List[Dict[str, Any]], embedder: TextEmbedding):
    """Incremental sync: add new, delete removed, skip unchanged."""
    if not client.collection_exists(COLLECTION):
        print("Collection does not exist — falling back to full sync.")
        return sync_full(client, records, embedder)

    # 1. Fetch existing listing_ids from Qdrant
    print("Fetching existing IDs from Qdrant...")
    existing = fetch_existing_ids(client)
    print(f"  Existing points: {len(existing):,}")

    # 2. Build set of new listing_ids
    new_ids: Dict[str, Dict[str, Any]] = {}
    for rec in records:
        lid = rec.get("listing_id", "")
        if lid:
            new_ids[lid] = rec

    # 3. Compute delta
    existing_set = set(existing.keys())
    new_set = set(new_ids.keys())
    to_add = new_set - existing_set
    to_remove = existing_set - new_set
    unchanged = existing_set & new_set

    print(f"\n  Delta: +{len(to_add):,} new | -{len(to_remove):,} removed | ={len(unchanged):,} unchanged")

    # 4. Delete removed listings
    if to_remove:
        remove_uuids = [existing[lid] for lid in to_remove]
        # Delete in batches
        for i in range(0, len(remove_uuids), BATCH_SIZE):
            batch = remove_uuids[i:i + BATCH_SIZE]
            client.delete(
                collection_name=COLLECTION,
                points_selector=models.PointIdsList(points=batch),
            )
        print(f"  Deleted {len(to_remove):,} removed listings")

    # 5. Embed + upsert new listings
    if to_add:
        add_recs = [new_ids[lid] for lid in to_add]
        add_texts = [build_embed_text(r) for r in add_recs]

        upserted = 0
        for i in range(0, len(add_recs), BATCH_SIZE):
            batch_recs = add_recs[i:i + BATCH_SIZE]
            batch_texts = add_texts[i:i + BATCH_SIZE]
            vectors = list(embedder.embed(batch_texts))

            points = []
            for rec, vec in zip(batch_recs, vectors):
                lid = rec.get("listing_id", "")
                if not lid:
                    continue
                loc_tokens = build_location_tokens(rec)
                payload = build_payload(rec, loc_tokens)
                points.append(models.PointStruct(
                    id=listing_id_to_uuid(lid),
                    vector=vec.tolist(),
                    payload=payload,
                ))

            if points:
                client.upsert(collection_name=COLLECTION, points=points)
                upserted += len(points)
                print(f"  Upserted {upserted:,}/{len(to_add):,}", end="\r")

        print(f"\n  Added {upserted:,} new listings")

    # 6. Summary
    final_info = client.get_collection(COLLECTION)
    print(f"\nSync complete. Collection: {final_info.points_count:,} points")


def purge_stale(client: QdrantClient, days: int):
    """Delete listings whose scraped_at is older than `days` days ago."""
    from datetime import datetime, timedelta, timezone

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    cutoff_str = cutoff.strftime("%Y-%m-%dT%H:%M:%S")
    print(f"Purging listings with scraped_at before {cutoff_str} ({days} days ago)...")

    if not client.collection_exists(COLLECTION):
        print("[WARN] Collection does not exist, nothing to purge.")
        return

    # Scroll all points and check scraped_at
    stale_ids: list[str] = []
    offset = None
    while True:
        points, offset = client.scroll(
            collection_name=COLLECTION,
            limit=500,
            offset=offset,
            with_payload=["scraped_at", "listing_id"],
            with_vectors=False,
        )
        for p in points:
            scraped = (p.payload or {}).get("scraped_at", "")
            if not scraped:
                continue
            # scraped_at is ISO string like "2025-06-15T10:30:00"
            if str(scraped) < cutoff_str:
                stale_ids.append(str(p.id))
        if offset is None:
            break

    if not stale_ids:
        print("  No stale listings found.")
        return

    # Delete in batches
    for i in range(0, len(stale_ids), BATCH_SIZE):
        batch = stale_ids[i:i + BATCH_SIZE]
        client.delete(
            collection_name=COLLECTION,
            points_selector=models.PointIdsList(points=batch),
        )

    final_info = client.get_collection(COLLECTION)
    print(f"  Purged {len(stale_ids):,} stale listings. Collection: {final_info.points_count:,} points")


# ══════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Sync crawled listings to Qdrant Cloud")
    parser.add_argument("--mode", choices=["full", "sync"], default=None,
                        help="full = drop + rebuild | sync = incremental (default)")
    parser.add_argument("--source", type=str, default=None,
                        help="Path to properties_final.jsonl (default: latest crawl run)")
    parser.add_argument("--purge-days", type=int, default=None,
                        help="Delete listings with scraped_at older than N days")
    args = parser.parse_args()

    # Must specify --mode or --purge-days (or both)
    if args.mode is None and args.purge_days is None:
        args.mode = "sync"  # default when neither is specified

    # Connect
    client = connect_qdrant()

    # Run sync if --mode is specified
    if args.mode is not None:
        # Find source JSONL
        if args.source:
            source_path = Path(args.source)
            if not source_path.exists():
                print(f"[ERROR] Source file not found: {source_path}")
                sys.exit(1)
        else:
            source_path = find_latest_source()

        # Load data
        records = load_jsonl(source_path)
        if not records:
            print("[ERROR] No records to sync.")
            sys.exit(1)

        # Load embedder
        print(f"Loading embedding model: {EMBED_MODEL}")
        embedder = TextEmbedding(EMBED_MODEL)

        # Sync
        if args.mode == "full":
            sync_full(client, records, embedder)
        else:
            sync_incremental(client, records, embedder)

    # Run purge if --purge-days is specified
    if args.purge_days is not None:
        purge_stale(client, args.purge_days)

    # Rebuild location match index after any Qdrant changes
    if args.mode is not None or args.purge_days is not None:
        print("\nRebuilding location match index...")
        sys.path.insert(0, str(PROJECT_ROOT))
        from skills.search.location_match import rebuild_location_index
        rebuild_location_index()


if __name__ == "__main__":
    main()
