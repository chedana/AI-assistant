import json
import math
import re
from typing import Any, Dict, List, Optional

import numpy as np

from core.llm_client import qwen_chat
from core.internal_helpers import _collect_value_candidates, _embed_texts_cached
from skills.qa.plan import build_qa_plan
from skills.search.extractors import _norm_furnish_value
from skills.search.signals import split_query_signals


# ── Text utilities ────────────────────────────────────────────────────────────

def _strip_think_blocks(text: str) -> str:
    s = str(text or "")
    if not s:
        return s
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


def _parse_deposit_amount(v: Any) -> Dict[str, Any]:
    raw = str(v or "").strip()
    low = raw.lower()
    if not raw or low in {"unknown", "not provided", "ask agent", "n/a", "na", "none", "null"}:
        return {"state": "unknown", "amount": None, "raw": raw}
    if re.search(r"\b(zero|no)\s+deposit\b", low):
        return {"state": "known", "amount": 0.0, "raw": raw}
    m = re.search(r"(\d+(?:\.\d+)?)", raw.replace(",", ""))
    if not m:
        return {"state": "unknown", "amount": None, "raw": raw}
    try:
        return {"state": "known", "amount": float(m.group(1)), "raw": raw}
    except Exception:
        return {"state": "unknown", "amount": None, "raw": raw}


def _norm_let_type_value(v: Any) -> str:
    s = str(v or "").strip().lower()
    if not s:
        return ""
    s = s.replace("_", " ").replace("-", " ")
    s = re.sub(r"\s+", " ", s).strip()
    if s in {"ask agent", "unknown", "not provided", "n/a", "na"}:
        return "unknown"
    return s


# ── Question context ──────────────────────────────────────────────────────────

def build_qa_context(question: str) -> Dict[str, Any]:
    question_text = str(question or "").strip()
    sanitized_question = _sanitize_question_for_qa(question_text)
    extraction_input = sanitized_question or question_text
    plan = build_qa_plan(extraction_input)
    final_constraints = dict(plan.hard_constraints or {})
    semantic_terms = dict(plan.semantic_terms or {})
    signals = split_query_signals(
        extraction_input,
        final_constraints,
        precomputed_semantic_terms=semantic_terms,
        semantic_parse_source=str(plan.plan_source or "qa_rule_fallback"),
    )
    return {
        "question_text": question_text,
        "extraction_input": extraction_input,
        "plan_source": str(plan.plan_source or "qa_rule_fallback"),
        "llm_extract_all_error": dict(plan.llm_error or {}),
        "semantic_terms": semantic_terms,
        "signals": signals,
        "final_constraints": final_constraints or {},
    }


def _build_qa_signals(question: str) -> Dict[str, Any]:
    return build_qa_context(question)


# ── BM25 retrieval ────────────────────────────────────────────────────────────

def _tokenize_bm25(text: str) -> List[str]:
    return re.findall(r"[a-z0-9]+", str(text or "").lower())


def _bm25_scores(query_terms: List[str], texts: List[str], k1: float = 1.5, b: float = 0.75) -> List[float]:
    if not texts or not query_terms:
        return [0.0] * len(texts)
    tokenized = [_tokenize_bm25(t) for t in texts]
    N = len(tokenized)
    avg_len = sum(len(t) for t in tokenized) / N
    scores = []
    for tokens in tokenized:
        doc_len = len(tokens)
        score = 0.0
        for term in set(query_terms):
            tf = tokens.count(term)
            if tf == 0:
                continue
            df = sum(1 for t in tokenized if term in t)
            idf = math.log((N - df + 0.5) / (df + 0.5) + 1)
            tf_norm = (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * doc_len / (avg_len or 1)))
            score += idf * tf_norm
        scores.append(score)
    return scores


# ── Embedding retrieval ───────────────────────────────────────────────────────

def _embedding_scores(query: str, texts: List[str], embedder) -> List[float]:
    if not embedder or not texts or not (query or "").strip():
        return [0.0] * len(texts)
    cache: Dict[str, np.ndarray] = {}
    vecs = _embed_texts_cached(embedder, [query] + texts, cache)
    q_vec = vecs[0]
    return [float(max(0.0, min(1.0, float(np.dot(q_vec, tv))))) for tv in vecs[1:]]


# ── Chunk extraction per category ─────────────────────────────────────────────

# Maps each need category to the listing fields that are relevant.
_CATEGORY_FIELDS: Dict[str, set] = {
    "school":      {"schools", "description"},
    "transit":     {"stations", "description"},
    "amenity":     {"features", "description"},
    "general":     {"features", "description", "schools", "stations"},
}


