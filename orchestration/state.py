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

    # Display setting — not a search constraint; excluded from hash.
    k: Optional[int] = None

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
    original_budget: Optional[int] = None  # user's stated max_rent_pcm before any auto-relax
    last_intent: Optional[str] = None  # intent from most recent turn (set by process_turn)
    pending_suggestion: Optional[Dict[str, Any]] = None  # top ask_user suggestion awaiting confirmation
    # Structure: {"field": str, "new_value": Any, "display": str}
    # field maps: "budget"→max_rent_pcm, "furnish_type", "let_type",
    #             "available_from", "min_size_sqm", "min_tenancy"→min_tenancy_months
    pending_area_compare: Optional[Dict[str, Any]] = None  # pending area compare awaiting layout info
    # Structure: {"areas": List[str]}
    shortlist: List[Dict[str, Any]] = field(default_factory=list)  # user-saved listings
    last_compare_source: Optional[str] = None  # "shortlist" | "results" — set by compare_node


class GraphState(TypedDict, total=False):
    # ── Input ────────────────────────────────────────────────────────────────
    user_input: str
    route_hint: Optional[Dict[str, Any]]   # set by frontend for quick-reply buttons

    # ── Domain (per-turn, set by domain_router_node) ─────────────────────────
    domain: str                  # "Rental" | "General"

    # ── Explicit action params (set by route_node from route_hint) ───────────
    # Present only for button actions; search_node skips regex extraction when set.
    explicit_set_constraints: Dict[str, Any]   # e.g. {"max_rent_pcm": 1280}
    explicit_clear_fields: List[str]            # e.g. ["max_rent_pcm"]

    # ── Routing (per-turn, set by route_node) ────────────────────────────────
    intent: str
    route_reason: str
    need_clarify: bool
    clarify_question: Optional[str]
    target_indices: List[int]
    target_areas: List[str]
    shortlist_action: Optional[str]
    refinement_type: Optional[str]
    page_action: Optional[str]

    # ── Turn output ──────────────────────────────────────────────────────────
    reply_text: str
    error: Optional[str]
    attempt_count: int
    router_debug: bool
    last_search_status: str

    # ── Persistent state handles (do NOT duplicate AgentState fields here) ───
    # All cross-turn data lives in AgentState; access via state["agent_state"].
    agent_state: Any
    runtime: Any

    # ── QA pipeline scratch-pad (per-turn, set by qa_plan_node) ─────────────
    qa_target_scope: Optional[str]
    qa_extraction_input: Optional[str]
    qa_plan_source: Optional[str]
    qa_llm_extract_all_error: Dict[str, Any]
    qa_target_constraints: Dict[str, Any]
    qa_semantic_terms: Dict[str, Any]
    qa_signals: Dict[str, Any]

    # ── Evaluate / Relax pipeline (per-turn) ─────────────────────────────────
    eval_decision: str                      # "done" | "relax" | "ask_user"
    relax_attempt: int                      # 0 = first run; max 2
    relax_log: List[str]                    # human-readable relax actions taken
    relax_bottleneck: Optional[str]         # constraint name that triggered relax
    relax_override_constraints: Optional[Dict[str, Any]]   # relaxed constraints for next search
    stage_b_audits: List[Dict[str, Any]]    # full Stage B audit trail
    stage_a_prefilter_count: int            # 0 = location miss
    relax_near_miss: List[Dict[str, Any]]   # listings that failed exactly 1 constraint


def make_graph_state(user_input: str, *, agent_state: Any, runtime: Any, router_debug: bool = False, route_hint: Optional[Dict[str, Any]] = None) -> GraphState:
    return GraphState(
        # Input
        user_input=str(user_input or "").strip(),
        route_hint=route_hint,
        # Explicit action params — overwritten by route_node when route_hint is present
        explicit_set_constraints={},
        explicit_clear_fields=[],
        # Domain default — overwritten by domain_router_node
        domain="Rental",
        # Routing defaults — overwritten by route_node
        intent="Search",
        route_reason="",
        need_clarify=False,
        clarify_question=None,
        target_indices=[],
        target_areas=[],
        shortlist_action=None,
        refinement_type=None,
        page_action=None,
        # Turn output defaults
        reply_text="",
        error=None,
        attempt_count=0,
        router_debug=bool(router_debug),
        last_search_status="unknown",
        # Persistent state handles
        agent_state=agent_state,
        runtime=runtime,
        # QA scratch-pad defaults — overwritten by qa_plan_node
        qa_target_scope="",
        qa_extraction_input="",
        qa_plan_source="",
        qa_llm_extract_all_error={},
        qa_target_constraints={},
        qa_semantic_terms={},
        qa_signals={},
        # Evaluate / Relax defaults
        eval_decision="done",
        relax_attempt=0,
        relax_log=[],
        relax_bottleneck=None,
        relax_override_constraints=None,
        stage_b_audits=[],
        stage_a_prefilter_count=-1,
        relax_near_miss=[],
    )
