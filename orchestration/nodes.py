from __future__ import annotations

import copy
import json
import logging
import re
from typing import Literal

_logger = logging.getLogger(__name__)

from core.chatbot_config import GENERAL_SYSTEM
from core.llm_client import llm_grounded_explain, qwen_chat, render_stage_d_for_user
from orchestration.domain_router import domain_route_turn
from orchestration.merger import derive_snapshot, push_history, snapshot_from_constraints, snapshot_to_constraints
from orchestration.refinement_plan import build_refinement_plan
from orchestration.router import route_turn
from skills.common.context_provider import get_current_context_houses, get_focus_listing
from skills.qa.handler import (
    answer_multi_listing_question,
    answer_single_listing_question,
    build_qa_context,
    classify_qa_scope,
)
from skills.search.agentic import run_search_skill
from skills.search.handler import format_listing_row

from orchestration.state import GraphState

IntentName = Literal["Search", "Specific_QA", "Compare", "AreaCompare", "Shortlist", "Chitchat", "DirectReply", "Page_Nav", "Fallback", "Explain"]


def _auto_focus_first(agent_state) -> None:
    if not agent_state.last_results:
        agent_state.current_focus_listing_id = None
        agent_state.current_focus_listing_payload = None
        agent_state.focus_source = None
        return
    first = agent_state.last_results[0]
    agent_state.current_focus_listing_id = str(first.get("listing_id") or first.get("url") or "row_1")
    agent_state.current_focus_listing_payload = first
    agent_state.focus_source = "auto"


def _focus_by_index(agent_state, idx: int, source: str = "user_query") -> str | None:
    if idx < 1 or idx > len(agent_state.last_results):
        return f"Invalid index. Valid range: 1~{len(agent_state.last_results)}"
    picked = agent_state.last_results[idx - 1]
    agent_state.current_focus_listing_id = str(picked.get("listing_id") or picked.get("url") or f"row_{idx}")
    agent_state.current_focus_listing_payload = picked
    agent_state.focus_source = str(source or "user_query")
    return None


def _make_history_hint(agent_state, limit: int = 4) -> str | None:
    if not agent_state.history:
        return None
    rows = agent_state.history[-limit:]
    return "\n".join([f"U: {u}\nA: {a}" for u, a in rows])


def _debug_print(enabled: bool, payload: dict) -> None:
    if not enabled:
        return
    try:
        print("Bot> [debug] " + json.dumps(payload, ensure_ascii=False))
    except Exception:
        print(f"Bot> [debug] {payload}")


def _is_cross_candidate_query(text: str) -> bool:
    q = str(text or "").strip().lower()
    if not q:
        return False
    patterns = [
        r"\bwhich\s+one\b",
        r"\bwhich\s+listing\b",
        r"\bwhich\s+property\b",
        r"\bwhich\s+of\b",
    ]
    return any(re.search(p, q) for p in patterns)


def route_node(state: GraphState) -> GraphState:
    text = str(state.get("user_input") or "").strip()
    agent_state = state["agent_state"]
    if not text:
        state["intent"] = "Fallback"
        state["reply_text"] = "Empty input."
        return state

    pending = agent_state.pending_suggestion
    pending_ac = agent_state.pending_area_compare
    decision = route_turn(
        text,
        mode=agent_state.mode,
        history_hint=_make_history_hint(agent_state),
        has_listings=bool(agent_state.last_results),
        has_focus=bool(agent_state.current_focus_listing_payload),
        listings_count=len(agent_state.last_results),
        pending_suggestion_display=str(pending["display"]) if pending else None,
        pending_area_compare_areas=list(pending_ac["areas"]) if pending_ac and pending_ac.get("areas") else None,
    )
    state["intent"] = str(decision.intent or "Fallback")
    state["route_reason"] = str(decision.reason or "")
    state["need_clarify"] = bool(decision.need_clarify)
    state["clarify_question"] = decision.clarify_question
    state["target_indices"] = list(decision.target_indices or [])
    state["target_areas"] = list(decision.target_areas or [])
    state["shortlist_action"] = decision.shortlist_action
    state["refinement_type"] = decision.refinement_type
    state["page_action"] = getattr(decision, "page_action", None)

    if state.get("router_debug"):
        print(
            "Bot> [router] "
            + json.dumps(
                {
                    "intent": decision.intent,
                    "target_indices": list(decision.target_indices or []),
                    "target_areas": list(decision.target_areas or []),
                    "refinement_type": decision.refinement_type,
                    "page_action": getattr(decision, "page_action", None),
                    "confidence": decision.confidence,
                    "reason": decision.reason,
                    "need_clarify": decision.need_clarify,
                    "clarify_question": decision.clarify_question,
                    "has_listings": bool(agent_state.last_results),
                    "has_focus": bool(agent_state.current_focus_listing_payload),
                },
                ensure_ascii=False,
            )
        )
        _debug_print(
            True,
            {
                "phase": "turn_start",
                "intent": state["intent"],
                "constraints_current": agent_state.constraints or {},
            },
        )

    target_indices = list(state.get("target_indices") or [])

    if state["intent"] == "Specific_QA" and not target_indices and _is_cross_candidate_query(text):
        # Guardrail: ambiguous "which one..." with no explicit indices should go to list-QA, not single.
        # Only fires when the router did NOT resolve explicit target indices — explicit indices take priority.
        state["target_indices"] = []
        target_indices = []

    if state["intent"] == "Specific_QA" and len(target_indices) == 1:
        # Single-target QA: set focus listing.
        focus_err = _focus_by_index(agent_state, target_indices[0], source="user_query")
        if focus_err:
            state["reply_text"] = focus_err
            state["intent"] = "DirectReply"
            return state
        state["need_clarify"] = False
        state["clarify_question"] = None
    elif state["intent"] == "Specific_QA" and len(target_indices) > 1:
        # Multi-target QA: indices already stored, no single focus needed.
        state["need_clarify"] = False
        state["clarify_question"] = None
    elif state["intent"] == "Specific_QA" and agent_state.current_focus_listing_payload:
        state["need_clarify"] = False
        state["clarify_question"] = None

    if state.get("need_clarify") and state.get("clarify_question"):
        state["reply_text"] = str(state.get("clarify_question") or "")
        state["intent"] = "DirectReply"

    return state


