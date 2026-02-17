import json
from typing import Optional

from agent.router import route_turn
from agent.state import AgentState
from skills.qa.handler import answer_single_listing_question
from skills.search.agentic import build_search_runtime, run_search_skill


def run() -> None:
    runtime = build_search_runtime()
    state = AgentState()

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
        decision = route_turn(user_in, mode=state.mode, history_hint=history_hint)

        if decision.intent in {"Search", "Refinement"}:
            out = run_search_skill(
                user_text=user_in,
                state_constraints=state.constraints,
                runtime=runtime,
            )
            state.constraints = out.get("constraints")
            state.user_profile.update(out.get("profile_patch") or {})
            state.last_results = list(out.get("listings") or [])
            _auto_focus_first(state)
            bot_text = out.get("reply_text") or "No result."
        elif decision.intent == "Specific_QA":
            if not state.current_focus_listing_payload:
                bot_text = "你指的是哪一套房源？可以用 /focus 1 先选中一套。"
            else:
                bot_text = answer_single_listing_question(
                    question=user_in,
                    listing_payload=state.current_focus_listing_payload,
                )
        elif decision.intent == "Chitchat":
            bot_text = "你好，我可以帮你找房、调整条件，或者回答当前房源细节问题。"
        else:
            bot_text = "我没理解你的意思。你可以直接说预算、区域、户型，或者问“这套房离地铁远吗？”"

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
        return "当前没有可选房源，请先搜索。"
    try:
        idx = int(parts[1])
    except ValueError:
        return "Usage: /focus 1"
    if idx < 1 or idx > len(state.last_results):
        return f"无效序号。可选范围: 1~{len(state.last_results)}"
    picked = state.last_results[idx - 1]
    state.current_focus_listing_id = str(picked.get("listing_id") or picked.get("url") or f"row_{idx}")
    state.current_focus_listing_payload = picked
    title = str(picked.get("title") or state.current_focus_listing_id)
    return f"已切换到第 {idx} 套：{title}"


def _make_history_hint(state: AgentState, limit: int = 4) -> Optional[str]:
    if not state.history:
        return None
    rows = state.history[-limit:]
    return "\n".join([f"U: {u}\nA: {a}" for u, a in rows])
