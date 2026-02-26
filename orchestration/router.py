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
    page_action: Optional[str] = None


_INTENTS = {"Search", "Specific_QA", "Chitchat", "Page_Nav", "AcceptSuggestion", "Explain"}


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


def _classify_with_llm_no_listings(text: str, history_hint: Optional[str]) -> Optional[RouteDecision]:
    prompt = (
        "You are a router for a rental assistant.\n"
        "Current state always has_listings=false and has_focus=false.\n"
        "Return STRICT JSON only with schema:\n"
        '{"intent":"Search|Specific_QA|Chitchat|Page_Nav","target_index":null,"confidence":0.0,"reason":"...",'
        '"need_clarify":false,"clarify_question":null,"refinement_type":null,"page_action":null}\n'
        "Policy:\n"
        "- Without listings, Specific_QA is invalid and should generally map to Search.\n"
        "- If user asks to navigate pages, intent=Page_Nav with page_action='next' or 'prev'.\n"
        "- Use Chitchat for greetings/small talk.\n"
        "- Use Search for search requests or filter statements.\n"
        "\n"
        "Few-shot:\n"
        "Query: 'How r you'\n"
        'Output: {"intent":"Chitchat","target_index":null,"confidence":0.92,"reason":"small_talk","need_clarify":false,"clarify_question":null,"refinement_type":null}\n'
        "Query: 'Find 1 bed near Waterloo under 2500'\n"
        'Output: {"intent":"Search","target_index":null,"confidence":0.96,"reason":"search_request","need_clarify":false,"clarify_question":null,"refinement_type":null}\n'
        "Query: 'Is it close to the station?'\n"
        'Output: {"intent":"Search","target_index":null,"confidence":0.84,"reason":"no_listing_context_for_qa","need_clarify":false,"clarify_question":null,"refinement_type":null,"page_action":null}\n'
        "Query: 'show more'\n"
        'Output: {"intent":"Page_Nav","target_index":null,"confidence":0.95,"reason":"next_page_request","need_clarify":false,"clarify_question":null,"refinement_type":null,"page_action":"next"}'
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
    # Guardrail: no listings -> never QA or Explain.
    if intent == "Specific_QA":
        intent = "Search"
    if intent == "Explain":
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
    page_action = obj.get("page_action")
    page_action = str(page_action).strip().lower() if page_action is not None else None
    if page_action in {"", "none", "null"}:
        page_action = None
    if page_action not in {"next", "prev"}:
        page_action = None

    # No listings: target index is always irrelevant.
    target_index = None
    if intent != "Search":
        refinement_type = None
    if intent != "Page_Nav":
        page_action = None
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
        page_action=page_action,
    )


