"""Stage B — hard-constraint filtering with audit trail."""

import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from skills.search.text_utils import _norm_furnish_value, _safe_text, _to_float
from skills.search.signals import candidate_snapshot


# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------

def _parse_available_from_date(v: Any) -> pd.Timestamp:
    s = _safe_text(v).strip()
    if not s:
        return pd.NaT
    lowered = s.lower()
    if lowered in {"now", "available now", "immediately", "immediate"}:
        return pd.Timestamp(datetime.utcnow().date())
    return pd.to_datetime(s, errors="coerce", dayfirst=True)


def _is_available_now(v: Any) -> bool:
    s = _safe_text(v).strip().lower()
    return s in {"now", "available now", "immediately", "immediate"}


# ---------------------------------------------------------------------------
# Main hard-filter function
# ---------------------------------------------------------------------------

def apply_hard_filters_with_audit(df: pd.DataFrame, c: Dict[str, Any]) -> Tuple[pd.DataFrame, List[Dict[str, Any]]]:
    c = c or {}
    if df is None or len(df) == 0:
        return df, []

    keep_indices: List[int] = []
    audits: List[Dict[str, Any]] = []

    for idx, row in df.iterrows():
        r = row.to_dict()
        reasons: List[str] = []
        checks: Dict[str, Any] = {}

        def _norm_cat_text(v: Any) -> str:
            s = _safe_text(v).lower()
            if not s:
                return ""
            s = s.replace("_", " ").replace("-", " ")
            s = re.sub(r"\s+", " ", s).strip()
            return s

        def _norm_furnish(v: Any) -> str:
            return _norm_furnish_value(v)

        def _parse_months(v: Any) -> Optional[float]:
            s = _safe_text(v).lower()
            if not s:
                return None
            m = re.search(r"(\d+(?:\.\d+)?)", s)
            if not m:
                return None
            try:
                return float(m.group(1))
            except Exception:
                return None

        layout_options = c.get("layout_options") or []
        use_layout_options = isinstance(layout_options, list) and len(layout_options) > 0

        if use_layout_options:
            prop_val = _safe_text(r.get("property_type")).lower()
            bed_val = _to_float(r.get("bedrooms"))
            bath_val = _to_float(r.get("bathrooms"))
            option_audits: List[Dict[str, Any]] = []
            any_pass = False

            for opt in layout_options:
                if not isinstance(opt, dict):
                    continue
                req_bed = opt.get("bedrooms")
                req_bath = opt.get("bathrooms")
                req_prop = _safe_text(opt.get("property_type")).lower()
                req_tag = str(opt.get("layout_tag") or "").strip().lower()
                req_rent = opt.get("max_rent_pcm")
                opt_fail: List[str] = []

                if req_bed is not None and bed_val is not None:
                    try:
                        if int(round(bed_val)) != int(float(req_bed)):
                            opt_fail.append(f"bedrooms {bed_val:g} != {int(float(req_bed))}")
                    except Exception:
                        pass
                if req_bath is not None and bath_val is not None:
                    try:
                        if float(bath_val) != float(req_bath):
                            opt_fail.append(f"bathrooms {bath_val:g} != {float(req_bath):g}")
                    except Exception:
                        pass
                if req_prop:
                    if prop_val and prop_val != req_prop:
                        opt_fail.append(f"property_type '{prop_val}' != '{req_prop}'")
                if req_tag == "studio":
                    raw_prop = _safe_text(r.get("property_type")).lower()
                    is_raw_studio = (raw_prop == "studio")
                    is_flat_zero_bed = (
                        (raw_prop in {"flat", "apartment", "studio"})
                        and bed_val is not None
                        and int(round(bed_val)) == 0
                    )
                    if not (is_raw_studio or is_flat_zero_bed):
                        opt_fail.append("layout_tag 'studio' not matched")
                rent_val = _to_float(r.get("price_pcm"))
                eff_rent_req = req_rent if req_rent is not None else c.get("max_rent_pcm")
                if eff_rent_req is not None and rent_val is not None:
                    try:
                        if float(rent_val) > float(eff_rent_req):
                            opt_fail.append(f"price {rent_val:g} > {float(eff_rent_req):g}")
                    except Exception:
                        pass

                passed = len(opt_fail) == 0
                any_pass = any_pass or passed
                option_audits.append(
                    {
                        "required": {
                            "bedrooms": req_bed,
                            "bathrooms": req_bath,
                            "property_type": req_prop or None,
                            "layout_tag": req_tag or None,
                            "max_rent_pcm": eff_rent_req,
                        },
                        "actual": {
                            "bedrooms": bed_val,
                            "bathrooms": bath_val,
                            "property_type": prop_val or None,
                            "price_pcm": rent_val,
                        },
                        "pass": passed,
                        "fail_reasons": opt_fail,
                    }
                )

            checks["layout_options"] = {
                "active": True,
                "option_count": len(option_audits),
                "pass": any_pass,
                "options": option_audits,
            }
            if not any_pass:
                reasons.append("layout_options no option matched")

        rent_req = c.get("max_rent_pcm")
        has_layout_budget = any(
            isinstance(x, dict) and x.get("max_rent_pcm") is not None
            for x in (layout_options or [])
        )
        if rent_req is not None and not use_layout_options and not has_layout_budget:
            rent_val = _to_float(r.get("price_pcm"))
            checks["max_rent_pcm"] = {"actual": rent_val, "required": float(rent_req), "op": "lte"}
            if rent_val is not None and rent_val > float(rent_req):
                reasons.append(f"price {rent_val:g} > {float(rent_req):g}")

        avail_req = c.get("available_from")
        if avail_req is not None:
            listing_raw = r.get("available_from")
            listing_now = _is_available_now(listing_raw)
            listing_dt = _parse_available_from_date(listing_raw)
            req_dt = pd.to_datetime(avail_req, errors="coerce")
            checks["available_from"] = {
                "actual": "now" if listing_now else (None if pd.isna(listing_dt) else listing_dt.date().isoformat()),
                "required": None if pd.isna(req_dt) else req_dt.date().isoformat(),
                "op": "now_pass" if listing_now else "lte",
            }
            if (not listing_now) and pd.notna(listing_dt) and pd.notna(req_dt) and listing_dt > req_dt:
                reasons.append(
                    f"available_from {listing_dt.date().isoformat()} > {req_dt.date().isoformat()}"
                )

        furnish_req = _norm_furnish(c.get("furnish_type"))
        if furnish_req:
            furnish_val = _norm_furnish(r.get("furnish_type"))
            checks["furnish_type"] = {"actual": furnish_val or None, "required": furnish_req, "op": "eq"}
            # "ask agent" and "flexible" should pass hard filter for furnish_type.
            if furnish_val and furnish_val not in {"ask agent", "flexible"} and furnish_val != furnish_req:
                reasons.append(f"furnish_type '{furnish_val}' != '{furnish_req}'")

        let_req = _norm_cat_text(c.get("let_type"))
        if let_req:
            let_val = _norm_cat_text(r.get("let_type"))
            checks["let_type"] = {"actual": let_val or None, "required": let_req, "op": "eq"}
            if let_val and let_val != let_req:
                reasons.append(f"let_type '{let_val}' != '{let_req}'")

        tenancy_req = c.get("min_tenancy_months")
        if tenancy_req is not None:
            tenancy_val = _parse_months(r.get("min_tenancy"))
            checks["min_tenancy_months"] = {
                "actual": tenancy_val,
                "required": float(tenancy_req),
                "op": "eq",
            }
            if tenancy_val is not None and tenancy_val != float(tenancy_req):
                reasons.append(f"min_tenancy_months {tenancy_val:g} != {float(tenancy_req):g}")

        size_req = c.get("min_size_sqm")
        if size_req is not None:
            size_sqm = _to_float(r.get("size_sqm"))
            size_sqft = _to_float(r.get("size_sqft"))
            actual_sqm = size_sqm if size_sqm is not None else (size_sqft * 0.092903 if size_sqft is not None else None)
            checks["min_size_sqm"] = {
                "actual": actual_sqm,
                "required": float(size_req),
                "op": "gte",
            }
            if actual_sqm is not None and actual_sqm < float(size_req):
                reasons.append(f"size_sqm {actual_sqm:g} < {float(size_req):g}")

        hard_pass = len(reasons) == 0
        if hard_pass:
            keep_indices.append(idx)

        audits.append(
            {
                **candidate_snapshot(r),
                "hard_pass": hard_pass,
                "hard_fail_reasons": reasons,
                "hard_checks": checks,
                "score_formula": "hard_pass = all(active_hard_constraints_satisfied_or_unknown)",
                "score": 1.0 if hard_pass else 0.0,
            }
        )

    filtered = df.loc[keep_indices].copy().reset_index(drop=True)
    return filtered, audits
