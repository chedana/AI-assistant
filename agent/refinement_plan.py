from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from core.llm_client import qwen_chat
from skills.common.parse_signals import parse_signals
from skills.search.extractors import (
    _extract_json_obj,
    _normalize_constraint_extract,
    _normalize_semantic_extract,
)


SNAPSHOT_FIELDS = {
    "location_keywords",
    "layout_options",
    "max_rent_pcm",
    "available_from",
    "furnish_type",
    "let_type",
    "min_tenancy_months",
    "min_size_sqm",
}


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
        "You are a structured extraction engine for a rental-search assistant.\n"
        "Return STRICT JSON only (no markdown, no explanation).\n"
        "Schema:\n"
        "{\n"
        '  "set_fields": {\n'
        '    "location_keywords": string[]|null,\n'
        '    "max_rent_pcm": number|null,\n'
        '    "available_from": string|null,\n'
        '    "furnish_type": string|null,\n'
        '    "let_type": string|null,\n'
        '    "layout_options": [{"bedrooms": number|null, "bathrooms": number|null, "property_type": string|null, "layout_tag": string|null, "max_rent_pcm": number|null}]|null,\n'
        '    "min_tenancy_months": number|null,\n'
        '    "min_size_sqm": number|null\n'
        "  },\n"
        '  "clear_fields": [\n'
        '    "location_keywords" | "max_rent_pcm" | "available_from" | "furnish_type" | "let_type" | "layout_options" | "min_tenancy_months" | "min_size_sqm"\n'
        "  ],\n"
        '  "is_reset": boolean,\n'
        '  "semantic_terms": {\n'
        '    "transit_terms": string[],\n'
        '    "school_terms": string[],\n'
        '    "general_semantic_phrases": string[]\n'
        "  }\n"
        "}\n"
        "Rules:\n"
        "- Only use these 8 set_fields keys; do not add others.\n"
        "- clear_fields means explicit remove semantics: only include fields when user clearly says remove/clear/no-preference/unlimited "
        '(e.g., "no budget limit", "don\'t care about furnishing", "remove size requirement").\n'
        "- Default behavior is SET (add/update). Do not guess CLEAR.\n"
        "- If uncertain, leave fields null/empty instead of guessing.\n"
        "- For location_keywords, do verbatim extraction from user text spans only.\n"
        "- Do NOT correct spelling, expand abbreviations, canonicalize, or rewrite location text.\n"
        "- For any explicit location request (single or multiple), put them into set_fields.location_keywords.\n"
        "- For any explicit layout request (single or multiple), put them into set_fields.layout_options.\n"
        "- layout_options item schema: {\"bedrooms\":number|null,\"bathrooms\":number|null,\"property_type\":string|null,\"layout_tag\":string|null,\"max_rent_pcm\":number|null}.\n"
        "- semantic_terms are phrase-level soft intents for reranking only.\n"
        "- Keep named entities as full phrases; do NOT split entities into words.\n"
        "- Do NOT put hard constraints into semantic_terms (budget/bedrooms/property_type/strict location filters).\n"
        "- Avoid generic filler terms when concrete entities exist.\n"
        "- is_reset=true only for explicit reset/start-over/new-search-from-scratch/ignore-previous intent (equivalent to update_scope=replace_all).\n"
        "- Otherwise is_reset=false (equivalent to update_scope=patch).\n"
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
