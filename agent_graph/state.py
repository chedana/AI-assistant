from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict


class GraphState(TypedDict, total=False):
    # Input
    user_input: str

    # Routing
    intent: str
    route_reason: str
    need_clarify: bool
    clarify_question: Optional[str]
    target_index: Optional[int]
    refinement_type: Optional[str]
    page_action: Optional[str]

    # Runtime payload
    reply_text: str
    error: Optional[str]
    attempt_count: int
    router_debug: bool
    last_search_status: str

    # Shared conversational state mirrors existing agent state model.
    agent_state: Any
    runtime: Any
    constraints: Optional[Dict[str, Any]]
    user_profile: Dict[str, Any]
    last_results: List[Dict[str, Any]]
    search_full_results: List[Dict[str, Any]]
    page_index: int
    has_more: bool
    current_focus_listing_id: Optional[str]
    current_focus_listing_payload: Optional[Dict[str, Any]]
    focus_source: Optional[str]
    last_qa_scope: Optional[str]
    qa_target_scope: Optional[str]
    qa_extraction_input: Optional[str]
    qa_plan_source: Optional[str]
    qa_llm_extract_all_error: Dict[str, Any]
    qa_target_constraints: Dict[str, Any]
    qa_semantic_terms: Dict[str, Any]
    qa_signals: Dict[str, Any]
    history: List[tuple[str, str]]


def make_graph_state(user_input: str, *, agent_state: Any, runtime: Any, router_debug: bool = False) -> GraphState:
    return GraphState(
        user_input=str(user_input or "").strip(),
        intent="Search",
        route_reason="",
        need_clarify=False,
        clarify_question=None,
        target_index=None,
        refinement_type=None,
        page_action=None,
        reply_text="",
        error=None,
        attempt_count=0,
        router_debug=bool(router_debug),
        last_search_status="unknown",
        page_index=0,
        has_more=False,
        agent_state=agent_state,
        runtime=runtime,
    )
