from __future__ import annotations

from typing import Any, Dict, List, Optional


def get_focus_listing(agent_state: Any) -> Optional[Dict[str, Any]]:
    payload = getattr(agent_state, "current_focus_listing_payload", None)
    if isinstance(payload, dict):
        return payload
    return None


def get_current_context_houses(agent_state: Any, target_scope: str) -> List[Dict[str, Any]]:
    scope = str(target_scope or "").strip().lower()
    if scope == "list":
        rows = getattr(agent_state, "last_results", None) or []
        return [x for x in rows if isinstance(x, dict)]

    focus = get_focus_listing(agent_state)
    if focus:
        return [focus]
    return []
