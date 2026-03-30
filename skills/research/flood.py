import httpx
import time
from dataclasses import dataclass
from typing import Optional

@dataclass
class FloodRisk:
    level: str   # "very_low" | "low" | "medium" | "high"
    description: str

_cache: dict[str, tuple[Optional[FloodRisk], float]] = {}
_CACHE_TTL = 604800  # 7 days

# Severity mapping: EA severity 1=Severe, 2=Warning, 3=Alert, 4=No longer in force
_SEVERITY_TO_LEVEL = {
    1: "high",
    2: "high",
    3: "medium",
    4: "low",
}


async def get_flood_risk(lat: float, lon: float) -> Optional[FloodRisk]:
    """Fetch flood risk from Environment Agency flood-monitoring API."""
    cache_key = f"{round(lat, 2)},{round(lon, 2)}"
    now = time.time()
    cached = _cache.get(cache_key)
    if cached is not None:
        result, ts = cached
        if now - ts < _CACHE_TTL:
            return result

    try:
        async with httpx.AsyncClient(timeout=8) as client:
            resp = await client.get(
                "https://environment.data.gov.uk/flood-monitoring/id/floods",
                params={"lat": lat, "long": lon, "dist": 3},
            )
            if resp.status_code != 200:
                return None

            data = resp.json()
            items = data.get("items") or []

        if not items:
            result = FloodRisk(level="very_low", description="No flood alerts in this area")
        else:
            # Find the most severe active alert
            worst = 5
            for item in items:
                sev = item.get("severityLevel")
                if isinstance(sev, int) and sev < worst:
                    worst = sev
            level = _SEVERITY_TO_LEVEL.get(worst, "low")
            desc_map = {
                "high": "Active flood warning in area",
                "medium": "Flood alert — be prepared",
                "low": "Previous flood alert (no longer active)",
            }
            result = FloodRisk(level=level, description=desc_map.get(level, ""))

        _cache[cache_key] = (result, now)
        return result
    except Exception:
        return None
