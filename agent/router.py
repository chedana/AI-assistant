import json
import re
from dataclasses import dataclass
from typing import Any, Dict, Optional

from core.llm_client import qwen_router_chat


@dataclass
class RouteDecision:
    intent: str
    reason: str
    target_index: Optional[int] = None
    refinement_type: Optional[str] = None
    confidence: float = 0.0
    need_clarify: bool = False
    clarify_question: Optional[str] = None


_INTENTS = {"Search", "Specific_QA", "Chitchat"}


def _extract_first_json_obj(raw_text: str) -> Optional[Dict[str, Any]]:
    if not raw_text:
        return None
    s = raw_text.strip()
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


_ORDINAL_WORD_MAP = {
    "first": 1,
    "second": 2,
    "third": 3,
    "fourth": 4,
    "fifth": 5,
    "sixth": 6,
    "seventh": 7,
    "eighth": 8,
    "ninth": 9,
    "tenth": 10,
}


def _extract_target_index(text: str, max_index: Optional[int] = None) -> Optional[int]:
    t = (text or "").strip().lower()
    if not t:
        return None
    # Strict index reference patterns to avoid matching constraint numbers
    # like "1 bed", "zone 2", "under 2500".
    patterns = [
        r"^#\s*(\d{1,2})\??$",
        r"^(?:the\s+)?(\d{1,2})(?:st|nd|rd|th)(?:\s+(?:one|listing|result|option|property|flat))?\??$",
        r"^(?:listing|result|option|property|flat)\s*#?\s*(\d{1,2})\??$",
        r"^(?:what about|how about|tell me about)\s+(?:listing|result|option|property|flat)\s*#?\s*(\d{1,2})\??$",
        r"^(?:no\.?|number)\s*(\d{1,2})\??$",
    ]
    for p in patterns:
        m = re.match(p, t)
        if not m:
            continue
        try:
            idx = int(m.group(1))
            if idx >= 1:
                return idx
        except Exception:
            continue
    for k, v in _ORDINAL_WORD_MAP.items():
        if re.match(rf"^(?:the\s+)?{k}(?:\s+(?:one|listing|result|option|property|flat))?\??$", t):
            if max_index is not None and v > max_index:
                return None
            return v
    return None


def _extract_target_index_in_text(text: str, max_index: Optional[int] = None) -> Optional[int]:
    t = (text or "").strip().lower()
    if not t:
        return None

    for k, v in _ORDINAL_WORD_MAP.items():
        if re.search(rf"\b(?:the\s+)?{k}\s+(?:one|listing|result|option|property|flat)\b", t):
            if max_index is not None and v > max_index:
                return None
            return v

    m_ord_num = re.search(r"\b(?:the\s+)?(\d{1,2})(?:st|nd|rd|th)\s+(?:one|listing|result|option|property|flat)\b", t)
    if m_ord_num:
        try:
            idx = int(m_ord_num.group(1))
            if idx >= 1 and (max_index is None or idx <= max_index):
                return idx
        except Exception:
            pass

    m = re.search(r"\b(?:listing|result|option|property|flat)\s*#?\s*(\d{1,2})\b", t)
    if m:
        try:
            idx = int(m.group(1))
            if idx >= 1 and (max_index is None or idx <= max_index):
                return idx
        except Exception:
            pass

    m_hash = re.search(r"(?<!\w)#\s*(\d{1,2})(?!\w)", t)
    if m_hash:
        try:
            idx = int(m_hash.group(1))
            if idx >= 1 and (max_index is None or idx <= max_index):
                return idx
        except Exception:
            pass
    return None


def _is_chitchat(text: str) -> bool:
    t = (text or "").strip().lower()
    if not t:
        return False
    # Mixed utterances like "hi, need a flat near waterloo" should not be
    # swallowed by chitchat rules.
    if _has_search_intent(t):
        return False
    return bool(re.search(r"\b(hello|hi|hey|thanks|thank you|good morning|good evening)\b", t))


