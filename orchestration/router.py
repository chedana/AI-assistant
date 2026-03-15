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


_INTENTS = {"Search", "Specific_QA", "Compare", "AreaCompare", "Shortlist", "Chitchat", "Page_Nav", "AcceptSuggestion", "Explain", "TenantRights"}


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
        "Rental assistant router. State: has_listings=false, has_focus=false.\n"
        "Return STRICT JSON. Omit null values, empty arrays, and false booleans.\n"
        "Fields: intent(Search|Chitchat|Page_Nav|AreaCompare|Shortlist|TenantRights), confidence(0-1), reason(string), "
        "target_areas(string[]), shortlist_action(show|clear), page_action(next|prev), refinement_type(string).\n"
        "Policy: Without listings, QA/Compare/Explain→Search. Chitchat for greetings. "
        "AreaCompare for cross-area price comparison (set target_areas). "
        "TenantRights for legal questions about landlord obligations, eviction, deposits, repairs, tenancy law. "
        "Shortlist: show/clear only (add/remove need listings). Page_Nav for paging.\n"
        "\n"
        'Q: \'How r you\' → {"intent":"Chitchat","confidence":0.92,"reason":"small_talk"}\n'
        'Q: \'Find 1 bed near Waterloo under 2500\' → {"intent":"Search","confidence":0.96,"reason":"search_request"}\n'
        'Q: \'show more\' → {"intent":"Page_Nav","confidence":0.95,"reason":"next_page","page_action":"next"}\n'
        'Q: \'Is Hackney cheaper than Peckham?\' → {"intent":"AreaCompare","target_areas":["Hackney","Peckham"],"confidence":0.95,"reason":"area_comparison"}\n'
        'Q: \'show my shortlist\' → {"intent":"Shortlist","shortlist_action":"show","confidence":0.97,"reason":"show_saved"}\n'
        'Q: \'what are my rights if the landlord won\\\'t fix the boiler\' → {"intent":"TenantRights","confidence":0.96,"reason":"tenant_rights_repairs"}\n'
        'Q: \'can my landlord evict me for having a pet\' → {"intent":"TenantRights","confidence":0.95,"reason":"tenant_rights_eviction"}\n'
        'Q: \'is my deposit protected\' → {"intent":"TenantRights","confidence":0.97,"reason":"tenant_rights_deposit"}\n'
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
    # Never ask clarification before running a first search — just search.
    if intent == "Search":
        need_clarify = False
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
            f"Pending suggestion: \"{pending_suggestion_display}\". "
            "If user affirms (yes/ok/sure/do it/go ahead), intent=AcceptSuggestion. "
            "If user rejects or redirects, intent=Search.\n"
        )
        suggestion_few_shot = (
            f'Q: \'yes do that\' [pending] → {{"intent":"AcceptSuggestion","confidence":0.97,"reason":"accepting"}}\n'
            f'Q: \'no thanks\' [pending] → {{"intent":"Search","confidence":0.95,"reason":"rejecting_suggestion"}}\n'
        )

    prompt = (
        "Rental assistant router. State: has_listings=true, "
        f"has_focus={'true' if has_focus else 'false'}.\n"
        "Return STRICT JSON. Omit null values, empty arrays, and false booleans.\n"
        "Fields: intent(Search|Specific_QA|Compare|AreaCompare|Shortlist|Chitchat|Page_Nav|AcceptSuggestion|Explain|TenantRights), "
        "confidence(0-1), reason(string), target_indices(int[]), target_areas(string[]), "
        "shortlist_action(add|remove|show|clear), refinement_type(string), page_action(next|prev), "
        "need_clarify(bool), clarify_question(string).\n"
        "Policy: Search=new/refine/reset. Specific_QA=detail questions (set target_indices=[N]). "
        "Compare=side-by-side (set target_indices). Explain=holistic eval (which is best?, why these?). "
        "AreaCompare=cross-area price comparison (set target_areas). "
        "Page_Nav=paging (page_action=next/prev). "
        "Shortlist: add/remove (target_indices=[N]), show, clear. "
        "TenantRights=legal questions about landlord obligations, eviction, deposits, repairs, tenancy law. "
        "Chitchat=greetings/thanks. "
        "If has_focus=true, QA without index→Specific_QA. "
        "If ambiguous QA target and no focus, need_clarify=true. "
        "Price reduction→Search+refinement_type='price_down'.\n"
        + suggestion_policy
        + "\n"
        + suggestion_few_shot
        + 'Q: \'too expensive\' → {"intent":"Search","confidence":0.97,"reason":"refinement","refinement_type":"price_down"}\n'
        'Q: \'does it have a gym?\' → {"intent":"Specific_QA","confidence":0.90,"reason":"detail_question"}\n'
        'Q: \'second one?\' → {"intent":"Specific_QA","target_indices":[2],"confidence":0.96,"reason":"listing_ref"}\n'
        'Q: \'do listing 1 and 2 allow pets?\' → {"intent":"Specific_QA","target_indices":[1,2],"confidence":0.92,"reason":"multi_qa"}\n'
        'Q: \'start over\' → {"intent":"Search","confidence":0.98,"reason":"reset"}\n'
        'Q: \'thanks\' → {"intent":"Chitchat","confidence":0.95,"reason":"small_talk"}\n'
        'Q: \'show more\' → {"intent":"Page_Nav","confidence":0.96,"reason":"next_page","page_action":"next"}\n'
        'Q: \'go back\' → {"intent":"Page_Nav","confidence":0.96,"reason":"prev_page","page_action":"prev"}\n'
        'Q: \'which is best?\' → {"intent":"Explain","confidence":0.93,"reason":"evaluation"}\n'
        'Q: \'compare 1 and 3\' → {"intent":"Compare","target_indices":[1,3],"confidence":0.97,"reason":"comparison"}\n'
        'Q: \'compare all\' → {"intent":"Compare","confidence":0.92,"reason":"compare_all"}\n'
        'Q: \'Hackney vs Peckham?\' → {"intent":"AreaCompare","target_areas":["Hackney","Peckham"],"confidence":0.95,"reason":"area_compare"}\n'
        'Q: \'save listing 2\' → {"intent":"Shortlist","shortlist_action":"add","target_indices":[2],"confidence":0.97,"reason":"save"}\n'
        'Q: \'show my shortlist\' → {"intent":"Shortlist","shortlist_action":"show","confidence":0.97,"reason":"show_saved"}\n'
        'Q: \'what are my rights if the landlord won\\\'t fix the boiler\' → {"intent":"TenantRights","confidence":0.96,"reason":"tenant_rights_repairs"}\n'
        'Q: \'can my landlord evict me for having a pet\' → {"intent":"TenantRights","confidence":0.95,"reason":"tenant_rights_eviction"}\n'
        'Q: \'is my deposit protected\' → {"intent":"TenantRights","confidence":0.97,"reason":"tenant_rights_deposit"}\n'
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
    # Never block a search with a clarification question — just run the search.
    if intent == "Search":
        need_clarify = False
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
