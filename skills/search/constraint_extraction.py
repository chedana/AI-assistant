"""Rule-based constraint extraction, repair, and normalization of LLM output."""

import ast
import copy
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from core.chatbot_config import (
    LET_TYPE_RULES,
    TENANCY_MONTH_PATTERNS,
    TENANCY_YEAR_FIXED_RULES,
    TENANCY_YEAR_NUMERIC_RULES,
    BEDROOM_EQ_PATTERNS,
    BATHROOM_EQ_PATTERNS,
    BED_BATH_COMPACT_PATTERNS,
    NUM_WORDS,
    FURNISH_QUERY_PATTERNS,
    PROPERTY_TYPE_QUERY_PATTERNS,
    PROPERTY_TYPE_HOUSE_LIKE,
    PROPERTY_TYPE_FLAT_LIKE,
    PROPERTY_TYPE_SPECIAL_OR_UNKNOWN,
    RENT_PCM_PATTERNS,
    RENT_PCW_PATTERNS,
    AVAILABLE_FROM_PREFIX_PATTERNS,
    AVAILABLE_FROM_BARE_PATTERNS,
)
from skills.search.text_utils import (
    _norm_furnish_value,
    _norm_property_type_value,
    _safe_text,
    _truthy_env,
)


def _parse_user_date_uk_first(value: Any) -> Optional[str]:
    s = _safe_text(value)
    if not s:
        return None
    s = s.strip()

    m_iso = re.fullmatch(r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})", s)
    if m_iso:
        y, mth, d = int(m_iso.group(1)), int(m_iso.group(2)), int(m_iso.group(3))
        try:
            return datetime(y, mth, d).date().isoformat()
        except Exception:
            return None

    m_num = re.fullmatch(r"(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})", s)
    if m_num:
        p1, p2, y = int(m_num.group(1)), int(m_num.group(2)), int(m_num.group(3))
        if y < 100:
            y += 2000
        # UK first (DD/MM), but if MM/DD is obvious (2nd part > 12), switch.
        if p2 > 12 and p1 <= 12:
            month, day = p1, p2
        else:
            day, month = p1, p2
        try:
            return datetime(y, month, day).date().isoformat()
        except Exception:
            return None

    dt = pd.to_datetime(s, errors="coerce", dayfirst=True)
    if pd.notna(dt):
        return dt.date().isoformat()
    return None

def _infer_available_from_from_text(text: Any) -> Optional[str]:
    src = _safe_text(text)
    if not src:
        return None
    for pattern in AVAILABLE_FROM_PREFIX_PATTERNS:
        m = pattern.search(src)
        if not m:
            continue
        parsed = _parse_user_date_uk_first(m.group(1))
        if parsed:
            return parsed
    for pattern in AVAILABLE_FROM_BARE_PATTERNS:
        m = pattern.search(src)
        if not m:
            continue
        parsed = _parse_user_date_uk_first(m.group(1))
        if parsed:
            return parsed
    return None

def _infer_numeric_eq_from_patterns(text: Any, patterns: List[re.Pattern]) -> Optional[int]:
    src = _safe_text(text).lower()
    if not src:
        return None
    for w, d in NUM_WORDS.items():
        src = re.sub(rf"\b{w}\b", d, src)
    for pattern in patterns:
        m = pattern.search(src)
        if not m:
            continue
        try:
            v = int(float(m.group(1)))
            if v >= 0:
                return v
        except Exception:
            continue
    return None

def _infer_float_eq_from_patterns(text: Any, patterns: List[re.Pattern]) -> Optional[float]:
    src = _safe_text(text).lower()
    if not src:
        return None
    for w, d in NUM_WORDS.items():
        src = re.sub(rf"\b{w}\b", d, src)
    for pattern in patterns:
        m = pattern.search(src)
        if not m:
            continue
        try:
            v = float(m.group(1))
            if v >= 0:
                return v
        except Exception:
            continue
    return None

