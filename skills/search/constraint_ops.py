"""Constraint merging, normalization, diffing, and structured-policy helpers."""

import copy
import re
from typing import Any, Dict, List, Optional

import numpy as np

from skills.search.text_utils import (
    _norm_furnish_value,
    _safe_text,
    _to_float,
    _truthy_env,
)
from skills.search.constraint_extraction import (
    _normalize_constraint_extract,
    _normalize_layout_options,
    _parse_user_date_uk_first,
)
from skills.search.location_match import (
    _correct_location_keyword,
    _normalize_location_keyword,
)


def normalize_budget_to_pcm(c: dict) -> dict:
    """
    Normalize budget constraints to pcm.
    Supports:
      - max_rent_pcm
      - max_rent_pcw
    Priority:
      - If both provided, pcm wins.
    """
    if c is None:
        return c

    # if user gave pcw, convert to pcm
    if c.get("max_rent_pcm") is None and c.get("max_rent_pcw") is not None:
        try:
            pcw = float(c["max_rent_pcw"])
            c["max_rent_pcm"] = pcw * 52.0 / 12.0
        except:
            pass

    return c
def normalize_constraints(c: dict) -> dict:
    if c.get("available_from") is not None:
        c["available_from"] = _parse_user_date_uk_first(c.get("available_from"))
    c["available_from_op"] = None

    def _norm_cat_text(v: Any) -> Optional[str]:
        s = _safe_text(v).lower()
        if not s:
            return None
        s = s.replace("_", " ").replace("-", " ")
        s = re.sub(r"\s+", " ", s).strip()
        return s or None

    furn = _norm_furnish_value(c.get("furnish_type"))
    if furn not in {"furnished", "unfurnished", "part-furnished"}:
        furn = None
    c["furnish_type"] = furn
    let_type = _norm_cat_text(c.get("let_type"))
    c["let_type"] = let_type if let_type in {"short term", "long term"} else None
    c["layout_options"] = _normalize_layout_options(c.get("layout_options") or [])

    if c.get("min_tenancy_months") is not None:
        try:
            c["min_tenancy_months"] = float(c.get("min_tenancy_months"))
        except Exception:
            c["min_tenancy_months"] = None

    if c.get("min_size_sqm") is not None:
        try:
            c["min_size_sqm"] = float(c.get("min_size_sqm"))
        except Exception:
            c["min_size_sqm"] = None
    if c.get("min_size_sqft") is not None:
        try:
            c["min_size_sqft"] = float(c.get("min_size_sqft"))
        except Exception:
            c["min_size_sqft"] = None
    # merge size constraints into a single canonical hard filter in sqm
    if c.get("min_size_sqm") is None and c.get("min_size_sqft") is not None:
        c["min_size_sqm"] = float(c["min_size_sqft"]) * 0.092903
    c.pop("min_size_sqft", None)

    # Pre Stage A conservative location typo correction + normalized dedupe.
    locs = c.get("location_keywords") or []
    seen_loc = set()
    norm_locs: List[str] = []
    for x in locs:
        raw = str(x).strip()
        if not raw:
            continue
        corrected = _correct_location_keyword(raw)
        if _truthy_env("RENT_LOCATION_DEBUG_PRINT"):
            try:
                from core.logger import log_message

                log_message("INFO", f"location_flow_preA {raw} -> {corrected}")
            except Exception:
                print(f"[INFO] location_flow_preA {raw} -> {corrected}")
        k = _normalize_location_keyword(corrected)
        if not k or k in seen_loc:
            continue
        seen_loc.add(k)
        norm_locs.append(corrected)
    c["location_keywords"] = norm_locs

    return c

