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
    confidence: float = 0.0


_INTENTS = {"Search", "Specific_QA", "Refinement", "Chitchat"}


def _heuristic_route(user_text: str) -> str:
    t = (user_text or "").strip().lower()
    if not t:
        return "Chitchat"

    if re.search(r"\b(too expensive|cheaper|budget|change to|switch to|not ground floor|avoid ground floor)\b", t):
        return "Refinement"
    if re.search(r"\b(this one|this flat|that one|distance|pet|subway|metro|station|how far|near)\b", t):
        return "Specific_QA"
    if re.search(r"\b(hello|hi|thanks|thank you|hey)\b", t):
        return "Chitchat"
    return "Search"


def _extract_target_index_rule(user_text: str) -> Optional[int]:
    t = (user_text or "").strip().lower()
    if not t:
        return None
    m = re.search(r"(?:^|[\s#])(\d{1,2})(?:st|nd|rd|th)?(?:\s*(?:one|listing|result|option|flat|property))?\b", t)
    if m:
        try:
            idx = int(m.group(1))
            if idx >= 1:
                return idx
        except Exception:
            pass
    ord_map = {
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
    for k, v in ord_map.items():
        if re.search(rf"\b{k}\b", t):
            return v
    return None


def _should_force_specific_qa(user_text: str, has_focus: bool) -> bool:
    if not has_focus:
        return False
    t = (user_text or "").strip().lower()
    if not t:
        return False
    qa_cues = [
        "how far",
        "distance",
        "can i",
        "is it",
        "does it",
        "pet",
        "furnished",
        "deposit",
        "council tax",
        "nearest station",
        "this place",
        "this one",
        "that one",
        "how far",
        "near station",
    ]
    return any(cue in t for cue in qa_cues)


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
                chunk = s[start : i + 1]
                try:
                    obj = json.loads(chunk)
                    if isinstance(obj, dict):
                        return obj
                except Exception:
                    return None
    return None


def _classify_intent_with_llm(
    user_text: str,
    history_hint: Optional[str] = None,
    has_listings: bool = False,
    has_focus: bool = False,
) -> Optional[Dict[str, Any]]:
    prompt = (
        "You are an intent router for a rental assistant.\n"
        "Return STRICT JSON only with this schema:\n"
        '{"intent":"Search|Specific_QA|Refinement|Chitchat","target_index":null,"confidence":0.0,"reason":"..."}\n'
        "Rules:\n"
        "- target_index is 1-based when user references a result number; else null.\n"
        "- confidence must be between 0 and 1.\n"
        "- If the user asks about the current listing details, use Specific_QA.\n"
        "- If the user changes constraints or asks for cheaper/different options, use Refinement.\n"
        "- If user starts a new search request, use Search.\n"
        "- If greeting/thanks/small talk, use Chitchat.\n"
        "\n"
        "Few-shot examples:\n"
        "Input: has_listings=false, has_focus=false, query='Does it have a gym?'\n"
        'Output: {"intent":"Search","target_index":null,"confidence":0.86,"reason":"No current listing context, treat as search filter."}\n'
        "Input: has_listings=true, has_focus=true, query='Does it have a gym?'\n"
        'Output: {"intent":"Specific_QA","target_index":null,"confidence":0.93,"reason":"Question about details of current listing."}\n'
        "Input: has_listings=true, has_focus=false, query='second one?'\n"
        'Output: {"intent":"Specific_QA","target_index":2,"confidence":0.95,"reason":"User references listing #2 for follow-up."}\n'
        "Input: has_listings=true, has_focus=true, query='too expensive, cheaper please'\n"
        'Output: {"intent":"Refinement","target_index":null,"confidence":0.97,"reason":"Budget refinement request."}\n'
        "Input: has_listings=true, has_focus=true, query='start over, new search in Waterloo'\n"
        'Output: {"intent":"Search","target_index":null,"confidence":0.97,"reason":"Explicit new search intent."}'
    )
    user_payload = (
        f"State:\n- has_listings={str(bool(has_listings)).lower()}\n- has_focus={str(bool(has_focus)).lower()}\n\n"
        f"Conversation summary:\n{history_hint or '(none)'}\n\nUser input:\n{user_text}"
    )
    try:
        out = qwen_router_chat(
            [
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_payload},
            ],
            temperature=0.0,
        ).strip()
    except Exception:
        return None

    obj = _extract_first_json_obj(out)
    if not obj:
        return None
    intent = str(obj.get("intent") or "").strip()
    if intent not in _INTENTS:
        return None
    conf_raw = obj.get("confidence", 0.0)
    try:
        confidence = float(conf_raw)
    except Exception:
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))
    target_index = obj.get("target_index")
    try:
        target_index = int(target_index) if target_index is not None else None
        if target_index is not None and target_index < 1:
            target_index = None
    except Exception:
        target_index = None
    reason = str(obj.get("reason") or "llm_router")
    return {
        "intent": intent,
        "confidence": confidence,
        "target_index": target_index,
        "reason": reason,
    }


