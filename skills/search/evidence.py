"""Stage D — evidence building for grounded explanation."""

import json
import re
from typing import Any, Dict, List
from urllib.parse import urlparse

import pandas as pd

from skills.search.hard_filter import _parse_available_from_date
from skills.search.text_utils import _safe_text, _to_float


def build_evidence_for_row(r: Dict[str, Any], c: Dict[str, Any], user_query: str = "") -> Dict[str, Any]:
    url = str(r.get("url", "") or "").strip()
    source = str(r.get("source", "") or "").strip()
    if not source and url:
        try:
            host = (urlparse(url).netloc or "").lower()
            if "rightmove" in host:
                source = "rightmove"
            elif "zoopla" in host:
                source = "zoopla"
            elif host:
                source = host
        except Exception:
            source = ""
    if not source:
        source = "unknown"

    ev: Dict[str, Any] = {
        "source": source,
        "url": url,
    }

    fields: Dict[str, Any] = {}

    if c.get("max_rent_pcm") is not None:
        try:
            p = pd.to_numeric(r.get("price_pcm"), errors="coerce")
            fields["price_pcm"] = None if pd.isna(p) else float(p)
            fields["max_rent_pcm"] = float(c["max_rent_pcm"])
            fields["within_budget"] = None if pd.isna(p) else (float(p) <= float(c["max_rent_pcm"]))
        except Exception:
            fields["within_budget"] = None

    if c.get("available_from") is not None:
        dt = _parse_available_from_date(r.get("available_from"))
        fields["available_from"] = None if pd.isna(dt) else dt.date().isoformat()
        fields["available_required"] = str(c["available_from"])
        fields["available_op"] = "lte"

    if c.get("min_tenancy_months") is not None:
        try:
            raw_t = _safe_text(r.get("min_tenancy"))
            m = re.search(r"(\d+(?:\.\d+)?)", raw_t)
            fields["min_tenancy_months"] = float(m.group(1)) if m else None
            fields["min_tenancy_required_months"] = float(c["min_tenancy_months"])
        except Exception:
            fields["min_tenancy_months"] = None

    if c.get("min_size_sqm") is not None:
        try:
            sq_m = pd.to_numeric(r.get("size_sqm"), errors="coerce")
            sq_ft = pd.to_numeric(r.get("size_sqft"), errors="coerce")
            actual_sqm = None
            if not pd.isna(sq_m):
                actual_sqm = float(sq_m)
            elif not pd.isna(sq_ft):
                actual_sqm = float(sq_ft) * 0.092903
            fields["size_sqm"] = actual_sqm
            fields["min_size_required_sqm"] = float(c["min_size_sqm"])
        except Exception:
            fields["size_sqm"] = None

    # Always include key listing fields, even when no hard constraints were extracted.
    fields["price_pcm"] = None if pd.isna(pd.to_numeric(r.get("price_pcm"), errors="coerce")) else float(pd.to_numeric(r.get("price_pcm"), errors="coerce"))
    fields["bedrooms"] = None if pd.isna(pd.to_numeric(r.get("bedrooms"), errors="coerce")) else int(float(pd.to_numeric(r.get("bedrooms"), errors="coerce")))
    fields["bathrooms"] = None if pd.isna(pd.to_numeric(r.get("bathrooms"), errors="coerce")) else float(pd.to_numeric(r.get("bathrooms"), errors="coerce"))
    dt_any = _parse_available_from_date(r.get("available_from"))
    fields["available_from"] = None if pd.isna(dt_any) else dt_any.date().isoformat()

    ev["fields"] = fields
    pref_ctx: Dict[str, Any] = {}
    for key in ("transit_evidence", "school_evidence", "preference_evidence"):
        raw = r.get(key)
        if raw is None:
            continue
        vals: List[Dict[str, Any]] = []
        if isinstance(raw, list):
            vals = [x for x in raw if isinstance(x, dict)]
        elif isinstance(raw, str):
            s = raw.strip()
            if s:
                try:
                    parsed = json.loads(s)
                    if isinstance(parsed, list):
                        vals = [x for x in parsed if isinstance(x, dict)]
                except Exception:
                    vals = []
        if vals:
            pref_ctx[key] = vals
    if pref_ctx:
        ev["preference_context"] = pref_ctx
    return ev
