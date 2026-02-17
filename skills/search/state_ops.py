from typing import Any, Dict, Optional, Tuple

from core.settings import DEFAULT_K, DEFAULT_RECALL


def parse_command(s: str) -> Tuple[Optional[str], str]:
    s = s.strip()
    if not s.startswith("/"):
        return None, ""
    parts = s.split(maxsplit=1)
    cmd = parts[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else ""
    return cmd, arg


def _default_constraints(k: int) -> Dict[str, Any]:
    return {
        "k": k,
        "location_keywords": [],
        "max_rent_pcm": None,
        "available_from": None,
        "available_from_op": None,
        "furnish_type": None,
        "let_type": None,
        "layout_options": [],
        "min_tenancy_months": None,
        "min_size_sqm": None,
    }


def init_runtime_state() -> Dict[str, Any]:
    return {
        "history": [],
        "k": DEFAULT_K,
        "recall": DEFAULT_RECALL,
        "last_query": None,
        "last_df": None,
        "constraints": None,
        "view_mode": "summary",
    }


def reset_runtime_state(state: Dict[str, Any]) -> None:
    state["history"] = []
    state["last_query"] = None
    state["last_df"] = None
    state["constraints"] = None


def set_k_value(state: Dict[str, Any], arg: str) -> Tuple[bool, str]:
    try:
        n = int(arg)
        if n <= 0 or n > 50:
            raise ValueError()
        state["k"] = n
        if state.get("constraints") is None:
            state["constraints"] = _default_constraints(n)
        else:
            state["constraints"]["k"] = n
        return True, f"OK. k = {n}"
    except Exception:
        return False, "Usage: /k 5   (1~50)"


def set_recall_value(state: Dict[str, Any], arg: str) -> Tuple[bool, str]:
    try:
        n = int(arg)
        if n <= 0 or n > 2000:
            raise ValueError()
        state["recall"] = n
        return True, f"OK. recall = {n}"
    except Exception:
        return False, "Usage: /recall 200   (1~2000)"


def set_view_mode(state: Dict[str, Any], arg: str) -> Tuple[bool, str]:
    mode = str(arg or "").strip().lower()
    if mode not in {"summary", "debug"}:
        return False, "Usage: /view summary   or   /view debug"
    state["view_mode"] = mode
    return True, f"OK. view = {mode}"