def search_node(state: GraphState) -> GraphState:
    agent_state = state["agent_state"]
    runtime = state["runtime"]
    prev_results = list(agent_state.last_results or [])
    prev_full_results = list(agent_state.search_full_results or prev_results)
    prev_page_index = int(agent_state.page_index or 0)
    prev_has_more = bool(agent_state.has_more)
    prev_focus_id = agent_state.current_focus_listing_id
    prev_focus_payload = agent_state.current_focus_listing_payload
    prev_focus_source = agent_state.focus_source
    prev_constraints = copy.deepcopy(agent_state.constraints)

    # If relax_node prepared override constraints, use them directly and skip
    # the normal refinement-plan / cache-check cycle.
    relax_override = state.get("relax_override_constraints")
    if relax_override is not None:
        state["relax_override_constraints"] = None  # consume
        try:
            out = run_search_skill(
                user_text=str(state.get("user_input") or ""),
                state_constraints=agent_state.constraints,
                runtime=runtime,
                override_constraints=relax_override,
                precomputed_semantic_terms={},
            )
        except Exception:
            _logger.exception("search_node (relax): run_search_skill failed — rolling back state")
            state["last_search_status"] = "error"
            agent_state.constraints = prev_constraints
            agent_state.search_full_results = prev_full_results
            agent_state.page_index = prev_page_index
            agent_state.has_more = prev_has_more
            state["reply_text"] = (
                "Search failed this turn. I kept your previous results intact. "
                "Please retry or adjust your query."
            )
            return state

        # Write audit data to GraphState regardless of result count.
        state["stage_b_audits"] = list(out.get("stage_b_audits") or [])
        state["stage_a_prefilter_count"] = int(out.get("stage_a_prefilter_count") or 0)

        agent_state.constraints = out.get("constraints")
        # Auto-relax must not permanently modify the user's stated budget.
        # Restore it so the next fresh search starts from the user's original figure.
        if agent_state.original_budget is not None and agent_state.constraints:
            agent_state.constraints["max_rent_pcm"] = agent_state.original_budget
        agent_state.user_profile.update(out.get("profile_patch") or {})
        full_results = list(out.get("all_ranked_listings") or out.get("listings") or [])
        k = int(((out.get("constraints") or {}).get("k") or 5))
        new_results = list(full_results[:k])

        committed_snapshot = snapshot_from_constraints(agent_state.constraints, results=full_results)
        new_history, _ = push_history(agent_state.snapshot_history or [], committed_snapshot, max_size=5)
        agent_state.snapshot_history = new_history

        if new_results:
            agent_state.search_full_results = full_results
            agent_state.page_index = 0
            agent_state.last_results = new_results
            agent_state.has_more = len(full_results) > len(new_results)
            _auto_focus_first(agent_state)
            state["last_search_status"] = "success"
        else:
            agent_state.last_results = prev_results
            agent_state.search_full_results = prev_full_results
            agent_state.page_index = prev_page_index
            agent_state.has_more = prev_has_more
            agent_state.current_focus_listing_id = prev_focus_id
            agent_state.current_focus_listing_payload = prev_focus_payload
            agent_state.focus_source = prev_focus_source
            state["last_search_status"] = "empty"
        agent_state.last_qa_scope = None
        # Leave reply_text blank — evaluate_node / finalize_node will fill it.
        state["reply_text"] = out.get("reply_text") or ""
        return state

    # ── Normal (non-relax) path ───────────────────────────────────────────────
    # Reset relax counters and pending suggestion at the start of every fresh search.
    state["relax_attempt"] = 0
    state["relax_log"] = []
    state["relax_near_miss"] = []
    state["stage_b_audits"] = []
    state["stage_a_prefilter_count"] = -1
    agent_state.pending_suggestion = None

    # Build merge plan from current user turn before running physical search.
    plan = build_refinement_plan(
        user_text=str(state.get("user_input") or ""),
        existing_constraints=agent_state.constraints,
    )

    # If the user explicitly sets a new budget (or resets entirely), clear the
    # stored original_budget so ★ markup reflects the new intent.
    if "max_rent_pcm" in plan.set_fields or plan.is_reset:
        agent_state.original_budget = None

    old_snapshot = snapshot_from_constraints(
        agent_state.constraints,
        results=agent_state.last_results,
    )
    target_snapshot = derive_snapshot(
        old_snapshot=old_snapshot,
        set_fields=plan.set_fields,
        clear_fields=plan.clear_fields,
        is_reset=plan.is_reset,
    )
    target_constraints = snapshot_to_constraints(target_snapshot)
    _debug_print(
        bool(state.get("router_debug")),
        {
            "phase": "search_plan",
            "intent": "Search",
            "constraints_old": agent_state.constraints or {},
            "constraints_new": target_constraints or {},
            "set_fields": plan.set_fields or {},
            "clear_fields": plan.clear_fields or [],
            "is_reset": bool(plan.is_reset),
            "plan_source": plan.source,
        },
    )
    target_hash = target_snapshot.get_hash()
    history = list(agent_state.snapshot_history or [])
    hit_idx = next((i for i, x in enumerate(history) if x.get_hash() == target_hash), -1)

    if hit_idx >= 0:
        matched = history.pop(hit_idx)
        history.insert(0, matched)
        agent_state.snapshot_history = history[:5]

        agent_state.constraints = snapshot_to_constraints(matched)
        cached_results = list(matched.results or [])
        if cached_results:
            agent_state.search_full_results = cached_results
            agent_state.page_index = 0
            k = int((agent_state.constraints or {}).get("k") or 5)
            agent_state.last_results = list(cached_results[:k])
            agent_state.has_more = len(cached_results) > len(agent_state.last_results)
            _auto_focus_first(agent_state)
            state["last_search_status"] = "cache_hit"
            lines = [f"Reused cached results ({len(cached_results)} listings).", "", f"Top {len(agent_state.last_results)} results:"]
            for i, row in enumerate(agent_state.last_results, start=1):
                lines.append(format_listing_row(row, i, view_mode="summary"))
            bot_text = "\n".join(lines)
        else:
            # Snapshot matched but had no results — clear state so user sees 0 results,
            # not the previous search's listings.
            agent_state.last_results = []
            agent_state.search_full_results = []
            agent_state.page_index = 0
            agent_state.has_more = False
            agent_state.current_focus_listing_id = None
            agent_state.current_focus_listing_payload = None
            agent_state.focus_source = None
            state["last_search_status"] = "cache_hit_empty"
            bot_text = "No listings found for this search. Try adjusting your requirements."
        agent_state.last_qa_scope = None
        if agent_state.last_results and agent_state.current_focus_listing_payload:
            focus_title = str(
                agent_state.current_focus_listing_payload.get("title")
                or agent_state.current_focus_listing_id
                or "listing #1"
            )
            bot_text += (
                f"\n\nNote: default focus is set to listing #1 ({focus_title}). "
                "Use /focus N to switch target, or ask 'which one has ...' to compare all current listings."
            )
        state["reply_text"] = bot_text
        return state

    try:
        out = run_search_skill(
            user_text=str(state.get("user_input") or ""),
            state_constraints=agent_state.constraints,
            runtime=runtime,
            refinement_type=None,
            override_constraints=target_constraints,
            precomputed_semantic_terms=plan.semantic_terms or {},
        )
    except Exception:
        _logger.exception("search_node: run_search_skill failed — rolling back state")
        state["last_search_status"] = "error"
        agent_state.constraints = prev_constraints
        agent_state.search_full_results = prev_full_results
        agent_state.page_index = prev_page_index
        agent_state.has_more = prev_has_more
        state["reply_text"] = (
            "Search failed this turn. I kept your previous results intact. "
            "Please retry or adjust your query."
        )
        return state

    # Write audit data to GraphState for evaluate_node.
    state["stage_b_audits"] = list(out.get("stage_b_audits") or [])
    state["stage_a_prefilter_count"] = int(out.get("stage_a_prefilter_count") or 0)

    agent_state.constraints = out.get("constraints")
    agent_state.user_profile.update(out.get("profile_patch") or {})
    full_results = list(out.get("all_ranked_listings") or [])
    if not full_results:
        full_results = list(out.get("listings") or [])
    k = int(((out.get("constraints") or {}).get("k") or 5))
    new_results = list(full_results[:k])
    bot_text = out.get("reply_text") or "No result."

    committed_snapshot = snapshot_from_constraints(
        agent_state.constraints,
        results=full_results,
    )
    new_history, _ = push_history(agent_state.snapshot_history or [], committed_snapshot, max_size=5)
    agent_state.snapshot_history = new_history

    if new_results:
        agent_state.search_full_results = full_results
        agent_state.page_index = 0
        agent_state.last_results = new_results
        agent_state.has_more = len(full_results) > len(new_results)
        _auto_focus_first(agent_state)
        state["last_search_status"] = "success"
    else:
        # Preserve prior context to avoid QA hard break after an empty/failed search result.
        agent_state.last_results = prev_results
        agent_state.search_full_results = prev_full_results
        agent_state.page_index = prev_page_index
        agent_state.has_more = prev_has_more
        agent_state.current_focus_listing_id = prev_focus_id
        agent_state.current_focus_listing_payload = prev_focus_payload
        agent_state.focus_source = prev_focus_source
        state["last_search_status"] = "empty"
        if prev_results:
            bot_text += (
                "\n\nI kept your previous results. "
                "You can still ask follow-up questions about them."
            )
    agent_state.last_qa_scope = None

    if agent_state.last_results and agent_state.current_focus_listing_payload:
        focus_title = str(
            agent_state.current_focus_listing_payload.get("title")
            or agent_state.current_focus_listing_id
            or "listing #1"
        )
        bot_text += (
            f"\n\nNote: default focus is set to listing #1 ({focus_title}). "
            "Use /focus N to switch target, or ask 'which one has ...' to compare all current listings."
        )
    state["reply_text"] = bot_text
    return state