def _get_category_chunks(distilled: Dict[str, Any], category: str) -> List[Dict[str, str]]:
    allowed = _CATEGORY_FIELDS.get(category, _CATEGORY_FIELDS["general"])
    chunks = [c for c in _collect_value_candidates(distilled) if c.get("field") in allowed]
    # Prepend nearest_station as a synthetic transit chunk when relevant.
    if category in ("transit", "general"):
        ns = str(distilled.get("nearest_station") or "").strip()
        dist = distilled.get("distance_to_station_m")
        if ns:
            text = f"{ns} ({dist}m away)" if dist is not None else ns
            if text not in {c["text"] for c in chunks}:
                chunks.insert(0, {"field": "nearest_station", "text": text})
    return chunks


# ── Hybrid BM25 + embedding retrieval ────────────────────────────────────────

def _hybrid_retrieve(
    query_terms: List[str],
    chunks: List[Dict[str, str]],
    embedder,
    top_k: int = 4,
) -> List[Dict[str, Any]]:
    if not chunks:
        return []
    texts = [c["text"] for c in chunks]

    bm25 = _bm25_scores(query_terms, texts)
    bm25_max = max(bm25) if any(s > 0 for s in bm25) else 1.0
    bm25_norm = [s / (bm25_max + 1e-8) for s in bm25]

    query_str = " ".join(query_terms)
    emb = _embedding_scores(query_str, texts, embedder)

    seen: set = set()
    results: List[Dict[str, Any]] = []
    for i, chunk in enumerate(chunks):
        text = chunk["text"]
        if text in seen:
            continue
        seen.add(text)
        results.append({
            "field": chunk["field"],
            "text": text,
            "score": round(max(bm25_norm[i], emb[i]), 4),
        })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:top_k]


# ── Evidence retrieval across all need categories ─────────────────────────────

def _retrieve_evidence(
    signals: Dict[str, Any],
    distilled: Dict[str, Any],
    embedder,
    top_k: int = 4,
) -> Dict[str, List[Dict[str, Any]]]:
    topic_pref = (signals or {}).get("topic_preferences") or {}
    school_terms  = [str(x) for x in (topic_pref.get("school_terms")  or []) if str(x).strip()]
    transit_terms = [str(x) for x in (topic_pref.get("transit_terms") or []) if str(x).strip()]
    general_terms = [str(x) for x in ((signals or {}).get("general_semantic") or []) if str(x).strip()]

    evidence: Dict[str, List[Dict[str, Any]]] = {}

    if school_terms:
        hits = _hybrid_retrieve(school_terms, _get_category_chunks(distilled, "school"), embedder, top_k)
        if hits:
            evidence["school"] = hits

    if transit_terms:
        hits = _hybrid_retrieve(transit_terms, _get_category_chunks(distilled, "transit"), embedder, top_k)
        if hits:
            evidence["transportation"] = hits

    if general_terms:
        hits = _hybrid_retrieve(general_terms, _get_category_chunks(distilled, "amenity"), embedder, top_k)
        if hits:
            evidence["amenity"] = hits

    # Fallback: no categories extracted — search all text fields
    if not evidence:
        all_terms = school_terms + transit_terms + general_terms
        hits = _hybrid_retrieve(all_terms, _get_category_chunks(distilled, "general"), embedder, top_k)
        if hits:
            evidence["general"] = hits

    return evidence


# ── QA scope classifier ───────────────────────────────────────────────────────

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
        "- Use list ONLY when user explicitly asks cross-candidate comparison/selection (e.g., 'which one', 'which listing', 'which property').\n"
        "- If user asks about current listing with explicit deixis (it/this/this listing/this property), target_scope=single.\n"
        "- If has_focus=false and user uses unresolved deixis (it/this/that one), target_scope=clarify.\n"
        "- If previous QA scope was single and current question has no explicit cross-candidate wording, keep target_scope=single.\n"
        "- When unsure and has_focus=true, prefer single.\n"
        "Few-shot:\n"
        "State: has_focus=true, has_listings=true, last_qa_scope=single; Q: How about transportation\n"
        'Output: {"target_scope":"single","confidence":0.90,"reason":"qa_continuity_single"}\n'
        "State: has_focus=true, has_listings=true, last_qa_scope=single; Q: How about schools\n"
        'Output: {"target_scope":"single","confidence":0.90,"reason":"qa_continuity_single"}\n'
        "State: has_focus=true, has_listings=true; Q: Does it have a gym?\n"
        'Output: {"target_scope":"single","confidence":0.78,"reason":"default_focus_continuity"}\n'
        "State: has_focus=true, has_listings=true; Q: Does this listing have a gym?\n"
        'Output: {"target_scope":"single","confidence":0.90,"reason":"explicit_deixis_current_listing"}\n'
        "State: has_focus=false, has_listings=true; Q: Does this one have a gym?\n"
        'Output: {"target_scope":"clarify","confidence":0.92,"reason":"deixis_without_target"}\n'
        "State: has_focus=true, has_listings=true; Q: Which one has a gym?\n"
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

    # Fallback: use focus state and prior scope rather than always clarifying.
    if has_focus:
        return {"target_scope": "single", "confidence": 0.0, "reason": "fallback:has_focus"}
    if last_qa_scope == "list":
        return {"target_scope": "list", "confidence": 0.0, "reason": "fallback:last_scope_list"}
    return {"target_scope": "clarify", "confidence": 0.0, "reason": "fallback:llm_unavailable"}


