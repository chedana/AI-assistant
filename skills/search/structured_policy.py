"""Structured-policy arbitration: choose between LLM and rule-extracted constraints."""

from typing import Any, Dict, List, Tuple

from core.internal_helpers import HIGH_RISK_STRUCTURED_FIELDS, _choose_structured_value
from skills.search.constraint_ops import _canon_for_structured_compare, _normalize_for_structured_policy

# NOTE: audit_log is imported lazily inside the functions below to avoid the
# circular import:  structured_policy → skills.common.audit_log (triggers
# skills.common.__init__) → parse_signals → structured_policy.


STRUCTURED_FIELDS = [
    "max_rent_pcm",
    "available_from",
    "furnish_type",
    "let_type",
    "layout_options",
    "min_tenancy_months",
    "min_size_sqm",
    "location_keywords",
    "k",
    "bool_preferences",
    "commute_destination",
]


def apply_structured_policy(
    user_text: str,
    llm_constraints: Dict[str, Any],
    rule_constraints: Dict[str, Any],
    policy: str,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    llm_n = _normalize_for_structured_policy(llm_constraints)
    rule_n = _normalize_for_structured_policy(rule_constraints)

    final_constraints: Dict[str, Any] = {}
    conflicts: List[Dict[str, Any]] = []
    agreements = 0

    for field in STRUCTURED_FIELDS:
        llm_v = llm_n.get(field)
        rule_v = rule_n.get(field)
        final_v, action = _choose_structured_value(policy, field, llm_v, rule_v)
        final_constraints[field] = final_v

        same = _canon_for_structured_compare(llm_v) == _canon_for_structured_compare(rule_v)
        if same:
            agreements += 1
            continue

        conflicts.append(
            {
                "field": field,
                "risk": "high" if field in HIGH_RISK_STRUCTURED_FIELDS else "low",
                "action": action,
                "llm_value": llm_v,
                "rule_value": rule_v,
                "final_value": final_v,
            }
        )

    final_constraints = _normalize_for_structured_policy(final_constraints)
    total = len(STRUCTURED_FIELDS)
    conflict_count = len(conflicts)
    agreement_rate = float(agreements) / float(total) if total > 0 else 1.0

    audit = {
        "policy": policy,
        "input_text": user_text,
        "llm_constraints": llm_n,
        "rule_constraints": rule_n,
        "final_constraints": final_constraints,
        "total_fields": total,
        "agreement_fields": agreements,
        "conflict_count": conflict_count,
        "agreement_rate": agreement_rate,
        "conflicts": conflicts,
    }
    return final_constraints, audit


def append_structured_conflict_log(
    user_text: str,
    semantic_parse_source: str,
    audit: Dict[str, Any],
) -> None:
    from skills.common.audit_log import append_structured_conflict_log as _common  # lazy import
    _common(
        user_text=user_text,
        semantic_parse_source=semantic_parse_source,
        audit=audit,
        context="search",
    )


def append_structured_training_samples(
    user_text: str,
    semantic_parse_source: str,
    audit: Dict[str, Any],
) -> None:
    from skills.common.audit_log import append_structured_training_samples as _common  # lazy import
    _common(
        user_text=user_text,
        semantic_parse_source=semantic_parse_source,
        audit=audit,
        context="search",
    )
