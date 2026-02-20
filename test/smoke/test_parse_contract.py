#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import os
import sys
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def run() -> int:
    # parse_signals imports core.llm_client; openai package must be importable.
    if importlib.util.find_spec("openai") is None:
        print("SKIP: openai dependency is not installed.")
        return 0

    from skills.common.parse_signals import derive_signals, parse_signals

    with patch(
        "skills.common.parse_signals.llm_extract_all_signals",
        return_value={
            "constraints": {"max_rent_pcm": 2500, "location_keywords": ["waterloo"]},
            "semantic_terms": {"transit_terms": ["waterloo station"], "school_terms": [], "general_semantic_phrases": []},
        },
    ), patch(
        "skills.common.parse_signals.repair_extracted_constraints",
        side_effect=lambda c, _t: c,
    ), patch(
        "skills.common.parse_signals.apply_structured_policy",
        return_value=({"max_rent_pcm": 2500, "location_keywords": ["waterloo"]}, {"conflict_count": 0}),
    ), patch(
        "skills.common.parse_signals.split_query_signals",
        side_effect=lambda _text, c, **_kwargs: {
            "hard_constraints": {"max_rent_pcm": c.get("max_rent_pcm")},
            "location_intent": c.get("location_keywords") or [],
            "topic_preferences": {"transit_terms": ["waterloo station"], "school_terms": []},
            "general_semantic": [],
            "semantic_debug": {},
        },
    ), patch("skills.common.parse_signals.emit_structured_audit_logs") as mock_emit:
        parsed = parse_signals(
            "find 1 bed near waterloo under 2500",
            emit_audit=True,
            audit_context="qa",
        )

    required_keys = {
        "semantic_parse_source",
        "llm_constraints",
        "semantic_terms",
        "rule_constraints",
        "final_constraints",
        "structured_audit",
        "signals",
    }
    _assert(required_keys.issubset(set(parsed.keys())), "parse_signals contract keys missing")
    _assert(isinstance(parsed["signals"], dict), "signals must be dict")
    _assert(mock_emit.call_count == 1, "emit_structured_audit_logs should be called when emit_audit=True")
    call_kwargs = mock_emit.call_args.kwargs
    _assert(call_kwargs.get("context") == "qa", "audit context should be passed through")

    derived = derive_signals(parsed=parsed, user_text="same query", constraints={"max_rent_pcm": 2200, "location_keywords": ["bank"]})
    _assert(isinstance(derived, dict), "derive_signals must return dict")
    _assert("hard_constraints" in derived, "derived signals missing hard_constraints")
    print("PASS: parse_signals contract")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
