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

import re
from collections import Counter
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

from orchestration.state import GraphState
from skills.search.formatter import format_relax_results_reply

# ── Tunables ──────────────────────────────────────────────────────────────────
MIN_PAGES = 2
MAX_RELAX_ATTEMPTS = 2

# Constraints that can be relaxed automatically without changing user intent.
AUTO_RELAX_SAFE = {"budget", "furnish_type", "let_type", "available_from", "min_size_sqm", "min_tenancy"}


# ── Helpers ──────────────────────────────────────────────────────────────────

def _to_num(v: Any) -> Optional[float]:
    """Safely convert a value to float; return None if not possible."""
    if v is None:
        return None
    try:
        s = re.sub(r"[^\d.\-]", "", str(v))
        return float(s) if s else None
    except (TypeError, ValueError):
        return None


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


# ── Internal relax-decision helpers (single-miss based) ─────────────────────


def _find_near_miss(audits: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Return audit records for listings that failed exactly one hard constraint."""
    return [a for a in audits if not a.get("hard_pass") and len(a.get("hard_fail_reasons") or []) == 1]



# ── Confirmed sensitivity (user-facing) ─────────────────────────────────────

def _extract_layout_requirements(constraints: Dict[str, Any]) -> Tuple[set, set]:
    """Extract required bedroom/bathroom values from layout_options."""
    req_beds: set = set()
    req_baths: set = set()
    for opt in (constraints.get("layout_options") or []):
        if not isinstance(opt, dict):
            continue
        b = opt.get("bedrooms")
        if b is not None:
            try:
                req_beds.add(int(round(float(b))))
            except (TypeError, ValueError):
                pass
        ba = opt.get("bathrooms")
        if ba is not None:
            try:
                req_baths.add(float(ba))
            except (TypeError, ValueError):
                pass
    return req_beds, req_baths


def compute_confirmed_sensitivity(
    audits: List[Dict[str, Any]],
    constraints: Dict[str, Any],
) -> Dict[str, Any]:
    """Count listings with CONFIRMED values for alternative constraint scenarios.

    Returns dict with optional keys:
      "budget":  {"threshold": int, "gain": int}   — raise budget to threshold → +gain
      "layout":  [(bed_count, confirmed_count), ...]  — alternative bedrooms within budget
      "other":   {constraint_name: count, ...}      — single-miss for minor constraints
    """
    budget = _to_num(constraints.get("max_rent_pcm"))
    req_beds, req_baths = _extract_layout_requirements(constraints)
    result: Dict[str, Any] = {}

    # --- Budget sensitivity ---
    # How many CONFIRMED layout-matching listings are just above the current budget?
    if budget is not None and req_beds:
        for factor in [1.15, 1.25, 1.50]:
            new_budget = int(round(budget * factor))
            gain = 0
            for a in audits:
                price = _to_num(a.get("price_pcm"))
                beds = _to_num(a.get("bedrooms"))
                if price is None or beds is None:
                    continue
                # Must be over current budget but within new budget
                if price <= budget or price > new_budget:
                    continue
                # Must match bedroom requirement
                if int(round(beds)) not in req_beds:
                    continue
                # Bathrooms: if user specified, require confirmed match
                if req_baths:
                    baths = _to_num(a.get("bathrooms"))
                    if baths is None:
                        continue
                    if float(baths) not in req_baths:
                        continue
                gain += 1
            if gain > 0:
                result["budget"] = {"threshold": new_budget, "gain": gain}
                break  # use the smallest meaningful threshold

    # --- Layout sensitivity ---
    # How many CONFIRMED listings with different bedrooms are within budget?
    layout_counts: Counter = Counter()
    for a in audits:
        price = _to_num(a.get("price_pcm"))
        beds = _to_num(a.get("bedrooms"))
        if price is None or beds is None:
            continue
        bed_val = int(round(beds))
        # Must be within budget (confirmed)
        if budget is not None and price > budget:
            continue
        # Must be a different bedroom count than requested
        if bed_val in req_beds:
            continue
        layout_counts[bed_val] += 1
    if layout_counts:
        # Top 2 alternatives, sorted by count descending
        result["layout"] = layout_counts.most_common(2)

    # --- Other constraints (furnish, let_type, etc.) ---
    # Single-miss approach is fine here — null values are rare for these fields.
    other_counts: Counter = Counter()
    for a in audits:
        if a.get("hard_pass"):
            continue
        reasons = a.get("hard_fail_reasons") or []
        if len(reasons) != 1:
            continue
        name = _parse_constraint_name(reasons[0])
        if name in ("budget", "layout", "location", "other"):
            continue  # handled separately or not actionable
        other_counts[name] += 1
    if other_counts:
        result["other"] = dict(other_counts)

    return result


def _build_sensitivity_message(
    confirmed: Dict[str, Any],
    constraints: Optional[Dict[str, Any]] = None,
) -> str:
    """Build a human-readable sensitivity message from confirmed sensitivity data."""
    if not confirmed:
        return ""
    lines = ["", "To find more:"]
    c = constraints or {}

    # Budget suggestion
    budget_info = confirmed.get("budget")
    if budget_info:
        threshold = budget_info["threshold"]
        gain = budget_info["gain"]
        plural = "listings" if gain != 1 else "listing"
        lines.append(f"  \U0001f4a1 Raise budget to \u00a3{threshold:,} \u2192 +{gain} confirmed {plural}")

    # Layout alternatives
    layout_info = confirmed.get("layout")
    if layout_info:
        budget_val = _to_num(c.get("max_rent_pcm"))
        budget_str = f" under \u00a3{int(budget_val):,}" if budget_val else ""
        for bed_count, count in layout_info:
            if count <= 0:
                continue
            bed_label = "studio" if bed_count == 0 else f"{bed_count}-bed"
            plural = "listings" if count != 1 else "listing"
            lines.append(f"  \U0001f4a1 {bed_label}{budget_str} \u2192 {count} confirmed {plural}")

    # Other constraints
    other_info = confirmed.get("other", {})
    for name, count in sorted(other_info.items(), key=lambda x: -x[1]):
        if count <= 0:
            continue
        label = _other_constraint_label(name, c)
        plural = "listings" if count != 1 else "listing"
        lines.append(f"  \U0001f4a1 {label} \u2192 +{count} {plural}")

    return "\n".join(lines) if len(lines) > 1 else ""


def _other_constraint_label(name: str, c: Dict[str, Any]) -> str:
    """Human-readable label for minor constraints."""
    if name == "furnish_type":
        val = str(c.get("furnish_type") or "").strip()
        return f"Remove {val} requirement" if val else "Remove furnished/unfurnished requirement"
    if name == "let_type":
        val = str(c.get("let_type") or "").strip()
        return f"Remove {val} restriction" if val else "Remove let type restriction"
    if name == "available_from":
        try:
            raw = str(c.get("available_from") or "")[:10]
            d = date.fromisoformat(raw)
            new_d = d + timedelta(days=14)
            return f"Move available date to {new_d.isoformat()}"
        except (ValueError, TypeError):
            return "Relax available-from date"
    if name == "min_size_sqm":
        try:
            val = float(c.get("min_size_sqm") or 0)
            return f"Reduce min size to {val * 0.9:.0f} m\u00b2"
        except (TypeError, ValueError):
            return "Relax minimum size requirement"
    if name == "min_tenancy":
        try:
            months = c.get("min_tenancy_months")
            return f"Remove {int(float(months))}-month min tenancy" if months is not None else "Remove min tenancy restriction"
        except (TypeError, ValueError):
            return "Remove minimum tenancy restriction"
    return "Relax other filter"


# ── Near-miss display ────────────────────────────────────────────────────────

def _format_near_miss_block(near_miss: List[Dict[str, Any]], max_show: int = 3) -> str:
    """Format up to max_show near-miss audit records into a compact display block."""
    if not near_miss:
        return ""
    lines = ["", "Near misses (one constraint away):"]
    for rec in near_miss[:max_show]:
        title = str(rec.get("title") or rec.get("address") or "Unknown listing").strip()
        price = _to_num(rec.get("price_pcm"))
        beds = _to_num(rec.get("bedrooms"))
        baths = _to_num(rec.get("bathrooms"))
        reasons = rec.get("hard_fail_reasons") or []

        parts: List[str] = []
        if price is not None:
            parts.append(f"£{int(round(price))}/mo")
        if beds is not None:
            parts.append(f"{int(round(beds))} bed")
        if baths is not None:
            parts.append(f"{int(round(baths))} bath")
        detail = " | ".join(parts)
        why = reasons[0] if reasons else "unknown"
        lines.append(f"  • {title}" + (f" — {detail}" if detail else "") + f" (failed: {why})")
    return "\n".join(lines)


# ── Node ─────────────────────────────────────────────────────────────────────

def evaluate_node(state: GraphState) -> GraphState:
    """Inspect search results and audit trail; set eval_decision."""
    status = state.get("last_search_status") or "unknown"
    agent_state = state["agent_state"]
    results = list(agent_state.last_results or [])
    audits: List[Dict[str, Any]] = list(state.get("stage_b_audits") or [])
    prefilter_count: int = int(state.get("stage_a_prefilter_count") or -1)
    attempt: int = int(state.get("relax_attempt") or 0)
    original_budget: Optional[int] = agent_state.original_budget
    k: int = int(((agent_state.constraints or {}).get("k") or 5))

    # Use full result set (all pages) for threshold decisions, not just current page.
    full_results = list(getattr(agent_state, "search_full_results", None) or [])
    all_results = full_results if full_results else results

    # display_results: bedrooms constraint is confirmed (bathrooms may be null/unknown).
    # A listing with unknown_hard(bathrooms) only is still a valid 2-bed — show it with ⚠️.
    # A listing with unknown_hard(bedrooms) could be anything (studio, parking) — exclude.
    display_results = [
        r for r in all_results
        if "unknown_hard(bedrooms" not in str(r.get("penalty_reasons") or "")
    ]
    # strict_results: all required fields confirmed.
    strict_results = [
        r for r in all_results
        if "unknown_hard" not in str(r.get("penalty_reasons") or "")
    ]

    # 1. Cache hit with results — always sufficient, no relax-rebuild needed.
    if status == "cache_hit" and results:
        state["eval_decision"] = "done"
        return state

    # 2. Results present — at least one result has confirmed bedrooms.
    if status in ("cache_hit", "success") and len(display_results) >= 1:
        # Sparse display results on first attempt: try a one-time budget relax to surface
        # more confirmed listings.  Guard: attempt == 0 prevents cascading relax loops.
        # Uses display_results (bedrooms confirmed) not strict_results (all fields confirmed),
        # because strict is too aggressive — most listings have at least one null field.
        if attempt == 0 and len(display_results) < k * MIN_PAGES:
            has_budget = (agent_state.constraints or {}).get("max_rent_pcm") is not None
            if has_budget:
                state["eval_decision"] = "relax"
                state["relax_bottleneck"] = "budget"
                state["relax_near_miss"] = _find_near_miss(audits)
                return state

        state["eval_decision"] = "done"

        # Debug: show match counts so thresholds can be verified.
        n_display_total = len(display_results)
        n_strict_total = len(strict_results)
        count_line = f"\n\n[debug] display={n_display_total} strict={n_strict_total} k={k} threshold={k * MIN_PAGES} attempt={attempt}"

        # If we got here via a relax loop, rebuild reply with ★ markup + sensitivity table.
        if attempt > 0:
            confirmed = compute_confirmed_sensitivity(audits, agent_state.constraints or {})
            sensitivity_msg = _build_sensitivity_message(confirmed, agent_state.constraints)
            state["reply_text"] = format_relax_results_reply(
                listings=results,
                k=k,
                relax_log=list(state.get("relax_log") or []),
                sensitivity_message=sensitivity_msg,
                original_budget=original_budget,
            ) + count_line
        else:
            # attempt == 0, display >= threshold or no budget: show results with optional hint.
            if len(strict_results) < k * MIN_PAGES:
                confirmed = compute_confirmed_sensitivity(audits, agent_state.constraints or {})
                sensitivity_msg = _build_sensitivity_message(confirmed, agent_state.constraints)
                if sensitivity_msg:
                    note = (
                        f"\n\nOnly {n_strict_total} listing{'s' if n_strict_total != 1 else ''} fully matched your requirements. "
                        + sensitivity_msg
                    )
                    state["reply_text"] = str(state.get("reply_text") or "") + note
            state["reply_text"] = str(state.get("reply_text") or "") + count_line
        return state

    # 3. Location miss (Stage A found nothing matching the location filter).
    if prefilter_count == 0:
        state["eval_decision"] = "ask_user"
        state["relax_near_miss"] = []
        state["reply_text"] = (
            "I couldn't find any listings in that area \u2014 the location may not be in "
            "the database or the keywords didn't match.\n\n"
            "Try a different neighbourhood name, postcode, or nearby area."
        )
        return state

    # 4. Max relax attempts reached — stop and ask user.
    if attempt >= MAX_RELAX_ATTEMPTS:
        near_miss = _find_near_miss(audits)
        confirmed = compute_confirmed_sensitivity(audits, agent_state.constraints or {})
        state["eval_decision"] = "ask_user"
        state["relax_near_miss"] = near_miss
        relax_log = list(state.get("relax_log") or [])
        relax_summary = ""
        if relax_log:
            relax_summary = "\n\nI already tried: " + "; ".join(relax_log) + "."
        sensitivity_msg = _build_sensitivity_message(confirmed, agent_state.constraints)
        near_miss_block = _format_near_miss_block(near_miss)
        state["reply_text"] = (
            "I still couldn't find matching listings after widening the search."
            + relax_summary
            + near_miss_block
            + sensitivity_msg
        )
        return state

    # 5. Diagnose the bottleneck using confirmed sensitivity.
    #    Old approach (_compute_single_miss) was broken: layout_options bundled price
    #    failures into a single "layout" reason, so budget never appeared as bottleneck.
    confirmed = compute_confirmed_sensitivity(audits, agent_state.constraints or {})
    budget_gain = (confirmed.get("budget") or {}).get("gain", 0)
    other_counts = confirmed.get("other", {})

    # Find best AUTO_RELAX_SAFE target from confirmed data.
    # Budget uses confirmed gain; other minor constraints use single-miss (still valid).
    best_target: Optional[str] = None
    best_count = 0
    if budget_gain > 0:
        best_target = "budget"
        best_count = budget_gain
    for name, count in sorted(other_counts.items(), key=lambda x: -x[1]):
        if name in AUTO_RELAX_SAFE and count > best_count:
            best_target = name
            best_count = count

    if best_target is not None:
        # 6. Auto-relax: found an actionable bottleneck.
        state["eval_decision"] = "relax"
        state["relax_bottleneck"] = best_target
        state["relax_near_miss"] = _find_near_miss(audits)
        return state

    # No auto-relax-safe bottleneck found (layout/location only, or nothing).
    near_miss = _find_near_miss(audits)
    sensitivity_msg = _build_sensitivity_message(confirmed, agent_state.constraints)
    near_miss_block = _format_near_miss_block(near_miss)
    state["eval_decision"] = "ask_user"
    state["relax_near_miss"] = near_miss
    state["reply_text"] = (
        "I couldn't find listings matching all your requirements."
        + near_miss_block
        + sensitivity_msg
    )
    return state