def paginate_node(state: GraphState) -> GraphState:
    agent_state = state["agent_state"]
    action = str(state.get("page_action") or "next").strip().lower()
    if action not in {"next", "prev"}:
        action = "next"
    full = list(agent_state.search_full_results or [])
    if not full:
        full = list(agent_state.last_results or [])
        agent_state.search_full_results = list(full)

    if not full:
        state["reply_text"] = "I don't have active listings yet. Tell me your budget/location/layout first, and I'll search."
        return state

    k = int(((agent_state.constraints or {}).get("k") or 5))
    cur_page = int(agent_state.page_index or 0)
    target_page = cur_page + 1 if action == "next" else cur_page - 1
    start = target_page * k
    end = start + k
    if action == "next" and start >= len(full):
        agent_state.has_more = False
        state["reply_text"] = "This is already the last page."
        return state
    if action == "prev" and target_page < 0:
        state["reply_text"] = "This is already the first page."
        return state

    page_rows = list(full[start:end])
    agent_state.page_index = target_page
    agent_state.last_results = page_rows
    agent_state.has_more = end < len(full)
    _auto_focus_first(agent_state)

    lines = [f"Page {target_page + 1} results ({start + 1}-{min(end, len(full))} of {len(full)}):"]
    for i, row in enumerate(page_rows, start=1):
        lines.append(format_listing_row(row, i, view_mode="summary"))
    if agent_state.current_focus_listing_payload:
        focus_title = str(
            agent_state.current_focus_listing_payload.get("title")
            or agent_state.current_focus_listing_id
            or "listing #1"
        )
        lines.append("")
        lines.append(
            f"Note: default focus is set to listing #1 ({focus_title}). "
            "Use /focus N to switch target, or ask 'which one has ...' to compare all current listings."
        )

    _debug_print(
        bool(state.get("router_debug")),
        {
            "phase": "paginate",
            "action": action,
            "page_index_old": cur_page,
            "page_index_new": target_page,
            "slice_start": start,
            "slice_end": min(end, len(full)),
            "total": len(full),
            "k": k,
            "has_more": agent_state.has_more,
        },
    )
    state["reply_text"] = "\n".join(lines)
    return state


