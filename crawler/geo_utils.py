"""
pipeline/geo_utils.py
---------------------
地理工具函数：
  1. 从地址提取 postcode district
  2. postcode district → region 标签列表
  3. lat/lng → 距离最近的 region（排序用）
"""

import re
import math
from typing import Optional

# 导入映射表（london_regions.py 放在项目根目录）
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from london_regions import LONDON_REGIONS, LONDON_POSTCODE_DISTRICTS


# ── 1. 从地址提取 postcode ────────────────────────────────────────

# 完整 UK postcode 正则（e.g. "E8 1JU", "SW1A 2AA"）
_FULL_POSTCODE_RE = re.compile(
    r'\b([A-Z]{1,2}\d{1,2}[A-Z]?)\s*(\d[A-Z]{2})\b',
    re.IGNORECASE,
)

# 只有 district 的正则（e.g. "E8", "SW1"）
_DISTRICT_RE = re.compile(
    r'\b([A-Z]{1,2}\d{1,2}[A-Z]?)\b',
    re.IGNORECASE,
)


def extract_postcode_district(address: str) -> Optional[str]:
    """
    从地址字符串提取 postcode district。
    e.g. "123 Kingsland Road, London, E8 1JU" → "E8"
         "SW1A 2AA"                             → "SW1A"
         "Canary Wharf, E14"                    → "E14"
    """
    if not address:
        return None

    text = address.upper().strip()

    # 优先匹配完整 postcode（更准确）
    m = _FULL_POSTCODE_RE.search(text)
    if m:
        district = m.group(1).upper()
        # 标准化：SW1A → SW1A，E8 → E8
        return district

    # fallback：只有 district
    for m in _DISTRICT_RE.finditer(text):
        candidate = m.group(1).upper()
        if candidate in LONDON_POSTCODE_DISTRICTS:
            return candidate

    return None


def extract_full_postcode(address: str) -> Optional[str]:
    """
    提取完整 postcode（用于 Nominatim geocoding）
    e.g. "E8 1JU"
    """
    if not address:
        return None
    m = _FULL_POSTCODE_RE.search((address or "").upper())
    if m:
        district = m.group(1).upper()
        sector_unit = m.group(2).upper()
        return f"{district} {sector_unit}"
    return None


# ── 2. postcode district → region 标签 ───────────────────────────

def get_regions_for_district(district: str) -> list[str]:
    """
    给定 postcode district，返回所有匹配的 mental region 名字。
    e.g. "E8" → ["Hackney Central", "Dalston"]
         "E1" → ["Shoreditch", "Spitalfields", "Aldgate", "Whitechapel", "Shadwell"]
    """
    if not district:
        return []
    district_upper = district.upper().strip()
    matches = []
    for region_name, data in LONDON_REGIONS.items():
        if district_upper in [p.upper() for p in data["postcodes"]]:
            matches.append(region_name)
    return matches


def get_regions_for_address(address: str) -> list[str]:
    """
    从地址直接得到 region 标签列表（组合函数）
    e.g. "123 Kingsland Road, E8 1JU" → ["Hackney Central", "Dalston"]
    """
    district = extract_postcode_district(address)
    if not district:
        return []
    return get_regions_for_district(district)


# ── 3. lat/lng → 距离计算 ─────────────────────────────────────────

def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """
    计算两点间的球面距离（千米）
    """
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi/2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def get_nearest_regions(lat: float, lng: float, max_km: float = 1.5) -> list[dict]:
    """
    给定坐标，返回 max_km 范围内所有 region，按距离排序。
    用于搜索时的 geo ranking。

    返回格式：
    [
      {"region": "Dalston", "distance_km": 0.3, "lat": ..., "lng": ...},
      {"region": "Hackney Central", "distance_km": 0.8, ...},
    ]
    """
    results = []
    for region_name, data in LONDON_REGIONS.items():
        dist = haversine_km(lat, lng, data["lat"], data["lng"])
        if dist <= max_km:
            results.append({
                "region": region_name,
                "distance_km": round(dist, 3),
                "lat": data["lat"],
                "lng": data["lng"],
                "zone": data.get("zone"),
                "borough": data.get("borough"),
            })
    results.sort(key=lambda x: x["distance_km"])
    return results


def get_primary_region(lat: float, lng: float) -> Optional[str]:
    """
    返回距离最近的单个 region 名字（主 region，用于显示）
    """
    nearest = get_nearest_regions(lat, lng, max_km=2.0)
    return nearest[0]["region"] if nearest else None


# ── 4. 搜索辅助：region name → 中心坐标 ──────────────────────────

def get_region_center(region_name: str) -> Optional[tuple[float, float]]:
    """
    "Dalston" → (51.5463, -0.0750)
    用于搜索时构造 Qdrant geo radius filter
    """
    r = LONDON_REGIONS.get(region_name)
    if r:
        return r["lat"], r["lng"]
    # 模糊匹配（不区分大小写）
    name_lower = region_name.lower()
    for k, v in LONDON_REGIONS.items():
        if k.lower() == name_lower:
            return v["lat"], v["lng"]
    return None


def miles_to_meters(miles: float) -> float:
    return miles * 1609.34


# ── 快速测试 ──────────────────────────────────────────────────────

if __name__ == "__main__":
    # 测试地址解析
    tests = [
        "123 Kingsland Road, London, E8 1JU",
        "Flat 4, 10 Commercial Street, London E1 6LZ",
        "Canary Wharf, E14 5AB",
        "SW1A 2AA",
        "Some Road, London",  # 没有 postcode
    ]
    print("── postcode extraction ──")
    for addr in tests:
        d = extract_postcode_district(addr)
        r = get_regions_for_address(addr)
        print(f"  {addr[:45]:<45} → {str(d):<6} → {r}")

    print("\n── nearest regions to E8 center ──")
    # E8 大概在 51.5463, -0.0750
    nearest = get_nearest_regions(51.5463, -0.0750, max_km=1.0)
    for n in nearest:
        print(f"  {n['region']:<25} {n['distance_km']} km")

    print("\n── region center lookup ──")
    for name in ["Shoreditch", "Dalston", "Canary Wharf", "Unknown"]:
        print(f"  {name}: {get_region_center(name)}")
