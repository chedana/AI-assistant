"""
merge_listings.py
-----------------
Merge Rightmove and OpenRent JSONL files into a single deduped dataset.

Strategy:
  - For duplicates (same property on both platforms):
      * Rightmove record is the base
      * OpenRent fills missing fields + provides its exclusive fields
      * source_site = "rightmove+openrent"
      * discovery_paths combines both
  - OpenRent-only listings: kept as-is (source_site = "openrent")
  - Rightmove-only listings: kept as-is (source_site = "rightmove")

Dedup criteria (ALL must match):
  - Haversine distance < 10 m
  - Same bedrooms (when both known)
  - Price within £100 pcm (when both known)

Usage:
    python -m crawler.openrent.merge_listings [--openrent PATH] [--rightmove PATH] [--output PATH]
"""
from __future__ import annotations

import json
import math
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS_DIR = PROJECT_ROOT / "crawler" / "artifacts"

DEFAULT_OPENRENT  = ARTIFACTS_DIR / "openrent"  / "properties_final.jsonl"
DEFAULT_RIGHTMOVE = ARTIFACTS_DIR / "rightmove" / "properties_final.jsonl"
DEFAULT_OUTPUT    = ARTIFACTS_DIR / "merged"     / "properties_merged.jsonl"

HAVERSINE_THRESHOLD_M = 10.0
PRICE_THRESHOLD_PCM   = 100

# OpenRent-exclusive fields to copy into a matched Rightmove record
OPENRENT_EXTRA_FIELDS = [
    "bills_included", "student_friendly", "families_allowed",
    "pets_allowed", "smokers_allowed", "dss_covers_rent",
    "garden", "parking", "fireplace", "epc_rating",
]

# Fields to backfill from OpenRent if missing/null in Rightmove
BACKFILL_FIELDS = [
    "deposit", "deposit_amount", "available_from", "min_tenancy",
    "furnish_type", "let_type", "council_tax", "features",
    "stations", "description", "image_url", "image_urls",
]


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def _beds(rec: dict) -> int | None:
    v = rec.get("bedrooms")
    if v is None or str(v).lower() in ("ask agent", "", "none"):
        return None
    try:
        return int(v)
    except (ValueError, TypeError):
        return None


def _price(rec: dict) -> int | None:
    v = rec.get("price_pcm")
    if v is None:
        return None
    try:
        return int(v)
    except (ValueError, TypeError):
        return None


def _coords(rec: dict) -> tuple[float, float] | None:
    lat, lon = rec.get("latitude"), rec.get("longitude")
    if lat is None or lon is None:
        return None
    try:
        return float(lat), float(lon)
    except (ValueError, TypeError):
        return None


def _is_blank(v) -> bool:
    """True if a field value is absent / null / 'ask agent'."""
    if v is None:
        return True
    if isinstance(v, str) and v.strip().lower() in ("ask agent", "", "none", "[]"):
        return True
    return False


def load_jsonl(path: Path) -> list[dict]:
    records = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return records


def merge_records(rm_rec: dict, or_rec: dict) -> dict:
    """
    Merge OpenRent data into a Rightmove base record.
    Returns a new dict (does not mutate inputs).
    """
    merged = dict(rm_rec)

    # --- Exclusive OpenRent fields (always copy if present) ---
    for field in OPENRENT_EXTRA_FIELDS:
        val = or_rec.get(field)
        if val is not None:
            merged[field] = val

    # --- Backfill: fill Rightmove gaps from OpenRent ---
    for field in BACKFILL_FIELDS:
        if _is_blank(merged.get(field)) and not _is_blank(or_rec.get(field)):
            merged[field] = or_rec[field]

    # --- Merge image_urls list (combine both, deduplicate) ---
    rm_imgs = merged.get("image_urls") or []
    or_imgs = or_rec.get("image_urls") or []
    if isinstance(rm_imgs, str):
        try:
            rm_imgs = json.loads(rm_imgs)
        except Exception:
            rm_imgs = []
    if isinstance(or_imgs, str):
        try:
            or_imgs = json.loads(or_imgs)
        except Exception:
            or_imgs = []
    all_imgs = list(dict.fromkeys(rm_imgs + or_imgs))
    if all_imgs:
        merged["image_urls"] = all_imgs

    # --- Source tracking ---
    merged["source_site"] = "rightmove+openrent"

    # Combine discovery_paths
    rm_paths = merged.get("discovery_paths") or []
    or_paths = or_rec.get("discovery_paths") or []
    if isinstance(rm_paths, str):
        try:
            rm_paths = json.loads(rm_paths)
        except Exception:
            rm_paths = [rm_paths]
    if isinstance(or_paths, str):
        try:
            or_paths = json.loads(or_paths)
        except Exception:
            or_paths = [or_paths]
    merged["discovery_paths"] = list(dict.fromkeys(rm_paths + or_paths))

    # Record the OpenRent URL as an alternative reference
    merged["openrent_url"] = or_rec.get("url")

    return merged


