"""阶段 2 第 1、2 项：清洗房源库并解析邮编区号。

规则依据：sft/DATA_CLEANING_NOTES.md（D1–D5）、sft/schema.json、sft/ANNOTATION_GUIDE.md。
输入：crawler/artifacts/merged/properties_merged.jsonl
输出：sft/data/listings_clean.jsonl，sft/results/clean_report.json
只用标准库；结果确定性（不涉及随机）。
"""
import hashlib, json, re, sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "crawler/artifacts/merged/properties_merged.jsonl"
OUT = ROOT / "sft/data/listings_clean.jsonl"
REPORT = ROOT / "sft/results/clean_report.json"

# D2：八类，全部归一化为 flat（精确匹配原始值）
FLAT_TYPES = {"Flat", "Apartment", "Penthouse", "Maisonette", "Studio",
              "Ground Flat", "Duplex", "Ground Maisonette"}
INVALID = {None, "", "nan", "none", "ask agent"}
BOOL_FIELDS = ["pets_allowed", "garden", "parking", "bills_included",
               "student_friendly", "families_allowed", "smokers_allowed"]
FURNISH_MAP = {"furnished": "furnished", "fully furnished": "furnished",
               "unfurnished": "unfurnished", "part furnished": "part-furnished",
               "part-furnished": "part-furnished"}
FURNISH_FLEXIBLE = {"furnished or unfurnished, landlord is flexible", "at tenant choice"}
LET_MAP = {"long term": "long term", "short term": "short term"}
BATH_MAX = 10                       # D1：来源数据清洗阈值，不是 schema 上限
PRICE_OUTLIER_LOW, PRICE_OUTLIER_HIGH = 300, 50000   # P04：只标记
NOW_WINDOW = timedelta(days=7)
# 取地址中最后一个邮区代码；前后不能紧贴字母数字，可带完整邮编的后半段
OUTCODE_RE = re.compile(r"(?<![A-Z0-9])([A-Z]{1,2}[0-9][A-Z0-9]?)(?:\s+[0-9][A-Z]{2})?(?![A-Z0-9])")
# 伦敦及周边邮区字母前缀，防止把 "Block B1" 之类误认成邮区
LONDON_AREAS = {"E", "EC", "N", "NW", "SE", "SW", "W", "WC", "BR", "CR", "DA", "EN",
                "HA", "IG", "KT", "RM", "SM", "TW", "UB", "WD", "CM", "AL", "SL", "GU",
                "RH", "TN", "ME", "HP", "SS", "LU", "SG", "RG", "MK", "OX", "CB"}
PAGE_TEXT_MARK = "javascript is disabled"


def extract_outcode(text):
    if not text:
        return None
    for m in reversed(list(OUTCODE_RE.finditer(text.upper()))):
        code = m.group(1)
        if re.match(r"[A-Z]+", code).group(0) in LONDON_AREAS:
            return code
    return None


def is_invalid(v):
    if v is None:
        return True
    if isinstance(v, float) and v != v:
        return True
    return isinstance(v, str) and v.strip().lower() in INVALID


def to_number(v):
    if is_invalid(v):
        return None
    try:
        x = float(str(v).replace(",", "").strip())
    except ValueError:
        return None
    return int(x) if x.is_integer() else x


def parse_date(v):
    if is_invalid(v):
        return None
    for fmt in ("%Y-%m-%d", "%d %B, %Y"):
        try:
            return datetime.strptime(v.strip(), fmt).date()
        except ValueError:
            pass
    return "UNPARSED"


def parse_scraped(v):
    return datetime.fromisoformat(v.replace("Z", "+00:00")).astimezone(timezone.utc).date()


def parse_stations(v):
    if is_invalid(v):
        return []
    items = json.loads(v) if isinstance(v, str) else v
    out = []
    for s in items:
        name = (s.get("name") or "").strip()
        if name:
            out.append({"name": name, "miles": to_number(s.get("miles"))})
    return out


