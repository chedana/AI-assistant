from __future__ import annotations

import copy
import json
import logging
import re
from typing import Literal

_logger = logging.getLogger(__name__)

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

IntentName = Literal["Search", "Specific_QA", "Chitchat", "DirectReply", "Page_Nav", "Fallback"]


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

    decision = route_turn(
        text,
        mode=agent_state.mode,
        history_hint=_make_history_hint(agent_state),
        has_listings=bool(agent_state.last_results),
        has_focus=bool(agent_state.current_focus_listing_payload),
        listings_count=len(agent_state.last_results),
    )
    state["intent"] = str(decision.intent or "Fallback")
    state["route_reason"] = str(decision.reason or "")
    state["need_clarify"] = bool(decision.need_clarify)
    state["clarify_question"] = decision.clarify_question
    state["target_index"] = decision.target_index
    state["refinement_type"] = decision.refinement_type
    state["page_action"] = getattr(decision, "page_action", None)

    if state.get("router_debug"):
        print(
            "Bot> [router] "
            + json.dumps(
                {
                    "intent": decision.intent,
                    "target_index": decision.target_index,
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

    if state["intent"] == "Specific_QA" and _is_cross_candidate_query(text):
        # Guardrail: comparative "which one..." should not be coerced into single-target QA.
        state["target_index"] = None

    if state["intent"] == "Specific_QA" and state.get("target_index") is not None:
        focus_err = _focus_by_index(agent_state, int(state["target_index"]), source="user_query")
        if focus_err:
            state["reply_text"] = focus_err
            state["intent"] = "DirectReply"
            return state
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
    # Reset relax counters at the start of every fresh user-initiated search.
    state["relax_attempt"] = 0
    state["relax_log"] = []
    state["relax_near_miss"] = []
    state["stage_b_audits"] = []
    state["stage_a_prefilter_count"] = -1
    state["original_budget"] = None

    # Build merge plan from current user turn before running physical search.
    plan = build_refinement_plan(
        user_text=str(state.get("user_input") or ""),
        existing_constraints=agent_state.constraints,
    )

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

    if state.get("target_index") is not None:
        target_scope = "single"
    else:
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

    if state.get("target_index") is not None:
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
    if intent == "Chitchat":
        return "Chitchat"
    if intent == "DirectReply":
        return "DirectReply"
    if intent == "Page_Nav":
        return "Page_Nav"
    return "Fallback"