def qa_plan_node(state: GraphState) -> GraphState:
    agent_state = state["agent_state"]
    user_in = str(state.get("user_input") or "")
    qa_ctx = build_qa_context(user_in)
    state["qa_extraction_input"] = str((qa_ctx or {}).get("extraction_input") or user_in)
    state["qa_plan_source"] = str((qa_ctx or {}).get("plan_source") or "fallback_split_calls")
    state["qa_llm_extract_all_error"] = dict((qa_ctx or {}).get("llm_extract_all_error") or {})
    state["qa_target_constraints"] = dict((qa_ctx or {}).get("final_constraints") or {})
    state["qa_semantic_terms"] = dict((qa_ctx or {}).get("semantic_terms") or {})
    state["qa_signals"] = dict((qa_ctx or {}).get("signals") or {})

    target_indices = list(state.get("target_indices") or [])
    if len(target_indices) > 1:
        # Explicit multi-index from router (e.g. "do listing 1 and 2 have pets?") — scope is unambiguous.
        target_scope = "list"
    elif len(target_indices) == 1:
        target_scope = "single"
    else:
        # No explicit indices — let classify_qa_scope decide (single / list / clarify).
        scope = classify_qa_scope(
            question=user_in,
            has_focus=bool(agent_state.current_focus_listing_payload),
            has_listings=bool(agent_state.last_results),
            last_qa_scope=agent_state.last_qa_scope,
        )
        target_scope = str(scope.get("target_scope") or "").strip().lower() or "clarify"
    state["qa_target_scope"] = target_scope

    signals = state.get("qa_signals") or {}
    _debug_print(
        bool(state.get("router_debug")),
        {
            "phase": "qa_extract",
            "query": str(state.get("qa_extraction_input") or user_in),
            "plan_source": state.get("qa_plan_source"),
            "extracted": {
                "constraints": state.get("qa_target_constraints") or {},
                "semantic_terms": state.get("qa_semantic_terms") or {},
            },
            "llm_error": state.get("qa_llm_extract_all_error") or {},
        },
    )
    return state


def qa_execute_node(state: GraphState) -> GraphState:
    agent_state = state["agent_state"]
    runtime = state["runtime"]
    user_in = str(state.get("user_input") or "")
    qa_ctx = {
        "question_text": user_in,
        "extraction_input": str(state.get("qa_extraction_input") or user_in),
        "plan_source": str(state.get("qa_plan_source") or "fallback_split_calls"),
        "llm_extract_all_error": dict(state.get("qa_llm_extract_all_error") or {}),
        "final_constraints": dict(state.get("qa_target_constraints") or {}),
        "semantic_terms": dict(state.get("qa_semantic_terms") or {}),
        "signals": dict(state.get("qa_signals") or {}),
    }
    target_scope = str(state.get("qa_target_scope") or "").strip().lower()

    # Multi-target QA: user asked about N specific listings (e.g. "do listing 1 and 2 allow pets?")
    qa_target_indices = [i for i in (state.get("target_indices") or []) if isinstance(i, int)]
    if len(qa_target_indices) > 1:
        agent_state.last_qa_scope = "list"
        all_listings = list(agent_state.last_results or [])
        selected = [all_listings[i - 1] for i in qa_target_indices if 1 <= i <= len(all_listings)]
        if not selected:
            state["reply_text"] = "Could not find the specified listings on this page."
            return state
        state["reply_text"] = answer_multi_listing_question(
            question=user_in,
            listings=selected,
            embedder=runtime.embedder,
            qa_ctx=qa_ctx,
        )
        return state

    if len(state.get("target_indices") or []) == 1:
        focus_listing = get_focus_listing(agent_state)
        if not focus_listing:
            state["reply_text"] = "Which listing do you mean? Use /focus 1 to select one first."
            return state
        agent_state.last_qa_scope = "single"
        state["reply_text"] = answer_single_listing_question(
            question=user_in,
            listing_payload=focus_listing,
            embedder=runtime.embedder,
            qa_ctx=qa_ctx,
        )
        return state

    if target_scope == "clarify":
        agent_state.last_qa_scope = "clarify"
        state["reply_text"] = "Please specify which listing you mean (for example: listing 2), or ask 'which one has ...'."
    elif target_scope == "list":
        agent_state.last_qa_scope = "list"
        listings = get_current_context_houses(agent_state, "list")
        if not listings:
            state["reply_text"] = (
                "I don't have active listings yet. "
                "Tell me your budget/location/layout first, and I'll search."
            )
            return state
        state["reply_text"] = answer_multi_listing_question(
            question=user_in,
            listings=listings,
            embedder=runtime.embedder,
            qa_ctx=qa_ctx,
        )
    elif not get_focus_listing(agent_state):
        agent_state.last_qa_scope = "clarify"
        state["reply_text"] = "Which listing do you mean? Use /focus 1 to select one first."
    else:
        agent_state.last_qa_scope = "single"
        focus_listing = get_focus_listing(agent_state)
        bot_text = answer_single_listing_question(
            question=user_in,
            listing_payload=focus_listing,
            embedder=runtime.embedder,
            qa_ctx=qa_ctx,
        )
        if agent_state.focus_source == "auto":
            bot_text += "\n\nNote: this answer is based on default focus listing #1."
        state["reply_text"] = bot_text
    return state


