from __future__ import annotations

from datetime import datetime
from typing import Any, Dict

from core.logger import append_jsonl
from core.settings import (
    ENABLE_STRUCTURED_CONFLICT_LOG,
    ENABLE_STRUCTURED_TRAINING_LOG,
    STRUCTURED_CONFLICT_LOG_PATH,
    STRUCTURED_TRAINING_LOG_PATH,
)


def append_structured_conflict_log(
    *,
    user_text: str,
    semantic_parse_source: str,
    audit: Dict[str, Any],
    context: str = "search",
) -> None:
    if not ENABLE_STRUCTURED_CONFLICT_LOG:
        return
    if not audit or int(audit.get("conflict_count", 0)) <= 0:
        return
    rec = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "context": str(context or "search"),
        "policy": audit.get("policy"),
        "semantic_parse_source": semantic_parse_source,
        "user_text": user_text,
        "agreement_rate": audit.get("agreement_rate"),
        "conflict_count": audit.get("conflict_count"),
        "conflicts": audit.get("conflicts", []),
        "llm_constraints": audit.get("llm_constraints", {}),
        "rule_constraints": audit.get("rule_constraints", {}),
        "final_constraints": audit.get("final_constraints", {}),
    }
    append_jsonl(STRUCTURED_CONFLICT_LOG_PATH, rec, "structured conflict log")


def append_structured_training_samples(
    *,
    user_text: str,
    semantic_parse_source: str,
    audit: Dict[str, Any],
    context: str = "search",
) -> None:
    if not ENABLE_STRUCTURED_TRAINING_LOG:
        return
    if not audit:
        return
    conflicts = audit.get("conflicts", [])
    if not conflicts:
        return

    ts = datetime.utcnow().isoformat() + "Z"
    for item in conflicts:
        rec = {
            "timestamp": ts,
            "context": str(context or "search"),
            "sample_type": "rule_disagreement_supervision",
            "policy": audit.get("policy"),
            "semantic_parse_source": semantic_parse_source,
            "user_text": user_text,
            "field": item.get("field"),
            "risk": item.get("risk"),
            "action": item.get("action"),
            "llm_value": item.get("llm_value"),
            "rule_value": item.get("rule_value"),
            "target_value": item.get("final_value"),
            "target_constraints": audit.get("final_constraints", {}),
        }
        append_jsonl(STRUCTURED_TRAINING_LOG_PATH, rec, "structured training samples")


def emit_structured_audit_logs(
    *,
    user_text: str,
    semantic_parse_source: str,
    audit: Dict[str, Any],
    context: str = "search",
) -> None:
    append_structured_conflict_log(
        user_text=user_text,
        semantic_parse_source=semantic_parse_source,
        audit=audit,
        context=context,
    )
    append_structured_training_samples(
        user_text=user_text,
        semantic_parse_source=semantic_parse_source,
        audit=audit,
        context=context,
    )
