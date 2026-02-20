import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


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

    def to_hash_payload(self) -> Dict[str, Any]:
        loc = [str(x).strip() for x in (self.location_keywords or []) if str(x).strip()]
        loc = sorted(set(loc), key=lambda s: s.lower())
        layout = list(self.layout_options or [])
        layout = sorted(
            layout,
            key=lambda x: json.dumps(x, ensure_ascii=False, sort_keys=True),
        )
        return {
            "location_keywords": loc,
            "layout_options": layout,
            "max_rent_pcm": self.max_rent_pcm,
            "available_from": self.available_from,
            "furnish_type": self.furnish_type,
            "let_type": self.let_type,
            "min_tenancy_months": self.min_tenancy_months,
            "min_size_sqm": self.min_size_sqm,
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
    snapshot_history: List[QuerySnapshot] = field(default_factory=list)