def qa_node(state: GraphState) -> GraphState:
    # Backward-compatible composite entrypoint.
    return qa_execute_node(qa_plan_node(state))


_SUGGESTION_FIELD_MAP = {
    "budget": "max_rent_pcm",
    "furnish_type": "furnish_type",
    "let_type": "let_type",
    "available_from": "available_from",
    "min_size_sqm": "min_size_sqm",
    "min_tenancy": "min_tenancy_months",
}


def apply_suggestion_node(state: GraphState) -> GraphState:
    """Apply the stored pending_suggestion directly as override constraints."""
    agent_state = state["agent_state"]
    suggestion = agent_state.pending_suggestion
    agent_state.pending_suggestion = None  # consume regardless

    if not suggestion:
        # Nothing to apply — fall through to search with current constraints.
        state["relax_override_constraints"] = None
        return state

    import copy
    constraints = copy.deepcopy(agent_state.constraints or {})
    field = suggestion.get("field")
    new_value = suggestion.get("new_value")
    constraint_key = _SUGGESTION_FIELD_MAP.get(str(field or ""))

    if constraint_key:
        constraints[constraint_key] = new_value

    state["relax_override_constraints"] = constraints
    # Reset relax counters so the subsequent search starts fresh.
    state["relax_attempt"] = 0
    state["relax_log"] = []
    state["relax_near_miss"] = []
    state["stage_b_audits"] = []
    state["stage_a_prefilter_count"] = -1
    return state


def domain_router_node(state: GraphState) -> GraphState:
    agent_state = state["agent_state"]
    text = str(state.get("user_input") or "").strip()
    decision = domain_route_turn(
        user_text=text,
        history_hint=_make_history_hint(agent_state),
        has_listings=bool(agent_state.last_results),
    )
    state["domain"] = decision.domain
    if state.get("router_debug"):
        _debug_print(True, {"phase": "domain_router", "domain": decision.domain, "reason": decision.reason})
    return state


def domain_branch(state: GraphState) -> str:
    return str(state.get("domain") or "Rental")


def _build_search_context_summary(agent_state) -> str:
    """One-line summary of active constraints for general_node context."""
    c = agent_state.constraints or {}
    parts = []
    locs = c.get("location_keywords") or []
    if locs:
        parts.append(", ".join(str(l) for l in locs[:3]))
    for opt in (c.get("layout_options") or [])[:1]:
        if isinstance(opt, dict):
            beds = opt.get("bedrooms")
            if beds is not None:
                parts.append(f"{int(beds)}-bed")
    budget = c.get("max_rent_pcm")
    if budget is not None:
        parts.append(f"under £{int(budget)}/mo")
    if not parts:
        return ""
    return "Currently searching: " + " | ".join(parts)


def general_node(state: GraphState) -> GraphState:
    agent_state = state["agent_state"]
    text = str(state.get("user_input") or "").strip()

    context_parts = []
    history_hint = _make_history_hint(agent_state)
    if history_hint:
        context_parts.append(f"Conversation so far:\n{history_hint}")
    search_summary = _build_search_context_summary(agent_state)
    if search_summary:
        context_parts.append(search_summary)
    context = "\n".join(context_parts)

    user_payload = f"{context}\n\nUser: {text}".strip() if context else text

    try:
        reply = qwen_chat(
            [
                {"role": "system", "content": GENERAL_SYSTEM},
                {"role": "user", "content": user_payload},
            ],
            temperature=0.7,
        )
    except Exception:
        reply = "Sorry, I'm having trouble responding right now. How can I help you with your rental search?"

    state["reply_text"] = reply.strip()
    return state


def chitchat_node(state: GraphState) -> GraphState:
    state["reply_text"] = state.get("reply_text") or "Hi, how can I help?"
    return state


def fallback_node(state: GraphState) -> GraphState:
    state["reply_text"] = state.get("reply_text") or (
        "I could not classify that request. You can provide budget/location/layout, "
        "or ask something like 'How far is this listing from the station?'"
    )
    return state


def direct_reply_node(state: GraphState) -> GraphState:
    state["reply_text"] = state.get("reply_text") or "Please clarify your request."
    return state


def _build_explain_query(user_in: str, constraints: dict, signals: dict) -> str:
    """Reframe the user question with structured context for Stage D.

    Combines hard constraints + soft preferences into a concise framing
    so the LLM knows what to evaluate against, not just "which is best?".
    """
    parts = []

    # Hard requirements
    req = []
    locs = constraints.get("location_keywords") or []
    if locs:
        req.append(", ".join(str(l) for l in locs[:3]))
    for opt in (constraints.get("layout_options") or [])[:1]:
        if isinstance(opt, dict):
            beds = opt.get("bedrooms")
            if beds is not None:
                req.append(f"{int(beds)}-bed")
    budget = constraints.get("max_rent_pcm")
    if budget is not None:
        req.append(f"budget £{int(budget)}/mo")
    if req:
        parts.append("Looking for: " + ", ".join(req))

    # Soft preferences
    prefs = []
    topic = (signals.get("topic_preferences") or {})
    prefs.extend(topic.get("transit_terms") or [])
    prefs.extend(topic.get("school_terms") or [])
    prefs.extend(signals.get("general_semantic") or [])
    if prefs:
        parts.append("Preferences: " + ", ".join(prefs[:6]))

    if not parts:
        return user_in

    return "\n".join(parts) + f"\n\nQuestion: {user_in}"


