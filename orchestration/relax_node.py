"""relax_node — apply a single constraint relaxation and hand off to search_node.

Reads:
  state["relax_bottleneck"]      — which constraint to relax
  state["relax_attempt"]         — 0-based attempt index (controls relax magnitude)
  state["agent_state"].constraints — current merged constraints

Writes:
  state["relax_override_constraints"] — relaxed constraints for search_node
  state["relax_attempt"]              — incremented
  state["relax_log"]                  — human-readable log entry appended
  state["original_budget"]            — set on first budget relax (for ★ markup)
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from orchestration.state import GraphState


def _parse_available_from_date(value: Any) -> Optional[date]:
    """Parse an ISO-format date string, returning None on failure."""
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except (ValueError, TypeError):
        return None


def relax_node(state: GraphState) -> GraphState:
    """Apply one relaxation step to the active constraints."""
    bottleneck: Optional[str] = state.get("relax_bottleneck")
    agent_state = state["agent_state"]
    constraints: Dict[str, Any] = deepcopy(agent_state.constraints or {})
    attempt: int = int(state.get("relax_attempt") or 0)
    relax_log: List[str] = list(state.get("relax_log") or [])

    if bottleneck == "budget":
        factor = 1.15 if attempt == 0 else 1.25
        original = constraints.get("max_rent_pcm")
        if original is not None:
            original_val = float(original)
            new_val = int(round(original_val * factor))
            constraints["max_rent_pcm"] = new_val
            relax_log.append(f"budget widened from £{int(original_val):,} to £{new_val:,}")
            # Record original budget for ★ over-budget markup in formatter.
            # Only store on the very first relax so we keep the user's original figure.
            if state.get("original_budget") is None:
                state["original_budget"] = int(original_val)

    elif bottleneck == "furnish_type":
        old = constraints.get("furnish_type") or "any"
        constraints["furnish_type"] = None
        relax_log.append(f"removed furnished/unfurnished filter (was: {old})")

    elif bottleneck == "let_type":
        old = constraints.get("let_type") or "any"
        constraints["let_type"] = None
        relax_log.append(f"removed let type filter (was: {old})")

    elif bottleneck == "available_from":
        d = _parse_available_from_date(constraints.get("available_from"))
        if d is not None:
            new_d = d + timedelta(days=14)
            constraints["available_from"] = new_d.isoformat()
            relax_log.append(f"available_from pushed +14 days to {new_d.isoformat()}")
        else:
            # Can't parse date — remove constraint entirely.
            constraints["available_from"] = None
            relax_log.append("removed available_from filter (could not parse date)")

    elif bottleneck == "min_size_sqm":
        original = constraints.get("min_size_sqm")
        if original is not None:
            new_val = round(float(original) * 0.9, 1)
            constraints["min_size_sqm"] = new_val
            relax_log.append(f"min size reduced from {original}m² to {new_val}m²")

    elif bottleneck == "min_tenancy":
        old = constraints.get("min_tenancy_months")
        constraints["min_tenancy_months"] = None
        relax_log.append(f"removed minimum tenancy restriction (was: {old} months)")

    # Write relaxed constraints and updated counters back to state.
    state["relax_override_constraints"] = constraints
    state["relax_attempt"] = attempt + 1
    state["relax_log"] = relax_log
    return state
