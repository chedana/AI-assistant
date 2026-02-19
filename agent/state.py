from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class AgentState:
    history: List[Tuple[str, str]] = field(default_factory=list)
    mode: str = "assistant"
    constraints: Optional[Dict[str, Any]] = None
    user_profile: Dict[str, Any] = field(default_factory=dict)
    current_focus_listing_id: Optional[str] = None
    current_focus_listing_payload: Optional[Dict[str, Any]] = None
    focus_source: Optional[str] = None  # auto | user_command | user_query
    last_results: List[Dict[str, Any]] = field(default_factory=list)