def explain_node(state: GraphState) -> GraphState:
    """P2-C: Stage D grounded explanation on evaluation/comparison intent."""
    agent_state = state["agent_state"]
    user_in = str(state.get("user_input") or "")
    listings = list(agent_state.last_results or [])

    if not listings:
        state["reply_text"] = (
            "I don't have any listings to explain yet. "
            "Tell me your search requirements first and I'll find some options."
        )
        return state

    try:
        import pandas as pd
        df = pd.DataFrame(listings)
        constraints = dict(agent_state.constraints or {})
        signals = dict(agent_state.user_profile or {})

        user_query = _build_explain_query(user_in, constraints, signals)

        grounded_out, _, _ = llm_grounded_explain(
            user_query=user_query,
            c=constraints,
            signals=signals,
            df=df,
        )
        reply = render_stage_d_for_user(grounded_out, df=df, max_items=len(listings))
        if not reply:
            reply = grounded_out
    except Exception:
        _logger.exception("explain_node: llm_grounded_explain failed")
        reply = (
            "I had trouble generating an explanation. "
            "You can ask about a specific listing, e.g., 'tell me more about listing 2'."
        )

    state["reply_text"] = reply
    return state


_COMPARE_FIELDS = [
    ("price_pcm",     "Price/mo",   lambda v: f"£{int(float(v)):,}" if v is not None else "—"),
    ("bedrooms",      "Beds",       lambda v: str(int(float(v))) if v is not None else "—"),
    ("bathrooms",     "Baths",      lambda v: str(v) if v is not None else "—"),
    ("deposit",       "Deposit",    lambda v: f"£{int(float(v)):,}" if v is not None else "—"),
    ("available_from","Available",  lambda v: str(v) if v else "—"),
    ("size_sqm",      "Size",       lambda v: f"{float(v):.0f} sqm" if v is not None else "—"),
    ("furnish_type",  "Furnished",  lambda v: str(v) if v else "—"),
    ("property_type", "Type",       lambda v: str(v) if v else "—"),
]


def _short_title(r: dict) -> str:
    title = str(r.get("title") or r.get("address") or "").strip()
    if not title:
        return "listing"
    return title[:28] + ("…" if len(title) > 28 else "")


def _run_compare(user_in: str, rows: list, constraints: dict, signals: dict) -> str:
    """Build a markdown table + LLM verdict for N listings."""
    headers = ["Field"] + [f"#{idx} — {_short_title(r)}" for idx, r in rows]
    table_rows = []
    for field_key, field_label, fmt in _COMPARE_FIELDS:
        cells = [field_label]
        for _idx, r in rows:
            raw = r.get(field_key)
            try:
                cells.append(fmt(raw) if raw is not None else "—")
            except Exception:
                cells.append("—")
        table_rows.append(cells)

    def _row_md(cells):
        return "| " + " | ".join(str(c) for c in cells) + " |"

    sep = "| " + " | ".join(["---"] * len(headers)) + " |"
    table_md = "\n".join([_row_md(headers), sep] + [_row_md(r) for r in table_rows])

    # Context for LLM verdict
    req_parts = []
    locs = constraints.get("location_keywords") or []
    if locs:
        req_parts.append(f"location: {', '.join(str(l) for l in locs[:3])}")
    budget = constraints.get("max_rent_pcm")
    if budget:
        req_parts.append(f"budget: £{int(budget)}/mo")
    for opt in (constraints.get("layout_options") or [])[:1]:
        if isinstance(opt, dict) and opt.get("bedrooms") is not None:
            req_parts.append(f"{int(opt['bedrooms'])}-bed")

    pref_parts: list = []
    topic = (signals.get("topic_preferences") or {})
    pref_parts.extend(topic.get("transit_terms") or [])
    pref_parts.extend(topic.get("school_terms") or [])
    pref_parts.extend(signals.get("general_semantic") or [])

    context_lines = []
    if req_parts:
        context_lines.append("Requirements: " + ", ".join(req_parts))
    if pref_parts:
        context_lines.append("Preferences: " + ", ".join(str(p) for p in pref_parts[:5]))
    context = "\n".join(context_lines)

    system = (
        "You are a rental comparison assistant. "
        "Given a comparison table and user requirements, write a concise 2-4 sentence verdict. "
        "Identify the strongest option and explain why, referencing specific numbers. Be direct."
    )
    user_payload = (f"{context}\n\n" if context else "") + (
        f"Comparison ({len(rows)} listings):\n{table_md}\n\nUser question: {user_in}\n\nVerdict:"
    )
    try:
        verdict = qwen_chat(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": user_payload},
            ],
            temperature=0.3,
        ).strip()
    except Exception:
        verdict = ""

    label = " vs ".join(f"#{idx}" for idx, _ in rows)
    lines = [f"**Comparison: {label}**", "", table_md]
    if verdict:
        lines += ["", "**Verdict**", verdict]
    return "\n".join(lines)


def compare_node(state: GraphState) -> GraphState:
    """Structured side-by-side comparison of N listings with LLM verdict."""
    agent_state = state["agent_state"]
    user_in = str(state.get("user_input") or "")
    listings = list(agent_state.last_results or [])

    if not listings:
        state["reply_text"] = (
            "I don't have any listings to compare yet. "
            "Tell me your search requirements first and I'll find some options."
        )
        return state

    raw_indices = [i for i in (state.get("target_indices") or []) if isinstance(i, int)]

    if len(raw_indices) >= 2:
        rows, bad = [], []
        for idx in raw_indices:
            if 1 <= idx <= len(listings):
                rows.append((idx, listings[idx - 1]))
            else:
                bad.append(idx)
        if bad:
            state["reply_text"] = (
                f"Listing {bad[0] if len(bad) == 1 else bad} out of range. "
                f"I have {len(listings)} listing{'s' if len(listings) != 1 else ''} on this page."
            )
            return state
    else:
        # No specific indices — compare all on current page.
        rows = [(i + 1, r) for i, r in enumerate(listings)]

    if len(rows) < 2:
        state["reply_text"] = "I need at least 2 listings to compare. Try searching first."
        return state

    constraints = dict(agent_state.constraints or {})
    signals = dict(agent_state.user_profile or {})

    try:
        reply = _run_compare(user_in, rows, constraints, signals)
    except Exception:
        _logger.exception("compare_node: _run_compare failed")
        reply = (
            "I had trouble generating a comparison. "
            "You can ask about individual listings, e.g. 'tell me more about listing 2'."
        )

    state["reply_text"] = reply
    return state