def _infer_bed_bath_compact_from_query(text: Any) -> Tuple[Optional[int], Optional[float]]:
    src = _safe_text(text).lower()
    if not src:
        return None, None
    for w, d in NUM_WORDS.items():
        src = re.sub(rf"\b{w}\b", d, src)
    for pattern in BED_BATH_COMPACT_PATTERNS:
        m = pattern.search(src)
        if not m:
            continue
        try:
            bed = int(float(m.group(1)))
            bath = float(m.group(2))
            if bed >= 0 and bath >= 0:
                return bed, bath
        except Exception:
            continue
    return None, None

def _infer_furnish_type_from_query(text: Any) -> Optional[str]:
    src = _safe_text(text).lower()
    if not src:
        return None
    # Ambiguous request: do not force hard furnish filter.
    if "furnished or unfurnished" in src or ("landlord" in src and "flexible" in src):
        return None
    for pattern, mapped in FURNISH_QUERY_PATTERNS:
        if pattern.search(src):
            return mapped
    return None

def _infer_property_type_from_query(text: Any) -> Optional[str]:
    src = _safe_text(text).lower()
    if not src:
        return None
    for pattern, mapped in PROPERTY_TYPE_QUERY_PATTERNS:
        if pattern.search(src):
            return mapped
    # Fallback: tolerate misconfigured pattern tables and catch core intent words.
    if re.search(r"\b(flat|flats|apartment|apartments|apt|apts)\b", src):
        return "flat"
    if re.search(
        r"\b(house|detached|semi[- ]?detached|town\s*house|terraced|mews|cottage|bungalow)\b",
        src,
    ):
        return "house"
    return None


def _normalize_layout_options(raw: Any) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    seen = set()
    for item in (raw or []):
        if not isinstance(item, dict):
            continue
        bed = item.get("bedrooms")
        bath = item.get("bathrooms")
        ptype = item.get("property_type")
        tag = _safe_text(item.get("layout_tag")).lower()
        budget = item.get("max_rent_pcm")
        bed_n: Optional[int] = None
        bath_n: Optional[float] = None
        ptype_n: Optional[str] = None
        tag_n: Optional[str] = None
        budget_n: Optional[float] = None
        if bed is not None:
            try:
                bed_n = int(float(bed))
            except Exception:
                bed_n = None
        if bath is not None:
            try:
                bath_n = float(bath)
            except Exception:
                bath_n = None
        pnorm = _norm_property_type_value(ptype)
        if pnorm in {"flat", "house", "other"}:
            ptype_n = pnorm
        if tag in {"studio"}:
            tag_n = tag
        if budget is not None:
            try:
                budget_n = float(budget)
                if budget_n <= 0:
                    budget_n = None
            except Exception:
                budget_n = None
        key = (bed_n, bath_n, ptype_n, tag_n, budget_n)
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "bedrooms": bed_n,
                "bathrooms": bath_n,
                "property_type": ptype_n,
                "layout_tag": tag_n,
                "max_rent_pcm": budget_n,
            }
        )
    return out