def _has_search_intent(text: str) -> bool:
    t = (text or "").strip().lower()
    if not t:
        return False
    patterns = [
        r"\b(find|search|looking\s+for|need|want)\b",
        r"\b(flat|apartment|studio|house|property|listing)\b",
        r"\b(\d+\s*bed(room)?s?|\d+\s*b\d*)\b",
        r"\b(under|below|budget|pcm|pcw|rent)\b",
        r"\b(near|in|around)\s+[a-z0-9]",
    ]
    return any(re.search(p, t) for p in patterns)


def _is_reset(text: str) -> bool:
    t = (text or "").strip().lower()
    return bool(re.search(r"\b(start over|new search|reset|reset search|not looking anymore|stop searching)\b", t))


def _is_refinement_hint(text: str) -> bool:
    t = (text or "").strip().lower()
    # If this looks like a contextual detail question, do not treat as
    # refinement even if it contains amenity terms like "balcony/gym".
    if _looks_like_contextual_qa(t):
        return False
    return bool(
        re.search(
            r"\b(too expensive|cheaper|lower budget|change area|another area|different location|balcony|with gym|closer to station|not ground floor)\b",
            t,
        )
    )


def _looks_like_contextual_qa(text: str) -> bool:
    t = (text or "").strip().lower()
    if not t:
        return False
    question_starter = bool(
        re.search(r"^(does|do|is|are|has|have|what|which|how|where|when|can)\b", t)
        or "?" in t
    )
    if not question_starter:
        return False
    # Reference to an existing result/listing in context.
    has_reference = bool(
        re.search(
            r"\b(this|that|it|the last(?: one)?|last one|last listing|current listing|selected listing|one)\b",
            t,
        )
    )
    return has_reference


def _route_no_listings(text: str) -> RouteDecision:
    if _is_chitchat(text):
        return RouteDecision(intent="Chitchat", reason="rule:chitchat_no_listings", confidence=1.0)
    # Non-trivial inputs should go to LLM for better generalization.
    return RouteDecision(intent="Search", reason="defer_to_llm_no_listings", confidence=0.0)


def _classify_with_llm_no_listings(text: str, history_hint: Optional[str]) -> Optional[RouteDecision]:
    prompt = (
        "You are a router for a rental assistant.\n"
        "Current state always has_listings=false and has_focus=false.\n"
        "Return STRICT JSON only with schema:\n"
        '{"intent":"Search|Specific_QA|Chitchat","target_index":null,"confidence":0.0,"reason":"...",'
        '"need_clarify":false,"clarify_question":null,"refinement_type":null}\n'
        "Policy:\n"
        "- Without listings, Specific_QA is invalid and should generally map to Search.\n"
        "- Use Chitchat for greetings/small talk.\n"
        "- Use Search for search requests or filter statements.\n"
        "\n"
        "Few-shot:\n"
        "Query: 'How r you'\n"
        'Output: {"intent":"Chitchat","target_index":null,"confidence":0.92,"reason":"small_talk","need_clarify":false,"clarify_question":null,"refinement_type":null}\n'
        "Query: 'Find 1 bed near Waterloo under 2500'\n"
        'Output: {"intent":"Search","target_index":null,"confidence":0.96,"reason":"search_request","need_clarify":false,"clarify_question":null,"refinement_type":null}\n'
        "Query: 'Is it close to the station?'\n"
        'Output: {"intent":"Search","target_index":null,"confidence":0.84,"reason":"no_listing_context_for_qa","need_clarify":false,"clarify_question":null,"refinement_type":null}'
    )
    user_payload = f"Conversation summary:\n{history_hint or '(none)'}\n\nUser input:\n{text}"
    try:
        raw = qwen_router_chat(
            [
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_payload},
            ],
            temperature=0.0,
        ).strip()
    except Exception:
        return None
    obj = _extract_first_json_obj(raw)
    if not obj:
        return None

    intent = str(obj.get("intent") or "").strip()
    if intent not in _INTENTS:
        return None
    # Guardrail: no listings -> never QA.
    if intent == "Specific_QA":
        intent = "Search"

    try:
        conf = float(obj.get("confidence", 0.0))
    except Exception:
        conf = 0.0
    conf = max(0.0, min(1.0, conf))
    reason = str(obj.get("reason") or "llm_router_no_listings")
    need_clarify = bool(obj.get("need_clarify", False))
    clarify_question = obj.get("clarify_question")
    clarify_question = str(clarify_question).strip() if clarify_question is not None else None
    if clarify_question == "":
        clarify_question = None
    refinement_type = obj.get("refinement_type")
    refinement_type = str(refinement_type).strip().lower() if refinement_type is not None else None
    if refinement_type in {"", "none", "null"}:
        refinement_type = None

    # No listings: target index is always irrelevant.
    target_index = None
    if intent != "Search":
        refinement_type = None
    if not need_clarify:
        clarify_question = None
    return RouteDecision(
        intent=intent,
        reason=f"llm_no_listings:{reason}",
        target_index=target_index,
        refinement_type=refinement_type,
        confidence=conf,
        need_clarify=need_clarify,
        clarify_question=clarify_question,
    )


