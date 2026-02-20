import json
import os
from typing import Optional

from agent_graph import build_graph, make_graph_state
from agent.router import route_turn
from agent.state import AgentState
from skills.qa.handler import answer_multi_listing_question, answer_single_listing_question, classify_qa_scope
from skills.search.agentic import build_search_runtime, run_search_skill

_GRAPH_RUNNER = None


def _legacy_process_turn(user_in: str, state: AgentState, runtime, router_debug: bool = False) -> str:
    history_hint = _make_history_hint(state)
    decision = route_turn(
        user_in,
        mode=state.mode,
        history_hint=history_hint,
        has_listings=bool(state.last_results),
        has_focus=bool(state.current_focus_listing_payload),
        listings_count=len(state.last_results),
    )

    if router_debug:
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
                    "has_listings": bool(state.last_results),
                    "has_focus": bool(state.current_focus_listing_payload),
                },
                ensure_ascii=False,
            )
        )

    if decision.intent == "Specific_QA" and decision.target_index is not None:
        focus_err = _focus_by_index(state, decision.target_index, source="user_query")
        if focus_err:
            state.history.append((user_in, focus_err))
            return focus_err
        # Target index resolved explicitly, no need to ask follow-up clarification.
        decision.need_clarify = False
        decision.clarify_question = None
    elif decision.intent == "Specific_QA" and state.current_focus_listing_payload:
        # Keep QA continuity on current focus when user does not re-specify index.
        decision.need_clarify = False
        decision.clarify_question = None

    if decision.need_clarify and decision.clarify_question:
        bot_text = decision.clarify_question
    elif decision.intent == "Search":
        out = run_search_skill(
            user_text=user_in,
            state_constraints=state.constraints,
            runtime=runtime,
            refinement_type=None,
        )
        state.constraints = out.get("constraints")
        state.user_profile.update(out.get("profile_patch") or {})
        state.last_results = list(out.get("listings") or [])
        _auto_focus_first(state)
        state.last_qa_scope = None
        bot_text = out.get("reply_text") or "No result."
        if state.last_results and state.current_focus_listing_payload:
            focus_title = str(
                state.current_focus_listing_payload.get("title")
                or state.current_focus_listing_id
                or "listing #1"
            )
            bot_text += (
                f"\n\nNote: default focus is set to listing #1 ({focus_title}). "
                "Use /focus N to switch target, or ask 'which one has ...' to compare all current listings."
            )
    elif decision.intent == "Specific_QA":
        # Explicit target index from router always means single-listing QA.
        if decision.target_index is not None:
            if not state.current_focus_listing_payload:
                bot_text = "Which listing do you mean? Use /focus 1 to select one first."
            else:
                state.last_qa_scope = "single"
                bot_text = answer_single_listing_question(
                    question=user_in,
                    listing_payload=state.current_focus_listing_payload,
                    embedder=runtime.embedder,
                )
        else:
            scope = classify_qa_scope(
                question=user_in,
                has_focus=bool(state.current_focus_listing_payload),
                has_listings=bool(state.last_results),
                last_qa_scope=state.last_qa_scope,
            )
            target_scope = str(scope.get("target_scope") or "").strip().lower()
            if target_scope == "clarify":
                state.last_qa_scope = "clarify"
                bot_text = "Please specify which listing you mean (for example: listing 2), or ask 'which one has ...'."
            elif target_scope == "list":
                state.last_qa_scope = "list"
                bot_text = answer_multi_listing_question(
                    question=user_in,
                    listings=state.last_results,
                    embedder=runtime.embedder,
                )
            elif not state.current_focus_listing_payload:
                state.last_qa_scope = "clarify"
                bot_text = "Which listing do you mean? Use /focus 1 to select one first."
            else:
                state.last_qa_scope = "single"
                bot_text = answer_single_listing_question(
                    question=user_in,
                    listing_payload=state.current_focus_listing_payload,
                    embedder=runtime.embedder,
                )
                if state.focus_source == "auto":
                    bot_text += "\n\nNote: this answer is based on default focus listing #1."
    elif decision.intent == "Chitchat":
        bot_text = "Hi, how can I help?"
    else:
        bot_text = "I could not classify that request. You can provide budget/location/layout, or ask something like 'How far is this listing from the station?'"

    state.history.append((user_in, bot_text))
    return bot_text