def _extract_layout_options_candidates(text: Any) -> List[Dict[str, Any]]:
    src = _safe_text(text).lower()
    if not src:
        return []
    for w, d in NUM_WORDS.items():
        src = re.sub(rf"\b{w}\b", d, src)

    options: List[Dict[str, Any]] = []
    used_spans: List[Tuple[int, int]] = []

    budget_patterns = [
        re.compile(r"(?:under|below|max(?:imum)?|up\s*to|within|at\s*most|budget)\s*£?\s*([0-9][0-9,]*(?:\.\d+)?)", re.I),
        re.compile(r"£\s*([0-9][0-9,]*(?:\.\d+)?)\s*(?:pcm|per\s*month|p/?m|pm)\b", re.I),
        re.compile(r"\b([0-9][0-9,]*(?:\.\d+)?)\s*(?:pcm|per\s*month|p/?m|pm)\b", re.I),
    ]

    clause_boundaries: List[Tuple[int, int]] = []
    cut_points = [0]
    for sep in re.finditer(r"\b(?:and|or)\b|[,;]", src, flags=re.I):
        cut_points.append(sep.start())
        cut_points.append(sep.end())
    cut_points.append(len(src))
    cut_points = sorted(set(x for x in cut_points if 0 <= x <= len(src)))
    for i in range(0, len(cut_points) - 1, 2):
        a = cut_points[i]
        b = cut_points[i + 1]
        if a < b:
            clause_boundaries.append((a, b))
    if not clause_boundaries:
        clause_boundaries = [(0, len(src))]

    def _clause_index(pos: int) -> int:
        for i, (a, b) in enumerate(clause_boundaries):
            if a <= pos < b:
                return i
        return max(0, len(clause_boundaries) - 1)

    budget_hits: List[Tuple[int, int, float]] = []
    for pat in budget_patterns:
        for m in pat.finditer(src):
            try:
                v = float(str(m.group(1)).replace(",", ""))
                if v > 0:
                    budget_hits.append((m.start(), m.end(), v))
            except Exception:
                continue

    def _nearest_budget(start: int, end: int, max_gap: int = 48) -> Optional[float]:
        if not budget_hits:
            return None
        cid = _clause_index(start)
        local_hits = [(bs, be, v) for bs, be, v in budget_hits if _clause_index(bs) == cid]
        hits = local_hits if local_hits else budget_hits
        # Prefer explicit price mention immediately after the layout phrase.
        after = [(bs - end, v) for bs, be, v in hits if bs >= end and (bs - end) <= max_gap]
        if after:
            after.sort(key=lambda x: x[0])
            return float(after[0][1])

        # Then allow price mention immediately before the layout phrase.
        before = [(start - be, v) for bs, be, v in hits if be <= start and (start - be) <= max_gap]
        if before:
            before.sort(key=lambda x: x[0])
            return float(before[0][1])

        # Fallback to nearest absolute distance when still close enough.
        nearest: List[Tuple[int, float]] = []
        for bs, be, v in hits:
            if be <= start:
                d = start - be
            elif bs >= end:
                d = bs - end
            else:
                d = 0
            if d <= max_gap:
                nearest.append((d, v))
        if nearest:
            nearest.sort(key=lambda x: x[0])
            return float(nearest[0][1])
        return None

    def _local_budget(start: int, end: int) -> Optional[float]:
        return _nearest_budget(start, end)

    for m in re.finditer(
        r"\b(\d+(?:\.\d+)?)\s*(?:bed(?:room)?s?|bd|br|b)\s*[/,-]?\s*(\d+(?:\.\d+)?)\s*(?:bath(?:room)?s?|ba|b)\b",
        src,
        flags=re.I,
    ):
        try:
            bed = int(float(m.group(1)))
            bath = float(m.group(2))
            options.append(
                {
                    "bedrooms": bed,
                    "bathrooms": bath,
                    "property_type": None,
                    "max_rent_pcm": _local_budget(m.start(), m.end()),
                }
            )
            used_spans.append((m.start(), m.end()))
        except Exception:
            continue

    mask = [True] * len(src)
    for a, b in used_spans:
        for i in range(max(0, a), min(len(src), b)):
            mask[i] = False
    remain = "".join(ch if mask[i] else " " for i, ch in enumerate(src))

    for m in re.finditer(r"\b(\d+(?:\.\d+)?)\s*[- ]?\s*(?:bed(?:room)?s?|bd|br|b)\b", remain, flags=re.I):
        try:
            bed = int(float(m.group(1)))
            options.append(
                {
                    "bedrooms": bed,
                    "bathrooms": None,
                    "property_type": None,
                    "max_rent_pcm": _local_budget(m.start(), m.end()),
                }
            )
        except Exception:
            continue

    for m in re.finditer(r"\b(\d+(?:\.\d+)?)\s*[- ]?\s*(?:bath(?:room)?s?|ba)\b", remain, flags=re.I):
        try:
            bath = float(m.group(1))
            options.append(
                {
                    "bedrooms": None,
                    "bathrooms": bath,
                    "property_type": None,
                    "max_rent_pcm": _local_budget(m.start(), m.end()),
                }
            )
        except Exception:
            continue

    for _ in re.finditer(r"\bstudio\b", src, flags=re.I):
        options.append(
            {
                "bedrooms": None,
                "bathrooms": None,
                "property_type": "flat",
                "layout_tag": "studio",
                "max_rent_pcm": _local_budget(_.start(), _.end()),
            }
        )

    inferred_ptype = _infer_property_type_from_query(src)
    has_explicit_nonstudio_ptype = bool(
        re.search(
            r"\b(flat|flats|apartment|apartments|apt|apts|house|detached|semi[- ]?detached|town\s*house|terraced|mews|cottage|bungalow)\b",
            src,
        )
    )
    if inferred_ptype is not None:
        # If layout options already exist, treat explicit property type as a shared
        # constraint on those options (instead of creating a new OR branch).
        if options and has_explicit_nonstudio_ptype:
            for it in options:
                if not isinstance(it, dict):
                    continue
                if _safe_text(it.get("layout_tag")).lower() == "studio":
                    continue
                if not _safe_text(it.get("property_type")):
                    it["property_type"] = inferred_ptype
        elif not options:
            options.append(
                {
                    "bedrooms": None,
                    "bathrooms": None,
                    "property_type": inferred_ptype,
                    "layout_tag": None,
                    "max_rent_pcm": None,
                }
            )

    normalized = _normalize_layout_options(options)
    return normalized