def merge_constraints(old: Optional[dict], new: dict) -> dict:
    if old is None:
        old = {}
    out = dict(old)
    if bool(new.get("_replace_all_constraints")):
        old_k = out.get("k")
        out = {}
        if old_k is not None and new.get("k") is None:
            out["k"] = old_k

    def _layout_selector_match(item: Dict[str, Any], selector: Dict[str, Any]) -> bool:
        if not isinstance(item, dict) or not isinstance(selector, dict):
            return False
        for k in ("bedrooms", "bathrooms", "property_type", "layout_tag"):
            sv = selector.get(k)
            if sv is None:
                continue
            if item.get(k) != sv:
                return False
        return True

    cur_layout = _normalize_layout_options(out.get("layout_options") or [])
    remove_selectors = _normalize_layout_options(new.get("_remove_layout_options") or [])
    if remove_selectors:
        kept = []
        for opt in cur_layout:
            if any(_layout_selector_match(opt, sel) for sel in remove_selectors):
                continue
            kept.append(opt)
        cur_layout = kept
    out["layout_options"] = cur_layout

    # scalar fields: new overrides if not null
    for key in [
        "max_rent_pcm",
        "available_from",
        "furnish_type",
        "let_type",
        "min_tenancy_months",
        "min_size_sqm",
        "min_size_sqft",
        "k",
    ]:
        if new.get(key) is not None:
            out[key] = new.get(key)

    def merge_list(a, b):
        a = a or []
        b = b or []
        seen = set()
        res = []
        for x in a + b:
            s = str(x).strip()
            if not s:
                continue
            k = _normalize_location_keyword(s)
            if not k:
                continue
            if k in seen:
                continue
            seen.add(k)
            res.append(s)
        return res

    old_locs = old.get("location_keywords") or []
    new_locs = new.get("location_keywords") or []
    if bool(new.get("_clear_location_keywords")):
        out["location_keywords"] = []
    else:
        location_mode = _safe_text(new.get("_location_update_mode")).lower()
        if location_mode == "append":
            out["location_keywords"] = merge_list(old_locs, new_locs)
        elif location_mode == "keep":
            out["location_keywords"] = merge_list(old_locs, [])
        else:
            # default hard-filter behavior: replace when new location is explicitly provided.
            out["location_keywords"] = merge_list(new_locs, []) if len(new_locs) > 0 else merge_list(old_locs, [])

    new_layout = _normalize_layout_options(new.get("layout_options") or [])
    if new_layout:
        layout_mode = _safe_text(new.get("_layout_update_mode")).lower()
        if layout_mode == "append":
            out["layout_options"] = _normalize_layout_options((out.get("layout_options") or []) + new_layout)
        else:
            out["layout_options"] = new_layout

    # Budget scope policy:
    # - If no global budget exists, first seen layout budget becomes global.
    # - If a budget is mentioned and only one active layout exists, sync that
    #   layout budget with global budget.
    # - With multiple layouts, missing layout budget keeps None and will
    #   fallback to global budget during hard filtering.
    layout_opts = _normalize_layout_options(out.get("layout_options") or [])
    global_budget = out.get("max_rent_pcm")
    mentioned_global_budget = new.get("max_rent_pcm") is not None
    mentioned_layout_budget = any(
        isinstance(x, dict) and x.get("max_rent_pcm") is not None
        for x in (new.get("layout_options") or [])
    )
    budget_mentioned = bool(mentioned_global_budget or mentioned_layout_budget)

    if global_budget is None:
        for opt in layout_opts:
            if not isinstance(opt, dict):
                continue
            b = opt.get("max_rent_pcm")
            if b is not None:
                out["max_rent_pcm"] = b
                global_budget = b
                break

    if budget_mentioned and len(layout_opts) == 1 and global_budget is not None:
        if isinstance(layout_opts[0], dict):
            layout_opts[0]["max_rent_pcm"] = global_budget
            out["layout_options"] = _normalize_layout_options(layout_opts)

    # default k
    if out.get("k") is None:
        out["k"] = DEFAULT_K

    return normalize_constraints(out)

def _norm_scalar_for_diff(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, float):
        if np.isnan(v):
            return None
        return float(v)
    if isinstance(v, (int, bool)):
        return v
    s = str(v).strip()
    return s if s != "" else None


