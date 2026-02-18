import json
import os
import re
from typing import Optional

from agent.router import route_turn
from agent.state import AgentState
from skills.qa.handler import answer_single_listing_question
from skills.search.agentic import build_search_runtime, run_search_skill


def run() -> None:
    runtime = build_search_runtime()
    state = AgentState()
    router_debug = str(os.environ.get("ROUTER_DEBUG", "0")).strip().lower() in {"1", "true", "yes", "on"}

    print("Rent Assistant (agentic MVP)")
    print("Intents: Search / Specific_QA / Refinement / Chitchat")
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

        history_hint = _make_history_hint(state)
        decision = route_turn(
            user_in,
            mode=state.mode,
            history_hint=history_hint,
            has_listings=bool(state.last_results),
            has_focus=bool(state.current_focus_listing_payload),
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

        if _is_focus_only_request(user_in, decision):
            if decision.target_index is None:
                bot_text = "Please specify which listing index to focus on."
            else:
                focus_err = _focus_by_index(state, decision.target_index)
                if focus_err:
                    bot_text = focus_err
                else:
                    title = str(state.current_focus_listing_payload.get("title") or state.current_focus_listing_id)
                    bot_text = (
                        f"Focus switched to listing {decision.target_index}: {title}. "
                        "What would you like to know about it?"
                    )
            print("\nBot> " + bot_text)
            state.history.append((user_in, bot_text))
            continue

        if decision.intent == "Specific_QA" and decision.target_index is not None:
            focus_err = _focus_by_index(state, decision.target_index)
            if focus_err:
                bot_text = focus_err
                print("\nBot> " + bot_text)
                state.history.append((user_in, bot_text))
                continue
            # Target index resolved explicitly, no need to ask follow-up clarification.
            decision.need_clarify = False
            decision.clarify_question = None

        if decision.need_clarify and decision.clarify_question:
            bot_text = decision.clarify_question
        elif decision.intent in {"Search", "Refinement"}:
            if decision.refinement_type == "price_down":
                c = state.constraints or {}
                if c.get("max_rent_pcm") is None:
                    bot_text = "What budget range do you want now?"
                    print("\nBot> " + bot_text)
                    state.history.append((user_in, bot_text))
                    continue
            out = run_search_skill(
                user_text=user_in,
                state_constraints=state.constraints,
                runtime=runtime,
                refinement_type=decision.refinement_type,
            )
            state.constraints = out.get("constraints")
            state.user_profile.update(out.get("profile_patch") or {})
            state.last_results = list(out.get("listings") or [])
            _auto_focus_first(state)
            bot_text = out.get("reply_text") or "No result."
        elif decision.intent == "Specific_QA":
            if not state.current_focus_listing_payload:
                bot_text = "Which listing do you mean? Use /focus 1 to select one first."
            else:
                bot_text = answer_single_listing_question(
                    question=user_in,
                    listing_payload=state.current_focus_listing_payload,
                )
        elif decision.intent == "Chitchat":
            bot_text = "Hi, how can I help?"
        else:
            bot_text = "I could not classify that request. You can provide budget/location/layout, or ask something like 'How far is this listing from the station?'"

        print("\nBot> " + bot_text)
        state.history.append((user_in, bot_text))


def _auto_focus_first(state: AgentState) -> None:
    if not state.last_results:
        state.current_focus_listing_id = None
        state.current_focus_listing_payload = None
        return
    first = state.last_results[0]
    state.current_focus_listing_id = str(first.get("listing_id") or first.get("url") or "row_1")
    state.current_focus_listing_payload = first


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
    err = _focus_by_index(state, idx)
    if err:
        return err
    title = str(state.current_focus_listing_payload.get("title") or state.current_focus_listing_id)
    return f"Focus switched to listing {idx}: {title}"


def _focus_by_index(state: AgentState, idx: int) -> Optional[str]:
    if idx < 1 or idx > len(state.last_results):
        return f"Invalid index. Valid range: 1~{len(state.last_results)}"
    picked = state.last_results[idx - 1]
    state.current_focus_listing_id = str(picked.get("listing_id") or picked.get("url") or f"row_{idx}")
    state.current_focus_listing_payload = picked
    return None


def _is_focus_only_request(user_in: str, decision) -> bool:
    if decision.intent != "Specific_QA" or decision.target_index is None:
        return False
    t = (user_in or "").strip().lower()
    if not t:
        return False
    # Pure index references and short pointer phrases should switch focus only.
    focus_only_patterns = [
        r"^#\s*\d{1,2}\??$",
        r"^(?:the\s+)?\d{1,2}(?:st|nd|rd|th)\??$",
        r"^(?:the\s+)?(?:first|second|third|fourth|fifth)\??$",
        r"^(?:the\s+)?(?:first|second|third|fourth|fifth)\s+(?:one|listing|result|option|property|flat)\??$",
        r"^(?:listing|result|option|property|flat)\s*#?\s*\d{1,2}\??$",
        r"^(?:what about|how about)\s+(?:the\s+)?(?:first|second|third|fourth|fifth|\d{1,2}(?:st|nd|rd|th)|#\d{1,2})\??$",
    ]
    for p in focus_only_patterns:
        if re.match(p, t):
            return True
    return False


def _make_history_hint(state: AgentState, limit: int = 4) -> Optional[str]:
    if not state.history:
        return None
    rows = state.history[-limit:]
    return "\n".join([f"U: {u}\nA: {a}" for u, a in rows])