def _infer_layout_options_from_query(text: Any) -> List[Dict[str, Any]]:
    normalized = _extract_layout_options_candidates(text)
    return normalized if len(normalized) >= 1 else []


def _infer_layout_remove_ops_from_query(text: Any) -> Dict[str, Any]:
    src = _safe_text(text).lower()
    if not src:
        return {"remove_layout_options": []}

    has_remove_verb = bool(re.search(r"\b(?:remove|drop|delete|clear)\b", src))
    remove_layout_options: List[Dict[str, Any]] = []
    if has_remove_verb:
        remove_layout_options = _extract_layout_options_candidates(src)
        # Delete selectors should match layout identity, not budget amounts.
        for it in remove_layout_options:
            if isinstance(it, dict):
                it["max_rent_pcm"] = None
    return {
        "remove_layout_options": _normalize_layout_options(remove_layout_options),
    }


def _infer_replace_all_from_query(text: Any) -> bool:
    src = _safe_text(text).lower()
    if not src:
        return False
    patterns = [
        r"\bstart over\b",
        r"\bnew search\b",
        r"\bignore (the )?(previous|last)\b",
        r"\breset (the )?(constraints|filters|search)\b",
        r"\bfrom scratch\b",
    ]
    return any(re.search(p, src) for p in patterns)


def _infer_append_mode_from_query(text: Any) -> bool:
    src = _safe_text(text).lower()
    if not src:
        return False
    patterns = [
        r"\balso\b",
        r"\bin addition\b",
        r"\bas well\b",
        r"\bplus\b",
        r"\balong with\b",
    ]
    return any(re.search(p, src) for p in patterns)


def _infer_replace_mode_from_query(text: Any) -> bool:
    src = _safe_text(text).lower()
    if not src:
        return False
    patterns = [
        r"\binstead\b",
        r"\bswitch to\b",
        r"\bchange to\b",
        r"\breplace\b",
    ]
    return any(re.search(p, src) for p in patterns)


def _infer_clear_location_from_query(text: Any) -> bool:
    src = _safe_text(text).lower()
    if not src:
        return False
    patterns = [
        r"\bany location\b",
        r"\bno location preference\b",
        r"\bremove location\b",
        r"\bdon'?t care (about )?location\b",
    ]
    return any(re.search(p, src) for p in patterns)


def _infer_max_rent_pcm_from_query(text: Any) -> Optional[float]:
    src = _safe_text(text)
    if not src:
        return None

    def _to_amount(raw: str) -> Optional[float]:
        try:
            val = float(str(raw).replace(",", ""))
            return val if val > 0 else None
        except Exception:
            return None

    for pattern in RENT_PCW_PATTERNS:
        m = pattern.search(src)
        if not m:
            continue
        amt = _to_amount(m.group(1))
        if amt is not None:
            return amt * 52.0 / 12.0

    for pattern in RENT_PCM_PATTERNS:
        m = pattern.search(src)
        if not m:
            continue
        amt = _to_amount(m.group(1))
        if amt is not None:
            return amt

    return None

