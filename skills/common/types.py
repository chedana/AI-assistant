from __future__ import annotations

from typing import Any, Dict, List, Literal, TypedDict


SemanticParseSource = Literal["llm_combined", "fallback_split_calls"]


class SemanticTerms(TypedDict, total=False):
    transit_terms: List[str]
    school_terms: List[str]
    general_semantic_phrases: List[str]


class ParseSignalsOutput(TypedDict):
    semantic_parse_source: SemanticParseSource | str
    llm_constraints: Dict[str, Any]
    semantic_terms: SemanticTerms
    rule_constraints: Dict[str, Any]
    final_constraints: Dict[str, Any]
    structured_audit: Dict[str, Any]
    signals: Dict[str, Any]
