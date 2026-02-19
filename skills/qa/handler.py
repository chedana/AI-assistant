import json
import re
from typing import Any, Dict, List, Optional

from core.llm_client import llm_extract, llm_extract_all_signals, qwen_chat
from core.settings import STRUCTURED_POLICY
from skills.qa.lookup import semantic_lookup, semantic_vector_lookup, structured_lookup
from skills.search.extractors import repair_extracted_constraints
from skills.search.handler import apply_structured_policy, split_query_signals


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
    }


def classify_qa_scope(question: str, has_focus: bool, has_listings: bool) -> Dict[str, Any]:
    prompt = (
        "You classify QA scope for rental listings.\n"
        "Return STRICT JSON only:\n"
        '{"target_scope":"single|list|clarify","confidence":0.0,"reason":"..."}\n'
        "Policy:\n"
        "- If has_focus=true and user asks about current listing (it/this/这个), target_scope=single.\n"
        "- If user asks compare/filter across results (which one/哪一个/哪个/which listing), target_scope=list.\n"
        "- If has_focus=false and user uses unresolved deixis (it/this/这个), target_scope=clarify.\n"
        "- When unsure, prefer list if question asks 'which one', otherwise clarify.\n"
    )
    user_payload = (
        f"State: has_focus={'true' if has_focus else 'false'}, has_listings={'true' if has_listings else 'false'}\n"
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
    _ = question, has_focus, has_listings
    return {"target_scope": "clarify", "confidence": 0.0, "reason": "fallback:llm_unavailable"}


def answer_single_listing_question(question: str, listing_payload: Dict[str, Any], embedder=None) -> str:
    if not listing_payload:
        return "I don't have the selected listing details yet."
    qa_ctx = _build_qa_signals(question)
    extraction_input = qa_ctx["extraction_input"]
    signals = qa_ctx["signals"]
    distilled = _distill_listing_payload(listing_payload)

    structured = structured_lookup(signals, distilled, raw_question=extraction_input)
    semantic_fallback = semantic_lookup(signals, distilled, raw_question=extraction_input)
    vector_eval = (
        semantic_vector_lookup(
            signals,
            distilled,
            embedder=embedder,
            raw_question=extraction_input,
            high_threshold=SEMANTIC_HIGH_THRESHOLD,
            low_threshold=SEMANTIC_LOW_THRESHOLD,
        )
        if embedder is not None
        else None
    )

    no_evidence = (not structured.found) and (not semantic_fallback.found) and not (vector_eval and vector_eval.get("found"))
    if no_evidence:
        return "This listing does not provide that information. Please ask the agent to confirm."

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

    matched_confirmed: List[Dict[str, Any]] = []
    matched_uncertain: List[Dict[str, Any]] = []
    for idx, payload in enumerate(rows, start=1):
        distilled = _distill_listing_payload(payload)
        if embedder is not None:
            vec = semantic_vector_lookup(
                signals,
                distilled,
                embedder=embedder,
                raw_question=extraction_input,
                high_threshold=SEMANTIC_HIGH_THRESHOLD,
                low_threshold=SEMANTIC_LOW_THRESHOLD,
            )
            label = str(vec.get("summary_label") or "not_found")
            evidence = (vec.get("evidence") or [{}])[0]
            score = None
            term_matches = vec.get("term_matches") or []
            if term_matches:
                score = term_matches[0].get("score")
        else:
            sem = semantic_lookup(signals, distilled, raw_question=extraction_input)
            label = "confirmed" if sem.found else "not_found"
            evidence = (sem.evidence or [{}])[0]
            score = None

        rec = {
            "index": idx,
            "title": str(distilled.get("title") or f"listing_{idx}"),
            "label": label,
            "evidence": str(evidence.get("text") or "").strip(),
            "score": score,
        }
        if label == "confirmed":
            matched_confirmed.append(rec)
        elif label == "uncertain":
            matched_uncertain.append(rec)

    if not matched_confirmed and not matched_uncertain:
        return "No listing shows clear evidence for that in features/description. Please confirm with the agent."

    lines: List[str] = []
    if matched_confirmed:
        lines.append("Confirmed matches:")
        for x in matched_confirmed:
            snippet = x["evidence"][:120]
            detail = f" (score {x['score']})" if x.get("score") is not None else ""
            lines.append(f"- #{x['index']} {x['title']}{detail}: {snippet}")
    if matched_uncertain:
        lines.append("Possible matches (uncertain):")
        for x in matched_uncertain:
            snippet = x["evidence"][:120]
            detail = f" (score {x['score']})" if x.get("score") is not None else ""
            lines.append(f"- #{x['index']} {x['title']}{detail}: {snippet}")
    lines.append("Please confirm key details with the listing agent before final decision.")
    return "\n".join(lines)
