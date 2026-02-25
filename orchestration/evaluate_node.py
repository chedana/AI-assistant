"""evaluate_node — diagnose empty / sparse search results and decide next action.

Decision outcomes written to state["eval_decision"]:
  "done"      — results are sufficient (≥ MIN_RESULTS), or cache hit
  "relax"     — an auto-relax-safe bottleneck was found; relax_node should act
  "ask_user"  — location miss, layout bottleneck, or retries exhausted; show
                sensitivity table and ask the user to adjust

Also populates:
  state["relax_bottleneck"]  — constraint name driving the relax action
  state["relax_near_miss"]   — listings that failed exactly one constraint
"""
from __future__ import annotations

from collections import Counter
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from orchestration.state import GraphState
from skills.search.formatter import format_relax_results_reply

# ── Tunables ──────────────────────────────────────────────────────────────────
MIN_RESULTS = 1   # ≥ 1 result is "sufficient" (user can always ask for more)
MAX_RELAX_ATTEMPTS = 2

# Constraints that can be relaxed automatically without changing user intent.
AUTO_RELAX_SAFE = {"budget", "furnish_type", "let_type", "available_from", "min_size_sqm", "min_tenancy"}


# ── Constraint-name parsing ───────────────────────────────────────────────────

def _parse_constraint_name(reason: str) -> str:
    """Map a hard-filter fail reason string to a canonical constraint name."""
    r = reason.lower()
    if "price" in r or "rent" in r or "budget" in r:
        return "budget"
    if "layout" in r or "bedroom" in r or "bathroom" in r:
        return "layout"
    if "furnish" in r:
        return "furnish_type"
    if "available" in r:
        return "available_from"
    if "let_type" in r or "let type" in r:
        return "let_type"
    if "tenancy" in r or "min_tenancy" in r:
        return "min_tenancy"
    if "size" in r or "sqm" in r:
        return "min_size_sqm"
    if "location" in r or "area" in r or "zone" in r:
        return "location"
    return "other"


# ── Core analysis functions ───────────────────────────────────────────────────

def compute_sensitivity(audits: List[Dict[str, Any]]) -> Dict[str, int]:
    """For each active constraint, count listings that failed *only* that constraint.

    This is the marginal gain from relaxing that single constraint.
    """
    counts: Counter = Counter()
    for audit in audits:
        if audit.get("hard_pass"):
            continue
        reasons = audit.get("hard_fail_reasons") or []
        if len(reasons) == 1:
            counts[_parse_constraint_name(reasons[0])] += 1
    return dict(counts)


