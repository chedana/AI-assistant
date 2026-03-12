from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

try:
    from fastembed import TextEmbedding as _FastEmbed
    _USE_FASTEMBED = True
except ImportError:
    from sentence_transformers import SentenceTransformer as _FastEmbed  # type: ignore
    _USE_FASTEMBED = False

from skills.common.parse_signals import derive_signals, parse_signals
from core.settings import (
    DEFAULT_K,
    DEFAULT_RECALL,
    EMBED_MODEL,
    ENABLE_STAGE_D_EXPLAIN,
)
from skills.search.engine import load_stage_a_resources, stage_a_search
from skills.search.extractors import (
    compact_constraints_view,
    merge_constraints,
    normalize_constraints,
    summarize_constraint_changes,
)
from skills.search.hard_filter import apply_hard_filters_with_audit
from skills.search.signals import build_stage_a_query
from skills.search.handler import (
    format_listing_row,
    rank_stage_c,
)


@dataclass
class SearchRuntime:
    qdrant_client: Any
    embedder: Any


def build_search_runtime() -> SearchRuntime:
    embedder = _FastEmbed(EMBED_MODEL) if _USE_FASTEMBED else _FastEmbed(EMBED_MODEL)
    return SearchRuntime(
        qdrant_client=load_stage_a_resources(),
        embedder=embedder,
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
    refinement_type: Optional[str] = None,
    override_constraints: Optional[Dict[str, Any]] = None,
    precomputed_semantic_terms: Optional[Dict[str, Any]] = None,
    k: int = DEFAULT_K,
    recall: int = DEFAULT_RECALL,
) -> Dict[str, Any]:
    prev_constraints = dict(state_constraints or {})
    structured_audit = {}
    if override_constraints is None:
        parsed = parse_signals(
            user_text,
            state_constraints,
            emit_audit=True,
            audit_context="search",
        )
        extracted = parsed.get("final_constraints") or {}
        structured_audit = parsed.get("structured_audit") or {}
        merged = merge_constraints(state_constraints, extracted)
        semantic_terms = parsed.get("semantic_terms") or {}
        semantic_source = str(parsed.get("semantic_parse_source") or "llm_combined")
    else:
        merged = dict(override_constraints or {})
        semantic_terms = dict(precomputed_semantic_terms or {})
        semantic_source = "precomputed_plan"

    merged = normalize_constraints(merged)
    auto_refine_note: Optional[str] = None
    if str(refinement_type or "").strip().lower() == "price_down":
        current_budget = merged.get("max_rent_pcm")
        if current_budget is not None:
            factor = float(os.environ.get("RENT_PRICE_DOWN_FACTOR", "0.85"))
            factor = min(max(factor, 0.5), 0.99)
            new_budget = max(1.0, float(current_budget) * factor)
            merged["max_rent_pcm"] = round(new_budget, 2)
            auto_refine_note = (
                f"Applied price-down refinement: max rent adjusted from {float(current_budget):.0f} to "
                f"{float(merged['max_rent_pcm']):.0f}."
            )
    if not merged.get("k"):
        merged["k"] = int(k)

    signals = derive_signals(
        parsed={
            "semantic_terms": semantic_terms,
            "semantic_parse_source": semantic_source,
            "final_constraints": merged,
        },
        user_text=user_text,
        constraints=merged,
    )
    stage_a_query = build_stage_a_query(signals, user_text)
    stage_a_df = stage_a_search(
        runtime.qdrant_client,
        runtime.embedder,
        query=stage_a_query,
        recall=int(recall),
        c=merged,
    )
    stage_a_prefilter_count: int = int(
        stage_a_df.attrs.get("prefilter_count") or 0
    ) if hasattr(stage_a_df, "attrs") else 0
    stage_a_geo_fallback_area: Optional[str] = (
        stage_a_df.attrs.get("geo_fallback_area") or None
    ) if hasattr(stage_a_df, "attrs") else None
    filtered, stage_b_audits = apply_hard_filters_with_audit(stage_a_df, merged)
    ranked, _ = rank_stage_c(filtered, signals, embedder=runtime.embedder)
    ranked_full = ranked.reset_index(drop=True)

    n_filtered = len(filtered) if filtered is not None else 0
    if n_filtered < int(k):
        df = ranked.reset_index(drop=True)
    else:
        df = ranked.head(int(k)).reset_index(drop=True)

    listings: List[Dict[str, Any]] = []
    if df is not None and len(df) > 0:
        for _, row in df.iterrows():
            listings.append(row.to_dict())
    all_ranked_listings: List[Dict[str, Any]] = []
    if ranked_full is not None and len(ranked_full) > 0:
        for _, row in ranked_full.iterrows():
            all_ranked_listings.append(row.to_dict())

    lines: List[str] = []
    if not listings:
        lines.append("I couldn't find any matching listings. Try changing area, budget, or layout.")
    else:
        if auto_refine_note:
            lines.append(auto_refine_note)
        lines.append(f"Top {min(int(k), len(listings))} results:")
        for i, row in enumerate(listings[: int(k)], start=1):
            lines.append(format_listing_row(row, i, view_mode="summary"))
        if ENABLE_STAGE_D_EXPLAIN:
            lines.append("")
            lines.append("Tip: ask follow-up questions like 'How far is this listing from the station?'")

    return {
        "reply_text": "\n".join(lines),
        "constraints": merged,
        "profile_patch": _build_profile_patch(merged),
        "changes": summarize_constraint_changes(prev_constraints, merged),
        "active_constraints": compact_constraints_view(merged),
        "listings": listings,
        "all_ranked_listings": all_ranked_listings,
        "structured_audit": structured_audit,
        "stage_b_audits": stage_b_audits,
        "stage_a_prefilter_count": stage_a_prefilter_count,
        "stage_a_geo_fallback_area": stage_a_geo_fallback_area,
    }
