import re
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from core.internal_helpers import _collect_value_candidates, _score_single_intent
from skills.search.extractors import _safe_text, parse_jsonish_items


@dataclass
class LookupResult:
    found: bool
    mode: str
    facts: Dict[str, Any]
    evidence: List[Dict[str, str]]


def extract_snippets(payload: Dict[str, Any]) -> List[Tuple[str, str]]:
    # Reuse Search candidate splitter and keep QA scope on features/description only.
    candidates = _collect_value_candidates(payload or {})
    return [
        (str(c.get("field") or ""), str(c.get("text") or ""))
        for c in candidates
        if str(c.get("field") or "") in {"features", "description"} and _safe_text(c.get("text"))
    ]


_NON_STRUCTURED_FALLBACK_FIELDS = {"description", "features"}
_GENERIC_QUERY_TERMS = {
    "the",
    "a",
    "an",
    "is",
    "are",
    "do",
    "does",
    "did",
    "it",
    "its",
    "this",
    "that",
    "there",
    "here",
    "what",
    "which",
    "where",
    "when",
    "how",
    "far",
    "away",
    "near",
    "have",
    "has",
    "with",
    "from",
    "about",
    "one",
    "ones",
    "listing",
    "result",
    "option",
    "property",
    "flat",
    "apartment",
    "home",
}


def _normalize_token(s: str) -> str:
    t = re.sub(r"[^a-z0-9]+", "", str(s or "").lower())
    if t.endswith("s") and len(t) > 3:
        t = t[:-1]
    return t


def _is_empty_value(v: Any) -> bool:
    if v is None:
        return True
    if isinstance(v, str):
        x = v.strip().lower()
        return x in {"", "none", "null", "n/a", "na", "unknown", "not provided", "ask agent"}
    if isinstance(v, list):
        return len([x for x in v if not _is_empty_value(x)]) == 0
    return False


def _flatten_structured_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for k, v in (payload or {}).items():
        key = str(k or "").strip()
        if not key:
            continue
        if key in _NON_STRUCTURED_FALLBACK_FIELDS:
            continue
        if isinstance(v, (dict, tuple, set)):
            continue
        if _is_empty_value(v):
            continue
        out[key] = v
    return out


def _terms_from_signals(signals: Dict[str, Any], raw_question: str = "") -> List[str]:
    topic_pref = (signals or {}).get("topic_preferences") or {}
    hard = (signals or {}).get("hard_constraints") or {}
    terms: List[str] = []
    terms.extend([str(x).strip().lower() for x in (topic_pref.get("transit_terms") or []) if str(x).strip()])
    terms.extend([str(x).strip().lower() for x in (topic_pref.get("school_terms") or []) if str(x).strip()])
    terms.extend([str(x).strip().lower() for x in ((signals or {}).get("general_semantic") or []) if str(x).strip()])
    terms.extend([str(x).strip().lower() for x in ((signals or {}).get("location_intent") or []) if str(x).strip()])
    for k in ("furnish_type", "let_type"):
        v = hard.get(k)
        if v:
            terms.append(str(v).strip().lower())
    if raw_question:
        for x in re.findall(r"[a-zA-Z0-9\-\+']{3,}", str(raw_question)):
            xl = x.lower()
            if xl in _GENERIC_QUERY_TERMS:
                continue
            terms.append(xl)
    dedup = []
    seen = set()
    for t in terms:
        n = _normalize_token(t)
        if not n or n in seen:
            continue
        seen.add(n)
        dedup.append(t)
    return dedup[:20]


def semantic_terms_from_signals(signals: Dict[str, Any], raw_question: str = "") -> List[str]:
    terms = [x.lower().strip() for x in _terms_from_signals(signals, raw_question=raw_question) if _safe_text(x)]
    terms = [x for x in terms if len(_normalize_token(x)) >= 3]
    # Keep query-order while removing normalized duplicates.
    out: List[str] = []
    seen = set()
    for x in terms:
        nx = _normalize_token(x)
        if not nx or nx in seen:
            continue
        seen.add(nx)
        out.append(x)
    return out


def _structured_key_hints_from_signals(signals: Dict[str, Any]) -> List[str]:
    hard = (signals or {}).get("hard_constraints") or {}
    topic_pref = (signals or {}).get("topic_preferences") or {}
    keys: List[str] = []

    # Map Search hard constraints to listing payload fields.
    if hard.get("max_rent_pcm") is not None:
        keys.append("price_pcm")
    if hard.get("available_from") is not None:
        keys.append("available_from")
    if hard.get("furnish_type"):
        keys.append("furnish_type")
    if hard.get("let_type"):
        keys.append("let_type")
    if hard.get("min_tenancy_months") is not None:
        keys.extend(["min_tenancy_months", "min_tenancy"])
    if hard.get("min_size_sqm") is not None:
        keys.extend(["size_sqm", "size_sqft"])
    if hard.get("layout_options"):
        keys.extend(["bedrooms", "bathrooms", "property_type", "layout_tag"])

    if topic_pref.get("school_terms"):
        keys.append("schools")
    if topic_pref.get("transit_terms"):
        keys.extend(["stations", "nearest_station", "distance_to_station_m"])

    if (signals or {}).get("location_intent"):
        keys.extend(["address", "postcode"])

    out = []
    seen = set()
    for k in keys:
        nk = _normalize_token(k)
        if nk in seen:
            continue
        seen.add(nk)
        out.append(k)
    return out