def _infer_let_type_from_text(text: Any) -> Optional[str]:
    src = _safe_text(text).lower()
    if not src:
        return None
    for pattern, mapped in LET_TYPE_RULES:
        if pattern.search(src):
            return mapped
    return None

def _infer_min_tenancy_months_from_text(text: Any) -> Optional[float]:
    src = _safe_text(text).lower()
    if not src:
        return None

    for pattern in TENANCY_MONTH_PATTERNS:
        m = pattern.search(src)
        if not m:
            continue
        try:
            months = float(m.group(1))
            if months > 0:
                return months
        except Exception:
            continue

    for pattern, months in TENANCY_YEAR_FIXED_RULES:
        if pattern.search(src):
            return months

    for pattern in TENANCY_YEAR_NUMERIC_RULES:
        m = pattern.search(src)
        if not m:
            continue
        try:
            years = float(m.group(1))
            months = years * 12.0
            if months > 0:
                return months
        except Exception:
            continue
    return None

def repair_extracted_constraints(extracted: Dict[str, Any], user_text: str) -> Dict[str, Any]:
    out = dict(extracted or {})
    inferred_from_query = _infer_let_type_from_text(user_text)
    inferred_tenancy_months = _infer_min_tenancy_months_from_text(user_text)
    inferred_available_from = _infer_available_from_from_text(user_text)
    inferred_furnish = _infer_furnish_type_from_query(user_text)
    inferred_max_rent_pcm = _infer_max_rent_pcm_from_query(user_text)
    inferred_layout_options = _infer_layout_options_from_query(user_text)
    inferred_layout_remove_ops = _infer_layout_remove_ops_from_query(user_text)
    inferred_replace_all = _infer_replace_all_from_query(user_text)
    inferred_append = _infer_append_mode_from_query(user_text)
    inferred_replace = _infer_replace_mode_from_query(user_text)
    inferred_clear_location = _infer_clear_location_from_query(user_text)
    remove_opts = inferred_layout_remove_ops.get("remove_layout_options") or []

    # Rescue common slot-mapping error:
    # available_from_op gets "short/long term" text by mistake.
    inferred_from_avail_op = _infer_let_type_from_text(out.get("available_from_op"))
    if inferred_from_avail_op:
        out["available_from_op"] = None
        if not _safe_text(out.get("let_type")):
            out["let_type"] = inferred_from_avail_op

    # Query text has highest confidence for these explicit phrases.
    if inferred_from_query:
        out["let_type"] = inferred_from_query
    let_type_norm = _safe_text(out.get("let_type")).lower().replace("_", " ").replace("-", " ")
    let_type_norm = re.sub(r"\s+", " ", let_type_norm).strip()
    if let_type_norm not in {"short term", "long term"}:
        out["let_type"] = None

    # Keep min_tenancy_months only when explicit month/year evidence exists in query text.
    # This prevents model drift like "short term" -> min_tenancy_months = 1.
    if inferred_tenancy_months is not None:
        out["min_tenancy_months"] = inferred_tenancy_months
    else:
        out["min_tenancy_months"] = None

    try:
        if out.get("min_tenancy_months") is not None and float(out["min_tenancy_months"]) <= 0:
            out["min_tenancy_months"] = None
    except Exception:
        out["min_tenancy_months"] = None

    if inferred_available_from:
        out["available_from"] = inferred_available_from
    else:
        out["available_from"] = _parse_user_date_uk_first(out.get("available_from"))

    if inferred_furnish is not None:
        out["furnish_type"] = inferred_furnish

    if inferred_max_rent_pcm is not None:
        out["max_rent_pcm"] = inferred_max_rent_pcm

    if len(inferred_layout_options) >= 1 and not remove_opts:
        out["layout_options"] = inferred_layout_options

    if remove_opts:
        out["_remove_layout_options"] = remove_opts

    llm_scope = _safe_text(out.get("update_scope")).lower()
    llm_replace_all = out.get("_replace_all_constraints")
    if not isinstance(llm_replace_all, bool):
        llm_replace_all = (llm_scope == "replace_all")
    if isinstance(llm_replace_all, bool):
        out["_replace_all_constraints"] = bool(llm_replace_all or inferred_replace_all)
    else:
        out["_replace_all_constraints"] = bool(inferred_replace_all)

    llm_loc_mode = _safe_text(out.get("_location_update_mode")).lower()
    if llm_loc_mode not in {"keep", "replace", "append"}:
        llm_loc_mode = _safe_text(out.get("location_update_mode")).lower()
    if inferred_append and not inferred_replace:
        out["_location_update_mode"] = "append"
    elif inferred_replace:
        out["_location_update_mode"] = "replace"
    elif llm_loc_mode in {"keep", "replace", "append"}:
        out["_location_update_mode"] = llm_loc_mode
    else:
        out["_location_update_mode"] = "replace"
    out["_clear_location_keywords"] = bool(inferred_clear_location)

    llm_layout_mode = _safe_text(out.get("_layout_update_mode")).lower()
    if llm_layout_mode not in {"replace", "append"}:
        llm_layout_mode = _safe_text(out.get("layout_update_mode")).lower()
    if inferred_append and not inferred_replace:
        out["_layout_update_mode"] = "append"
    elif inferred_replace:
        out["_layout_update_mode"] = "replace"
    elif llm_layout_mode in {"replace", "append"}:
        out["_layout_update_mode"] = llm_layout_mode
    else:
        out["_layout_update_mode"] = "replace"

    # Deprecated field: always ignore op and use latest move-in semantics.
    out["available_from_op"] = None

    return out
