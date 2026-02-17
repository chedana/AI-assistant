from dataclasses import dataclass, field
from typing import Any, Dict, Optional, List, Tuple


@dataclass
class AgentState:
    history: List[Tuple[str, str]] = field(default_factory=list)
    mode: str = "search"
    selected_listing_id: Optional[str] = None
    selected_listing_payload: Optional[Dict[str, Any]] = None
