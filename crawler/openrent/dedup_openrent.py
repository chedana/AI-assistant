"""
dedup_openrent.py
-----------------
Remove OpenRent listings that duplicate a Rightmove listing.

Dedup criteria (ALL must match):
  - Haversine distance < 10 m
  - Same bedrooms (numeric)
  - Price within £100 pcm

Usage:
    python -m crawler.openrent.dedup_openrent [--openrent PATH] [--rightmove PATH] [--output PATH]

Outputs a cleaned JSONL with duplicates removed.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS_DIR = PROJECT_ROOT / "crawler" / "artifacts"

DEFAULT_OPENRENT  = ARTIFACTS_DIR / "openrent"  / "properties_final.jsonl"
DEFAULT_RIGHTMOVE = ARTIFACTS_DIR / "rightmove" / "properties_final.jsonl"
DEFAULT_OUTPUT    = ARTIFACTS_DIR / "openrent"  / "properties_deduped.jsonl"

HAVERSINE_THRESHOLD_M = 10.0   # metres — within same building/room
PRICE_THRESHOLD_PCM   = 100    # £100 pcm tolerance


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return distance in metres between two WGS84 points."""
    R = 6_371_000  # Earth radius in metres
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


def build_spatial_index(records: list[dict]) -> list[tuple[float, float, int, int | None, dict]]:
    """Return list of (lat, lon, price_pcm, bedrooms, rec) for records with valid coords."""
    index = []
    for rec in records:
        lat = rec.get("latitude")
        lon = rec.get("longitude")
        if lat is None or lon is None:
            continue
        try:
            lat, lon = float(lat), float(lon)
        except (ValueError, TypeError):
            continue
        index.append((lat, lon, _price(rec) or 0, _beds(rec), rec))
    return index


def is_duplicate(or_rec: dict, rm_index: list) -> bool:
    """
    Return True if or_rec (OpenRent) matches any Rightmove listing in rm_index.
    Criteria: distance < 10m AND beds match AND price within £100.
    """
    lat = or_rec.get("latitude")
    lon = or_rec.get("longitude")
    if lat is None or lon is None:
        return False
    try:
        lat, lon = float(lat), float(lon)
    except (ValueError, TypeError):
        return False

    or_beds  = _beds(or_rec)
    or_price = _price(or_rec)

    for rm_lat, rm_lon, rm_price, rm_beds, _ in rm_index:
        dist = haversine_m(lat, lon, rm_lat, rm_lon)
        if dist > HAVERSINE_THRESHOLD_M:
            continue
        # Beds must match (if both known)
        if or_beds is not None and rm_beds is not None and or_beds != rm_beds:
            continue
        # Price must be within threshold (if both known)
        if or_price is not None and rm_price is not None:
            if abs(or_price - rm_price) > PRICE_THRESHOLD_PCM:
                continue
        return True

    return False


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Dedup OpenRent vs Rightmove")
    parser.add_argument("--openrent",  default=str(DEFAULT_OPENRENT))
    parser.add_argument("--rightmove", default=str(DEFAULT_RIGHTMOVE))
    parser.add_argument("--output",    default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    openrent_path  = Path(args.openrent)
    rightmove_path = Path(args.rightmove)
    output_path    = Path(args.output)

    print(f"[dedup] Loading OpenRent:  {openrent_path}")
    or_records = load_jsonl(openrent_path)
    print(f"[dedup] Loading Rightmove: {rightmove_path}")
    rm_records = load_jsonl(rightmove_path)

    print(f"[dedup] OpenRent: {len(or_records):,} | Rightmove: {len(rm_records):,}")

    rm_index = build_spatial_index(rm_records)
    print(f"[dedup] Rightmove spatial index: {len(rm_index):,} records with valid coords")

    kept = []
    dupes = 0
    no_coords = 0
    for rec in or_records:
        if rec.get("latitude") is None or rec.get("longitude") is None:
            no_coords += 1
            kept.append(rec)
            continue
        if is_duplicate(rec, rm_index):
            dupes += 1
        else:
            kept.append(rec)

    print(f"[dedup] Duplicates removed: {dupes}")
    print(f"[dedup] No-coords (kept):   {no_coords}")
    print(f"[dedup] Kept: {len(kept):,}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        for rec in kept:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
    print(f"[dedup] Written → {output_path}")


if __name__ == "__main__":
    main()