def _extract_json_obj(txt: str) -> dict:
    s = str(txt or "").strip()
    if not s:
        return {}

    # Prefer content outside reasoning blocks when available.
    s_no_think = re.sub(r"<think>.*?</think>", " ", s, flags=re.I | re.S).strip()
    if s_no_think:
        s = s_no_think

    # Unwrap fenced code blocks if present.
    fence = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", s, flags=re.I)
    candidates: List[str] = []
    if fence:
        candidates.append(fence.group(1).strip())

    # Collect balanced JSON object candidates from left to right.
    start_positions = [i for i, ch in enumerate(s) if ch == "{"]
    for st in start_positions[:20]:
        depth = 0
        for i in range(st, len(s)):
            ch = s[i]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    seg = s[st : i + 1].strip()
                    if seg:
                        candidates.append(seg)
                    break

    # Last resort: keep legacy greedy capture for compatibility.
    m = re.search(r"\{.*\}", s, flags=re.S)
    if m:
        candidates.append(m.group(0).strip())

    seen = set()
    deduped: List[str] = []
    for c in candidates:
        if c in seen:
            continue
        seen.add(c)
        deduped.append(c)

    for c in deduped:
        # 1) strict JSON
        try:
            obj = json.loads(c)
            if isinstance(obj, dict):
                return obj
        except Exception:
            pass

        # 2) tolerant JSON: remove trailing commas
        try:
            c2 = re.sub(r",\s*([}\]])", r"\1", c)
            obj = json.loads(c2)
            if isinstance(obj, dict):
                return obj
        except Exception:
            pass

        # 3) python-literal-like dict (single quotes / True/False/None)
        try:
            py_like = c
            py_like = re.sub(r"\btrue\b", "True", py_like, flags=re.I)
            py_like = re.sub(r"\bfalse\b", "False", py_like, flags=re.I)
            py_like = re.sub(r"\bnull\b", "None", py_like, flags=re.I)
            py_like = re.sub(r",\s*([}\]])", r"\1", py_like)
            obj = ast.literal_eval(py_like)
            if isinstance(obj, dict):
                return obj
        except Exception:
            pass

    # Never crash the pipeline because of malformed LLM output.
    return {}

