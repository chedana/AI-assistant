"""Red flag detection — scan listing text for tenant-unfriendly signals.

Rule-based regex on all candidates (fast), with structured boolean
fields from OpenRent taking priority over text parsing.

Flags are surfaced as red warning tags on listing cards, separate from
the existing amber penalty_reasons (which track missing data).
"""

import re
from typing import Any, Dict, List, Tuple


# ---------------------------------------------------------------------------
# Pattern definitions — ordered: positive patterns checked first to avoid
# false positives (e.g. "pet friendly" should NOT trigger "no pets").
# ---------------------------------------------------------------------------

_FLAGS: Dict[str, Dict[str, Any]] = {
    "No DSS": {
        "positive": [
            r"(?<!\bno\s)dss\s*(welcome|accepted|ok|okay|considered|friendly)",
            r"(?<!\bno\s)housing\s+benefit\s*(welcome|accepted|ok|okay|considered)",
            r"(?:accept|welcome)s?\s+(?:dss|housing\s+benefit)",
            r"(?<!\bno\s)universal\s+credit\s*(welcome|accepted|ok|okay|considered)",
        ],
        "negative": [
            r"\bno\s+dss\b",
            r"dss\s+not\s+(?:accepted|considered|permitted)",
            r"\bno\s+housing\s+benefit",
            r"housing\s+benefit\s+not\s+(?:accepted|considered)",
            r"(?:cannot|can'?t|unable\s+to)\s+accept\s+(?:dss|housing\s+benefit)",
            r"\bno\s+(?:universal\s+credit|uc)\b",
        ],
        "bool_field": "dss_allowed",
        "bool_negative": False,  # dss_allowed=False → flag
    },
    "No pets": {
        "positive": [
            r"(?<!\bno\s)pets?\s*(welcome|friendly|allowed|accepted|ok|okay|considered|negotiable)",
            r"(?:accept|welcome|allow)s?\s+pets?",
            r"pet[- ]friendly",
        ],
        "negative": [
            r"\bno\s+pets?\b",
            r"pets?\s+not\s+(?:allowed|permitted|accepted|considered)",
            r"(?:cannot|can'?t|unable\s+to)\s+(?:accept|allow|accommodate)\s+pets?",
            r"unfortunately.*pets?\b",
        ],
        "bool_field": "pets_allowed",
        "bool_negative": False,
    },
"No deposit protection": {
        "positive": [
            r"deposit\s+(?:protected|registered|held)\s+(?:with|by|in)\s+(?:tds|dps|mydeposits|tenancy\s+deposit\s+scheme)",
        ],
        "negative": [
            r"deposit\s+(?:not\s+)?protected",
            r"(?:unprotected|no\s+protection)\b.*deposit",
            r"deposit\s+held\s+by\s+(?:landlord|agent)",
            r"\bno\s+(?:tenancy\s+)?deposit\s+(?:scheme|protection)",
        ],
        "bool_field": None,
        "bool_negative": None,
    },
    "Guarantor required": {
        "positive": [],
        "negative": [
            r"\bguarantor\s+(?:required|needed|essential|must|necessary)",
            r"(?:must|need\s+to|required\s+to)\s+(?:provide|have)\s+(?:a\s+)?(?:uk\s+)?guarantor",
        ],
        "bool_field": None,
        "bool_negative": None,
    },
}

# Pre-compile all patterns
for _flag_def in _FLAGS.values():
    _flag_def["_pos_compiled"] = [re.compile(p, re.IGNORECASE) for p in _flag_def["positive"]]
    _flag_def["_neg_compiled"] = [re.compile(p, re.IGNORECASE) for p in _flag_def["negative"]]


def detect_red_flags(row: Dict[str, Any]) -> List[str]:
    """Detect tenant-unfriendly signals in a listing.

    Args:
        row: dict of listing fields (description, features, tenant_prefs, etc.)

    Returns:
        List of human-readable red flag labels, e.g. ["No DSS", "Admin fees"]
    """
    # Build searchable text from description + features
    desc = str(row.get("description") or "")
    feats = row.get("features")
    if isinstance(feats, list):
        feats = " ".join(str(f) for f in feats)
    else:
        feats = str(feats or "")
    text = f"{desc} {feats}".strip()
    text_lower = text.lower()

    if not text_lower:
        return []

    flags: List[str] = []

    for label, defn in _FLAGS.items():
        # 1) Structured boolean field takes priority (OpenRent data)
        bool_field = defn.get("bool_field")
        if bool_field:
            val = row.get(bool_field)
            # Also check inside tenant_prefs dict if present
            if val is None:
                tp = row.get("tenant_prefs")
                if isinstance(tp, dict):
                    val = tp.get(bool_field)
            if val is not None:
                # Normalise string booleans
                if isinstance(val, str):
                    val = val.strip().lower() in ("true", "1", "yes")
                if bool(val) == defn["bool_negative"]:
                    flags.append(label)
                continue  # boolean is authoritative, skip regex

        # 2) Check positive patterns first — if any match, skip this flag
        if any(pat.search(text) for pat in defn["_pos_compiled"]):
            continue

        # 3) Check negative patterns
        if any(pat.search(text) for pat in defn["_neg_compiled"]):
            flags.append(label)

    return flags
