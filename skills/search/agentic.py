from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from sentence_transformers import SentenceTransformer

from core.llm_client import llm_extract, llm_extract_all_signals
from core.settings import DEFAULT_K, DEFAULT_RECALL, EMBED_MODEL, ENABLE_STAGE_D_EXPLAIN
from skills.search.engine import load_stage_a_resources, stage_a_search
from skills.search.extractors import (
    compact_constraints_view,
    merge_constraints,
    normalize_budget_to_pcm,
    normalize_constraints,
    repair_extracted_constraints,
    summarize_constraint_changes,
)
from skills.search.handler import (
    apply_hard_filters_with_audit,
    apply_structured_policy,
    build_stage_a_query,
    format_listing_row,
    rank_stage_c,
    split_query_signals,
)


@dataclass
class SearchRuntime:
    qdrant_client: Any
    embedder: SentenceTransformer


def build_search_runtime() -> SearchRuntime:
    return SearchRuntime(
        qdrant_client=load_stage_a_resources(),
        embedder=SentenceTransformer(EMBED_MODEL),
    )


def _build_profile_patch(constraints: Dict[str, Any]) -> Dict[str, Any]:
    patch: Dict[str, Any] = {}
    if constraints.get("max_rent_pcm") is not None:
        patch["budget_max_pcm"] = constraints.get("max_rent_pcm")
    locs = constraints.get("location_keywords") or []
    if locs:
        patch["locations"] = list(locs)
    layouts = constraints.get("layout_options") or []
    if layouts:
        patch["layout_options"] = list(layouts)
    if constraints.get("furnish_type"):
        patch["furnish_type"] = constraints.get("furnish_type")
    if constraints.get("let_type"):
        patch["let_type"] = constraints.get("let_type")
    return patch


def run_search_skill(
    *,
    user_text: str,
    state_constraints: Optional[Dict[str, Any]],
    runtime: SearchRuntime,
    k: int = DEFAULT_K,
    recall: int = DEFAULT_RECALL,
) -> Dict[str, Any]:
    semantic_parse_source = "llm_combined"
    combined: Dict[str, Any] = {"constraints": {}, "semantic_terms": {}}
    llm_extracted: Dict[str, Any] = {}
    try:
        combined = llm_extract_all_signals(user_text, state_constraints)
        llm_extracted = combined.get("constraints") or {}
        semantic_terms = combined.get("semantic_terms") or {}
    except Exception:
        semantic_parse_source = "fallback_split_calls"
        llm_extracted = llm_extract(user_text, state_constraints)
        semantic_terms = {}

    prev_constraints = dict(state_constraints or {})
    llm_extracted_raw = copy.deepcopy(llm_extracted or {})
    rule_extracted = repair_extracted_constraints(llm_extracted, user_text)
    extracted, structured_audit = apply_structured_policy(
        user_text=user_text,
        llm_constraints=llm_extracted_raw,
        rule_constraints=rule_extracted,
    )

    merged = merge_constraints(state_constraints, extracted)
    merged = normalize_budget_to_pcm(merged)
    merged = normalize_constraints(merged)
    if not merged.get("k"):
        merged["k"] = int(k)

    signals = split_query_signals(
        user_text,
        merged,
        precomputed_semantic_terms=semantic_terms,
        semantic_parse_source=semantic_parse_source,
    )
    stage_a_query = build_stage_a_query(signals, user_text)
    stage_a_df = stage_a_search(
        runtime.qdrant_client,
        runtime.embedder,
        query=stage_a_query,
        recall=int(recall),
        c=merged,
    )
    filtered, _ = apply_hard_filters_with_audit(stage_a_df, merged)
    ranked, _ = rank_stage_c(filtered, signals, embedder=runtime.embedder)

    if len(filtered) < int(k):
        df = ranked.reset_index(drop=True)
    else:
        df = ranked.head(int(k)).reset_index(drop=True)

    listings: List[Dict[str, Any]] = []
    if df is not None and len(df) > 0:
        for _, row in df.iterrows():
            listings.append(row.to_dict())

    lines: List[str] = []
    if not listings:
        lines.append("I couldn't find any matching listings. Try changing area, budget, or layout.")
    else:
        lines.append(f"Top {min(int(k), len(listings))} results:")
        for i, row in enumerate(listings[: int(k)], start=1):
            lines.append(format_listing_row(row, i, view_mode="summary"))
        if ENABLE_STAGE_D_EXPLAIN:
            lines.append("")
            lines.append("Tip: ask follow-up questions like “这套离地铁远吗？”")

    return {
        "reply_text": "\n".join(lines),
        "constraints": merged,
        "profile_patch": _build_profile_patch(merged),
        "changes": summarize_constraint_changes(prev_constraints, merged),
        "active_constraints": compact_constraints_view(merged),
        "listings": listings,
        "structured_audit": structured_audit,
    }
