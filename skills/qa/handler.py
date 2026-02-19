import json
import re
from typing import Any, Dict, List, Optional

import pandas as pd

from core.llm_client import llm_extract, llm_extract_all_signals, qwen_chat
from core.settings import STRUCTURED_POLICY
from skills.qa.lookup import semantic_lookup, semantic_vector_lookup, structured_lookup
from skills.search.extractors import _norm_furnish_value, repair_extracted_constraints
from skills.search.handler import apply_hard_filters_with_audit, apply_structured_policy, split_query_signals


SEMANTIC_HIGH_THRESHOLD = 0.75
SEMANTIC_LOW_THRESHOLD = 0.60


def _strip_think_blocks(text: str) -> str:
    s = str(text or "")
    if not s:
        return s
    # Remove reasoning tags if model emits them.
    s = re.sub(r"<think>.*?</think>", "", s, flags=re.IGNORECASE | re.DOTALL)
    s = re.sub(r"^\s*\n+", "", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def _sanitize_list_output(text: str) -> str:
    s = str(text or "").strip()
    if not s:
        return s
    s = s.replace("**", "")
    s = re.sub(r"\bIndex\s+(\d+)\b", r"#\1", s, flags=re.IGNORECASE)
    s = re.sub(r"[ \t]+$", "", s, flags=re.MULTILINE)
    return s.strip()


def _sanitize_question_for_qa(text: str) -> str:
    s = str(text or "").strip()
    if not s:
        return ""
    patterns = [
        r"\b(?:the\s+)?(?:first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|\d{1,2}(?:st|nd|rd|th))\s+(?:one|listing|result|option|property|flat)\b",
        r"\b(?:listing|result|option|property|flat)\s*#?\s*\d{1,2}\b",
        r"(?<!\w)#\s*\d{1,2}(?!\w)",
    ]
    out = s
    for p in patterns:
        out = re.sub(p, " ", out, flags=re.IGNORECASE)
    out = re.sub(r"\s+", " ", out).strip(" ,.;:!?")
    return out


def _extract_first_json_obj(raw_text: str) -> Optional[Dict[str, Any]]:
    if not raw_text:
        return None
    s = str(raw_text).strip()
    try:
        obj = json.loads(s)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass
    start = s.find("{")
    if start < 0:
        return None
    depth = 0
    for i in range(start, len(s)):
        ch = s[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    obj = json.loads(s[start : i + 1])
                    if isinstance(obj, dict):
                        return obj
                except Exception:
                    return None
    return None


def _distill_listing_payload(listing_payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "listing_id": listing_payload.get("listing_id"),
        "title": listing_payload.get("title"),
        "address": listing_payload.get("address"),
        "price_pcm": listing_payload.get("price_pcm"),
        "bedrooms": listing_payload.get("bedrooms"),
        "bathrooms": listing_payload.get("bathrooms"),
        "available_from": listing_payload.get("available_from"),
        "let_type": listing_payload.get("let_type"),
        "furnish_type": listing_payload.get("furnish_type"),
        "description": listing_payload.get("description"),
        "features": listing_payload.get("features"),
        "nearest_station": listing_payload.get("nearest_station"),
        "distance_to_station_m": listing_payload.get("distance_to_station_m"),
        "schools": listing_payload.get("schools"),
        "stations": listing_payload.get("stations"),
        "deposit": listing_payload.get("deposit"),
        "min_tenancy": listing_payload.get("min_tenancy"),
        "min_tenancy_months": listing_payload.get("min_tenancy_months"),
        "size_sqm": listing_payload.get("size_sqm"),
        "size_sqft": listing_payload.get("size_sqft"),
        "property_type": listing_payload.get("property_type"),
        "postcode": listing_payload.get("postcode"),
        "layout_tag": listing_payload.get("layout_tag"),
        "url": listing_payload.get("url"),
    }


def _build_qa_signals(question: str) -> Dict[str, Any]:
    question_text = str(question or "").strip()
    sanitized_question = _sanitize_question_for_qa(question_text)
    extraction_input = sanitized_question or question_text

    semantic_parse_source = "llm_combined"
    combined = {"constraints": {}, "semantic_terms": {}}
    llm_constraints: Dict[str, Any] = {}
    semantic_terms: Dict[str, Any] = {}
    try:
        combined = llm_extract_all_signals(extraction_input, existing_constraints=None)
        llm_constraints = combined.get("constraints") or {}
        semantic_terms = combined.get("semantic_terms") or {}
    except Exception:
        semantic_parse_source = "fallback_split_calls"
        llm_constraints = llm_extract(extraction_input, existing_constraints=None)
        semantic_terms = {}
    rule_constraints = repair_extracted_constraints(llm_constraints, extraction_input)
    final_constraints, _ = apply_structured_policy(
        user_text=extraction_input,
        llm_constraints=llm_constraints,
        rule_constraints=rule_constraints,
        policy=STRUCTURED_POLICY,
    )
    signals = split_query_signals(
        extraction_input,
        final_constraints or {},
        precomputed_semantic_terms=semantic_terms,
        semantic_parse_source=semantic_parse_source,
    )
    return {
        "question_text": question_text,
        "extraction_input": extraction_input,
        "signals": signals,
        "final_constraints": final_constraints or {},
    }


def _semantic_allowed_fields(signals: Dict[str, Any]) -> set:
    topic_pref = (signals or {}).get("topic_preferences") or {}
    has_school = bool(topic_pref.get("school_terms"))
    has_transit = bool(topic_pref.get("transit_terms"))
    if has_school and has_transit:
        return {"schools", "stations", "description"}
    if has_school:
        return {"schools", "description"}
    if has_transit:
        return {"stations", "description"}
    return {"features", "description"}


def _is_unknown_value(v: Any) -> bool:
    if v is None:
        return True
    s = str(v).strip().lower()
    if s in {"", "none", "null", "unknown", "not provided", "ask agent", "n/a", "na"}:
        return True
    return False


def _mentioned_structured_fields(question: str, final_constraints: Dict[str, Any]) -> List[str]:
    q = str(question or "").lower()
    c = final_constraints or {}
    out: List[str] = []

    # Constraint-derived mentions (preferred).
    if c.get("max_rent_pcm") is not None:
        out.append("price_pcm")
    if c.get("available_from") is not None:
        out.append("available_from")
    if c.get("furnish_type"):
        out.append("furnish_type")
    if c.get("let_type"):
        out.append("let_type")
    if c.get("min_tenancy_months") is not None:
        out.append("min_tenancy")
    if c.get("min_size_sqm") is not None:
        out.extend(["size_sqm", "size_sqft"])
    if c.get("layout_options"):
        out.extend(["bedrooms", "bathrooms", "property_type", "layout_tag"])

    # Query mention fallback (for fields extractor may miss, e.g. deposit).
    mention_map = [
        (r"\bdeposit\b", ["deposit"]),
        (r"\bfurnish|furnished|unfurnished|part[- ]?furnished\b", ["furnish_type"]),
        (r"\blet\b|\bshort term\b|\blong term\b", ["let_type"]),
        (r"\bprice\b|\brent\b|\bbudget\b|\bpcm\b", ["price_pcm"]),
        (r"\bbed(room)?s?\b|\b\d+\s*bed\b", ["bedrooms"]),
        (r"\bbath(room)?s?\b|\b\d+\s*bath\b", ["bathrooms"]),
        (r"\bavailable\b|\bmove[- ]?in\b", ["available_from"]),
        (r"\btenancy\b|\bmonth\b", ["min_tenancy"]),
        (r"\bsize\b|\bsqm\b|\bsqft\b", ["size_sqm", "size_sqft"]),
        (r"\bflat\b|\bapartment\b|\bhouse\b|\bstudio\b", ["property_type"]),
        (r"\bpostcode\b", ["postcode"]),
        (r"\blayout\b", ["layout_tag"]),
        (r"\bschool\b", ["schools"]),
        (r"\bstation\b|\btransport\b|\btube\b", ["stations", "nearest_station", "distance_to_station_m"]),
    ]
    for pat, keys in mention_map:
        if re.search(pat, q):
            out.extend(keys)

    dedup: List[str] = []
    seen = set()
    for k in out:
        if k in seen:
            continue
        seen.add(k)
        dedup.append(k)
    return dedup


def _has_active_structured_constraints(constraints: Dict[str, Any]) -> bool:
    c = constraints or {}
    return any(
        [
            c.get("max_rent_pcm") is not None,
            c.get("available_from") is not None,
            bool(c.get("furnish_type")),
            bool(c.get("let_type")),
            c.get("min_tenancy_months") is not None,
            c.get("min_size_sqm") is not None,
            bool(c.get("layout_options")),
        ]
    )


def _structured_match_eval(listing_payload: Dict[str, Any], constraints: Dict[str, Any]) -> Dict[str, Any]:
    if not _has_active_structured_constraints(constraints):
        return {
            "active": False,
            "decisive": False,
            "hard_pass": None,
            "unknown_fields": [],
            "fail_reasons": [],
            "checks": {},
        }
    df = pd.DataFrame([dict(listing_payload or {})])
    _filtered, audits = apply_hard_filters_with_audit(df, constraints or {})
    audit = (audits or [{}])[0]
    checks: Dict[str, Any] = (audit or {}).get("hard_checks") or {}
    fail_reasons: List[str] = list(audit.get("hard_fail_reasons") or [])
    hard_pass = bool(audit.get("hard_pass"))

    unknown_fields: List[str] = []
    for k, v in checks.items():
        if not isinstance(v, dict):
            continue
        req = v.get("required")
        actual = v.get("actual")
        if req is None:
            continue
        if actual is None or (isinstance(actual, str) and not actual.strip()):
            unknown_fields.append(str(k))
    return {
        "active": True,
        "decisive": len(unknown_fields) == 0,
        "hard_pass": bool(hard_pass),
        "unknown_fields": unknown_fields,
        "fail_reasons": fail_reasons,
        "checks": checks,
    }


def _pick_decision_label(structured_eval: Dict[str, Any], vector_eval: Optional[Dict[str, Any]], semantic_fallback) -> Dict[str, Any]:
    if structured_eval.get("active") and structured_eval.get("decisive"):
        return {
            "source": "structured_hard",
            "label": "confirmed" if structured_eval.get("hard_pass") else "not_found",
        }
    if vector_eval and vector_eval.get("found"):
        return {
            "source": "semantic_vector",
            "label": str(vector_eval.get("summary_label") or "not_found"),
        }
    if semantic_fallback and semantic_fallback.found:
        return {"source": "semantic_keyword", "label": "confirmed"}
    return {"source": "none", "label": "not_found"}


def _norm_let_type_value(v: Any) -> str:
    s = str(v or "").strip().lower()
    if not s:
        return ""
    s = s.replace("_", " ").replace("-", " ")
    s = re.sub(r"\s+", " ", s).strip()
    if s in {"ask agent", "unknown", "not provided", "n/a", "na"}:
        return "unknown"
    return s


def classify_qa_scope(
    question: str,
    has_focus: bool,
    has_listings: bool,
    last_qa_scope: Optional[str] = None,
) -> Dict[str, Any]:
    prompt = (
        "You classify QA scope for rental listings.\n"
        "Return STRICT JSON only:\n"
        '{"target_scope":"single|list|clarify","confidence":0.0,"reason":"..."}\n'
        "Policy:\n"
        "- Default behavior with has_focus=true is single-listing QA continuity.\n"
        "- Use list ONLY when user explicitly asks cross-candidate comparison/selection (e.g., 'which one', '哪一个', '哪个房源').\n"
        "- If user asks about current listing with explicit deixis (it/this/this listing/这个/这套), target_scope=single.\n"
        "- If has_focus=false and user uses unresolved deixis (it/this/这个), target_scope=clarify.\n"
        "- If previous QA scope was single and current question has no explicit cross-candidate wording, keep target_scope=single.\n"
        "- When unsure and has_focus=true, prefer single.\n"
        "Few-shot:\n"
        "State: has_focus=true, has_listings=true, last_qa_scope=single; Q: How about transportation\n"
        'Output: {"target_scope":"single","confidence":0.90,"reason":"qa_continuity_single"}\n'
        "State: has_focus=true, has_listings=true, last_qa_scope=single; Q: How about schools\n"
        'Output: {"target_scope":"single","confidence":0.90,"reason":"qa_continuity_single"}\n'
        "State: has_focus=true, has_listings=true; Q: 有没有gym\n"
        'Output: {"target_scope":"single","confidence":0.78,"reason":"default_focus_continuity"}\n'
        "State: has_focus=true, has_listings=true; Q: 这个有gym吗\n"
        'Output: {"target_scope":"single","confidence":0.90,"reason":"explicit_deixis_current_listing"}\n'
        "State: has_focus=false, has_listings=true; Q: 这个有gym吗\n"
        'Output: {"target_scope":"clarify","confidence":0.92,"reason":"deixis_without_target"}\n'
        "State: has_focus=true, has_listings=true; Q: 哪一个有gym\n"
        'Output: {"target_scope":"list","confidence":0.94,"reason":"which_one_over_candidates"}\n'
    )
    user_payload = (
        f"State: has_focus={'true' if has_focus else 'false'}, "
        f"has_listings={'true' if has_listings else 'false'}, "
        f"last_qa_scope={str(last_qa_scope or 'none').strip().lower()}\n"
        f"Question: {str(question or '').strip()}"
    )
    try:
        raw = qwen_chat(
            [
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_payload},
            ],
            temperature=0.0,
        )
        obj = _extract_first_json_obj(raw)
        if isinstance(obj, dict):
            scope = str(obj.get("target_scope") or "").strip().lower()
            if scope in {"single", "list", "clarify"}:
                return {
                    "target_scope": scope,
                    "confidence": float(obj.get("confidence", 0.0) or 0.0),
                    "reason": str(obj.get("reason") or "llm"),
                }
    except Exception:
        pass

    # No rule-based scope inference here: fallback is always clarify.
    _ = question, has_focus, has_listings, last_qa_scope
    return {"target_scope": "clarify", "confidence": 0.0, "reason": "fallback:llm_unavailable"}


def answer_single_listing_question(question: str, listing_payload: Dict[str, Any], embedder=None) -> str:
    if not listing_payload:
        return "I don't have the selected listing details yet."
    qa_ctx = _build_qa_signals(question)
    extraction_input = qa_ctx["extraction_input"]
    signals = qa_ctx["signals"]
    final_constraints = qa_ctx.get("final_constraints") or {}
    allowed_fields = _semantic_allowed_fields(signals)
    distilled = _distill_listing_payload(listing_payload)
    structured_eval = _structured_match_eval(distilled, final_constraints)

    # Structured-first short path for explicit categorical constraints.
    if final_constraints.get("furnish_type"):
        actual = _norm_furnish_value(distilled.get("furnish_type"))
        if actual and actual != "ask agent":
            req = _norm_furnish_value(final_constraints.get("furnish_type"))
            if actual == req:
                return f"Yes. Listing is {actual}. Please confirm with the listing agent."
            return f"No. Listing is {actual}, not {req}. Please confirm with the listing agent."
    if final_constraints.get("let_type"):
        actual = _norm_let_type_value(distilled.get("let_type"))
        if actual and actual != "unknown":
            req = _norm_let_type_value(final_constraints.get("let_type"))
            if actual == req:
                return f"Yes. Listing let type is {actual}. Please confirm with the listing agent."
            return f"No. Listing let type is {actual}, not {req}. Please confirm with the listing agent."

    structured = structured_lookup(signals, distilled, raw_question=extraction_input)
    semantic_fallback = semantic_lookup(
        signals,
        distilled,
        raw_question=extraction_input,
        allowed_fields=allowed_fields,
    )
    vector_eval = (
        semantic_vector_lookup(
            signals,
            distilled,
            embedder=embedder,
            raw_question=extraction_input,
            high_threshold=SEMANTIC_HIGH_THRESHOLD,
            low_threshold=SEMANTIC_LOW_THRESHOLD,
            allowed_fields=allowed_fields,
        )
        if embedder is not None
        else None
    )

    decision = _pick_decision_label(structured_eval, vector_eval, semantic_fallback)
    if decision["label"] == "not_found" and decision["source"] == "none":
        return "Not found in listing data. Please ask the agent to confirm."

    system_prompt = (
        "You are a rental property QA assistant.\n"
        "You must answer using only the provided evidence and facts.\n"
        "Do not guess or add information that is not in evidence.\n"
        "If evidence is insufficient, say not provided and ask user to check with agent.\n"
        "Always remind user to confirm key details with the listing agent.\n"
        "Keep answer concise and concrete."
    )
    qa_payload = {
        "question": extraction_input,
        "signals": signals,
        "final_constraints": final_constraints,
        "decision": decision,
        "structured_match_eval": structured_eval,
        "structured": {
            "found": structured.found,
            "facts": structured.facts,
            "evidence": structured.evidence,
        },
        "semantic_keyword_fallback": {
            "found": semantic_fallback.found,
            "facts": semantic_fallback.facts,
            "evidence": semantic_fallback.evidence,
        },
        "semantic_vector": vector_eval,
        "listing": {
            "title": distilled.get("title"),
            "address": distilled.get("address"),
            "price_pcm": distilled.get("price_pcm"),
            "url": distilled.get("url"),
        },
    }
    try:
        out = qwen_chat(
            [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": "Answer based on this grounded QA JSON only:\n"
                    + json.dumps(qa_payload, ensure_ascii=False),
                },
            ],
            temperature=0.0,
        )
        cleaned = _strip_think_blocks(out)
        return cleaned or "Not provided in listing data. Please ask the agent to confirm."
    except Exception:
        if decision["label"] == "confirmed":
            return "Confirmed by listing data. Please confirm with the listing agent."
        if decision["label"] == "uncertain":
            return "Possibly matched, but not certain from listing data. Please confirm with the listing agent."
        top_evidence = []
        if vector_eval and vector_eval.get("evidence"):
            top_evidence = vector_eval["evidence"][:2]
        elif structured.evidence:
            top_evidence = structured.evidence[:2]
        elif semantic_fallback.evidence:
            top_evidence = semantic_fallback.evidence[:2]
        if not top_evidence:
            return "Not provided in listing data. Please ask the agent to confirm."
        bits = [f"{x.get('field')}: {x.get('text')}" for x in top_evidence if x.get("text")]
        if not bits:
            return "Not provided in listing data. Please ask the agent to confirm."
        return "From listing details: " + "; ".join(bits) + ". Please confirm with the agent."