def _is_reset_search(user_text: str) -> bool:
    t = (user_text or "").strip().lower()
    if not t:
        return False
    return bool(re.search(r"\b(start over|new search|reset search|ignore previous|from scratch)\b", t))


def _default_decision(intent: str, reason: str, target_index: Optional[int] = None, confidence: float = 0.7) -> RouteDecision:
    return RouteDecision(intent=intent, reason=reason, target_index=target_index, confidence=confidence)


def _post_check_override(intent: str, user_text: str, has_focus: bool) -> str:
    t = (user_text or "").strip().lower()
    if intent == "Search" and has_focus and ("?" in t or _should_force_specific_qa(t, has_focus=True)):
        return "Specific_QA"
    return intent


def _fallback_route(user_text: str, has_focus: bool) -> RouteDecision:
    intent = _heuristic_route(user_text)
    intent = _post_check_override(intent, user_text, has_focus=has_focus)
    idx = _extract_target_index_rule(user_text) if intent == "Specific_QA" else None
    return _default_decision(intent=intent, reason="heuristic_fallback", target_index=idx, confidence=0.51)


def _route_by_rules(user_text: str, has_focus: bool) -> Optional[RouteDecision]:
    t = (user_text or "").strip()
    if t.startswith("/"):
        return _default_decision(intent="control", reason="command", confidence=1.0)
    if _is_reset_search(t):
        return _default_decision(intent="Search", reason="explicit_new_search", confidence=1.0)
    idx = _extract_target_index_rule(t)
    if idx is not None:
        return _default_decision(intent="Specific_QA", reason="explicit_index_reference", target_index=idx, confidence=0.98)
    if _should_force_specific_qa(t, has_focus=has_focus):
        return _default_decision(intent="Specific_QA", reason="focus_qa_override", confidence=0.95)
    return None


def route_turn(
    user_text: str,
    mode: str = "assistant",
    history_hint: Optional[str] = None,
    has_listings: bool = False,
    has_focus: bool = False,
) -> RouteDecision:
    t = (user_text or "").strip()
    rule_hit = _route_by_rules(t, has_focus=has_focus)
    if rule_hit is not None:
        return rule_hit

    llm_out = _classify_intent_with_llm(
        user_text=t,
        history_hint=history_hint,
        has_listings=has_listings,
        has_focus=has_focus,
    )
    if llm_out:
        intent = _post_check_override(llm_out["intent"], t, has_focus=has_focus)
        target_index = llm_out.get("target_index")
        if intent != "Specific_QA":
            target_index = None
        return _default_decision(
            intent=intent,
            reason=f"llm_classifier:{llm_out.get('reason', 'ok')}",
            target_index=target_index,
            confidence=float(llm_out.get("confidence", 0.0)),
        )

    return _fallback_route(t, has_focus=has_focus)
