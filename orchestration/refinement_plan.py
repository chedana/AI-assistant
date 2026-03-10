from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from core.llm_client import qwen_chat
from orchestration.merger import SNAPSHOT_FIELDS
from skills.common.parse_signals import parse_signals
from skills.search.extractors import (
    _extract_json_obj,
    _normalize_constraint_extract,
    _normalize_semantic_extract,
)


@dataclass
class RefinementPlan:
    set_fields: Dict[str, Any]
    clear_fields: List[str]
    is_reset: bool = False
    semantic_terms: Dict[str, Any] = None
    source: str = "fallback"


def _infer_clear_fields_from_text(user_text: str) -> List[str]:
    text = str(user_text or "").lower()
    if not text:
        return []

    clear_fields: List[str] = []
    rules = [
        ("location_keywords", [r"\bany location\b", r"\bno location preference\b", r"\bremove location\b"]),
        ("layout_options", [r"\bany layout\b", r"\bno layout preference\b", r"\bremove layout\b"]),
        ("furnish_type", [r"\bno furnish(?:ing)? preference\b", r"\bremove furnish(?:ing)?\b"]),
        ("let_type", [r"\bno let type preference\b", r"\bremove let type\b"]),
        ("max_rent_pcm", [r"\bno budget limit\b", r"\bremove budget\b"]),
        ("available_from", [r"\bany move[\s-]?in\b", r"\bremove move[\s-]?in\b"]),
        ("min_tenancy_months", [r"\bno tenancy minimum\b", r"\bremove tenancy\b"]),
        ("min_size_sqm", [r"\bno size minimum\b", r"\bremove size\b"]),
    ]
    for field, patterns in rules:
        if any(re.search(p, text) for p in patterns):
            clear_fields.append(field)
    return clear_fields


def _try_build_plan_via_llm(
    *,
    user_text: str,
    existing_constraints: Optional[Dict[str, Any]],
) -> Optional[RefinementPlan]:
    system_prompt = (
        "Rental-search constraint extractor. Return STRICT JSON only, no markdown.\n"
        "Omit null values, empty arrays [], empty objects {}, and false booleans. Only include fields the user actually mentioned.\n"
        "set_fields keys (only these 8): location_keywords(string[]), max_rent_pcm(number), available_from(string), "
        "furnish_type(string), let_type(string), layout_options([{bedrooms,bathrooms,property_type,layout_tag,max_rent_pcm}]), "
        "min_tenancy_months(number), min_size_sqm(number).\n"
        "clear_fields: list field names ONLY when user explicitly says remove/clear/no-preference (e.g. \"no budget limit\"). Default is SET, not CLEAR.\n"
        "is_reset: true only for explicit reset/start-over intent.\n"
        "semantic_terms: {transit_terms[], school_terms[], general_semantic_phrases[]} — soft reranking phrases only, no hard constraints.\n"
        "Rules: location_keywords verbatim from user text, no spelling correction. Keep named entities as full phrases. "
        "layout_options: studio→bedrooms:0+layout_tag:\"studio\". If uncertain, omit the field.\n"
        "\n"
        "Q: '2 bed in Canary Wharf under 2500'\n"
        'A: {"set_fields":{"location_keywords":["Canary Wharf"],"max_rent_pcm":2500,"layout_options":[{"bedrooms":2}]}}\n'
        "Q: 'start over, I want something different'\n"
        'A: {"is_reset":true}\n'
        "Q: 'furnished flat near good schools in Brixton'\n"
        'A: {"set_fields":{"location_keywords":["Brixton"],"furnish_type":"furnished"},"semantic_terms":{"school_terms":["good schools"]}}\n'
    )
    user_payload = "User input:\n" + str(user_text or "")
    try:
        raw = qwen_chat(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_payload},
            ],
            temperature=0.0,
        ).strip()
    except Exception:
        return None

    obj = _extract_json_obj(raw)
    if not isinstance(obj, dict):
        return None

    normalized_set = _normalize_constraint_extract(obj.get("set_fields") or {})
    set_fields = {k: normalized_set.get(k) for k in SNAPSHOT_FIELDS}

    clear_fields_raw = obj.get("clear_fields")
    clear_fields: List[str] = []
    if isinstance(clear_fields_raw, list):
        for x in clear_fields_raw:
            key = str(x).strip()
            if key in SNAPSHOT_FIELDS:
                clear_fields.append(key)
    clear_fields = list(dict.fromkeys(clear_fields))

    is_reset = bool(obj.get("is_reset"))
    semantic_terms = _normalize_semantic_extract(obj.get("semantic_terms") or {})
    return RefinementPlan(
        set_fields=set_fields,
        clear_fields=clear_fields,
        is_reset=is_reset,
        semantic_terms=semantic_terms,
        source="llm_unified_plan",
    )


def build_refinement_plan(
    *,
    user_text: str,
    existing_constraints: Optional[Dict[str, Any]],
) -> RefinementPlan:
    llm_plan = _try_build_plan_via_llm(
        user_text=user_text,
        existing_constraints=existing_constraints,
    )
    if llm_plan is not None:
        # Rule-level safety net: conservative clear inference can only add fields.
        inferred_clear = _infer_clear_fields_from_text(user_text)
        if inferred_clear:
            llm_plan.clear_fields = list(dict.fromkeys(llm_plan.clear_fields + inferred_clear))
        return llm_plan

    parsed = parse_signals(
        user_text,
        existing_constraints,
        emit_audit=False,
        audit_context="search",
    )
    set_fields = parsed.get("final_constraints") or {}
    set_fields = {k: v for k, v in set_fields.items() if k in SNAPSHOT_FIELDS}

    rule_constraints = parsed.get("rule_constraints") or {}
    is_reset = bool(rule_constraints.get("_replace_all_constraints"))

    clear_fields = []
    if bool(rule_constraints.get("_clear_location_keywords")):
        clear_fields.append("location_keywords")
    clear_fields.extend(_infer_clear_fields_from_text(user_text))
    clear_fields = list(dict.fromkeys([x for x in clear_fields if x in SNAPSHOT_FIELDS]))

    return RefinementPlan(
        set_fields=set_fields,
        clear_fields=clear_fields,
        is_reset=is_reset,
        semantic_terms=parsed.get("semantic_terms") or {},
        source="parse_signals+rules",
    )