def _find_near_miss(audits: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Return audit records for listings that failed exactly one hard constraint."""
    return [a for a in audits if not a.get("hard_pass") and len(a.get("hard_fail_reasons") or []) == 1]


def _find_auto_relax_target(sensitivity: Dict[str, int]) -> Optional[str]:
    """Return the highest-impact auto-relax-safe constraint, or None."""
    for constraint, count in sorted(sensitivity.items(), key=lambda x: -x[1]):
        if constraint in AUTO_RELAX_SAFE and count > 0:
            return constraint
    return None


def _build_sensitivity_message(
    sensitivity: Dict[str, int],
    constraints: Optional[Dict[str, Any]] = None,
    relax_attempt: int = 0,
    original_budget: Optional[int] = None,
) -> str:
    """Build a human-readable sensitivity table with specific actionable values.

    For each blocking constraint, shows exactly what change would unlock more listings.
    Falls back to a generic label if the specific value cannot be computed.
    """
    if not sensitivity:
        return ""
    lines = ["", "Adjusting one constraint could unlock more listings:"]
    c = constraints or {}

    for constraint, count in sorted(sensitivity.items(), key=lambda x: -x[1]):
        if count <= 0:
            continue

        label: str
        if constraint == "budget":
            try:
                base = float(original_budget) if original_budget is not None else float(c.get("max_rent_pcm") or 0)
                factor = 1.15 if relax_attempt == 0 else 1.25
                next_val = int(round(base * factor))
                label = f"Raise budget to £{next_val:,}"
            except (TypeError, ValueError):
                label = "Raise budget"

        elif constraint == "furnish_type":
            val = str(c.get("furnish_type") or "").strip()
            label = f"Remove {val} requirement" if val else "Remove furnished/unfurnished requirement"

        elif constraint == "let_type":
            val = str(c.get("let_type") or "").strip()
            label = f"Remove {val} restriction" if val else "Remove let type restriction"

        elif constraint == "available_from":
            try:
                raw = str(c.get("available_from") or "")[:10]
                d = date.fromisoformat(raw)
                new_d = d + timedelta(days=14)
                label = f"Move available date to {new_d.isoformat()}"
            except (ValueError, TypeError):
                label = "Relax available-from date"

        elif constraint == "min_size_sqm":
            try:
                val = float(c.get("min_size_sqm") or 0)
                new_val = val * 0.9
                label = f"Reduce min size to {new_val:.0f} m²"
            except (TypeError, ValueError):
                label = "Relax minimum size requirement"

        elif constraint == "min_tenancy":
            try:
                months = c.get("min_tenancy_months")
                label = f"Remove {int(float(months))}-month min tenancy" if months is not None else "Remove min tenancy restriction"
            except (TypeError, ValueError):
                label = "Remove minimum tenancy restriction"

        elif constraint == "layout":
            label = "Adjust bedroom/bathroom requirements"

        else:
            label = "Relax other filter"

        lines.append(f"  \U0001f4a1 {label} \u2192 +{count} listing{'s' if count != 1 else ''}")

    return "\n".join(lines)


def _build_layout_suggestion(
    near_miss: List[Dict[str, Any]],
    constraints: Optional[Dict[str, Any]],
) -> str:
    """Generate a concrete layout alternative from near-miss listings.

    Looks at listings that failed only a layout constraint, counts available
    bedroom configurations, and suggests the most common one.
    """
    if not near_miss or not constraints:
        return ""

    # Filter to layout-only failures
    layout_misses = [
        a for a in near_miss
        if len(a.get("hard_fail_reasons") or []) == 1
        and _parse_constraint_name((a.get("hard_fail_reasons") or [""])[0]) == "layout"
    ]
    if not layout_misses:
        return ""

    # Count available bedroom configurations
    bed_counts: Counter = Counter()
    for a in layout_misses:
        beds = a.get("bedrooms")
        if beds is not None:
            try:
                bed_counts[int(round(float(beds)))] += 1
            except (TypeError, ValueError):
                pass

    if not bed_counts:
        return ""

    top_beds, top_count = bed_counts.most_common(1)[0]
    bed_label = "studio" if top_beds == 0 else f"{top_beds}-bedroom"
    plural = "listings" if top_count != 1 else "listing"

    # Suggest how to search
    search_hint = f"say '{top_beds} bedroom'" if top_beds > 0 else "say 'studio'"
    return f"  \U0001f4a1 {top_count} {plural} available as {bed_label} — {search_hint} to search those instead"


# ── Node ─────────────────────────────────────────────────────────────────────

def evaluate_node(state: GraphState) -> GraphState:
    """Inspect search results and audit trail; set eval_decision."""
    status = state.get("last_search_status") or "unknown"
    agent_state = state["agent_state"]
    results = list(agent_state.last_results or [])
    audits: List[Dict[str, Any]] = list(state.get("stage_b_audits") or [])
    prefilter_count: int = int(state.get("stage_a_prefilter_count") or -1)
    attempt: int = int(state.get("relax_attempt") or 0)
    original_budget: Optional[int] = state.get("original_budget")

    # 1. Cache hit with results — always sufficient, no relax-rebuild needed.
    if status == "cache_hit" and results:
        state["eval_decision"] = "done"
        return state

    # 2. Results are sufficient — done.
    if status in ("cache_hit", "success") and len(results) >= MIN_RESULTS:
        state["eval_decision"] = "done"
        # If we got here via a relax loop, rebuild reply with ★ markup + sensitivity table.
        if attempt > 0:
            sensitivity = compute_sensitivity(audits)
            sensitivity_msg = _build_sensitivity_message(
                sensitivity,
                constraints=agent_state.constraints,
                relax_attempt=attempt,
                original_budget=original_budget,
            )
            k = int(((agent_state.constraints or {}).get("k") or 5))
            state["reply_text"] = format_relax_results_reply(
                listings=results,
                k=k,
                relax_log=list(state.get("relax_log") or []),
                sensitivity_message=sensitivity_msg,
                original_budget=original_budget,
            )
        return state

    # 3. Location miss (Stage A found nothing matching the location filter).
    if prefilter_count == 0:
        state["eval_decision"] = "ask_user"
        state["relax_near_miss"] = []
        sensitivity = compute_sensitivity(audits)
        state["reply_text"] = (
            "I couldn't find any listings in that area — the location may not be in "
            "the database or the keywords didn't match.\n\n"
            "Try a different neighbourhood name, postcode, or nearby area."
            + _build_sensitivity_message(
                sensitivity,
                constraints=agent_state.constraints,
                relax_attempt=attempt,
                original_budget=original_budget,
            )
        )
        return state

    # 4. Max relax attempts reached — stop and ask user.
    if attempt >= MAX_RELAX_ATTEMPTS:
        near_miss = _find_near_miss(audits)
        sensitivity = compute_sensitivity(audits)
        state["eval_decision"] = "ask_user"
        state["relax_near_miss"] = near_miss
        relax_log = list(state.get("relax_log") or [])
        relax_summary = ""
        if relax_log:
            relax_summary = "\n\nI already tried: " + "; ".join(relax_log) + "."
        layout_hint = _build_layout_suggestion(near_miss, agent_state.constraints)
        state["reply_text"] = (
            "I still couldn't find matching listings after widening the search."
            + relax_summary
            + _build_sensitivity_message(
                sensitivity,
                constraints=agent_state.constraints,
                relax_attempt=attempt,
                original_budget=original_budget,
            )
            + ("\n" + layout_hint if layout_hint else "")
        )
        return state

    # 5. Diagnose the bottleneck from the audit trail.
    sensitivity = compute_sensitivity(audits)
    bottleneck = _find_auto_relax_target(sensitivity)

    if bottleneck is None:
        # Only layout / location / unknown constraints blocking — can't auto-relax.
        near_miss = _find_near_miss(audits)
        layout_hint = _build_layout_suggestion(near_miss, agent_state.constraints)
        state["eval_decision"] = "ask_user"
        state["relax_near_miss"] = near_miss
        state["reply_text"] = (
            "I couldn't find listings matching all your requirements."
            + _build_sensitivity_message(
                sensitivity,
                constraints=agent_state.constraints,
                relax_attempt=attempt,
                original_budget=original_budget,
            )
            + ("\n" + layout_hint if layout_hint else "")
        )
        return state

    # 6. Auto-relax: found a safe bottleneck.
    state["eval_decision"] = "relax"
    state["relax_bottleneck"] = bottleneck
    # Store sensitivity so formatter can show the table after relax completes.
    state["relax_near_miss"] = _find_near_miss(audits)
    return state