def _has_layout_constraints(constraints: dict) -> bool:
    """Return True if constraints include at least one layout option with bedrooms specified."""
    for opt in (constraints.get("layout_options") or []):
        if isinstance(opt, dict) and opt.get("bedrooms") is not None:
            return True
    return False


def _describe_layout(constraints: dict) -> str:
    """Human-readable layout description from constraints (e.g. '2-bed furnished')."""
    parts = []
    for opt in (constraints.get("layout_options") or [])[:1]:
        if isinstance(opt, dict):
            beds = opt.get("bedrooms")
            baths = opt.get("bathrooms")
            if beds is not None:
                parts.append(f"{int(beds)}-bed")
            if baths is not None:
                parts.append(f"{int(baths)}-bath")
    furnish = constraints.get("furnish_type")
    if furnish:
        parts.append(str(furnish))
    return " ".join(parts) if parts else ""


def _format_areas(areas: list) -> str:
    """Human-readable area list: 'Hackney, Peckham and Brixton'."""
    if not areas:
        return "those areas"
    if len(areas) == 1:
        return areas[0]
    if len(areas) == 2:
        return f"{areas[0]} and {areas[1]}"
    return ", ".join(areas[:-1]) + f" and {areas[-1]}"


def _run_area_compare(areas: list, base_constraints: dict, user_in: str, runtime) -> str:
    """Per-area Qdrant search → aggregate price stats → markdown table + LLM verdict."""
    import statistics as _stats

    area_data = []
    for area in areas:
        area_constraints = {**base_constraints, "location_keywords": [area]}
        try:
            out = run_search_skill(
                user_text="",
                state_constraints={},
                runtime=runtime,
                override_constraints=area_constraints,
                precomputed_semantic_terms={},
            )
            all_listings = list(out.get("all_ranked_listings") or out.get("listings") or [])
            prices = [
                float(r["price_pcm"])
                for r in all_listings
                if r.get("price_pcm") is not None
            ]
        except Exception:
            _logger.exception("area_compare: search failed for area=%s", area)
            all_listings = []
            prices = []

        if prices:
            min_p = min(prices)
            max_p = max(prices)
            med_p = _stats.median(prices)
        else:
            min_p = max_p = med_p = None

        area_data.append({
            "area": area,
            "count": len(all_listings),
            "min": min_p,
            "median": med_p,
            "max": max_p,
        })

    def _fp(v):
        return f"£{int(v):,}" if v is not None else "—"

    def _row_md(cells):
        return "| " + " | ".join(str(c) for c in cells) + " |"

    headers = ["Area", "Listings", "Min/mo", "Median/mo", "Max/mo"]
    sep = "| " + " | ".join(["---"] * len(headers)) + " |"
    rows_md = [
        _row_md([
            d["area"],
            str(d["count"]) if d["count"] > 0 else "No results",
            _fp(d["min"]),
            _fp(d["median"]),
            _fp(d["max"]),
        ])
        for d in area_data
    ]
    table_md = "\n".join([_row_md(headers), sep] + rows_md)

    layout_desc = _describe_layout(base_constraints)
    title_suffix = f" ({layout_desc})" if layout_desc else ""

    system = (
        "You are a rental market analyst. "
        "Given an area comparison table, write a concise 2-4 sentence verdict. "
        "State which area is cheapest, by how much, and any notable trade-offs (supply count, price spread). "
        "Reference specific figures. Be direct and factual."
    )
    budget = base_constraints.get("max_rent_pcm")
    budget_line = f"Budget cap: £{int(budget)}/mo. " if budget else ""
    user_payload = (
        f"{budget_line}Layout: {layout_desc or 'any'}.\n\n"
        f"Area price comparison:\n{table_md}\n\n"
        f"User question: {user_in}\n\nVerdict:"
    )
    try:
        verdict = qwen_chat(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": user_payload},
            ],
            temperature=0.3,
        ).strip()
    except Exception:
        verdict = ""

    areas_label = " vs ".join(d["area"] for d in area_data)
    lines = [f"**Area comparison: {areas_label}{title_suffix}**", "", table_md]
    if verdict:
        lines += ["", "**Verdict**", verdict]
    if not _has_layout_constraints(base_constraints):
        lines += ["", "_Note: prices include all listings in each area (studios, 1-beds, 2-beds, etc. mixed together) — add a bedroom filter (e.g. '2-bed') for a like-for-like view._"]
    return "\n".join(lines)