# ── Single listing QA ─────────────────────────────────────────────────────────

def answer_single_listing_question(
    question: str,
    listing_payload: Dict[str, Any],
    embedder=None,
    qa_ctx: Optional[Dict[str, Any]] = None,
) -> str:
    if not listing_payload:
        return "I don't have the selected listing details yet."

    ctx = qa_ctx or build_qa_context(question)
    extraction_input = ctx["extraction_input"]
    signals = ctx["signals"]
    final_constraints = ctx.get("final_constraints") or {}
    distilled = _distill_listing_payload(listing_payload)

    # ── Structured fast paths (exact field lookups, no retrieval needed) ───────
    dep_req = final_constraints.get("deposit")
    if dep_req is not None:
        dep = _parse_deposit_amount(distilled.get("deposit"))
        if dep.get("state") != "known":
            return "Deposit is not provided in listing data (ask agent)."
        amount = float(dep.get("amount") or 0.0)
        amount_txt = str(int(amount)) if float(amount).is_integer() else f"{amount:g}"
        if isinstance(dep_req, (int, float)) and float(dep_req) == 0.0:
            if amount == 0.0:
                return "Yes. This listing has no deposit (£0)."
            return f"No. This listing has a deposit of £{amount_txt}."
        if amount > 0.0:
            return f"The deposit is £{amount_txt}."
        return "No. This listing has no deposit (£0)."

    if final_constraints.get("furnish_type"):
        actual = _norm_furnish_value(distilled.get("furnish_type"))
        if actual and actual != "ask agent":
            req = _norm_furnish_value(final_constraints.get("furnish_type"))
            if actual == req:
                return f"Yes. This listing is {actual}. Please confirm with the listing agent."
            return f"No. This listing is {actual}, not {req}. Please confirm with the listing agent."

    if final_constraints.get("let_type"):
        actual = _norm_let_type_value(distilled.get("let_type"))
        if actual and actual != "unknown":
            req = _norm_let_type_value(final_constraints.get("let_type"))
            if actual == req:
                return f"Yes. Let type is {actual}. Please confirm with the listing agent."
            return f"No. Let type is {actual}, not {req}. Please confirm with the listing agent."

    # ── Hybrid retrieval: BM25 + embedding per need category ──────────────────
    evidence_by_category = _retrieve_evidence(signals, distilled, embedder)

    # ── LLM reasons over structured fields + retrieved evidence ───────────────
    system_prompt = (
        "You are a rental property assistant.\n"
        "Answer the user's question using ONLY the listing_fields and evidence_by_category provided.\n"
        "Be direct and concise. Quote specific evidence when helpful.\n"
        "If evidence is absent, say: 'Not mentioned in listing data — please ask the agent.'\n"
        "Return strict JSON only:\n"
        '{"answer": "string", "evidence_quote": "string or empty string"}'
    )
    payload = {
        "question": extraction_input,
        "listing_fields": {
            k: v for k, v in {
                "title":                distilled.get("title"),
                "address":              distilled.get("address"),
                "price_pcm":            distilled.get("price_pcm"),
                "bedrooms":             distilled.get("bedrooms"),
                "bathrooms":            distilled.get("bathrooms"),
                "available_from":       distilled.get("available_from"),
                "furnish_type":         distilled.get("furnish_type"),
                "let_type":             distilled.get("let_type"),
                "min_tenancy_months":   distilled.get("min_tenancy_months"),
                "size_sqm":             distilled.get("size_sqm"),
                "property_type":        distilled.get("property_type"),
                "nearest_station":      distilled.get("nearest_station"),
                "distance_to_station_m": distilled.get("distance_to_station_m"),
            }.items() if v is not None
        },
        "evidence_by_category": {
            cat: [{"field": e["field"], "text": e["text"]} for e in chunks[:3]]
            for cat, chunks in evidence_by_category.items()
            if chunks
        },
    }
    try:
        raw = qwen_chat(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            temperature=0.0,
        )
        cleaned = _strip_think_blocks(raw)
        obj = _extract_first_json_obj(cleaned)
        if obj and obj.get("answer"):
            answer = str(obj["answer"]).strip()
            quote = str(obj.get("evidence_quote") or "").strip()
            if quote:
                return f'{answer}\n\nEvidence: "{quote}"'
            return answer
        if cleaned:
            return cleaned
    except Exception:
        pass

    return "Not provided in listing data. Please ask the listing agent to confirm."


