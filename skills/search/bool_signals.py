"""Boolean signal resolution from listing data.

Resolves True/False/None for boolean rental attributes by:
1. Checking explicit boolean fields in the listing payload
2. Scanning features and description text via regex
3. Returning None when no evidence is found
"""

import re
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Signal definitions
# ---------------------------------------------------------------------------

BOOL_SIGNAL_DEFS: Dict[str, Dict[str, Any]] = {
    "pets_allowed": {
        "field": "pets_allowed",
        "positive_patterns": [
            r"\bpets?\s*(?:allowed|considered|friendly|welcome|accepted)\b",
            r"\bpet[- ]?friendly\b",
        ],
        "negative_patterns": [
            r"\bno\s*pets?\b",
            r"\bpets?\s*not\s*(?:allowed|accepted|permitted)\b",
        ],
    },
    "garden": {
        "field": "garden",
        "positive_patterns": [
            r"\b(?:private\s+)?garden\b",
            r"\brear\s+garden\b",
            r"\bcommunal\s+garden\b",
        ],
        "negative_patterns": [r"\bno\s+garden\b"],
    },
    "parking": {
        "field": "parking",
        "positive_patterns": [
            r"\b(?:off[- ]?street\s+)?parking\b",
            r"\bgarage\b",
            r"\bdriveway\b",
        ],
        "negative_patterns": [r"\bno\s+parking\b"],
    },
    "bills_included": {
        "field": "bills_included",
        "positive_patterns": [
            r"\bbills?\s*incl(?:uded)?\b",
            r"\ball\s*bills?\b",
        ],
        "negative_patterns": [
            r"\bbills?\s*(?:not\s+included|excluded|extra|separate)\b",
            r"\bexcluding\s+bills?\b",
        ],
    },
    "student_friendly": {
        "field": "student_friendly",
        "positive_patterns": [
            r"\bstudents?\s*(?:welcome|friendly|accepted|can\s+enquire)\b",
            r"\bstudent[- ]?friendly\b",
        ],
        "negative_patterns": [
            r"\bno\s+students?\b",
            r"\bstudents?\s*not\s*(?:accepted|allowed)\b",
        ],
    },
    "families_allowed": {
        "field": "families_allowed",
        "positive_patterns": [
            r"\bfamil(?:y|ies)\s*(?:welcome|friendly|accepted|allowed)\b",
            r"\bfamily[- ]?friendly\b",
        ],
        "negative_patterns": [
            r"\bno\s+famil(?:y|ies)\b",
            r"\bfamil(?:y|ies)\s*not\s*(?:accepted|allowed)\b",
        ],
    },
    "smokers_allowed": {
        "field": "smokers_allowed",
        "positive_patterns": [
            r"\bsmok(?:ing|ers?)\s*(?:allowed|permitted|ok)\b",
        ],
        "negative_patterns": [
            r"\bno\s+smok(?:ing|ers?)\b",
            r"\bnon[- ]?smok(?:ing|ers?)\b",
        ],
    },
    "dss_accepted": {
        "field": "dss_income_accepted",
        "positive_patterns": [
            r"\bdss\s*(?:accepted|welcome|ok|considered)\b",
            r"\bhousing\s*benefit\s*(?:accepted|welcome)\b",
            r"\buniversal\s*credit\s*(?:accepted|welcome)\b",
        ],
        "negative_patterns": [
            r"\bno\s+dss\b",
            r"\bdss\s*not\s*(?:accepted|allowed)\b",
            r"\bhousing\s*benefit\s*not\b",
        ],
    },
}

# Synthetic text phrases emitted when a signal is True.
_SYNTHETIC_PHRASES: Dict[str, List[str]] = {
    "pets_allowed": ["pets allowed", "pet friendly"],
    "garden": ["has garden", "garden"],
    "parking": ["parking available", "off-street parking"],
    "bills_included": ["bills included", "all bills included"],
    "student_friendly": ["student friendly"],
    "families_allowed": ["family friendly", "families welcome"],
    "smokers_allowed": ["smoking allowed"],
    "dss_accepted": ["DSS accepted", "housing benefit accepted"],
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_searchable_text(listing: dict) -> str:
    """Concatenate features and description into a single searchable string."""
    parts: List[str] = []

    features = listing.get("features")
    if isinstance(features, list):
        parts.extend(str(f) for f in features if f)
    elif isinstance(features, str) and features:
        parts.append(features)

    description = listing.get("description")
    if isinstance(description, str) and description:
        parts.append(description)

    return " ".join(parts)


def _coerce_bool(value: Any) -> Optional[bool]:
    """Coerce a payload value to bool if it looks boolean-ish."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        import math
        if math.isnan(value):
            return None  # NaN means unknown, not True
        return bool(value)
    if isinstance(value, str):
        low = value.strip().lower()
        if low in {"true", "yes", "1", "y"}:
            return True
        if low in {"false", "no", "0", "n", "nan"}:
            return False if low != "nan" else None
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def resolve_bool_signal(signal_name: str, listing: dict) -> Optional[bool]:
    """Resolve a boolean signal from listing data.

    1. Check explicit field in payload -> return bool
    2. Scan features + description text -> return bool
    3. Return None if unknown
    """
    defn = BOOL_SIGNAL_DEFS.get(signal_name)
    if defn is None:
        return None

    # Step 1: explicit field
    field_name = defn.get("field", "")
    if field_name:
        payload = listing.get("payload", listing)
        raw = payload.get(field_name)
        if raw is None and payload is not listing:
            raw = listing.get(field_name)
        if raw is not None:
            coerced = _coerce_bool(raw)
            if coerced is not None:
                return coerced

    # Step 2: text scan
    text = _get_searchable_text(listing.get("payload", listing))
    if not text:
        text = _get_searchable_text(listing)
    if not text:
        return None

    text_lower = text.lower()

    # Check negative patterns first (more specific, e.g. "no pets")
    for pat in defn.get("negative_patterns", []):
        if re.search(pat, text_lower, re.IGNORECASE):
            return False

    for pat in defn.get("positive_patterns", []):
        if re.search(pat, text_lower, re.IGNORECASE):
            return True

    # Step 3: unknown
    return None


def resolve_all_bool_signals(listing: dict) -> Dict[str, Optional[bool]]:
    """Resolve all boolean signals for a listing.

    Returns {signal_name: True/False/None}.
    """
    return {name: resolve_bool_signal(name, listing) for name in BOOL_SIGNAL_DEFS}


def synthetic_text_from_bools(listing: dict) -> List[str]:
    """Generate synthetic text candidates from resolved boolean signals.

    Only emits phrases for signals that resolve to True.
    Used to inject into semantic matching candidates.
    """
    resolved = resolve_all_bool_signals(listing)
    phrases: List[str] = []
    for name, value in resolved.items():
        if value is True:
            phrases.extend(_SYNTHETIC_PHRASES.get(name, []))
    return phrases