def build_openrent_index(or_records: list[dict]) -> list[tuple]:
    """(lat, lon, price, beds, rec) for records with valid coords."""
    idx = []
    for rec in or_records:
        coords = _coords(rec)
        if coords:
            idx.append((*coords, _price(rec) or 0, _beds(rec), rec))
    return idx


def find_openrent_match(rm_rec: dict, or_index: list) -> dict | None:
    """Return the best-matching OpenRent record, or None."""
    coords = _coords(rm_rec)
    if not coords:
        return None
    lat, lon = coords
    rm_beds  = _beds(rm_rec)
    rm_price = _price(rm_rec)

    for or_lat, or_lon, or_price, or_beds, or_rec in or_index:
        dist = haversine_m(lat, lon, or_lat, or_lon)
        if dist > HAVERSINE_THRESHOLD_M:
            continue
        if rm_beds is not None and or_beds is not None and rm_beds != or_beds:
            continue
        if rm_price is not None and or_price:
            if abs(rm_price - or_price) > PRICE_THRESHOLD_PCM:
                continue
        return or_rec
    return None


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Merge Rightmove + OpenRent listings")
    parser.add_argument("--openrent",  default=str(DEFAULT_OPENRENT))
    parser.add_argument("--rightmove", default=str(DEFAULT_RIGHTMOVE))
    parser.add_argument("--output",    default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    or_path = Path(args.openrent)
    rm_path = Path(args.rightmove)
    out_path = Path(args.output)

    print(f"[merge] Loading Rightmove: {rm_path}")
    rm_records = load_jsonl(rm_path)
    print(f"[merge] Loading OpenRent:  {or_path}")
    or_records = load_jsonl(or_path)

    print(f"[merge] Rightmove: {len(rm_records):,} | OpenRent: {len(or_records):,}")

    or_index = build_openrent_index(or_records)
    print(f"[merge] OpenRent spatial index: {len(or_index):,} records with valid coords")

    output: list[dict] = []
    matched_or_urls: set[str] = set()

    merged_count = 0
    rm_only = 0

    # Step 1: process all Rightmove records
    for rm_rec in rm_records:
        or_match = find_openrent_match(rm_rec, or_index)
        if or_match:
            merged = merge_records(rm_rec, or_match)
            output.append(merged)
            matched_or_urls.add(or_match.get("url", ""))
            merged_count += 1
        else:
            # Ensure source_site is set
            rec = dict(rm_rec)
            if not rec.get("source_site"):
                rec["source_site"] = "rightmove"
            output.append(rec)
            rm_only += 1

    # Step 2: add OpenRent-only records (not matched to any Rightmove)
    or_only = 0
    for or_rec in or_records:
        if or_rec.get("url") not in matched_or_urls:
            rec = dict(or_rec)
            if not rec.get("source_site"):
                rec["source_site"] = "openrent"
            output.append(rec)
            or_only += 1

    print(f"[merge] Merged (both):    {merged_count:,}")
    print(f"[merge] Rightmove-only:   {rm_only:,}")
    print(f"[merge] OpenRent-only:    {or_only:,}")
    print(f"[merge] Total output:     {len(output):,}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for rec in output:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
    print(f"[merge] Written → {out_path}")


if __name__ == "__main__":
    main()