def answer_multi_listing_question(question: str, listings: List[Dict[str, Any]], embedder=None) -> str:
    rows = list(listings or [])
    if not rows:
        return "There are no listings to compare yet. Please run a search first."

    qa_ctx = _build_qa_signals(question)
    extraction_input = qa_ctx["extraction_input"]
    signals = qa_ctx["signals"]
    final_constraints = qa_ctx.get("final_constraints") or {}
    requested_fields = _mentioned_structured_fields(extraction_input, final_constraints)
    allowed_fields = _semantic_allowed_fields(signals)
    rows_eval: List[Dict[str, Any]] = []
    for idx, payload in enumerate(rows, start=1):
        distilled = _distill_listing_payload(payload)
        structured_eval = _structured_match_eval(distilled, final_constraints)
        if embedder is not None:
            vec = semantic_vector_lookup(
                signals,
                distilled,
                embedder=embedder,
                raw_question=extraction_input,
                high_threshold=SEMANTIC_HIGH_THRESHOLD,
                low_threshold=SEMANTIC_LOW_THRESHOLD,
                allowed_fields=allowed_fields,
            )
            label = str(vec.get("summary_label") or "not_found")
            evidence = (vec.get("evidence") or [{}])[0]
            score = None
            term_matches = vec.get("term_matches") or []
            if term_matches:
                score = term_matches[0].get("score")
        else:
            sem = semantic_lookup(
                signals,
                distilled,
                raw_question=extraction_input,
                allowed_fields=allowed_fields,
            )
            label = "confirmed" if sem.found else "not_found"
            evidence = (sem.evidence or [{}])[0]
            score = None

        decision = _pick_decision_label(structured_eval, vec if embedder is not None else None, sem if embedder is None else None)
        label = str(decision.get("label") or label)
        field_values = {k: distilled.get(k) for k in requested_fields}
        unknown_fields = [k for k, v in field_values.items() if _is_unknown_value(v)]
        missing_structured = bool(requested_fields) and len(unknown_fields) > 0
        if structured_eval.get("active") and structured_eval.get("decisive"):
            status = "match" if structured_eval.get("hard_pass") else "not_match"
            source = "structured"
        elif missing_structured:
            # For fields missing in structured payload, defer decision to semantic/LLM.
            status = "unknown"
            source = "structured_missing"
        else:
            if label == "confirmed":
                status = "match"
            elif label == "not_found":
                status = "unknown"
            else:
                status = "unknown"
            source = str(decision.get("source") or "semantic")

        check_values: List[Dict[str, Any]] = []
        for k, v in (structured_eval.get("checks") or {}).items():
            if not isinstance(v, dict):
                continue
            if v.get("required") is None:
                continue
            check_values.append(
                {
                    "field": str(k),
                    "required": v.get("required"),
                    "actual": v.get("actual"),
                    "op": v.get("op"),
                }
            )

        rec = {
            "index": idx,
            "title": str(distilled.get("title") or f"listing_{idx}"),
            "status": status,
            "source": source,
            "decision_label": label,
            "structured": {
                "active": bool(structured_eval.get("active")),
                "decisive": bool(structured_eval.get("decisive")),
                "hard_pass": structured_eval.get("hard_pass"),
                "fail_reasons": list(structured_eval.get("fail_reasons") or []),
                "checks": check_values,
            },
            "semantic": {
                "top_evidence": str(evidence.get("text") or "").strip(),
                "score": score,
            },
            "requested_fields": requested_fields,
            "field_values": field_values,
            "unknown_fields": unknown_fields,
        }
        rows_eval.append(rec)

    system_prompt = (
        "You are a rental property QA assistant.\n"
        "Answer using ONLY the provided rows evaluation JSON.\n"
        "Do not invent facts.\n"
        "Use plain bullet lists only (lines starting with '-').\n"
        "Do not use markdown emphasis like **Index 5:**.\n"
        "Use only query-relevant fields/evidence from each row.\n"
        "Do NOT introduce unrelated attributes from other fields.\n"
        "For each row, rely on requested_fields/field_values first.\n"
        "If unknown_fields is non-empty for requested fields, use semantic evidence for fallback and then classify.\n"
        "Summarize which listings match, which do not match (and why, including actual values), and which are unknown.\n"
        "For not-match rows, include the conflicting structured value when available (e.g., unfurnished vs furnished).\n"
        "If a section has no items, omit that section entirely.\n"
        "If none match, state that explicitly.\n"
        "Always remind user to confirm with listing agent."
    )
    qa_payload = {
        "user_question": extraction_input,
        "question": extraction_input,
        "signals": signals,
        "final_constraints": final_constraints,
        "rows": rows_eval,
    }
    try:
        out = qwen_chat(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": "Answer from this JSON only:\n" + json.dumps(qa_payload, ensure_ascii=False)},
            ],
            temperature=0.0,
        )
        cleaned = _sanitize_list_output(_strip_think_blocks(out))
        if cleaned:
            return cleaned
    except Exception:
        pass

    matched = [f"#{x['index']}" for x in rows_eval if x.get("status") == "match"]
    not_matched = [f"#{x['index']}" for x in rows_eval if x.get("status") == "not_match"]
    unknown = [f"#{x['index']}" for x in rows_eval if x.get("status") == "unknown"]
    lines: List[str] = []
    if matched:
        lines.append("Matched:")
        lines.extend([f"- {x}" for x in matched])
    if not_matched:
        lines.append("Not matched:")
        lines.extend([f"- {x}" for x in not_matched])
    if unknown:
        lines.append("Unknown:")
        lines.extend([f"- {x}" for x in unknown])
    if not lines:
        lines.append("No matched listings found.")
    lines.append("Please confirm key details with the listing agent before final decision.")
    return "\n".join(lines)
