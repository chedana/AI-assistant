#!/usr/bin/env python3
"""
Unit tests for the page-navigation feature (Page_Nav intent + paginate_node).

Covers:
  1. paginate_node  — pagination arithmetic, boundary guards, state mutations
  2. _is_cross_candidate_query — regex guard for comparative QA queries
  3. RouteDecision.page_action — field presence and sanitisation logic
  4. search_node pagination state — after a new search page_index resets to 0

Run with:
  python -m pytest test/smoke/test_page_nav.py -v
  # or directly:
  python test/smoke/test_page_nav.py
"""
from __future__ import annotations

import re
import sys
import os
from types import SimpleNamespace
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _assert(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def _make_listings(n: int):
    """Create n minimal listing dicts with stable IDs."""
    return [{"listing_id": f"id-{i}", "title": f"Listing {i}"} for i in range(1, n + 1)]


def _make_agent_state(full_results=None, page_index=0, has_more=False, constraints=None):
    from agent.state import AgentState
    s = AgentState()
    s.search_full_results = list(full_results or [])
    s.last_results = list(full_results[:5] if full_results else [])
    s.page_index = page_index
    s.has_more = has_more
    s.constraints = constraints or {"k": 5}
    return s


def _make_graph_state(agent_state, page_action="next"):
    return {
        "agent_state": agent_state,
        "page_action": page_action,
        "reply_text": "",
        "router_debug": False,
    }


# ---------------------------------------------------------------------------
# Section 1: paginate_node
# ---------------------------------------------------------------------------

def test_paginate_no_listings():
    """paginate_node with no results returns a guidance message."""
    from agent_graph.nodes import paginate_node
    from agent.state import AgentState
    state = {"agent_state": AgentState(), "page_action": "next", "reply_text": "", "router_debug": False}
    result = paginate_node(state)
    _assert("don't have active listings" in result["reply_text"].lower(),
            "should guide user to search when no listings are loaded")


def test_paginate_next_page_basic():
    """Next page advances page_index and slices the correct rows."""
    from agent_graph.nodes import paginate_node
    full = _make_listings(12)
    agent_state = _make_agent_state(full_results=full, page_index=0, constraints={"k": 5})
    state = _make_graph_state(agent_state, page_action="next")
    result = paginate_node(state)
    _assert(agent_state.page_index == 1, "page_index should advance to 1")
    _assert(len(agent_state.last_results) == 5, "page 2 should have 5 rows")
    _assert(agent_state.last_results[0]["listing_id"] == "id-6", "page 2 starts at listing 6")
    _assert("Page 2" in result["reply_text"], "reply should mention Page 2")
    _assert("6-10 of 12" in result["reply_text"], "reply should show correct range")
    _assert(agent_state.has_more is True, "page 3 exists so has_more=True")


def test_paginate_next_last_partial_page():
    """Last partial page has_more=False and contains only remaining rows."""
    from agent_graph.nodes import paginate_node
    full = _make_listings(12)
    agent_state = _make_agent_state(full_results=full, page_index=1, constraints={"k": 5})
    state = _make_graph_state(agent_state, page_action="next")
    result = paginate_node(state)
    _assert(agent_state.page_index == 2, "should advance to page index 2")
    _assert(len(agent_state.last_results) == 2, "last page has only 2 rows (11-12)")
    _assert(agent_state.last_results[0]["listing_id"] == "id-11", "should start at listing 11")
    _assert(agent_state.has_more is False, "no more pages after the last")
    _assert("11-12 of 12" in result["reply_text"], "range display is correct")


def test_paginate_next_beyond_last_page():
    """Asking 'next' when already on last page returns boundary message."""
    from agent_graph.nodes import paginate_node
    full = _make_listings(5)  # exactly one page
    agent_state = _make_agent_state(full_results=full, page_index=0, constraints={"k": 5})
    state = _make_graph_state(agent_state, page_action="next")
    result = paginate_node(state)
    _assert("last page" in result["reply_text"].lower(),
            "should say this is already the last page")
    _assert(agent_state.page_index == 0, "page_index should not change on boundary")


def test_paginate_prev_page_basic():
    """Prev page goes back and slices correct rows."""
    from agent_graph.nodes import paginate_node
    full = _make_listings(12)
    agent_state = _make_agent_state(full_results=full, page_index=1, constraints={"k": 5})
    state = _make_graph_state(agent_state, page_action="prev")
    result = paginate_node(state)
    _assert(agent_state.page_index == 0, "should go back to page 0")
    _assert(len(agent_state.last_results) == 5, "page 1 should have 5 rows")
    _assert(agent_state.last_results[0]["listing_id"] == "id-1", "back to first listing")
    _assert("Page 1" in result["reply_text"], "reply should mention Page 1")
    _assert("1-5 of 12" in result["reply_text"], "range display is correct")


def test_paginate_prev_already_first_page():
    """Asking 'prev' from page 0 returns boundary message."""
    from agent_graph.nodes import paginate_node
    full = _make_listings(10)
    agent_state = _make_agent_state(full_results=full, page_index=0, constraints={"k": 5})
    state = _make_graph_state(agent_state, page_action="prev")
    result = paginate_node(state)
    _assert("first page" in result["reply_text"].lower(),
            "should say this is already the first page")
    _assert(agent_state.page_index == 0, "page_index should not change on boundary")


def test_paginate_auto_focus_updated():
    """After pagination, focus is auto-set to first listing of new page."""
    from agent_graph.nodes import paginate_node
    full = _make_listings(10)
    agent_state = _make_agent_state(full_results=full, page_index=0, constraints={"k": 5})
    paginate_node(_make_graph_state(agent_state, page_action="next"))
    _assert(agent_state.current_focus_listing_id == "id-6",
            "focus should point to first listing of page 2 after next")


def test_paginate_invalid_action_defaults_to_next():
    """An unrecognised page_action string falls back to 'next'."""
    from agent_graph.nodes import paginate_node
    full = _make_listings(10)
    agent_state = _make_agent_state(full_results=full, page_index=0, constraints={"k": 5})
    state = {"agent_state": agent_state, "page_action": "forward", "reply_text": "", "router_debug": False}
    paginate_node(state)
    _assert(agent_state.page_index == 1, "invalid action should default to 'next'")


def test_paginate_fallback_to_last_results_when_full_empty():
    """If search_full_results is empty, paginate_node falls back to last_results."""
    from agent_graph.nodes import paginate_node
    from agent.state import AgentState
    agent_state = AgentState()
    agent_state.search_full_results = []
    agent_state.last_results = _make_listings(6)
    agent_state.page_index = 0
    agent_state.constraints = {"k": 5}
    state = _make_graph_state(agent_state, page_action="next")
    paginate_node(state)
    _assert(agent_state.page_index == 1, "should paginate using last_results as fallback")
    _assert(len(agent_state.search_full_results) == 6,
            "last_results should be promoted to search_full_results")


def test_paginate_has_more_is_false_on_exact_fit():
    """When total results are an exact multiple of k, has_more is False on last page."""
    from agent_graph.nodes import paginate_node
    full = _make_listings(10)  # 10 = 2 pages of k=5
    agent_state = _make_agent_state(full_results=full, page_index=0, constraints={"k": 5})
    paginate_node(_make_graph_state(agent_state, page_action="next"))
    _assert(agent_state.page_index == 1, "advance to page 2")
    _assert(len(agent_state.last_results) == 5, "page 2 has exactly 5 items")
    _assert(agent_state.has_more is False, "page 2 is the last page, no more pages")


# ---------------------------------------------------------------------------
# Section 2: _is_cross_candidate_query
# ---------------------------------------------------------------------------

def test_cross_candidate_which_one():
    from agent_graph.nodes import _is_cross_candidate_query
    _assert(_is_cross_candidate_query("which one is closer to the tube?"), "should match 'which one'")


def test_cross_candidate_which_listing():
    from agent_graph.nodes import _is_cross_candidate_query
    _assert(_is_cross_candidate_query("Which listing has parking?"), "should match 'which listing' (case-insensitive)")


def test_cross_candidate_which_property():
    from agent_graph.nodes import _is_cross_candidate_query
    _assert(_is_cross_candidate_query("which property allows pets?"), "should match 'which property'")


def test_cross_candidate_which_of():
    from agent_graph.nodes import _is_cross_candidate_query
    _assert(_is_cross_candidate_query("Which of these has a balcony?"), "should match 'which of'")


def test_cross_candidate_false_for_single_listing_qa():
    from agent_graph.nodes import _is_cross_candidate_query
    _assert(not _is_cross_candidate_query("does it have a garden?"), "single-listing QA should not match")


def test_cross_candidate_false_for_empty_string():
    from agent_graph.nodes import _is_cross_candidate_query
    _assert(not _is_cross_candidate_query(""), "empty string should return False")


def test_cross_candidate_false_for_search_query():
    from agent_graph.nodes import _is_cross_candidate_query
    _assert(not _is_cross_candidate_query("find 2 bed near waterloo"), "search query should not match")


# ---------------------------------------------------------------------------
# Section 3: RouteDecision page_action field
# ---------------------------------------------------------------------------

def test_route_decision_has_page_action_field():
    """RouteDecision dataclass must expose the page_action attribute."""
    from agent.router import RouteDecision
    rd = RouteDecision(intent="Page_Nav", reason="next_page_request", page_action="next")
    _assert(rd.page_action == "next", "page_action should be accessible on RouteDecision")


def test_route_decision_page_action_defaults_none():
    from agent.router import RouteDecision
    rd = RouteDecision(intent="Search", reason="test")
    _assert(rd.page_action is None, "page_action default should be None for non-paging intents")


def test_page_nav_intent_in_allowed_intents():
    """_INTENTS set must include Page_Nav so the router can classify it."""
    import agent.router as r
    _assert("Page_Nav" in r._INTENTS, "Page_Nav must be in the router's allowed intents set")


# ---------------------------------------------------------------------------
# Section 4: search_node resets pagination state on new results
# ---------------------------------------------------------------------------

def test_search_node_resets_pagination_on_new_results():
    """After a successful new search, page_index resets to 0 and has_more is set correctly."""
    import importlib.util
    if importlib.util.find_spec("langgraph") is None:
        print("SKIP: langgraph not installed.")
        return

    from agent.router import RouteDecision
    from agent.state import AgentState
    from agent.workflow import process_turn

    state = AgentState()
    # Simulate leftover pagination from a previous search.
    state.page_index = 2
    state.has_more = True
    state.search_full_results = _make_listings(15)
    state.last_results = _make_listings(5)
    state.constraints = {"k": 5}

    runtime = SimpleNamespace(embedder=object())
    all_new = _make_listings(12)

    with patch("agent.workflow._GRAPH_RUNNER", None):
        with patch(
            "agent_graph.nodes.route_turn",
            return_value=RouteDecision(intent="Search", reason="new_search"),
        ), patch(
            "agent_graph.nodes.run_search_skill",
            return_value={
                "reply_text": "Found 12 listings.",
                "constraints": {"k": 5},
                "profile_patch": {},
                "listings": all_new[:5],
                "all_ranked_listings": all_new,
            },
        ):
            process_turn("find 2 bed in Canary Wharf under 3000", state, runtime)

    _assert(state.page_index == 0, "new search must reset page_index to 0")
    _assert(len(state.search_full_results) == 12, "search_full_results should hold all 12 ranked listings")
    _assert(len(state.last_results) == 5, "last_results should be first page (k=5)")
    _assert(state.has_more is True, "has_more=True because 12 > 5")


def test_search_node_has_more_false_when_results_fit_one_page():
    """If total results ≤ k, has_more is False after a search."""
    import importlib.util
    if importlib.util.find_spec("langgraph") is None:
        print("SKIP: langgraph not installed.")
        return

    from agent.router import RouteDecision
    from agent.state import AgentState
    from agent.workflow import process_turn

    state = AgentState()
    runtime = SimpleNamespace(embedder=object())
    small_set = _make_listings(3)

    with patch("agent.workflow._GRAPH_RUNNER", None):
        with patch(
            "agent_graph.nodes.route_turn",
            return_value=RouteDecision(intent="Search", reason="new_search"),
        ), patch(
            "agent_graph.nodes.run_search_skill",
            return_value={
                "reply_text": "Found 3 listings.",
                "constraints": {"k": 5},
                "profile_patch": {},
                "listings": small_set,
                "all_ranked_listings": small_set,
            },
        ):
            process_turn("find something in zone 1", state, runtime)

    _assert(state.page_index == 0, "page_index should be 0")
    _assert(state.has_more is False, "has_more=False when all results fit on one page")


# ---------------------------------------------------------------------------
# Section 5: Integration — Page_Nav route goes through paginate_node
# ---------------------------------------------------------------------------

def test_page_nav_intent_routed_to_paginate_node():
    """process_turn with Page_Nav intent must call paginate_node and advance the page."""
    import importlib.util
    if importlib.util.find_spec("langgraph") is None:
        print("SKIP: langgraph not installed.")
        return

    from agent.router import RouteDecision
    from agent.state import AgentState
    from agent.workflow import process_turn

    state = AgentState()
    state.search_full_results = _make_listings(10)
    state.last_results = _make_listings(5)
    state.page_index = 0
    state.has_more = True
    state.constraints = {"k": 5}
    runtime = SimpleNamespace(embedder=object())

    with patch("agent.workflow._GRAPH_RUNNER", None):
        with patch(
            "agent_graph.nodes.route_turn",
            return_value=RouteDecision(intent="Page_Nav", reason="next_page_request", page_action="next"),
        ):
            reply = process_turn("show more", state, runtime)

    _assert(state.page_index == 1, "page_index should advance after Page_Nav turn")
    _assert("Page 2" in reply, "reply should mention the new page number")
    _assert(len(state.last_results) == 5, "second page should contain 5 listings")


def test_page_nav_prev_returns_to_page_one():
    """Page_Nav with prev from page 1 returns to page 0 content."""
    import importlib.util
    if importlib.util.find_spec("langgraph") is None:
        print("SKIP: langgraph not installed.")
        return

    from agent.router import RouteDecision
    from agent.state import AgentState
    from agent.workflow import process_turn

    state = AgentState()
    state.search_full_results = _make_listings(10)
    state.last_results = _make_listings(5)[5:10]  # simulating page 2 view
    state.page_index = 1
    state.has_more = False
    state.constraints = {"k": 5}
    runtime = SimpleNamespace(embedder=object())

    with patch("agent.workflow._GRAPH_RUNNER", None):
        with patch(
            "agent_graph.nodes.route_turn",
            return_value=RouteDecision(intent="Page_Nav", reason="prev_page_request", page_action="prev"),
        ):
            reply = process_turn("previous page", state, runtime)

    _assert(state.page_index == 0, "page_index should go back to 0")
    _assert("Page 1" in reply, "reply should mention Page 1")


def test_page_nav_no_listings_returns_guidance():
    """Page_Nav without any prior search gives a helpful guidance message."""
    import importlib.util
    if importlib.util.find_spec("langgraph") is None:
        print("SKIP: langgraph not installed.")
        return

    from agent.router import RouteDecision
    from agent.state import AgentState
    from agent.workflow import process_turn

    state = AgentState()  # empty state — no search done yet
    runtime = SimpleNamespace(embedder=object())

    with patch("agent.workflow._GRAPH_RUNNER", None):
        with patch(
            "agent_graph.nodes.route_turn",
            return_value=RouteDecision(intent="Page_Nav", reason="next_page_request", page_action="next"),
        ):
            reply = process_turn("show me next page", state, runtime)

    _assert("don't have active listings" in reply.lower(),
            "should guide user to search when no listings exist")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

_TESTS = [
    # paginate_node
    test_paginate_no_listings,
    test_paginate_next_page_basic,
    test_paginate_next_last_partial_page,
    test_paginate_next_beyond_last_page,
    test_paginate_prev_page_basic,
    test_paginate_prev_already_first_page,
    test_paginate_auto_focus_updated,
    test_paginate_invalid_action_defaults_to_next,
    test_paginate_fallback_to_last_results_when_full_empty,
    test_paginate_has_more_is_false_on_exact_fit,
    # _is_cross_candidate_query
    test_cross_candidate_which_one,
    test_cross_candidate_which_listing,
    test_cross_candidate_which_property,
    test_cross_candidate_which_of,
    test_cross_candidate_false_for_single_listing_qa,
    test_cross_candidate_false_for_empty_string,
    test_cross_candidate_false_for_search_query,
    # RouteDecision
    test_route_decision_has_page_action_field,
    test_route_decision_page_action_defaults_none,
    test_page_nav_intent_in_allowed_intents,
    # search_node pagination state
    test_search_node_resets_pagination_on_new_results,
    test_search_node_has_more_false_when_results_fit_one_page,
    # integration
    test_page_nav_intent_routed_to_paginate_node,
    test_page_nav_prev_returns_to_page_one,
    test_page_nav_no_listings_returns_guidance,
]


def run() -> int:
    passed = 0
    failed = 0
    skipped = 0
    for fn in _TESTS:
        try:
            fn()
            print(f"  PASS  {fn.__name__}")
            passed += 1
        except AssertionError as exc:
            print(f"  FAIL  {fn.__name__}: {exc}")
            failed += 1
        except Exception as exc:
            if "SKIP" in str(exc):
                print(f"  SKIP  {fn.__name__}: {exc}")
                skipped += 1
            else:
                import traceback
                print(f"  ERROR {fn.__name__}: {exc}")
                traceback.print_exc()
                failed += 1

    print(f"\n{passed} passed, {failed} failed, {skipped} skipped  (total {len(_TESTS)})")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(run())
