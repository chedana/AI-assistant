import json
import re
from typing import Any, Dict, List, Optional

import pandas as pd

from core.llm_client import llm_extract, llm_extract_all_signals, qwen_chat
from core.settings import STRUCTURED_POLICY
from skills.qa.lookup import semantic_lookup, semantic_vector_lookup, structured_lookup
from skills.search.extractors import repair_extracted_constraints
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
    checks = (audit or {}).get("hard_checks") or {}
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
        "hard_pass": bool(audit.get("hard_pass")),
        "unknown_fields": unknown_fields,
        "fail_reasons": list(audit.get("hard_fail_reasons") or []),
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
    allowed_fields = _semantic_allowed_fields(signals)

    matched_confirmed: List[Dict[str, Any]] = []
    matched_uncertain: List[Dict[str, Any]] = []
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
        rec = {
            "index": idx,
            "title": str(distilled.get("title") or f"listing_{idx}"),
            "label": label,
            "evidence": str(evidence.get("text") or "").strip(),
            "score": score,
            "decision": decision,
            "structured_match_eval": structured_eval,
        }
        rows_eval.append(rec)
        if label == "confirmed":
            matched_confirmed.append(rec)
        elif label == "uncertain":
            matched_uncertain.append(rec)

    if not matched_confirmed and not matched_uncertain:
        return "Not found in current listings. Please ask the agent to confirm."

    system_prompt = (
        "You are a rental property QA assistant.\n"
        "Answer using ONLY the provided rows evaluation JSON.\n"
        "Do not invent facts.\n"
        "Summarize confirmed matches first, then uncertain matches if any.\n"
        "Always remind user to confirm with listing agent."
    )
    qa_payload = {
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
        cleaned = _strip_think_blocks(out)
        if cleaned:
            return cleaned
    except Exception:
        pass

    lines: List[str] = []
    if matched_confirmed:
        lines.append("Confirmed matches:")
        for x in matched_confirmed:
            lines.append(f"- #{x['index']} {x['title']}")
    if matched_uncertain:
        lines.append("Possible matches (uncertain):")
        for x in matched_uncertain:
            lines.append(f"- #{x['index']} {x['title']}")
    lines.append("Please confirm key details with the listing agent before final decision.")
    return "\n".join(lines)
