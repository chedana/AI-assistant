from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Optional, Tuple

from agent.state import QuerySnapshot


SNAPSHOT_FIELDS: Tuple[str, ...] = (
    "location_keywords",
    "layout_options",
    "max_rent_pcm",
    "available_from",
    "furnish_type",
    "let_type",
    "min_tenancy_months",
    "min_size_sqm",
)


def empty_snapshot() -> QuerySnapshot:
    return QuerySnapshot(
        location_keywords=[],
        layout_options=[],
        max_rent_pcm=None,
        available_from=None,
        furnish_type=None,
        let_type=None,
        min_tenancy_months=None,
        min_size_sqm=None,
        results=[],
    )


def snapshot_from_constraints(
    constraints: Optional[Dict[str, Any]],
    *,
    results: Optional[List[Dict[str, Any]]] = None,
) -> QuerySnapshot:
    c = dict(constraints or {})
    snap = empty_snapshot()
    snap.location_keywords = list(c.get("location_keywords") or [])
    snap.layout_options = list(c.get("layout_options") or [])
    snap.max_rent_pcm = c.get("max_rent_pcm")
    snap.available_from = c.get("available_from")
    snap.furnish_type = c.get("furnish_type")
    snap.let_type = c.get("let_type")
    snap.min_tenancy_months = c.get("min_tenancy_months")
    snap.min_size_sqm = c.get("min_size_sqm")
    snap.results = list(results or [])
    return snap


def snapshot_to_constraints(snapshot: QuerySnapshot) -> Dict[str, Any]:
    return {
        "location_keywords": list(snapshot.location_keywords or []),
        "layout_options": list(snapshot.layout_options or []),
        "max_rent_pcm": snapshot.max_rent_pcm,
        "available_from": snapshot.available_from,
        "furnish_type": snapshot.furnish_type,
        "let_type": snapshot.let_type,
        "min_tenancy_months": snapshot.min_tenancy_months,
        "min_size_sqm": snapshot.min_size_sqm,
    }


def _is_effective_set_value(field: str, value: Any) -> bool:
    if value is None:
        return False
    if field in {"location_keywords", "layout_options"}:
        return isinstance(value, list) and len(value) > 0
    return True


def derive_snapshot(
    *,
    old_snapshot: Optional[QuerySnapshot],
    set_fields: Optional[Dict[str, Any]],
    clear_fields: Optional[List[str]],
    is_reset: bool = False,
) -> QuerySnapshot:
    if is_reset:
        return empty_snapshot()

    base = deepcopy(old_snapshot) if old_snapshot is not None else empty_snapshot()
    set_fields = dict(set_fields or {})
    clear_set = {str(x).strip() for x in (clear_fields or []) if str(x).strip() in SNAPSHOT_FIELDS}

    # Phase 1: SET (has value -> override; otherwise inherit)
    for field in SNAPSHOT_FIELDS:
        if field not in set_fields:
            continue
        value = set_fields.get(field)
        if not _is_effective_set_value(field, value):
            continue
        if field in {"location_keywords", "layout_options"}:
            setattr(base, field, list(value))
        else:
            setattr(base, field, value)

    # Phase 2: CLEAR (explicit nulling)
    for field in clear_set:
        if field in {"location_keywords", "layout_options"}:
            setattr(base, field, [])
        else:
            setattr(base, field, None)

    # Search results belong to the prior snapshot version; clear until refreshed.
    base.results = []
    return base


def push_history(
    history: List[QuerySnapshot],
    snapshot: QuerySnapshot,
    *,
    max_size: int = 5,
) -> Tuple[List[QuerySnapshot], bool]:
    out = list(history or [])
    target_hash = snapshot.get_hash()
    hit_idx = -1
    for i, item in enumerate(out):
        if item.get_hash() == target_hash:
            hit_idx = i
            break

    if hit_idx >= 0:
        matched = out.pop(hit_idx)
        out.insert(0, matched)
        return out[:max(1, int(max_size))], True

    out.insert(0, snapshot)
    return out[:max(1, int(max_size))], False
