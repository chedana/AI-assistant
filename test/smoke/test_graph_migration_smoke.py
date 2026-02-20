#!/usr/bin/env python3
from __future__ import annotations

import sys
import os
from types import SimpleNamespace
from unittest.mock import patch
import importlib.util

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def _skip_if_no_langgraph() -> bool:
    if importlib.util.find_spec("langgraph") is None:
        print("SKIP: langgraph is not installed.")
        return True
    return False


def _skip_if_no_runtime_deps() -> bool:
    if importlib.util.find_spec("openai") is None:
        print("SKIP: openai dependency is not installed.")
        return True
    return False


def run() -> int:
    if _skip_if_no_langgraph() or _skip_if_no_runtime_deps():
        return 0

    from agent.router import RouteDecision
    from agent.state import AgentState
    from agent.workflow import _handle_focus_command, process_turn

    state = AgentState()
    runtime = SimpleNamespace(embedder=object())

    search_listings = [
        {"listing_id": "id-1", "title": "Listing One", "url": "https://example.com/1"},
        {"listing_id": "id-2", "title": "Listing Two", "url": "https://example.com/2"},
    ]

    with patch("agent.workflow._GRAPH_RUNNER", None):
        with patch(
            "agent_graph.nodes.route_turn",
            return_value=RouteDecision(intent="Search", reason="test_search"),
        ), patch(
            "agent_graph.nodes.run_search_skill",
            return_value={
                "reply_text": "Top 2 results:\n1) Listing One\n2) Listing Two",
                "constraints": {"k": 5},
                "profile_patch": {"budget_max_pcm": 2500},
                "listings": search_listings,
            },
        ):
            out = process_turn("find me 2-bed in canary wharf", state, runtime, router_debug=False)

    _assert(isinstance(out, str) and len(out) > 0, "process_turn must return text for SSE layer")
    _assert(len(state.last_results) == 2, "search should update last_results")
    _assert(state.current_focus_listing_id == "id-1", "search should auto-focus listing #1")
    _assert(len(state.history) == 1, "history should append after search")

    focus_msg = _handle_focus_command("/focus 2", state)
    _assert("listing 2" in focus_msg.lower(), "focus command should switch to listing #2")
    _assert(state.current_focus_listing_id == "id-2", "focus id should point to listing #2")

    with patch("agent.workflow._GRAPH_RUNNER", None):
        with patch(
            "agent_graph.nodes.route_turn",
            return_value=RouteDecision(intent="Specific_QA", reason="test_qa_single"),
        ), patch(
            "agent_graph.nodes.classify_qa_scope",
            return_value={"target_scope": "single"},
        ), patch(
            "agent_graph.nodes.answer_single_listing_question",
            return_value="SINGLE_ANSWER",
        ):
            single_out = process_turn("does it allow pets?", state, runtime, router_debug=False)
    _assert(single_out == "SINGLE_ANSWER", "single QA should use single-listing answer tool")

    with patch("agent.workflow._GRAPH_RUNNER", None):
        with patch(
            "agent_graph.nodes.route_turn",
            return_value=RouteDecision(intent="Specific_QA", reason="test_qa_multi"),
        ), patch(
            "agent_graph.nodes.classify_qa_scope",
            return_value={"target_scope": "list"},
        ), patch(
            "agent_graph.nodes.answer_multi_listing_question",
            return_value="MULTI_ANSWER",
        ):
            multi_out = process_turn("which one has gym?", state, runtime, router_debug=False)
    _assert(multi_out == "MULTI_ANSWER", "multi QA should use multi-listing answer tool")
    _assert(len(state.history) == 3, "history should append for each turn")

    print("PASS: graph migration smoke checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
