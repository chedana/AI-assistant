"""Low-level text / value utilities shared across the search pipeline."""

import os
import re
import json
from typing import Any, List, Optional

from core.chatbot_config import (
    PROPERTY_TYPE_FLAT_LIKE,
    PROPERTY_TYPE_HOUSE_LIKE,
    PROPERTY_TYPE_SPECIAL_OR_UNKNOWN,
)


def _truthy_env(name: str) -> bool:
    v = str(os.environ.get(name) or "").strip().lower()
    return v in {"1", "true", "yes", "on"}


def _safe_text(v: Any) -> str:
    if v is None:
        return ""
    s = str(v).strip()
    if s.lower() in ("", "nan", "none", "ask agent"):
        return ""
    return s


def _to_float(v: Any) -> Optional[float]:
    try:
        if v is None:
            return None
        s = re.sub(r"[^\d\.\-]", "", str(v))
        if not s:
            return None
        return float(s)
    except Exception:
        return None


def _norm_furnish_value(v: Any) -> str:
    s = str(v).strip().lower() if v is not None else ""
    if not s:
        return ""
    s = s.replace("_", " ").replace("-", " ")
    s = re.sub(r"\s+", " ", s).strip()
    if not s:
        return ""
    if s in {"ask agent", "ask the agent", "unknown", "not provided", "not known", "n/a", "na"}:
        return "ask agent"
    if "furnished or unfurnished" in s or ("landlord" in s and "flexible" in s):
        return "flexible"
    if "unfurn" in s:
        return "unfurnished"
    if "part" in s and "furnish" in s:
        return "part-furnished"
    if "furnish" in s:
        return "furnished"
    return s


def _norm_property_type_value(v: Any) -> str:
    s = str(v).strip().lower() if v is not None else ""
    if not s:
        return ""
    s = s.replace("_", " ").replace("-", " ")
    s = re.sub(r"\s+", " ", s).strip()
    if not s:
        return ""
    if s in {"ask agent", "ask the agent", "unknown", "not provided", "not known", "n/a", "na"}:
        return "other"
    if s == "studio":
        return "flat"
    if s in {"apartment", "apartments"}:
        return "flat"
    if s in {"flat", "flats"}:
        return "flat"
    if s == "house":
        return "house"
    if s in PROPERTY_TYPE_HOUSE_LIKE:
        return "house"
    if s in PROPERTY_TYPE_FLAT_LIKE:
        return "flat"
    if s in PROPERTY_TYPE_SPECIAL_OR_UNKNOWN:
        return "other"
    return s


def parse_jsonish_items(v: Any) -> List[str]:
    s = _safe_text(v)
    if not s:
        return []
    if isinstance(v, list):
        out = []
        for it in v:
            t = _safe_text(it)
            if t:
                out.append(t)
        return out
    if s.startswith("[") or s.startswith("{"):
        try:
            parsed = json.loads(s)
            out: List[str] = []
            if isinstance(parsed, list):
                for it in parsed:
                    if isinstance(it, dict):
                        name = _safe_text(it.get("name"))
                        miles = _safe_text(it.get("miles"))
                        if name and miles:
                            out.append(f"{name} ({miles} miles)")
                        elif name:
                            out.append(name)
                    else:
                        t = _safe_text(it)
                        if t:
                            out.append(t)
                return out
            if isinstance(parsed, dict):
                name = _safe_text(parsed.get("name"))
                miles = _safe_text(parsed.get("miles"))
                if name and miles:
                    return [f"{name} ({miles} miles)"]
                if name:
                    return [name]
        except Exception:
            pass
    if "|" in s:
        return [_safe_text(x) for x in s.split("|") if _safe_text(x)]
    return [s]