# ── Multi-listing QA ──────────────────────────────────────────────────────────

def answer_multi_listing_question(
    question: str,
    listings: List[Dict[str, Any]],
    embedder=None,
    qa_ctx: Optional[Dict[str, Any]] = None,
) -> str:
    rows = list(listings or [])
    if not rows:
        return "There are no listings to compare yet. Please run a search first."

    ctx = qa_ctx or build_qa_context(question)
    extraction_input = ctx["extraction_input"]
    signals = ctx["signals"]
    final_constraints = ctx.get("final_constraints") or {}

    # ── Deposit fast path — just show the actual value per listing ─────────────
    if final_constraints.get("deposit") is not None:
        lines = []
        for idx, payload in enumerate(rows, start=1):
            distilled = _distill_listing_payload(payload)
            title = str(distilled.get("title") or f"Listing {idx}")
            dep = _parse_deposit_amount(distilled.get("deposit"))
            if dep.get("state") != "known":
                lines.append(f"- Listing {idx} ({title}): not provided — ask agent")
            else:
                amount = float(dep.get("amount") or 0.0)
                txt = str(int(amount)) if float(amount).is_integer() else f"{amount:g}"
                if amount == 0.0:
                    lines.append(f"- Listing {idx} ({title}): no deposit (£0)")
                else:
                    lines.append(f"- Listing {idx} ({title}): £{txt}")
        lines.append("\nPlease confirm deposit details with the listing agent.")
        return "\n".join(lines)

    # ── Per-listing hybrid retrieval ───────────────────────────────────────────
    listings_data = []
    for idx, payload in enumerate(rows, start=1):
        distilled = _distill_listing_payload(payload)
        evidence_by_category = _retrieve_evidence(signals, distilled, embedder)
        listings_data.append({
            "index": idx,
            "title": str(distilled.get("title") or f"Listing {idx}"),
            "listing_fields": {
                k: v for k, v in {
                    "price_pcm":             distilled.get("price_pcm"),
                    "bedrooms":              distilled.get("bedrooms"),
                    "bathrooms":             distilled.get("bathrooms"),
                    "available_from":        distilled.get("available_from"),
                    "furnish_type":          distilled.get("furnish_type"),
                    "let_type":              distilled.get("let_type"),
                    "nearest_station":       distilled.get("nearest_station"),
                    "distance_to_station_m": distilled.get("distance_to_station_m"),
                }.items() if v is not None
            },
            "evidence_by_category": {
                cat: [{"field": e["field"], "text": e["text"]} for e in chunks[:2]]
                for cat, chunks in evidence_by_category.items()
                if chunks
            },
        })

    # ── LLM reasons over all listings' fields + evidence ──────────────────────
    system_prompt = (
        "You are a rental property QA assistant.\n"
        "For each listing, answer the question using ONLY its listing_fields and evidence_by_category.\n"
        "Format: one bullet per listing:\n"
        "  - Listing N (title): your answer, quoting specific evidence where helpful\n"
        "If no evidence for a listing, write: 'not mentioned in listing data — ask agent'.\n"
        "End with: 'Please confirm key details with the listing agent.'"
    )
    payload = {
        "question": extraction_input,
        "listings": listings_data,
    }
    try:
        raw = qwen_chat(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            temperature=0.0,
        )
        cleaned = _sanitize_list_output(_strip_think_blocks(raw))
        if cleaned:
            return cleaned
    except Exception:
        pass

    # Fallback: plain listing of top evidence
    lines = []
    for d in listings_data:
        all_ev = [e["text"] for chunks in d["evidence_by_category"].values() for e in chunks]
        if all_ev:
            lines.append(f"- Listing {d['index']} ({d['title']}): {all_ev[0]}")
        else:
            lines.append(f"- Listing {d['index']} ({d['title']}): not found in listing data")
    lines.append("Please confirm with the listing agent.")
    return "\n".join(lines)
