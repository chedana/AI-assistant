from __future__ import annotations

import os
from typing import Any, Dict, Optional

from skills.common.audit_log import emit_structured_audit_logs
from core.llm_client import llm_extract, llm_extract_all_signals
from core.settings import STRUCTURED_POLICY
from skills.common.types import ParseSignalsOutput
from skills.search.extractors import repair_extracted_constraints
from skills.search.handler import apply_structured_policy, split_query_signals


def parse_signals(
    user_text: str,
    existing_constraints: Optional[Dict[str, Any]] = None,
    *,
    policy: Optional[str] = None,
    emit_audit: bool = False,
    audit_context: str = "search",
) -> ParseSignalsOutput:
    text = str(user_text or "").strip()
    semantic_parse_source = "llm_combined"
    debug_enabled = str(os.environ.get("ROUTER_DEBUG", "0")).strip().lower() in {"1", "true", "yes", "on"}
    llm_constraints: Dict[str, Any] = {}
    semantic_terms: Dict[str, Any] = {}

    try:
        combined = llm_extract_all_signals(text, existing_constraints)
        llm_constraints = combined.get("constraints") or {}
        semantic_terms = combined.get("semantic_terms") or {}
    except Exception as exc:
        if debug_enabled:
            try:
                print(
                    "Bot> [debug] "
                    + str(
                        {
                            "phase": "parse_signals_llm_extract_all_error",
                            "error_type": type(exc).__name__,
                            "error": str(exc),
                        }
                    )
                )
            except Exception:
                pass
        semantic_parse_source = "fallback_split_calls"
        llm_constraints = llm_extract(text, existing_constraints)
        semantic_terms = {}

    rule_constraints = repair_extracted_constraints(llm_constraints, text)
    final_constraints, structured_audit = apply_structured_policy(
        user_text=text,
        llm_constraints=llm_constraints,
        rule_constraints=rule_constraints,
        policy=str(policy or STRUCTURED_POLICY),
    )
    final_constraints = final_constraints or {}
    signals = split_query_signals(
        text,
        final_constraints,
        precomputed_semantic_terms=semantic_terms,
        semantic_parse_source=semantic_parse_source,
    )
    if emit_audit:
        emit_structured_audit_logs(
            user_text=text,
            semantic_parse_source=semantic_parse_source,
            audit=structured_audit or {},
            context=audit_context,
        )
    out: ParseSignalsOutput = {
        "semantic_parse_source": semantic_parse_source,
        "llm_constraints": llm_constraints,
        "semantic_terms": semantic_terms,
        "rule_constraints": rule_constraints,
        "final_constraints": final_constraints,
        "structured_audit": structured_audit or {},
        "signals": signals,
    }
    return out


def derive_signals(
    *,
    parsed: ParseSignalsOutput,
    user_text: str,
    constraints: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    c = constraints if constraints is not None else (parsed.get("final_constraints") or {})
    return split_query_signals(
        str(user_text or ""),
        c or {},
        precomputed_semantic_terms=parsed.get("semantic_terms") or {},
        semantic_parse_source=str(parsed.get("semantic_parse_source") or "llm_combined"),
    )
