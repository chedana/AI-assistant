import httpx
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import Optional

@dataclass
class CrimeStats:
    total: int
    categories: dict[str, int]  # e.g. {"burglary": 5, "robbery": 2, ...}
    level: str  # "Low" | "Medium" | "High"
    months_covered: int

# London-wide monthly averages per 1km radius (approximate baselines)
_LONDON_AVG_PER_MONTH = 25  # rough baseline

_cache: dict[str, tuple[CrimeStats, float]] = {}
_CACHE_TTL = 86400  # 24 hours


async def get_crime_stats(lat: float, lon: float) -> Optional[CrimeStats]:
    """Fetch street-level crime for last 3 months from data.police.uk"""
    cache_key = f"{round(lat, 2)},{round(lon, 2)}"
    now = datetime.now().timestamp()
    if cache_key in _cache:
        stats, ts = _cache[cache_key]
        if now - ts < _CACHE_TTL:
            return stats

    try:
        # Get last 3 months
        categories: dict[str, int] = {}
        total = 0
        months = 0
        async with httpx.AsyncClient(timeout=10) as client:
            for i in range(1, 4):
                dt = datetime.now() - timedelta(days=30 * i)
                date_str = dt.strftime("%Y-%m")
                resp = await client.get(
                    "https://data.police.uk/api/crimes-street/all-crime",
                    params={"lat": lat, "lng": lon, "date": date_str},
                )
                if resp.status_code == 200:
                    crimes = resp.json()
                    months += 1
                    for c in crimes:
                        cat = c.get("category", "other")
                        categories[cat] = categories.get(cat, 0) + 1
                        total += 1

        if months == 0:
            return None

        monthly_avg = total / months
        if monthly_avg < _LONDON_AVG_PER_MONTH * 0.6:
            level = "Low"
        elif monthly_avg < _LONDON_AVG_PER_MONTH * 1.4:
            level = "Medium"
        else:
            level = "High"

        stats = CrimeStats(
            total=total, categories=categories, level=level, months_covered=months
        )
        _cache[cache_key] = (stats, now)
        return stats
    except Exception:
        return None