def _classify_with_llm_for_listings(
    text: str,
    history_hint: Optional[str],
    has_focus: bool,
    pending_suggestion_display: Optional[str] = None,
) -> Optional[RouteDecision]:
    suggestion_policy = ""
    suggestion_few_shot = ""
    if pending_suggestion_display:
        suggestion_policy = (
            f"- The assistant previously suggested: \"{pending_suggestion_display}\".\n"
            "- If the user is affirming that suggestion (e.g. 'yes', 'ok', 'do it', 'sure', 'go ahead',\n"
            "  'yes please', 'sounds good', 'raise it'), set intent=AcceptSuggestion.\n"
            "- Only use AcceptSuggestion when a pending suggestion exists AND the user is clearly accepting it.\n"
        )
        suggestion_few_shot = (
            f"[Pending: \"{pending_suggestion_display}\"]\n"
            "Query: 'yes do that'\n"
            '{"intent":"AcceptSuggestion","target_index":null,"confidence":0.97,"reason":"accepting_suggestion","need_clarify":false,"clarify_question":null,"refinement_type":null,"page_action":null}\n'
            f"[Pending: \"{pending_suggestion_display}\"]\n"
            "Query: 'ok'\n"
            '{"intent":"AcceptSuggestion","target_index":null,"confidence":0.93,"reason":"accepting_suggestion","need_clarify":false,"clarify_question":null,"refinement_type":null,"page_action":null}\n'
        )

    prompt = (
        "You are a router for a rental assistant.\n"
        f"Current state: has_listings=true, has_focus={'true' if has_focus else 'false'}.\n"
        "Return STRICT JSON only with schema:\n"
        '{"intent":"Search|Specific_QA|Chitchat|Page_Nav|AcceptSuggestion|Explain","target_index":null,"confidence":0.0,"reason":"...",'
        '"need_clarify":false,"clarify_question":null,"refinement_type":null,"page_action":null}\n'
        "Interpretation policy:\n"
        "- Search includes both new-search and refinement/reset actions.\n"
        "- Specific_QA is for detail questions about current results/listings.\n"
        "- Page_Nav is for paging requests.\n"
        "- Use page_action='next' for: 'next page', 'show more', 'more results', 'next batch'.\n"
        "- Use page_action='prev' for: 'previous page', 'prev page', 'go back', 'last page'.\n"
        "- target_index is 1-based when user references a specific result number.\n"
        "- If has_focus=true and user asks a listing detail question without index, keep intent=Specific_QA and need_clarify=false.\n"
        "- If has_focus=false and QA target is ambiguous, set need_clarify=true.\n"
        "- If refinement request is underspecified (e.g., 'too expensive' without a target budget), set need_clarify=true.\n"
        "- For clear price reduction requests, set intent=Search and refinement_type='price_down'.\n"
        "- Explain is for evaluation or comparison requests like 'which is best?', 'explain these', 'why did you recommend these?', 'compare them'.\n"
        + suggestion_policy +
        "\n"
        "Few-shot:\n"
        + suggestion_few_shot +
        "Query: 'too expensive, cheaper please'\n"
        '{"intent":"Search","target_index":null,"confidence":0.97,"reason":"refinement_request","need_clarify":false,"clarify_question":null,"refinement_type":"price_down","page_action":null}\n'
        "Query: 'does it have a gym?'\n"
        '{"intent":"Specific_QA","target_index":null,"confidence":0.90,"reason":"detail_question_about_listing","need_clarify":false,"clarify_question":null,"refinement_type":null,"page_action":null}\n'
        "Query: 'second one?'\n"
        '{"intent":"Specific_QA","target_index":2,"confidence":0.96,"reason":"explicit_result_reference","need_clarify":false,"clarify_question":null,"refinement_type":null,"page_action":null}\n'
        "Query: 'start over'\n"
        '{"intent":"Search","target_index":null,"confidence":0.98,"reason":"reset_search","need_clarify":false,"clarify_question":null,"refinement_type":null,"page_action":null}\n'
        "Query: 'thanks'\n"
        '{"intent":"Chitchat","target_index":null,"confidence":0.95,"reason":"small_talk","need_clarify":false,"clarify_question":null,"refinement_type":null,"page_action":null}\n'
        "Query: 'show me next page'\n"
        '{"intent":"Page_Nav","target_index":null,"confidence":0.96,"reason":"next_page_request","need_clarify":false,"clarify_question":null,"refinement_type":null,"page_action":"next"}\n'
        "Query: 'go to previous page'\n"
        '{"intent":"Page_Nav","target_index":null,"confidence":0.96,"reason":"prev_page_request","need_clarify":false,"clarify_question":null,"refinement_type":null,"page_action":"prev"}\n'
        "Query: 'which one is best?'\n"
        '{"intent":"Explain","target_index":null,"confidence":0.93,"reason":"evaluation_request","need_clarify":false,"clarify_question":null,"refinement_type":null,"page_action":null}\n'
        "Query: 'explain these results'\n"
        '{"intent":"Explain","target_index":null,"confidence":0.95,"reason":"evaluation_request","need_clarify":false,"clarify_question":null,"refinement_type":null,"page_action":null}\n'
        "Query: 'why did you recommend these?'\n"
        '{"intent":"Explain","target_index":null,"confidence":0.91,"reason":"evaluation_request","need_clarify":false,"clarify_question":null,"refinement_type":null,"page_action":null}'
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
    page_action = obj.get("page_action")
    page_action = str(page_action).strip().lower() if page_action is not None else None
    if page_action in {"", "none", "null"}:
        page_action = None
    if page_action not in {"next", "prev"}:
        page_action = None
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
    if intent != "Page_Nav":
        page_action = None
    elif page_action is None:
        page_action = "next"
    if intent == "Specific_QA" and has_focus and target_index is None:
        need_clarify = False
        clarify_question = None
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
        page_action=page_action,
    )


def route_turn(
    user_text: str,
    mode: str = "assistant",
    history_hint: Optional[str] = None,
    has_listings: bool = False,
    has_focus: bool = False,
    listings_count: int = 0,
    pending_suggestion_display: Optional[str] = None,
) -> RouteDecision:
    _ = mode
    text = (user_text or "").strip()

    # Fixed, simple command rules.
    if text.lower() in {"/exit", "exit", "quit"}:
        return RouteDecision(intent="control", reason="rule:exit", confidence=1.0)
    if text.lower() in {"/state", "state"}:
        return RouteDecision(intent="control", reason="rule:state", confidence=1.0)
    m_focus = re.match(r"^/focus\s+(\d{1,2})\s*$", text.lower())
    if m_focus:
        return RouteDecision(intent="control", reason="rule:focus", target_index=int(m_focus.group(1)), confidence=1.0)

    # After command parsing, route by LLM only.
    if not has_listings:
        llm_no_listings = _classify_with_llm_no_listings(text, history_hint=history_hint)
        if llm_no_listings is not None:
            return llm_no_listings
        return RouteDecision(intent="Search", reason="fallback:no_listings_default_search", confidence=0.25)

    # has_listings=True: LLM intent routing only.
    llm_decision = _classify_with_llm_for_listings(
        text,
        history_hint=history_hint,
        has_focus=has_focus,
        pending_suggestion_display=pending_suggestion_display,
    )
    if llm_decision is not None:
        return llm_decision

    # LLM fallback with listings present.
    return RouteDecision(
        intent="Search",
        reason="fallback:search_with_listings",
        confidence=0.25,
        need_clarify=True,
        clarify_question="Could you clarify whether you want to refine filters or ask about a specific listing?",
    )
