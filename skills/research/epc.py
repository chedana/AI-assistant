"""EPC (Energy Performance Certificate) lookup via opendatacommunities.org API."""

import re
import time
import urllib.parse
import urllib.request
import json
from dataclasses import dataclass
from typing import Optional

from core.settings import EPC_API_TOKEN

@dataclass
class EPCData:
    rating: str           # A-G
    potential_rating: str  # A-G
    inspection_date: str   # e.g. "2021-05-14"


_cache: dict[str, tuple[Optional[EPCData], float]] = {}
_CACHE_TTL = 2592000  # 30 days


def _normalise(s: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace for fuzzy matching."""
    return re.sub(r"[^a-z0-9 ]", "", s.lower()).strip()


def _address_match(candidate: str, target: str) -> bool:
    """Case-insensitive substring match on normalised address strings."""
    nc = _normalise(candidate)
    nt = _normalise(target)
    if not nc or not nt:
        return False
    # Check if target words are a substring of candidate, or vice versa
    return nt in nc or nc in nt


def get_epc(postcode: str, address: str) -> Optional[EPCData]:
    """Look up EPC rating for a property.

    Returns EPCData if found, None if token is missing, API fails, or no match.
    Results are cached by postcode+address with 30-day TTL.
    """
    if not EPC_API_TOKEN:
        return None

    cache_key = f"{postcode.strip().upper()}|{_normalise(address)}"
    now = time.time()
    if cache_key in _cache:
        data, ts = _cache[cache_key]
        if now - ts < _CACHE_TTL:
            return data

    try:
        encoded_postcode = urllib.parse.quote(postcode.strip())
        url = (
            f"https://epc.opendatacommunities.org/api/v1/domestic/search"
            f"?postcode={encoded_postcode}&size=5"
        )
        req = urllib.request.Request(url, headers={
            "Authorization": f"Basic {EPC_API_TOKEN}",
            "Accept": "application/json",
        })
        with urllib.request.urlopen(req, timeout=5) as resp:
            body = json.loads(resp.read().decode())

        rows = body.get("rows") or []
        if not rows:
            _cache[cache_key] = (None, now)
            return None

        # Fuzzy-match address
        for row in rows:
            addr1 = row.get("address1") or row.get("address") or ""
            if _address_match(addr1, address):
                rating = (row.get("current-energy-rating") or "").strip().upper()
                potential = (row.get("potential-energy-rating") or "").strip().upper()
                inspection = row.get("inspection-date") or ""
                if rating and rating in "ABCDEFG":
                    result = EPCData(
                        rating=rating,
                        potential_rating=potential,
                        inspection_date=inspection,
                    )
                    _cache[cache_key] = (result, now)
                    return result

        # No match found
        _cache[cache_key] = (None, now)
        return None
    except Exception:
        return None
