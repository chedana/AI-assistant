from __future__ import annotations

from typing import Any

from orchestration.evaluate_node import evaluate_node
from orchestration.nodes import (
    apply_suggestion_node,
    direct_reply_node,
    domain_branch,
    domain_router_node,
    fallback_node,
    finalize_node,
    general_node,
    qa_execute_node,
    qa_plan_node,
    paginate_node,
    route_branch,
    route_node,
    search_node,
)
from orchestration.relax_node import relax_node
from orchestration.state import GraphState

try:
    from langgraph.graph import END, START, StateGraph
except Exception:  # pragma: no cover
    END = "__end__"
    START = "__start__"
    StateGraph = None


def build_graph() -> Any:
    if StateGraph is None:
        raise ImportError("langgraph is not installed. Please install langgraph before using build_graph().")

    graph = StateGraph(GraphState)

    # ── Top-level domain routing ──────────────────────────────────────────────
    graph.add_node("domain_router", domain_router_node)
    graph.add_node("general", general_node)

    # ── Rental sub-pipeline ───────────────────────────────────────────────────
    graph.add_node("route", route_node)
    graph.add_node("apply_suggestion", apply_suggestion_node)
    graph.add_node("search", search_node)
    graph.add_node("evaluate", evaluate_node)
    graph.add_node("relax", relax_node)
    graph.add_node("qa_plan", qa_plan_node)
    graph.add_node("qa_execute", qa_execute_node)
    graph.add_node("paginate", paginate_node)
    graph.add_node("direct_reply", direct_reply_node)
    graph.add_node("fallback", fallback_node)

    # ── Shared ────────────────────────────────────────────────────────────────
    graph.add_node("finalize", finalize_node)

    # ── Edges: domain dispatch ────────────────────────────────────────────────
    graph.add_edge(START, "domain_router")
    graph.add_conditional_edges(
        "domain_router",
        domain_branch,
        {
            "Rental": "route",
            "General": "general",
        },
    )

    # ── Edges: rental sub-pipeline ────────────────────────────────────────────
    graph.add_conditional_edges(
        "route",
        route_branch,
        {
            "Search": "search",
            "AcceptSuggestion": "apply_suggestion",
            "Specific_QA": "qa_plan",
            "DirectReply": "direct_reply",
            "Page_Nav": "paginate",
            "Fallback": "fallback",
        },
    )
    graph.add_edge("apply_suggestion", "search")
    # search → evaluate → (done|ask_user) → finalize, or relax → search loop
    graph.add_edge("search", "evaluate")
    graph.add_conditional_edges(
        "evaluate",
        lambda s: s.get("eval_decision") or "done",
        {
            "done": "finalize",
            "ask_user": "finalize",
            "relax": "relax",
        },
    )
    graph.add_edge("relax", "search")
    graph.add_edge("qa_plan", "qa_execute")
    graph.add_edge("qa_execute", "finalize")
    graph.add_edge("paginate", "finalize")
    graph.add_edge("direct_reply", "finalize")
    graph.add_edge("fallback", "finalize")

    # ── Edges: general ────────────────────────────────────────────────────────
    graph.add_edge("general", "finalize")

    graph.add_edge("finalize", END)

    return graph.compile()
