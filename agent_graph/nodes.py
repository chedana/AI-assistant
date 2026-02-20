from __future__ import annotations

import json
from typing import Literal

from agent.merger import derive_snapshot, push_history, snapshot_from_constraints, snapshot_to_constraints
from agent.refinement_plan import build_refinement_plan
from agent.router import route_turn
from skills.common.context_provider import get_current_context_houses, get_focus_listing
from skills.qa.handler import answer_multi_listing_question, answer_single_listing_question, classify_qa_scope
from skills.search.agentic import run_search_skill

from agent_graph.state import GraphState

IntentName = Literal["Search", "Specific_QA", "Chitchat", "DirectReply", "Fallback"]


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

    if state.get("router_debug"):
        print(
            "Bot> [router] "
            + json.dumps(
                {
                    "intent": decision.intent,
                    "target_index": decision.target_index,
                    "refinement_type": decision.refinement_type,
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
    prev_focus_id = agent_state.current_focus_listing_id
    prev_focus_payload = agent_state.current_focus_listing_payload
    prev_focus_source = agent_state.focus_source

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
            agent_state.last_results = cached_results
            _auto_focus_first(agent_state)
            state["last_search_status"] = "cache_hit"
            bot_text = f"Reused cached results ({len(cached_results)} listings)."
        else:
            # Keep prior context if a historical snapshot has no cached rows.
            agent_state.last_results = prev_results
            agent_state.current_focus_listing_id = prev_focus_id
            agent_state.current_focus_listing_payload = prev_focus_payload
            agent_state.focus_source = prev_focus_source
            state["last_search_status"] = "cache_hit_empty"
            bot_text = "Matched a previous query snapshot, but it has no cached listings."
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
            refinement_type=state.get("refinement_type"),
            override_constraints=target_constraints,
            precomputed_semantic_terms=plan.semantic_terms or {},
        )
    except Exception:
        state["last_search_status"] = "error"
        state["reply_text"] = (
            "Search failed this turn. I kept your previous results intact. "
            "Please retry or adjust your query."
        )
        return state

    agent_state.constraints = out.get("constraints")
    agent_state.user_profile.update(out.get("profile_patch") or {})
    new_results = list(out.get("listings") or [])
    bot_text = out.get("reply_text") or "No result."

    committed_snapshot = snapshot_from_constraints(
        agent_state.constraints,
        results=new_results,
    )
    new_history, _ = push_history(agent_state.snapshot_history or [], committed_snapshot, max_size=5)
    agent_state.snapshot_history = new_history

    if new_results:
        agent_state.last_results = new_results
        _auto_focus_first(agent_state)
        state["last_search_status"] = "success"
    else:
        # Preserve prior context to avoid QA hard break after an empty/failed search result.
        agent_state.last_results = prev_results
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


def qa_node(state: GraphState) -> GraphState:
    agent_state = state["agent_state"]
    runtime = state["runtime"]
    user_in = str(state.get("user_input") or "")

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
        )
        return state

    scope = classify_qa_scope(
        question=user_in,
        has_focus=bool(agent_state.current_focus_listing_payload),
        has_listings=bool(agent_state.last_results),
        last_qa_scope=agent_state.last_qa_scope,
    )
    target_scope = str(scope.get("target_scope") or "").strip().lower()
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
        )
        if agent_state.focus_source == "auto":
            bot_text += "\n\nNote: this answer is based on default focus listing #1."
        state["reply_text"] = bot_text
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
    return "Fallback"