def area_compare_node(state: GraphState) -> GraphState:
    """Compare rental price stats across multiple geographic areas."""
    agent_state = state["agent_state"]
    user_in = str(state.get("user_input") or "")
    runtime = state["runtime"]

    target_areas = [a for a in (state.get("target_areas") or []) if isinstance(a, str) and a.strip()]
    pending = agent_state.pending_area_compare

    # Resolve which areas to compare.
    if target_areas:
        areas = target_areas[:4]
        agent_state.pending_area_compare = None  # clear stale pending if user gave new areas
    elif pending and pending.get("areas"):
        areas = list(pending["areas"])[:4]
        agent_state.pending_area_compare = None  # consume
    else:
        state["reply_text"] = (
            "Which areas would you like to compare? "
            "For example: 'Is Hackney cheaper than Peckham?'"
        )
        return state

    # Use session constraints as base. Layout (bedrooms) is optional — if present the comparison
    # is like-for-like; if absent we compare all property types and note it in the output.
    base_constraints = dict(agent_state.constraints or {})

    # If user_in mentions a layout (e.g. "2 bed"), try to extract and layer it on top.
    if user_in and not _has_layout_constraints(base_constraints):
        try:
            plan = build_refinement_plan(user_text=user_in, existing_constraints=agent_state.constraints)
            old_snap = snapshot_from_constraints(agent_state.constraints or {}, results=[])
            new_snap = derive_snapshot(old_snap, plan.set_fields, plan.clear_fields, plan.is_reset)
            extracted = snapshot_to_constraints(new_snap) or {}
            if _has_layout_constraints(extracted):
                base_constraints = extracted
        except Exception:
            pass

    try:
        reply = _run_area_compare(areas, base_constraints, user_in, runtime)
    except Exception:
        _logger.exception("area_compare_node: _run_area_compare failed")
        reply = (
            "I had trouble comparing those areas. "
            "Please try again or search a specific area directly."
        )

    state["reply_text"] = reply
    return state


def shortlist_node(state: GraphState) -> GraphState:
    """Manage the user's saved (shortlisted) listings."""
    agent_state = state["agent_state"]
    action = str(state.get("shortlist_action") or "show").strip().lower()
    target_indices = [i for i in (state.get("target_indices") or []) if isinstance(i, int)]

    if action == "show":
        if not agent_state.shortlist:
            state["reply_text"] = (
                "Your shortlist is empty. "
                "Save listings by saying 'save listing 2' or clicking the bookmark icon on a listing card."
            )
        else:
            n = len(agent_state.shortlist)
            lines = [f"**Your shortlist ({n} listing{'s' if n != 1 else ''}):**", ""]
            for i, r in enumerate(agent_state.shortlist, start=1):
                lines.append(format_listing_row(r, i, view_mode="summary"))
            lines += ["", "Say 'remove shortlist 2' to remove an entry, or 'compare my shortlist' to compare them."]
            state["reply_text"] = "\n".join(lines)
        return state

    if action == "clear":
        count = len(agent_state.shortlist)
        agent_state.shortlist = []
        state["reply_text"] = (
            f"Cleared your shortlist ({count} listing{'s' if count != 1 else ''} removed)."
            if count else "Your shortlist was already empty."
        )
        return state

    if action == "add":
        listings = list(agent_state.last_results or [])
        if not listings:
            state["reply_text"] = "No listings on the current page to save. Run a search first."
            return state
        if not target_indices:
            state["reply_text"] = "Which listing would you like to save? (e.g. 'save listing 2')"
            return state
        existing_ids = {str(r.get("listing_id") or r.get("url") or "") for r in agent_state.shortlist}
        added, already = [], []
        for idx in target_indices:
            if idx < 1 or idx > len(listings):
                continue
            r = listings[idx - 1]
            lid = str(r.get("listing_id") or r.get("url") or f"row_{idx}")
            if lid in existing_ids:
                already.append(idx)
            else:
                agent_state.shortlist.append(r)
                existing_ids.add(lid)
                added.append(idx)
        parts = []
        if added:
            label = ", ".join(f"#{i}" for i in added)
            parts.append(f"Saved listing {label} to your shortlist ({len(agent_state.shortlist)} total).")
        if already:
            label = ", ".join(f"#{i}" for i in already)
            parts.append(f"Listing {label} was already in your shortlist.")
        state["reply_text"] = " ".join(parts) or "Nothing to save."
        return state

    if action == "remove":
        if not agent_state.shortlist:
            state["reply_text"] = "Your shortlist is empty."
            return state
        if not target_indices:
            state["reply_text"] = (
                "Which shortlist entry to remove? "
                "Say 'show my shortlist' to see positions, then 'remove shortlist 2'."
            )
            return state
        # target_indices = 1-based positions in shortlist
        valid = sorted([i for i in target_indices if 1 <= i <= len(agent_state.shortlist)], reverse=True)
        invalid = [i for i in target_indices if i < 1 or i > len(agent_state.shortlist)]
        for idx in valid:
            agent_state.shortlist.pop(idx - 1)
        parts = []
        if valid:
            label = ", ".join(f"#{i}" for i in sorted(valid))
            parts.append(f"Removed shortlist item {label} ({len(agent_state.shortlist)} remaining).")
        if invalid:
            label = ", ".join(f"#{i}" for i in invalid)
            parts.append(f"Index {label} out of range.")
        state["reply_text"] = " ".join(parts) or "Nothing removed."
        return state

    state["reply_text"] = (
        "Shortlist commands: 'show my shortlist', 'save listing 2', "
        "'remove shortlist 1', 'clear shortlist'."
    )
    return state


def finalize_node(state: GraphState) -> GraphState:
    state["attempt_count"] = int(state.get("attempt_count") or 0) + 1
    agent_state = state["agent_state"]
    user_in = str(state.get("user_input") or "")
    bot_text = str(state.get("reply_text") or "")
    agent_state.history.append((user_in, bot_text))
    return state


def route_branch(state: GraphState) -> IntentName:
    intent = str(state.get("intent") or "").strip()
    if intent == "Search":
        return "Search"
    if intent == "Specific_QA":
        return "Specific_QA"
    if intent == "Compare":
        return "Compare"
    if intent == "AreaCompare":
        return "AreaCompare"
    if intent == "Shortlist":
        return "Shortlist"
    if intent == "AcceptSuggestion":
        return "AcceptSuggestion"
    if intent == "Explain":
        return "Explain"
    if intent == "DirectReply":
        return "DirectReply"
    if intent == "Page_Nav":
        return "Page_Nav"
    return "Fallback"