def _classify_with_llm_for_listings(text: str, history_hint: Optional[str]) -> Optional[RouteDecision]:
    prompt = (
        "You are a router for a rental assistant.\n"
        "Current state always has_listings=true.\n"
        "Return STRICT JSON only with schema:\n"
        '{"intent":"Search|Specific_QA|Chitchat","target_index":null,"confidence":0.0,"reason":"...",'
        '"need_clarify":false,"clarify_question":null,"refinement_type":null}\n'
        "Interpretation policy:\n"
        "- Search includes both new-search and refinement/reset actions.\n"
        "- Specific_QA is for detail questions about current results/listings.\n"
        "- target_index is 1-based when user references a specific result number.\n"
        "- If refinement request is underspecified (e.g., 'too expensive' without a target budget), set need_clarify=true.\n"
        "- If QA target is ambiguous, set need_clarify=true and ask which listing.\n"
        "- For clear price reduction requests, set intent=Search and refinement_type='price_down'.\n"
        "\n"
        "Few-shot:\n"
        "Query: 'too expensive, cheaper please'\n"
        'Output: {"intent":"Search","target_index":null,"confidence":0.97,"reason":"refinement_request","need_clarify":false,"clarify_question":null,"refinement_type":"price_down"}\n'
        "Query: 'does it have a gym?'\n"
        'Output: {"intent":"Specific_QA","target_index":null,"confidence":0.90,"reason":"detail_question_about_listing","need_clarify":true,"clarify_question":"Which listing do you mean?","refinement_type":null}\n'
        "Query: 'second one?'\n"
        'Output: {"intent":"Specific_QA","target_index":2,"confidence":0.96,"reason":"explicit_result_reference","need_clarify":false,"clarify_question":null,"refinement_type":null}\n'
        "Query: 'start over'\n"
        'Output: {"intent":"Search","target_index":null,"confidence":0.98,"reason":"reset_search","need_clarify":false,"clarify_question":null,"refinement_type":null}\n'
        "Query: 'thanks'\n"
        'Output: {"intent":"Chitchat","target_index":null,"confidence":0.95,"reason":"small_talk","need_clarify":false,"clarify_question":null,"refinement_type":null}'
    )
    user_payload = f"Conversation summary:\n{history_hint or '(none)'}\n\nUser input:\n{text}"
    try:
        raw = qwen_router_chat(
            [
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_payload},
            ],
            temperature=0.0,
        ).strip()
    except Exception:
        return None
    obj = _extract_first_json_obj(raw)
    if not obj:
        return None

    intent = str(obj.get("intent") or "").strip()
    if intent not in _INTENTS:
        return None
    try:
        conf = float(obj.get("confidence", 0.0))
    except Exception:
        conf = 0.0
    conf = max(0.0, min(1.0, conf))
    reason = str(obj.get("reason") or "llm_router")
    refinement_type = obj.get("refinement_type")
    refinement_type = str(refinement_type).strip().lower() if refinement_type is not None else None
    if refinement_type in {"", "none", "null"}:
        refinement_type = None
    need_clarify = bool(obj.get("need_clarify", False))
    clarify_question = obj.get("clarify_question")
    clarify_question = str(clarify_question).strip() if clarify_question is not None else None
    if clarify_question == "":
        clarify_question = None
    target_index = obj.get("target_index")
    try:
        target_index = int(target_index) if target_index is not None else None
        if target_index is not None and target_index < 1:
            target_index = None
    except Exception:
        target_index = None
    if intent != "Specific_QA":
        target_index = None
    if intent != "Search":
        refinement_type = None
    if not need_clarify:
        clarify_question = None
    return RouteDecision(
        intent=intent,
        reason=f"llm:{reason}",
        target_index=target_index,
        refinement_type=refinement_type,
        confidence=conf,
        need_clarify=need_clarify,
        clarify_question=clarify_question,
    )


