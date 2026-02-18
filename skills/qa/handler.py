import json
import re
from typing import Any, Dict

from core.llm_client import llm_extract, llm_extract_all_signals, qwen_chat
from core.settings import STRUCTURED_POLICY
from skills.qa.lookup import semantic_lookup, structured_lookup
from skills.search.extractors import repair_extracted_constraints
from skills.search.handler import apply_structured_policy, split_query_signals


def _strip_think_blocks(text: str) -> str:
    s = str(text or "")
    if not s:
        return s
    # Remove reasoning tags if model emits them.
    s = re.sub(r"<think>.*?</think>", "", s, flags=re.IGNORECASE | re.DOTALL)
    s = re.sub(r"^\s*\n+", "", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def _has_index_reference(text: str) -> bool:
    s = str(text or "").strip()
    if not s:
        return False
    patterns = [
        r"\b(?:the\s+)?(?:first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|\d{1,2}(?:st|nd|rd|th))\s+(?:one|listing|result|option|property|flat)\b",
        r"\b(?:listing|result|option|property|flat)\s*#?\s*\d{1,2}\b",
        r"(?<!\w)#\s*\d{1,2}(?!\w)",
    ]
    for p in patterns:
        if re.search(p, s, flags=re.IGNORECASE):
            return True
    return False


def answer_single_listing_question(question: str, listing_payload: Dict[str, Any]) -> str:
    if not listing_payload:
        return "I don't have the selected listing details yet."
    question_text = str(question or "").strip()
    extraction_input = question_text
    if _has_index_reference(question_text):
        extraction_input += (
            "\n\nRouting note: If something is used as an index reference "
            "(e.g., first/second/#3/listing 2), remove it from constraints "
            "or condition terms for semantic matching."
        )

    distilled = {
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

    structured = structured_lookup(signals, distilled, raw_question=question_text)
    semantic = structured if structured.found else semantic_lookup(signals, distilled, raw_question=question_text)
    evidence_source = structured if structured.found else semantic

    if not evidence_source.found:
        return "This listing does not provide that information. Please ask the agent to confirm."

    system_prompt = (
        "You are a rental property QA assistant.\n"
        "You must answer using only the provided evidence and facts.\n"
        "Do not guess or add information that is not in evidence.\n"
        "If evidence is insufficient, say not provided and ask user to check with agent.\n"
        "Keep answer concise and concrete."
    )
    qa_payload = {
        "question": question,
        "extraction_input": extraction_input,
        "signals": signals,
        "lookup_mode": evidence_source.mode,
        "facts": evidence_source.facts,
        "evidence": evidence_source.evidence,
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
        top_evidence = evidence_source.evidence[:2]
        if not top_evidence:
            return "Not provided in listing data. Please ask the agent to confirm."
        bits = [f"{x.get('field')}: {x.get('text')}" for x in top_evidence]
        return "From listing details: " + "; ".join(bits)
