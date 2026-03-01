"""Signal building and Stage A query construction."""

from typing import Any, Dict, List, Optional

from skills.search.text_utils import _safe_text, _to_float
from skills.search.location_match import _normalize_location_keyword


def split_query_signals(
    user_in: str,
    c: Dict[str, Any],
    precomputed_semantic_terms: Optional[Dict[str, Any]] = None,
    semantic_parse_source: str = "llm",
) -> Dict[str, Any]:
    c = c or {}
    location_intent = []
    for x in (c.get("location_keywords") or []):
        raw = str(x).strip()
        if not raw:
            continue
        norm = _normalize_location_keyword(raw)
        if norm:
            location_intent.append(norm)

    model_terms = precomputed_semantic_terms or {
        "transit_terms": [],
        "school_terms": [],
        "general_semantic_phrases": [],
    }
    transit_terms: List[str] = []
    school_terms: List[str] = []
    for t in model_terms.get("transit_terms", []):
        s = str(t).strip().lower()
        if s:
            transit_terms.append(s)
    for t in model_terms.get("school_terms", []):
        s = str(t).strip().lower()
        if s:
            school_terms.append(s)

    general_semantic = [str(x).strip().lower() for x in model_terms.get("general_semantic_phrases", []) if str(x).strip()]
    general_semantic = list(dict.fromkeys(general_semantic))
    transit_terms = list(dict.fromkeys([x for x in transit_terms if str(x).strip()]))
    school_terms = list(dict.fromkeys([x for x in school_terms if str(x).strip()]))

    return {
        "hard_constraints": {
            "max_rent_pcm": c.get("max_rent_pcm"),
            "available_from": c.get("available_from"),
            "furnish_type": c.get("furnish_type"),
            "let_type": c.get("let_type"),
            "layout_options": c.get("layout_options") or [],
            "min_tenancy_months": c.get("min_tenancy_months"),
            "min_size_sqm": c.get("min_size_sqm"),
        },
        "location_intent": location_intent,
        "topic_preferences": {
            "transit_terms": transit_terms,
            "school_terms": school_terms,
        },
        "general_semantic": general_semantic,
        "semantic_debug": {
            "parse_source": semantic_parse_source,
            "model_terms": model_terms,
            "final_general_semantic": general_semantic,
        },
    }


def build_stage_a_query(signals: Dict[str, Any], user_in: str) -> str:
    parts: List[str] = []
    hard = signals.get("hard_constraints", {}) or {}

    # Keep hard hints in Stage A retrieval to improve recall coverage.
    if hard.get("max_rent_pcm") is not None:
        parts.append(f"under {int(float(hard.get('max_rent_pcm')))} pcm")
    if hard.get("furnish_type"):
        parts.append(str(hard.get("furnish_type")))
    if hard.get("let_type"):
        parts.append(str(hard.get("let_type")))
    for opt in (hard.get("layout_options") or []):
        if not isinstance(opt, dict):
            continue
        bed = opt.get("bedrooms")
        bath = opt.get("bathrooms")
        ptype = opt.get("property_type")
        ltag = str(opt.get("layout_tag") or "").strip().lower()
        obudget = opt.get("max_rent_pcm")
        seg: List[str] = []
        if ltag == "studio":
            seg.append("studio")
        if bed is not None:
            try:
                seg.append(f"{int(float(bed))} bedroom")
            except Exception:
                pass
        if bath is not None:
            try:
                seg.append(f"{float(bath):g} bathroom")
            except Exception:
                pass
        if ptype:
            seg.append(str(ptype))
        if obudget is not None:
            try:
                seg.append(f"under {int(float(obudget))} pcm")
            except Exception:
                pass
        if seg:
            parts.append(" ".join(seg))
    if hard.get("min_tenancy_months") is not None:
        parts.append(f"{float(hard.get('min_tenancy_months')):g} months tenancy")
    if hard.get("min_size_sqm") is not None:
        parts.append(f"at least {float(hard.get('min_size_sqm')):g} sqm")

    parts.extend([x for x in signals.get("location_intent", []) if str(x).strip()])
    parts.extend([x for x in signals.get("general_semantic", []) if str(x).strip()])
    if not parts:
        return user_in
    return " | ".join(parts[:20])


def candidate_snapshot(r: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "url": _safe_text(r.get("url")),
        "title": _safe_text(r.get("title")),
        "address": _safe_text(r.get("address")),
        "price_pcm": _to_float(r.get("price_pcm")),
        "bedrooms": _to_float(r.get("bedrooms")),
        "bathrooms": _to_float(r.get("bathrooms")),
        "available_from": _safe_text(r.get("available_from")),
        "retrieval_score": _to_float(r.get("retrieval_score")),
        "qdrant_score": _to_float(r.get("qdrant_score")),
        "_qdrant_id": _safe_text(r.get("_qdrant_id")) or None,
    }