def summarize_constraint_changes(old_c: Optional[dict], new_c: dict) -> str:
    old_c = old_c or {}
    new_c = new_c or {}
    keys = [
        "max_rent_pcm",
        "available_from",
        "furnish_type", "let_type",
        "min_tenancy_months", "min_size_sqm",
        "k",
    ]
    changes = []
    for k in keys:
        old_v = _norm_scalar_for_diff(old_c.get(k))
        new_v = _norm_scalar_for_diff(new_c.get(k))
        if old_v == new_v:
            continue
        if old_v is None and new_v is not None:
            changes.append(f"added {k}={new_v}")
        elif old_v is not None and new_v is None:
            changes.append(f"removed {k}")
        else:
            changes.append(f"updated {k}: {old_v} -> {new_v}")

    def _norm_list(x):
        out = []
        for i in (x or []):
            s = str(i).strip()
            if s:
                out.append(s)
        return out

    for k in ["location_keywords"]:
        old_list = _norm_list(old_c.get(k))
        new_list = _norm_list(new_c.get(k))
        old_set = set([x.lower() for x in old_list])
        new_set = set([x.lower() for x in new_list])
        added = [x for x in new_list if x.lower() not in old_set]
        removed = [x for x in old_list if x.lower() not in new_set]
        if added:
            changes.append(f"added {k}: {added}")
        if removed:
            changes.append(f"removed {k}: {removed}")

    old_layout = _normalize_layout_options(old_c.get("layout_options") or [])
    new_layout = _normalize_layout_options(new_c.get("layout_options") or [])
    if _canon_for_structured_compare(old_layout) != _canon_for_structured_compare(new_layout):
        if not old_layout and new_layout:
            changes.append(f"added layout_options: {new_layout}")
        elif old_layout and not new_layout:
            changes.append("removed layout_options")
        else:
            changes.append(f"updated layout_options: {old_layout} -> {new_layout}")

    return "; ".join(changes) if changes else "no constraint changes"


def compact_constraints_view(c: Optional[dict]) -> dict:
    c = c or {}
    out = {}
    keep_keys = [
        "max_rent_pcm",
        "available_from",
        "furnish_type", "let_type", "layout_options",
        "min_tenancy_months", "min_size_sqm",
        "location_keywords",
        "k",
    ]
    for k in keep_keys:
        v = c.get(k)
        if v is None:
            continue
        if isinstance(v, list) and len(v) == 0:
            continue
        out[k] = v
    return out



def _canon_for_structured_compare(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, float):
        if np.isnan(v):
            return None
        return round(float(v), 6)
    if isinstance(v, int):
        return int(v)
    if isinstance(v, list):
        if len(v) > 0 and isinstance(v[0], dict):
            norm = _normalize_layout_options(v)
            canon_items = []
            for it in norm:
                canon_items.append(
                    {
                        "bedrooms": it.get("bedrooms"),
                        "bathrooms": it.get("bathrooms"),
                        "property_type": it.get("property_type"),
                        "layout_tag": it.get("layout_tag"),
                        "max_rent_pcm": it.get("max_rent_pcm"),
                    }
                )
            return sorted(
                canon_items,
                key=lambda x: (
                    -1 if x.get("bedrooms") is None else int(x.get("bedrooms")),
                    -1 if x.get("bathrooms") is None else float(x.get("bathrooms")),
                    str(x.get("property_type") or ""),
                    str(x.get("layout_tag") or ""),
                    -1 if x.get("max_rent_pcm") is None else float(x.get("max_rent_pcm")),
                ),
            )
        out: List[str] = []
        seen = set()
        for x in v:
            s = str(x).strip()
            if not s:
                continue
            k = s.lower()
            if k in seen:
                continue
            seen.add(k)
            out.append(s)
        return sorted(out, key=lambda x: x.lower())
    s = str(v).strip()
    return s if s else None


def _normalize_for_structured_policy(obj: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    # Work on a deep copy so policy normalization never mutates raw LLM output.
    out = _normalize_constraint_extract(copy.deepcopy(obj or {}))
    out = normalize_budget_to_pcm(out)
    out = normalize_constraints(out)
    return out