def _match_structured_keys(signals: Dict[str, Any], fields: Dict[str, Any], raw_question: str = "") -> List[str]:
    if not fields:
        return []
    terms = [_normalize_token(x) for x in _terms_from_signals(signals, raw_question=raw_question) if _normalize_token(x)]
    terms = list(dict.fromkeys([t for t in terms if t]))

    norm_key_map = {_normalize_token(k): k for k in fields.keys()}
    matched: List[str] = []

    # 1) Hints derived from Search signals.
    for hk in _structured_key_hints_from_signals(signals):
        if hk in fields and hk not in matched:
            matched.append(hk)

    # 2) Token vs key direct match/contains.
    for t in terms:
        for nk, raw_key in norm_key_map.items():
            if nk == t or t in nk or nk in t:
                if raw_key not in matched:
                    matched.append(raw_key)

    return matched


def structured_lookup(signals: Dict[str, Any], payload: Dict[str, Any], raw_question: str = "") -> LookupResult:
    fields = _flatten_structured_payload(payload or {})
    matched_keys = _match_structured_keys(signals, fields, raw_question=raw_question)
    if not matched_keys:
        return LookupResult(False, "structured", {}, [])

    facts: Dict[str, Any] = {}
    evidence: List[Dict[str, str]] = []
    for key in matched_keys:
        val = fields.get(key)
        if _is_empty_value(val):
            continue
        if isinstance(val, list):
            items = parse_jsonish_items(val)
            if not items:
                continue
            facts[key] = items
            for it in items:
                evidence.append({"field": key, "text": it})
        elif isinstance(val, str):
            items = parse_jsonish_items(val)
            if len(items) > 1:
                facts[key] = items
                for it in items:
                    evidence.append({"field": key, "text": it})
            else:
                txt = _safe_text(val)
                if not txt:
                    continue
                facts[key] = txt
                evidence.append({"field": key, "text": txt})
        else:
            facts[key] = val
            evidence.append({"field": key, "text": str(val)})

    if not facts:
        return LookupResult(False, "structured", {}, [])
    return LookupResult(True, "structured", facts, evidence)


def semantic_lookup(signals: Dict[str, Any], payload: Dict[str, Any], raw_question: str = "") -> LookupResult:
    snippets = extract_snippets(payload)
    if not snippets:
        return LookupResult(False, "semantic", {}, [])

    terms = [x.lower() for x in _terms_from_signals(signals, raw_question=raw_question) if _safe_text(x)]
    terms = list(dict.fromkeys([t for t in terms if len(_normalize_token(t)) >= 3]))
    if not terms:
        return LookupResult(False, "semantic", {}, [])

    scored: List[Tuple[int, str, str]] = []
    for field, text in snippets:
        text_l = text.lower()
        score = sum(1 for t in terms if t in text_l)
        if score > 0:
            scored.append((score, field, text))
    scored.sort(key=lambda x: x[0], reverse=True)
    if not scored:
        return LookupResult(False, "semantic", {}, [])

    top = scored
    evidence = [{"field": f, "text": t} for _, f, t in top]
    facts = {
        "matched_terms": terms,
        "matched_count": len(top),
    }
    return LookupResult(True, "semantic", facts, evidence)


def semantic_vector_lookup(
    signals: Dict[str, Any],
    payload: Dict[str, Any],
    embedder,
    raw_question: str = "",
    high_threshold: float = 0.75,
    low_threshold: float = 0.60,
) -> Dict[str, Any]:
    candidates = [
        {"field": f, "text": t}
        for f, t in extract_snippets(payload)
        if f in {"features", "description"} and _safe_text(t)
    ]
    if not candidates:
        return {
            "found": False,
            "summary_label": "not_found",
            "terms": [],
            "term_matches": [],
            "evidence": [],
        }

    terms = semantic_terms_from_signals(signals, raw_question=raw_question)
    if not terms:
        return {
            "found": False,
            "summary_label": "no_terms",
            "terms": [],
            "term_matches": [],
            "evidence": [],
        }

    sim_cache: Dict[str, Any] = {}
    term_matches: List[Dict[str, Any]] = []
    for term in terms:
        score, _detail, top_struct = _score_single_intent(
            term,
            candidates,
            top_k=1,
            embedder=embedder,
            sim_cache=sim_cache,
        )
        best = top_struct[0] if top_struct else {}
        best_score = float(score)
        best_field = str(best.get("field") or "")
        best_text = str(best.get("text") or "")
        if best_score >= high_threshold:
            label = "confirmed"
        elif best_score >= low_threshold:
            label = "uncertain"
        else:
            label = "not_found"
        term_matches.append(
            {
                "term": term,
                "score": round(best_score, 4),
                "label": label,
                "field": best_field,
                "text": best_text,
            }
        )

    labels = [str(x.get("label") or "not_found") for x in term_matches]
    if labels and all(x == "confirmed" for x in labels):
        summary_label = "confirmed"
    elif labels and all(x != "not_found" for x in labels):
        summary_label = "uncertain"
    else:
        summary_label = "not_found"

    evidence = [
        {
            "field": str(x.get("field") or ""),
            "text": str(x.get("text") or ""),
            "term": str(x.get("term") or ""),
            "score": str(x.get("score")),
            "label": str(x.get("label") or ""),
        }
        for x in term_matches
    ]
    return {
        "found": bool(term_matches),
        "summary_label": summary_label,
        "terms": terms,
        "term_matches": term_matches,
        "evidence": evidence,
    }