def route_turn(
    user_text: str,
    mode: str = "assistant",
    history_hint: Optional[str] = None,
    has_listings: bool = False,
    has_focus: bool = False,
    listings_count: int = 0,
) -> RouteDecision:
    _ = (mode, has_focus)
    text = (user_text or "").strip()

    # Fixed, simple command rules.
    if text.lower() in {"/exit", "exit", "quit"}:
        return RouteDecision(intent="control", reason="rule:exit", confidence=1.0)
    if text.lower() in {"/state", "state"}:
        return RouteDecision(intent="control", reason="rule:state", confidence=1.0)
    m_focus = re.match(r"^/focus\s+(\d{1,2})\s*$", text.lower())
    if m_focus:
        return RouteDecision(intent="control", reason="rule:focus", target_index=int(m_focus.group(1)), confidence=1.0)

    # Decision Tree root: has_listings
    if not has_listings:
        quick = _route_no_listings(text)
        if quick.reason.startswith("rule:"):
            return quick
        llm_no_listings = _classify_with_llm_no_listings(text, history_hint=history_hint)
        if llm_no_listings is not None:
            return llm_no_listings
        return RouteDecision(intent="Search", reason="fallback:no_listings_default_search", confidence=0.25)

    # has_listings=True branch: cheap rules first.
    if _is_chitchat(text):
        return RouteDecision(intent="Chitchat", reason="rule:chitchat_with_listings", confidence=1.0)
    if _is_reset(text):
        return RouteDecision(intent="Search", reason="rule:reset_with_listings", confidence=1.0, refinement_type=None)

    max_index = listings_count if listings_count > 0 else None
    idx = _extract_target_index(text, max_index=max_index)
    if idx is not None:
        return RouteDecision(intent="Specific_QA", reason="rule:index_reference", target_index=idx, confidence=0.98)
    idx_inline = _extract_target_index_in_text(text, max_index=max_index)
    if idx_inline is not None and _looks_like_contextual_qa(text):
        return RouteDecision(
            intent="Specific_QA",
            reason="rule:inline_index_reference",
            target_index=idx_inline,
            confidence=0.97,
        )
    if _is_refinement_hint(text):
        return RouteDecision(
            intent="Search",
            reason="rule:refinement_with_listings",
            confidence=0.95,
            need_clarify=False,
            clarify_question=None,
            refinement_type="price_down" if re.search(r"\b(too expensive|cheaper|lower budget)\b", text.lower()) else None,
        )

    # Complex language goes to LLM.
    llm_decision = _classify_with_llm_for_listings(text, history_hint=history_hint)
    if llm_decision is not None:
        return llm_decision

    # Safe fallback with listings present: prefer Search.
    return RouteDecision(
        intent="Search",
        reason="fallback:search_with_listings",
        confidence=0.25,
        need_clarify=True,
        clarify_question="Could you clarify whether you want to refine filters or ask about a specific listing?",
    )