def _normalize_constraint_extract(obj: dict) -> dict:
    obj = obj or {}
    obj.setdefault("k", None)
    obj.setdefault("available_from", None)
    obj.setdefault("available_from_op", None)
    obj.setdefault("furnish_type", None)
    obj.setdefault("let_type", None)
    obj.setdefault("layout_options", [])
    obj.setdefault("min_tenancy_months", None)
    obj.setdefault("min_size_sqm", None)
    obj.setdefault("min_size_sqft", None)
    obj.setdefault("location_keywords", [])
    obj.setdefault("update_scope", "patch")
    obj.setdefault("location_update_mode", "replace")
    obj.setdefault("layout_update_mode", "replace")
    obj.setdefault("_replace_all_constraints", False)
    obj.setdefault("_location_update_mode", "replace")
    obj.setdefault("_layout_update_mode", "replace")
    obj.setdefault("_clear_location_keywords", False)
    obj.setdefault("_remove_layout_options", [])
    return obj

def _normalize_semantic_extract(obj: dict) -> dict:
    obj = obj or {}
    obj.setdefault("transit_terms", [])
    obj.setdefault("school_terms", [])
    obj.setdefault("general_semantic_phrases", [])

    def _norm_list(v: Any) -> List[str]:
        out = []
        seen = set()
        for x in (v or []):
            s = str(x).strip()
            if not s:
                continue
            k = s.lower()
            if k in seen:
                continue
            seen.add(k)
            out.append(s)
        return out

    def _drop_redundant_short_terms(items: List[str]) -> List[str]:
        cleaned = [str(x).strip() for x in (items or []) if str(x).strip()]
        out: List[str] = []
        for s in cleaned:
            sl = s.lower()
            redundant = False
            for t in cleaned:
                tl = t.lower()
                if tl == sl:
                    continue
                # Drop generic/short terms when fully covered by a longer phrase.
                if len(sl) <= len(tl) and re.search(rf"\b{re.escape(sl)}\b", tl):
                    redundant = True
                    break
            if not redundant:
                out.append(s)
        return out

    def _drop_hard_like_general_terms(items: List[str]) -> List[str]:
        out: List[str] = []
        for s in (items or []):
            sl = s.lower()
            # Remove hard/structured fragments from semantic phrases.
            # These should be handled by structured constraints or dedicated score components.
            if re.search(r"\bunder\s+\d+\b", sl):
                continue
            if re.search(r"\b(?:budget|price|rent|pcm|pcw|per\s*month|per\s*week)\b", sl):
                continue
            if re.search(r"\bdeposit\b", sl):
                continue
            if re.search(r"\b\d+\s*bed(room)?s?\b", sl):
                continue
            if re.search(r"\b\d+\s*[- ]?\s*bath(room)?s?\b", sl):
                continue
            if re.search(r"\b(flat|apartment|studio|house)\b", sl):
                continue
            if re.search(r"\b(?:furnished|unfurnished|part[- ]?furnished)\b", sl):
                continue
            if re.search(r"\b(?:short\s*term|long\s*term|short\s*let|long\s*let)\b", sl):
                continue
            if re.search(r"\b(?:move[- ]?in|available\s*from|availability|today|tomorrow|now)\b", sl):
                continue
            if re.search(r"\b(?:tenancy|months?|yrs?|years?)\b", sl):
                continue
            if re.search(r"\b(?:sqm|sq\s*m|sqft|square\s*feet|square\s*met(?:er|re)s?)\b", sl):
                continue
            out.append(s)
        return out

    school_terms = _drop_redundant_short_terms(_norm_list(obj.get("school_terms")))
    transit_terms = _drop_redundant_short_terms(_norm_list(obj.get("transit_terms")))
    general_terms = _drop_hard_like_general_terms(_norm_list(obj.get("general_semantic_phrases")))
    general_terms = _drop_redundant_short_terms(general_terms)

    return {
        "transit_terms": transit_terms,
        "school_terms": school_terms,
        "general_semantic_phrases": general_terms,
    }
