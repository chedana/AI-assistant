from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple
from datetime import datetime

from core.database import load_qdrant_client
from core.settings import QDRANT_COLLECTION


@dataclass
class RentStats:
    median: float
    p25: float
    p75: float
    count: int
    area: str
    bedrooms: Optional[int]


_cache: Dict[str, Tuple[RentStats, float]] = {}
_CACHE_TTL = 3600  # 1 hour


def get_area_rent_stats(area_name: str, bedrooms: Optional[int] = None) -> Optional[RentStats]:
    """Aggregate rent stats from Qdrant for a given area and bedroom count."""
    cache_key = f"{area_name}:{bedrooms}"
    now = datetime.now().timestamp()
    if cache_key in _cache:
        stats, ts = _cache[cache_key]
        if now - ts < _CACHE_TTL:
            return stats

    try:
        client = load_qdrant_client()
        from qdrant_client.models import Filter, FieldCondition, MatchValue

        must = [
            FieldCondition(
                key="location_region_tokens",
                match=MatchValue(value=area_name.lower()),
            )
        ]
        if bedrooms is not None:
            must.append(
                FieldCondition(key="bedrooms", match=MatchValue(value=bedrooms))
            )

        results = client.scroll(
            collection_name=QDRANT_COLLECTION,
            scroll_filter=Filter(must=must),
            limit=500,
            with_payload=["price_pcm"],
        )[0]

        prices = [p.payload.get("price_pcm") for p in results if p.payload.get("price_pcm")]
        prices = [p for p in prices if isinstance(p, (int, float)) and p > 0]

        if len(prices) < 3:
            return None

        prices.sort()
        n = len(prices)
        median = prices[n // 2]
        p25 = prices[n // 4]
        p75 = prices[3 * n // 4]

        stats = RentStats(
            median=median, p25=p25, p75=p75, count=n,
            area=area_name, bedrooms=bedrooms,
        )
        _cache[cache_key] = (stats, now)
        return stats
    except Exception:
        return None