def process_turn(user_in: str, state: AgentState, runtime, router_debug: bool = False) -> str:
    global _GRAPH_RUNNER

    if _GRAPH_RUNNER is None:
        try:
            _GRAPH_RUNNER = build_graph()
        except Exception:
            _GRAPH_RUNNER = False

    if not _GRAPH_RUNNER:
        return _legacy_process_turn(user_in, state, runtime, router_debug=router_debug)

    graph_state = make_graph_state(
        user_in,
        agent_state=state,
        runtime=runtime,
        router_debug=router_debug,
    )
    out = _GRAPH_RUNNER.invoke(graph_state)
    return str((out or {}).get("reply_text") or "")


def run() -> None:
    runtime = build_search_runtime()
    state = AgentState()
    router_debug = str(os.environ.get("ROUTER_DEBUG", "0")).strip().lower() in {"1", "true", "yes", "on"}

    print("Rent Assistant (agentic MVP)")
    print("Intents: Search / Specific_QA / Chitchat")
    print("Commands: /exit /reset /state /focus N")
    print("----")

    while True:
        try:
            user_in = input("\nYou> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            break

        if not user_in:
            continue

        if user_in == "/exit":
            print("Bye.")
            break
        if user_in == "/reset":
            state = AgentState()
            print("State reset.")
            continue
        if user_in == "/state":
            print(json.dumps(
                {
                    "user_profile": state.user_profile,
                    "current_focus_listing_id": state.current_focus_listing_id,
                    "focus_source": state.focus_source,
                    "last_qa_scope": state.last_qa_scope,
                    "history_size": len(state.history),
                    "constraints_active": bool(state.constraints),
                    "last_results_count": len(state.last_results),
                },
                ensure_ascii=False,
                indent=2,
            ))
            continue
        if user_in.startswith("/focus"):
            msg = _handle_focus_command(user_in, state)
            print(f"Bot> {msg}")
            continue

        bot_text = process_turn(user_in, state, runtime, router_debug=router_debug)
        print("\nBot> " + bot_text)


def _auto_focus_first(state: AgentState) -> None:
    if not state.last_results:
        state.current_focus_listing_id = None
        state.current_focus_listing_payload = None
        state.focus_source = None
        return
    first = state.last_results[0]
    state.current_focus_listing_id = str(first.get("listing_id") or first.get("url") or "row_1")
    state.current_focus_listing_payload = first
    state.focus_source = "auto"


def _handle_focus_command(user_in: str, state: AgentState) -> str:
    parts = user_in.split()
    if len(parts) != 2:
        return "Usage: /focus 1"
    if not state.last_results:
        return "There are no selectable listings yet. Please run a search first."
    try:
        idx = int(parts[1])
    except ValueError:
        return "Usage: /focus 1"
    err = _focus_by_index(state, idx, source="user_command")
    if err:
        return err
    title = str(state.current_focus_listing_payload.get("title") or state.current_focus_listing_id)
    return f"Focus switched to listing {idx}: {title}"


def _focus_by_index(state: AgentState, idx: int, source: str = "user_query") -> Optional[str]:
    if idx < 1 or idx > len(state.last_results):
        return f"Invalid index. Valid range: 1~{len(state.last_results)}"
    picked = state.last_results[idx - 1]
    state.current_focus_listing_id = str(picked.get("listing_id") or picked.get("url") or f"row_{idx}")
    state.current_focus_listing_payload = picked
    state.focus_source = str(source or "user_query")
    return None


def _make_history_hint(state: AgentState, limit: int = 4) -> Optional[str]:
    if not state.history:
        return None
    rows = state.history[-limit:]
    return "\n".join([f"U: {u}\nA: {a}" for u, a in rows])
