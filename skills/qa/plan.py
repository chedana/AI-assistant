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
Schema:
{
  "constraints": {
    "max_rent_pcm": number|null,
    "available_from": string|null,
    "furnish_type": string|null,
    "let_type": string|null,
    "layout_options": [{"bedrooms": int|null, "bathrooms": number|null, "property_type": string|null, "layout_tag": string|null, "max_rent_pcm": number|null}],
    "min_tenancy_months": number|null,
    "min_size_sqm": number|null,
    "min_size_sqft": number|null,
    "location_keywords": string[],
    "k": int|null,
    "update_scope": string|null,
    "location_update_mode": string|null,
    "layout_update_mode": string|null
  },
  "semantic_terms": {
    "transit_terms": string[],
    "school_terms": string[],
    "general_semantic_phrases": string[]
  }
}
Rules:
- This extraction is for QA over existing listings context.
- constraints: extract hard constraints only.
- semantic_terms: extract phrase-level semantic intents.
- For constraints.location_keywords, do verbatim extraction from user text spans only.
- Do NOT correct spelling, expand abbreviations, canonicalize, or rewrite location text.
- For any explicit layout request (single or multiple), put them into constraints.layout_options.
- Keep named entities as full phrases (e.g., "Seven Mills Primary School", "Heron Quays Station").
- Do NOT put hard constraints into semantic_terms (budget, bedroom count, property type, strict location filters).
- Do NOT split one entity into component words.
- Keep entity phrases intact (e.g., station/school full names).
- Return [] or null when absent.
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
        return {"transit_terms": [], "school_terms": [], "general_semantic_phrases": []}
    tokens = [t for t in re.findall(r"[a-z0-9][a-z0-9'_-]*", text) if len(t) >= 3]
    transit_terms = []
    school_terms = []
    general = []
    for t in tokens:
        if any(k in t for k in ("station", "tube", "metro", "train", "commute", "transport")):
            transit_terms.append(t)
        elif any(k in t for k in ("school", "college", "university", "catchment", "nursery")):
            school_terms.append(t)
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
        "general_semantic_phrases": _dedup(general)[:12],
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
    semantic_terms = _normalize_semantic_extract((obj or {}).get("semantic_terms") or {})
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
