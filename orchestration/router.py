import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core.llm_client import qwen_router_chat


@dataclass
class RouteDecision:
    intent: str
    reason: str
    target_indices: List[int] = field(default_factory=list)
    target_areas: List[str] = field(default_factory=list)
    shortlist_action: Optional[str] = None
    refinement_type: Optional[str] = None
    confidence: float = 0.0
    need_clarify: bool = False
    clarify_question: Optional[str] = None
    page_action: Optional[str] = None


_INTENTS = {"Search", "Specific_QA", "Compare", "AreaCompare", "Shortlist", "Chitchat", "Page_Nav", "AcceptSuggestion", "Explain"}


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


def _classify_with_llm_no_listings(
    text: str,
    history_hint: Optional[str],
    pending_area_compare_areas: Optional[List[str]] = None,
) -> Optional[RouteDecision]:
    prompt = (
        "You are a router for a rental assistant.\n"
        "Current state always has_listings=false and has_focus=false.\n"
        "Return STRICT JSON only with schema:\n"
        '{"intent":"Search|Specific_QA|Chitchat|Page_Nav|AreaCompare|Shortlist","shortlist_action":null,"target_areas":[],"confidence":0.0,"reason":"...",'
        '"need_clarify":false,"clarify_question":null,"refinement_type":null,"page_action":null}\n'
        "Policy:\n"
        "- Without listings, Specific_QA is invalid and should generally map to Search.\n"
        "- If user asks to navigate pages, intent=Page_Nav with page_action='next' or 'prev'.\n"
        "- Use Chitchat for greetings/small talk.\n"
        "- Use Search for search requests or filter statements.\n"
        "- Use AreaCompare when user wants to compare rental prices or availability across multiple areas "
        "(e.g. 'Is Hackney cheaper than Peckham?', 'compare rents in zone 2 vs zone 3'). "
        "Set target_areas to the list of area names mentioned.\n"
        "- Use Shortlist when user manages saved listings: shortlist_action='show' (show my shortlist/saved), "
        "'clear' (clear all saved). shortlist_action='add'/'remove' are valid only when listings exist.\n"
        "\n"
        "Few-shot:\n"
        "Query: 'How r you'\n"
        'Output: {"intent":"Chitchat","shortlist_action":null,"target_areas":[],"confidence":0.92,"reason":"small_talk","need_clarify":false,"clarify_question":null,"refinement_type":null}\n'
        "Query: 'Find 1 bed near Waterloo under 2500'\n"
        'Output: {"intent":"Search","shortlist_action":null,"target_areas":[],"confidence":0.96,"reason":"search_request","need_clarify":false,"clarify_question":null,"refinement_type":null}\n'
        "Query: 'show more'\n"
        'Output: {"intent":"Page_Nav","shortlist_action":null,"target_areas":[],"confidence":0.95,"reason":"next_page_request","need_clarify":false,"clarify_question":null,"refinement_type":null,"page_action":"next"}\n'
        "Query: 'Is Hackney cheaper than Peckham?'\n"
        'Output: {"intent":"AreaCompare","shortlist_action":null,"target_areas":["Hackney","Peckham"],"confidence":0.95,"reason":"area_price_comparison","need_clarify":false,"clarify_question":null,"refinement_type":null,"page_action":null}\n'
        "Query: 'show my shortlist'\n"
        'Output: {"intent":"Shortlist","shortlist_action":"show","target_areas":[],"confidence":0.97,"reason":"show_saved_listings","need_clarify":false,"clarify_question":null,"refinement_type":null,"page_action":null}\n'
        "Query: 'clear my saved listings'\n"
        'Output: {"intent":"Shortlist","shortlist_action":"clear","target_areas":[],"confidence":0.96,"reason":"clear_shortlist","need_clarify":false,"clarify_question":null,"refinement_type":null,"page_action":null}'
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
    # Guardrail: no listings -> never QA, Explain, or Compare.
    if intent == "Specific_QA":
        intent = "Search"
    if intent == "Explain":
        intent = "Search"
    if intent == "Compare":
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
    raw_areas = obj.get("target_areas") or []
    try:
        target_areas = [str(a).strip() for a in raw_areas if str(a).strip()]
    except Exception:
        target_areas = []
    if intent != "AreaCompare":
        target_areas = []
    shortlist_action = obj.get("shortlist_action")
    shortlist_action = str(shortlist_action).strip().lower() if shortlist_action is not None else None
    if shortlist_action in {"", "none", "null"}:
        shortlist_action = None
    if shortlist_action not in {"add", "remove", "show", "clear"}:
        shortlist_action = None
    if intent != "Shortlist":
        shortlist_action = None
    if intent != "Search":
        refinement_type = None
    if intent != "Page_Nav":
        page_action = None
    if not need_clarify:
        clarify_question = None
    return RouteDecision(
        intent=intent,
        reason=f"llm_no_listings:{reason}",
        target_areas=target_areas,
        shortlist_action=shortlist_action,
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
    pending_area_compare_areas: Optional[List[str]] = None,
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
            '{"intent":"AcceptSuggestion","confidence":0.97,"reason":"accepting_suggestion","need_clarify":false,"clarify_question":null,"refinement_type":null,"page_action":null}\n'
            f"[Pending: \"{pending_suggestion_display}\"]\n"
            "Query: 'ok'\n"
            '{"intent":"AcceptSuggestion","confidence":0.93,"reason":"accepting_suggestion","need_clarify":false,"clarify_question":null,"refinement_type":null,"page_action":null}\n'
            f"[Pending: \"{pending_suggestion_display}\"]\n"
            "Query: 'no thanks, show me cheaper areas instead'\n"
            '{"intent":"Search","confidence":0.95,"reason":"rejecting_suggestion_new_search","need_clarify":false,"clarify_question":null,"refinement_type":null,"page_action":null}\n'
            f"[Pending: \"{pending_suggestion_display}\"]\n"
            "Query: 'not really, maybe try a different location'\n"
            '{"intent":"Search","confidence":0.92,"reason":"rejecting_suggestion_redirect","need_clarify":false,"clarify_question":null,"refinement_type":null,"page_action":null}\n'
        )

    prompt = (
        "You are a router for a rental assistant.\n"
        f"Current state: has_listings=true, has_focus={'true' if has_focus else 'false'}.\n"
        "Return STRICT JSON only with schema:\n"
        '{"intent":"Search|Specific_QA|Compare|AreaCompare|Shortlist|Chitchat|Page_Nav|AcceptSuggestion|Explain","shortlist_action":null,"target_indices":[],"target_areas":[],"confidence":0.0,"reason":"...",'
        '"need_clarify":false,"clarify_question":null,"refinement_type":null,"page_action":null}\n'
        "Interpretation policy:\n"
        "- Search includes both new-search and refinement/reset actions.\n"
        "- Specific_QA is for detail questions about current results/listings.\n"
        "- Page_Nav is for paging requests.\n"
        "- Use page_action='next' for: 'next page', 'show more', 'more results', 'next batch'.\n"
        "- Use page_action='prev' for: 'previous page', 'prev page', 'go back', 'last page'.\n"
        "- For a single listing reference in QA, use target_indices=[N] (e.g. 'second listing' → target_indices=[2]).\n"
        "- Compare is for structured side-by-side comparison: 'compare listing 1 and 3', 'listing 2 vs 4', 'difference between 1 and 2'. Set target_indices to the 1-based indices mentioned. If no specific indices given, leave target_indices as [].\n"
        "- AreaCompare is for comparing rental prices/availability across multiple geographic areas "
        "(e.g. 'Is Hackney cheaper than Peckham?', 'compare rents in zone 2 vs zone 3'). "
        "Set target_areas to the list of area names mentioned.\n"
        "- Explain is for holistic evaluation without 'compare' keyword: 'which is best?', 'explain these results', 'why recommend these?'.\n"
        "- Specific_QA with multiple listings: e.g. 'do listing 1 and 2 allow pets?'. Set target_indices=[1,2].\n"
        "- If has_focus=true and user asks a listing detail question without index, keep intent=Specific_QA and need_clarify=false.\n"
        "- If has_focus=false and QA target is ambiguous, set need_clarify=true.\n"
        "- If refinement request is underspecified (e.g., 'too expensive' without a target budget), set need_clarify=true.\n"
        "- For clear price reduction requests, set intent=Search and refinement_type='price_down'.\n"
        "- Use Shortlist when user manages saved listings: shortlist_action='add' (save/bookmark listing N — set target_indices=[N]), "
        "'remove' (remove shortlist item N — set target_indices=[N]), "
        "'show' (show my shortlist/saved), 'clear' (clear all saved).\n"
        + suggestion_policy
        + "\n"
        "Few-shot:\n"
        + suggestion_few_shot
        + "Query: 'too expensive, cheaper please'\n"
        '{"intent":"Search","confidence":0.97,"reason":"refinement_request","need_clarify":false,"clarify_question":null,"refinement_type":"price_down","page_action":null}\n'
        "Query: 'does it have a gym?'\n"
        '{"intent":"Specific_QA","confidence":0.90,"reason":"detail_question_about_listing","need_clarify":false,"clarify_question":null,"refinement_type":null,"page_action":null}\n'
        "Query: 'second one?'\n"
        '{"intent":"Specific_QA","target_indices":[2],"confidence":0.96,"reason":"explicit_result_reference","need_clarify":false,"clarify_question":null,"refinement_type":null,"page_action":null}\n'
        "Query: 'start over'\n"
        '{"intent":"Search","confidence":0.98,"reason":"reset_search","need_clarify":false,"clarify_question":null,"refinement_type":null,"page_action":null}\n'
        "Query: 'thanks'\n"
        '{"intent":"Chitchat","confidence":0.95,"reason":"small_talk","need_clarify":false,"clarify_question":null,"refinement_type":null,"page_action":null}\n'
        "Query: 'show me next page'\n"
        '{"intent":"Page_Nav","confidence":0.96,"reason":"next_page_request","need_clarify":false,"clarify_question":null,"refinement_type":null,"page_action":"next"}\n'
        "Query: 'go to previous page'\n"
        '{"intent":"Page_Nav","confidence":0.96,"reason":"prev_page_request","need_clarify":false,"clarify_question":null,"refinement_type":null,"page_action":"prev"}\n'
        "Query: 'which one is best?'\n"
        '{"intent":"Explain","target_indices":[],"confidence":0.93,"reason":"evaluation_request","need_clarify":false,"clarify_question":null,"refinement_type":null,"page_action":null}\n'
        "Query: 'explain these results'\n"
        '{"intent":"Explain","target_indices":[],"confidence":0.95,"reason":"evaluation_request","need_clarify":false,"clarify_question":null,"refinement_type":null,"page_action":null}\n'
        "Query: 'why did you recommend these?'\n"
        '{"intent":"Explain","target_indices":[],"confidence":0.91,"reason":"evaluation_request","need_clarify":false,"clarify_question":null,"refinement_type":null,"page_action":null}\n'
        "Query: 'compare listing 1 and 3'\n"
        '{"intent":"Compare","target_indices":[1,3],"confidence":0.97,"reason":"structured_comparison","need_clarify":false,"clarify_question":null,"refinement_type":null,"page_action":null}\n'
        "Query: 'listing 2 vs 4'\n"
        '{"intent":"Compare","target_indices":[2,4],"confidence":0.96,"reason":"structured_comparison","need_clarify":false,"clarify_question":null,"refinement_type":null,"page_action":null}\n'
        "Query: 'what is the difference between 1 and 2?'\n"
        '{"intent":"Compare","target_indices":[1,2],"confidence":0.94,"reason":"structured_comparison","need_clarify":false,"clarify_question":null,"refinement_type":null,"page_action":null}\n'
        "Query: 'compare all of them'\n"
        '{"intent":"Compare","target_indices":[],"confidence":0.92,"reason":"structured_comparison_all","need_clarify":false,"clarify_question":null,"refinement_type":null,"page_action":null}\n'
        "Query: 'do listing 1 and 2 allow pets?'\n"
        '{"intent":"Specific_QA","target_indices":[1,2],"confidence":0.92,"reason":"multi_listing_qa","need_clarify":false,"clarify_question":null,"refinement_type":null,"page_action":null}\n'
        "Query: 'do the first and second allow pets?'\n"
        '{"intent":"Specific_QA","target_indices":[1,2],"confidence":0.91,"reason":"multi_listing_qa_ordinal","need_clarify":false,"clarify_question":null,"refinement_type":null,"page_action":null}\n'
        "Query: 'does the third one have a garden?'\n"
        '{"intent":"Specific_QA","target_indices":[3],"confidence":0.93,"reason":"explicit_result_reference_ordinal","need_clarify":false,"clarify_question":null,"refinement_type":null,"page_action":null}\n'
        "Query: 'Is Hackney cheaper than Peckham for a 2 bed?'\n"
        '{"intent":"AreaCompare","target_indices":[],"target_areas":["Hackney","Peckham"],"confidence":0.96,"reason":"area_price_comparison","need_clarify":false,"clarify_question":null,"refinement_type":null,"page_action":null}\n'
        "Query: 'which area is more affordable, Brixton or Clapham?'\n"
        '{"intent":"AreaCompare","target_indices":[],"target_areas":["Brixton","Clapham"],"confidence":0.94,"reason":"area_price_comparison","need_clarify":false,"clarify_question":null,"refinement_type":null,"page_action":null}\n'
        "Query: 'save listing 2'\n"
        '{"intent":"Shortlist","shortlist_action":"add","target_indices":[2],"target_areas":[],"confidence":0.97,"reason":"save_listing","need_clarify":false,"clarify_question":null,"refinement_type":null,"page_action":null}\n'
        "Query: 'bookmark listing 1 and 3'\n"
        '{"intent":"Shortlist","shortlist_action":"add","target_indices":[1,3],"target_areas":[],"confidence":0.95,"reason":"save_listings","need_clarify":false,"clarify_question":null,"refinement_type":null,"page_action":null}\n'
        "Query: 'show my shortlist'\n"
        '{"intent":"Shortlist","shortlist_action":"show","target_indices":[],"target_areas":[],"confidence":0.97,"reason":"show_saved","need_clarify":false,"clarify_question":null,"refinement_type":null,"page_action":null}\n'
        "Query: 'remove shortlist 2'\n"
        '{"intent":"Shortlist","shortlist_action":"remove","target_indices":[2],"target_areas":[],"confidence":0.95,"reason":"remove_saved","need_clarify":false,"clarify_question":null,"refinement_type":null,"page_action":null}\n'
        "Query: 'clear my shortlist'\n"
        '{"intent":"Shortlist","shortlist_action":"clear","target_indices":[],"target_areas":[],"confidence":0.96,"reason":"clear_shortlist","need_clarify":false,"clarify_question":null,"refinement_type":null,"page_action":null}'
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
    raw_indices = obj.get("target_indices") or []
    try:
        target_indices = [int(x) for x in raw_indices if isinstance(x, (int, float)) and int(x) >= 1]
    except Exception:
        target_indices = []
    if intent not in {"Compare", "Specific_QA", "Shortlist"}:
        target_indices = []
    raw_areas = obj.get("target_areas") or []
    try:
        target_areas = [str(a).strip() for a in raw_areas if str(a).strip()]
    except Exception:
        target_areas = []
    if intent != "AreaCompare":
        target_areas = []
    shortlist_action = obj.get("shortlist_action")
    shortlist_action = str(shortlist_action).strip().lower() if shortlist_action is not None else None
    if shortlist_action in {"", "none", "null"}:
        shortlist_action = None
    if shortlist_action not in {"add", "remove", "show", "clear"}:
        shortlist_action = None
    if intent != "Shortlist":
        shortlist_action = None
    if intent != "Search":
        refinement_type = None
    if intent != "Page_Nav":
        page_action = None
    elif page_action is None:
        page_action = "next"
    if intent == "Specific_QA" and has_focus and not target_indices:
        need_clarify = False
        clarify_question = None
    if not need_clarify:
        clarify_question = None
    return RouteDecision(
        intent=intent,
        reason=f"llm:{reason}",
        target_indices=target_indices,
        target_areas=target_areas,
        shortlist_action=shortlist_action,
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
    pending_area_compare_areas: Optional[List[str]] = None,
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
        return RouteDecision(intent="control", reason="rule:focus", target_indices=[int(m_focus.group(1))], confidence=1.0)

    # After command parsing, route by LLM only.
    if not has_listings:
        llm_no_listings = _classify_with_llm_no_listings(
            text,
            history_hint=history_hint,
            pending_area_compare_areas=pending_area_compare_areas,
        )
        if llm_no_listings is not None:
            return llm_no_listings
        return RouteDecision(intent="Search", reason="fallback:no_listings_default_search", confidence=0.25)

    # has_listings=True: LLM intent routing only.
    llm_decision = _classify_with_llm_for_listings(
        text,
        history_hint=history_hint,
        has_focus=has_focus,
        pending_suggestion_display=pending_suggestion_display,
        pending_area_compare_areas=pending_area_compare_areas,
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
