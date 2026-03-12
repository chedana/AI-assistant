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
You are a specialist in parsing rental property Q&A questions. Extract structured constraints and identify what topics the user is asking about.

### OUTPUT SCHEMA
{
  "constraints": {
    "deposit": string|number|null,
    "max_rent_pcm": number|null,
    "available_from": string|null,
    "furnish_type": string|null,
    "let_type": string|null,
    "layout_options": [{"bedrooms": int|null, "bathrooms": number|null, "property_type": string|null, "layout_tag": string|null}],
    "min_tenancy_months": number|null,
    "min_size_sqm": number|null,
    "min_size_sqft": number|null,
    "location_keywords": string[]
  },
  "semantic_terms": {
    "transit_terms": string[],
    "school_terms": string[],
    "general_semantic_phrases": string[]
  }
}

### RULES
constraints — only extract what is explicitly mentioned in the question:
- deposit: "__ASKED__" if user asks about deposit; 0 if user asks for no deposit; else null.
- furnish_type: "furnished" | "unfurnished" | "part-furnished" | null.
- let_type: "short term" | "long term" | null.
- location_keywords: verbatim place names from the question only. Do NOT correct spelling or expand.
- layout_options: only if user asks about specific room counts or property type.
- All other fields: extract only if explicitly mentioned. Default to null / [].

semantic_terms — extract the user's actual words/phrases. Do NOT expand or add synonyms:
- transit_terms: ANY transport-related topic — station names, line names, AND general words like "transport", "commute", "bus links", "tube links", "public transport", "getting around".
- school_terms: ANY education-related topic — school names, "good schools", "nurseries", "universities", "catchment area".
- general_semantic_phrases: everything else — "pet friendly", "gym", "parking", "garden", "quiet", "balcony", "concierge", "modern".

### EXAMPLES
Q: "Is transport good and is it pet friendly?"
{"constraints":{"deposit":null,"max_rent_pcm":null,"available_from":null,"furnish_type":null,"let_type":null,"layout_options":[],"min_tenancy_months":null,"min_size_sqm":null,"min_size_sqft":null,"location_keywords":[]},"semantic_terms":{"transit_terms":["transport"],"school_terms":[],"general_semantic_phrases":["pet friendly"]}}

Q: "Does it have a deposit?"
{"constraints":{"deposit":"__ASKED__","max_rent_pcm":null,"available_from":null,"furnish_type":null,"let_type":null,"layout_options":[],"min_tenancy_months":null,"min_size_sqm":null,"min_size_sqft":null,"location_keywords":[]},"semantic_terms":{"transit_terms":[],"school_terms":[],"general_semantic_phrases":[]}}

Q: "Is it near the Victoria line and are there good schools?"
{"constraints":{"deposit":null,"max_rent_pcm":null,"available_from":null,"furnish_type":null,"let_type":null,"layout_options":[],"min_tenancy_months":null,"min_size_sqm":null,"min_size_sqft":null,"location_keywords":[]},"semantic_terms":{"transit_terms":["Victoria line"],"school_terms":["good schools"],"general_semantic_phrases":[]}}

Q: "Is it furnished and does it allow pets?"
{"constraints":{"deposit":null,"max_rent_pcm":null,"available_from":null,"furnish_type":"furnished","let_type":null,"layout_options":[],"min_tenancy_months":null,"min_size_sqm":null,"min_size_sqft":null,"location_keywords":[]},"semantic_terms":{"transit_terms":[],"school_terms":[],"general_semantic_phrases":["pets allowed"]}}

Q: "Is the commute to the City easy?"
{"constraints":{"deposit":null,"max_rent_pcm":null,"available_from":null,"furnish_type":null,"let_type":null,"layout_options":[],"min_tenancy_months":null,"min_size_sqm":null,"min_size_sqft":null,"location_keywords":[]},"semantic_terms":{"transit_terms":["commute to the City"],"school_terms":[],"general_semantic_phrases":[]}}

Q: "Does it have a gym and parking, and is it pet friendly?"
{"constraints":{"deposit":null,"max_rent_pcm":null,"available_from":null,"furnish_type":null,"let_type":null,"layout_options":[],"min_tenancy_months":null,"min_size_sqm":null,"min_size_sqft":null,"location_keywords":[]},"semantic_terms":{"transit_terms":[],"school_terms":[],"general_semantic_phrases":["gym","parking","pet friendly"]}}

Q: "Is it available from March and is it furnished?"
{"constraints":{"deposit":null,"max_rent_pcm":null,"available_from":"2026-03-01","furnish_type":"furnished","let_type":null,"layout_options":[],"min_tenancy_months":null,"min_size_sqm":null,"min_size_sqft":null,"location_keywords":[]},"semantic_terms":{"transit_terms":[],"school_terms":[],"general_semantic_phrases":[]}}

Q: "Is it near good bus links and nurseries, and does it have a balcony?"
{"constraints":{"deposit":null,"max_rent_pcm":null,"available_from":null,"furnish_type":null,"let_type":null,"layout_options":[],"min_tenancy_months":null,"min_size_sqm":null,"min_size_sqft":null,"location_keywords":[]},"semantic_terms":{"transit_terms":["bus links"],"school_terms":["nurseries"],"general_semantic_phrases":["balcony"]}}
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
    if re.search(r"\bno\s+deposit\b|\bwithout\s+deposit\b", text):
        out["deposit"] = 0
    elif re.search(r"\bdeposit\b", text):
        out["deposit"] = "__ASKED__"

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


def _enrich_constraints_from_question(question_text: str, constraints: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(constraints or {})
    text = str(question_text or "").strip().lower()
    if not text:
        return out
    if out.get("deposit") is None:
        if re.search(r"\bno\s+deposit\b|\bwithout\s+deposit\b", text):
            out["deposit"] = 0
        elif re.search(r"\bdeposit\b", text):
            out["deposit"] = "__ASKED__"
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
        "general_semantic_phrases": _dedup(general)[:20],
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
    constraints = _enrich_constraints_from_question(text, constraints)
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
