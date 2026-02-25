import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, TypedDict


@dataclass
class QuerySnapshot:
    # Root/Stage-B hard-constraint snapshot fields.
    location_keywords: Optional[List[str]] = None
    layout_options: List[Dict[str, Any]] = field(default_factory=list)
    max_rent_pcm: Optional[float] = None
    available_from: Optional[str] = None
    furnish_type: Optional[str] = None
    let_type: Optional[str] = None
    min_tenancy_months: Optional[float] = None
    min_size_sqm: Optional[float] = None

    # Cached search output for this snapshot.
    results: List[Dict[str, Any]] = field(default_factory=list)

    @staticmethod
    def _norm_num(v: Any) -> Any:
        """Normalise float-valued integers to int so 2500.0 and 2500 hash identically."""
        if isinstance(v, float) and v == int(v):
            return int(v)
        return v

    def to_hash_payload(self) -> Dict[str, Any]:
        loc = [str(x).strip() for x in (self.location_keywords or []) if str(x).strip()]
        loc = sorted(set(loc), key=lambda s: s.lower())
        layout = [
            {k: self._norm_num(val) for k, val in item.items()}
            for item in (self.layout_options or [])
        ]
        layout = sorted(
            layout,
            key=lambda x: json.dumps(x, ensure_ascii=False, sort_keys=True),
        )
        return {
            "location_keywords": loc,
            "layout_options": layout,
            "max_rent_pcm": self._norm_num(self.max_rent_pcm),
            "available_from": self.available_from,
            "furnish_type": self.furnish_type,
            "let_type": self.let_type,
            "min_tenancy_months": self._norm_num(self.min_tenancy_months),
            "min_size_sqm": self._norm_num(self.min_size_sqm),
        }

    def get_hash(self) -> str:
        payload = json.dumps(self.to_hash_payload(), ensure_ascii=False, sort_keys=True)
        return hashlib.md5(payload.encode("utf-8")).hexdigest()


@dataclass
class AgentState:
    history: List[Tuple[str, str]] = field(default_factory=list)
    mode: str = "assistant"
    constraints: Optional[Dict[str, Any]] = None
    user_profile: Dict[str, Any] = field(default_factory=dict)
    current_focus_listing_id: Optional[str] = None
    current_focus_listing_payload: Optional[Dict[str, Any]] = None
    focus_source: Optional[str] = None  # auto | user_command | user_query
    last_qa_scope: Optional[str] = None  # single | list | clarify
    last_results: List[Dict[str, Any]] = field(default_factory=list)
    search_full_results: List[Dict[str, Any]] = field(default_factory=list)
    page_index: int = 0
    has_more: bool = False
    snapshot_history: List[QuerySnapshot] = field(default_factory=list)


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
