from __future__ import annotations

from typing import Any

from agent_graph.nodes import (
    chitchat_node,
    direct_reply_node,
    fallback_node,
    finalize_node,
    qa_execute_node,
    qa_plan_node,
    route_branch,
    route_node,
    search_node,
)
from agent_graph.state import GraphState

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
    graph.add_node("route", route_node)
    graph.add_node("search", search_node)
    graph.add_node("qa_plan", qa_plan_node)
    graph.add_node("qa_execute", qa_execute_node)
    graph.add_node("chitchat", chitchat_node)
    graph.add_node("direct_reply", direct_reply_node)
    graph.add_node("fallback", fallback_node)
    graph.add_node("finalize", finalize_node)

    graph.add_edge(START, "route")
    graph.add_conditional_edges(
        "route",
        route_branch,
        {
            "Search": "search",
            "Specific_QA": "qa_plan",
            "Chitchat": "chitchat",
            "DirectReply": "direct_reply",
            "Fallback": "fallback",
        },
    )
    graph.add_edge("search", "finalize")
    graph.add_edge("qa_plan", "qa_execute")
    graph.add_edge("qa_execute", "finalize")
    graph.add_edge("chitchat", "finalize")
    graph.add_edge("direct_reply", "finalize")
    graph.add_edge("fallback", "finalize")
    graph.add_edge("finalize", END)

    return graph.compile()