def parse_min_tenancy(v):
    if is_invalid(v):
        return None
    m = re.fullmatch(r"\s*(\d+)\s+months?\s*", v, re.I)
    return int(m.group(1)) if m else None


def clean(r, stats):
    notes = []
    raw_type = r["property_type"]
    is_studio = raw_type == "Studio"

    # 户型
    bedrooms = to_number(r.get("bedrooms"))
    bathrooms = to_number(r.get("bathrooms"))
    if bathrooms is not None and bathrooms > BATH_MAX and not is_studio:
        notes.append(f"bathrooms_outlier_nulled:{r['bathrooms']}")
        stats["bathrooms_nulled_gt10"] += 1
        bathrooms = None
    if is_studio:
        if bedrooms != 0:
            stats["studio_bedrooms_overridden"] += 1
            notes.append(f"studio_bedrooms_from:{r.get('bedrooms')}")
        if bathrooms != 1:
            stats["studio_bathrooms_overridden"] += 1
            notes.append(f"studio_bathrooms_from:{r.get('bathrooms')}")
        bedrooms, bathrooms = 0, 1
    if (bathrooms is not None and bedrooms is not None and not is_studio
            and bathrooms > bedrooms + 2):
        stats["d4_bath_gt_bed_plus2"] += 1
        stats.setdefault("d4_examples", []).append(r["listing_id"])

    # 价格（P01、D3、P04）
    pw, pcm = to_number(r.get("price_pw")), to_number(r.get("price_pcm"))
    price_derived = None
    if pw is not None and pcm is not None:
        if abs(pw * 52 / 12 - pcm) / pcm > 0.05:
            stats["price_inconsistent"] += 1
            stats.setdefault("price_inconsistent_examples", []).append(r["listing_id"])
            price_inconsistent = True
        else:
            price_inconsistent = False
    else:
        price_inconsistent = None
        if pw is None and pcm is not None:
            pw, price_derived = round(pcm * 12 / 52, 2), "price_pw"
        elif pcm is None and pw is not None:
            pcm, price_derived = round(pw * 52 / 12, 2), "price_pcm"
        if price_derived:
            stats[f"derived_{price_derived}"] += 1
    if pcm is None:
        stats["price_missing_both"] += 1
    price_outlier = pcm is not None and not (PRICE_OUTLIER_LOW <= pcm <= PRICE_OUTLIER_HIGH)
    if price_outlier:
        stats["price_outlier_flagged"] += 1

    # 家具、租期
    fraw = None if is_invalid(r.get("furnish_type")) else r["furnish_type"].strip().lower()
    furnish = FURNISH_MAP.get(fraw)
    furnish_flexible = fraw in FURNISH_FLEXIBLE
    if fraw and not furnish and not furnish_flexible:
        stats["furnish_unknown_value"] += 1
        notes.append(f"furnish_unknown:{r['furnish_type']}")
    lraw = None if is_invalid(r.get("let_type")) else r["let_type"].strip().lower()
    let_type = LET_MAP.get(lraw)
    if lraw and not let_type:
        stats["let_type_non_tenancy_value"] += 1

    # 入住日期
    scraped = parse_scraped(r["scraped_at"])
    av = parse_date(r.get("available_from"))
    available_now, available_month, available_date = None, None, None
    if av == "UNPARSED":
        stats["available_from_unparsed"] += 1
        notes.append(f"available_unparsed:{r['available_from']}")
    elif av is not None:
        available_date = av.isoformat()
        if av <= scraped + NOW_WINDOW:
            available_now = True
            stats["available_now"] += 1
        else:
            available_now = False
            available_month = av.strftime("%Y-%m")
            stats["available_future_month"] += 1

    # 布尔字段：缺失 = 未知 = null，不补 false
    bools = {}
    for f in BOOL_FIELDS:
        v = r.get(f)
        bools[f] = v if isinstance(v, bool) else None
    dss = r.get("dss_income_accepted")
    bools["dss_accepted"] = dss if isinstance(dss, bool) else None

    # 地址：P05，抓到网页提示文字时改用 title
    address = None if is_invalid(r.get("address")) else r["address"].strip()
    address_from_title = False
    if address and PAGE_TEXT_MARK in address.lower():
        stats["address_page_text"] += 1
        title = r.get("title")
        if not is_invalid(title) and PAGE_TEXT_MARK not in title.lower():
            address, address_from_title = title.strip(), True
            stats["address_replaced_by_title"] += 1
        else:
            address = None
        notes.append("address_was_page_text")

    # 邮编区号（阶段 2 第 2 项）
    pd = None if is_invalid(r.get("postcode_district")) else r["postcode_district"].strip().upper()
    pd_source = "source" if pd else None
    if not pd:
        pd = extract_outcode(address)
        if pd:
            pd_source = "address"
        elif not address_from_title:
            pd = extract_outcode(r.get("title"))
            pd_source = "title" if pd else None
    stats[f"postcode_district_{pd_source or 'missing'}"] += 1

    return {
        "listing_id": r["listing_id"],
        "source": r["source"],
        "url": r["url"],
        "scraped_at": r["scraped_at"],
        "address": address,
        "address_from_title": address_from_title,
        "postcode": None if is_invalid(r.get("postcode")) else r["postcode"],
        "postcode_district": pd,
        "postcode_district_source": pd_source,
        "discovery_paths": r.get("discovery_paths") or [],
        # 阶段 2 第 3 项：区域标签，去掉 ", London" 后缀，保持原顺序去重
        "regions": list(dict.fromkeys(
            re.sub(r",\s*London$", "", p.strip()) for p in (r.get("discovery_paths") or [])
            if p and p.strip() and not p.startswith("openrent:"))),
        "latitude": r.get("latitude"),
        "longitude": r.get("longitude"),
        "property_type_raw": raw_type,
        "property_type": "flat",
        "is_studio": is_studio,
        "bedrooms": bedrooms,
        "bathrooms": bathrooms,
        "price_pcm": pcm,
        "price_pw": pw,
        "price_derived_field": price_derived,
        "price_inconsistent": price_inconsistent,
        "price_outlier": price_outlier,
        "furnish_type": furnish,
        "furnish_flexible": furnish_flexible,
        "let_type": let_type,
        "available_from_date": available_date,
        "available_now": available_now,
        "available_from_month": available_month,
        **bools,
        "min_tenancy_months": parse_min_tenancy(r.get("min_tenancy")),
        "stations": parse_stations(r.get("stations")),
        "description": r.get("description"),
        "cleaning_notes": notes,
    }


def main():
    raw = SRC.read_bytes()
    stats = Counter()
    by_type_excluded, kept_by_source, kept_by_type = Counter(), Counter(), Counter()
    out = []
    for line in raw.decode("utf-8").splitlines():
        r = json.loads(line)
        stats["raw_total"] += 1
        if r["property_type"] not in FLAT_TYPES:
            by_type_excluded[str(r["property_type"])] += 1
            continue
        out.append(clean(r, stats))
        kept_by_source[r["source"]] += 1
        kept_by_type[r["property_type"]] += 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as f:
        for o in out:
            f.write(json.dumps(o, ensure_ascii=False) + "\n")
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "kept": len(out),
        "excluded_by_type": sum(by_type_excluded.values()),
        "kept_by_source": dict(kept_by_source),
        "kept_by_type": dict(kept_by_type),
        "excluded_types_top": dict(by_type_excluded.most_common(15)),
        "stats": {k: v for k, v in stats.items()},
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("kept", "excluded_by_type", "kept_by_source", "source_sha256")}, ensure_ascii=False))
    print(json.dumps(report["stats"], ensure_ascii=False, indent=1))


if __name__ == "__main__":
    sys.exit(main())
