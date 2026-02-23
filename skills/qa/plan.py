from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, Optional

from core.llm_client import qwen_chat
from skills.search.extractors import (
    _extract_json_obj,
    _normalize_constraint_extract,
    _normalize_semantic_extract,
)


QA_EXTRACT_ALL_SYSTEM = """You output STRICT JSON only (no markdown, no explanation).

### ROLE
You are a specialist in parsing Real Estate search queries. Your task is to transform natural language into a structured schema for property filtering and Q&A.

### SCHEMA SPECIFICATION
{
  "constraints": {
    "max_rent_pcm": number|null,
    "available_from": string|null, 
    "furnish_type": string|null,
    "let_type": string|null,
    "layout_options": [{"bedrooms": int|null, "bathrooms": number|null, "property_type": string|null, "layout_tag": string|null}],
    "min_tenancy_months": number|null,
    "min_size_sqm": number|null,
    "min_size_sqft": number|null,
    "location_keywords": string[],
    "k": int|null,
    "update_scope": "all"|"specific_index"|null,
    "location_update_mode": string|null
  },
  "semantic_terms": {
    "transit_terms": string[],
    "school_terms": string[],
    "amenities_and_services": string[], 
    "general_semantic_phrases": string[]
  }
}

### EXTRACTION RULES (STRICT)
1. **Layout vs. Semantic Separation**: 
   - `layout_options` MUST ONLY contain physical room counts (bedrooms, bathrooms) and property types (Flat, House, Studio).
   - `amenities_and_services` MUST contain building features: e.g., "Gym", "Concierge", "Porter", "Lift", "Parking", "Balcony", "Garden". 
   - NEVER put amenities (like Gym) into layout_options.

2. **Semantic Categorization**:
   - `transit_terms`: Only transport-related entities (Stations, Lines, DLR, Underground).
   - `school_terms`: Only education-related entities (Schools, Universities, Academies).
   - `amenities_and_services`: Physical building/flat features not related to room count.
   - `general_semantic_phrases`: Subjective or lifestyle descriptors (e.g., "modern", "quiet", "near parks").
"""

@dataclass
class QAPlan:
    hard_constraints: Dict[str, Any]
    semantic_terms: Dict[str, Any]
    plan_source: str
    llm_error: Dict[str, str]


def _qa_rule_fallback_hard_constraints(question_text: str) -> Dict[str, Any]:
    # Keep fallback conservative: only extract obvious let/furnish/date/price hints.
    text = str(question_text or "").strip().lower()
    if not text:
        return {}
    out: Dict[str, Any] = {}
    if re.search(r"\bfurnished\b", text):
        out["furnish_type"] = "furnished"
    elif re.search(r"\bunfurnished\b", text):
        out["furnish_type"] = "unfurnished"
    elif re.search(r"\bpart[- ]?furnished\b", text):
        out["furnish_type"] = "part-furnished"

    if re.search(r"\bshort[\s-]?term|\bshort[\s-]?let\b", text):
        out["let_type"] = "short term"
    elif re.search(r"\blong[\s-]?term|\blong[\s-]?let\b", text):
        out["let_type"] = "long term"
    return out


def _qa_rule_fallback_semantic_terms(question_text: str) -> Dict[str, Any]:
    text = str(question_text or "").strip().lower()
    if not text:
        return {"transit_terms": [], "school_terms": [], "amenities_and_services": [], "general_semantic_phrases": []}
    tokens = [t for t in re.findall(r"[a-z0-9][a-z0-9'_-]*", text) if len(t) >= 3]
    transit_terms = []
    school_terms = []
    amenities = []
    general = []
    for t in tokens:
        if any(k in t for k in ("station", "tube", "metro", "train", "commute", "transport")):
            transit_terms.append(t)
        elif any(k in t for k in ("school", "college", "university", "catchment", "nursery")):
            school_terms.append(t)
        elif any(
            k in t
            for k in (
                "gym",
                "concierge",
                "porter",
                "lift",
                "elevator",
                "parking",
                "balcony",
                "garden",
                "pool",
            )
        ):
            amenities.append(t)
        else:
            general.append(t)

    def _dedup(xs):
        out = []
        seen = set()
        for x in xs:
            if x in seen:
                continue
            seen.add(x)
            out.append(x)
        return out

    return {
        "transit_terms": _dedup(transit_terms)[:8],
        "school_terms": _dedup(school_terms)[:8],
        "amenities_and_services": _dedup(amenities)[:12],
        # Keep downstream compatibility: QA semantic pipeline consumes general_semantic_phrases.
        "general_semantic_phrases": _dedup(amenities + general)[:20],
    }


def _try_build_qa_plan_via_llm(question_text: str) -> Optional[QAPlan]:
    text = str(question_text or "").strip()
    try:
        raw = qwen_chat(
            [
                {"role": "system", "content": QA_EXTRACT_ALL_SYSTEM},
                {"role": "user", "content": "User asks:\n" + text},
            ],
            temperature=0.0,
        ).strip()
    except Exception:
        return None

    obj = _extract_json_obj(raw)
    if not isinstance(obj, dict):
        return None
    constraints = _normalize_constraint_extract((obj or {}).get("constraints") or {})
    semantic_terms_raw = (obj or {}).get("semantic_terms") or {}
    semantic_terms = _normalize_semantic_extract(semantic_terms_raw)
    amenities = [
        str(x).strip().lower()
        for x in (semantic_terms_raw.get("amenities_and_services") or [])
        if str(x).strip()
    ]
    if amenities:
        merged = list(semantic_terms.get("general_semantic_phrases") or [])
        seen = {str(x).strip().lower() for x in merged if str(x).strip()}
        for x in amenities:
            if x in seen:
                continue
            seen.add(x)
            merged.append(x)
        semantic_terms["general_semantic_phrases"] = merged
    semantic_terms["amenities_and_services"] = amenities
    return QAPlan(
        hard_constraints=constraints,
        semantic_terms=semantic_terms,
        plan_source="qa_unified_plan",
        llm_error={},
    )


def build_qa_plan(question_text: str) -> QAPlan:
    text = str(question_text or "").strip()
    plan = _try_build_qa_plan_via_llm(text)
    if plan is not None:
        return plan
    return QAPlan(
        hard_constraints=_qa_rule_fallback_hard_constraints(text),
        semantic_terms=_qa_rule_fallback_semantic_terms(text),
        plan_source="qa_rule_fallback",
        llm_error={"error_type": "UnifiedPlanFailed", "error": "LLM unavailable or invalid JSON"},
    )
