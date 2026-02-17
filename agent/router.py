import re
from dataclasses import dataclass
from typing import Optional

from core.llm_client import qwen_chat


@dataclass
class RouteDecision:
    intent: str
    reason: str


_INTENTS = {"Search", "Specific_QA", "Refinement", "Chitchat"}


def _heuristic_route(user_text: str) -> str:
    t = (user_text or "").strip().lower()
    if not t:
        return "Chitchat"

    if re.search(r"\b(too expensive|cheaper|budget|不要一楼|便宜点|太贵|不要|改成|换成)\b", t):
        return "Refinement"
    if re.search(r"\b(this one|this flat|that one|distance|pet|subway|地铁|这套|那套|能养猫|离)\b", t):
        return "Specific_QA"
    if re.search(r"\b(hello|hi|thanks|thank you|你好|哈喽|谢谢)\b", t):
        return "Chitchat"
    return "Search"


def _classify_intent_with_llm(user_text: str, history_hint: Optional[str] = None) -> Optional[str]:
    prompt = (
        "你是租房助手的意图分类器。\n"
        "类别只能是: Search, Specific_QA, Refinement, Chitchat。\n"
        "只输出类别名称，不要输出其他文字。"
    )
    user_payload = f"历史摘要:\n{history_hint or '(none)'}\n\n用户输入:\n{user_text}"
    try:
        out = qwen_chat(
            [
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_payload},
            ],
            temperature=0.0,
        ).strip()
    except Exception:
        return None

    token = out.splitlines()[0].strip()
    if token in _INTENTS:
        return token
    return None


def route_turn(user_text: str, mode: str = "assistant", history_hint: Optional[str] = None) -> RouteDecision:
    t = (user_text or "").strip()
    if t.startswith("/"):
        return RouteDecision(intent="control", reason="command")

    llm_intent = _classify_intent_with_llm(user_text=t, history_hint=history_hint)
    if llm_intent:
        return RouteDecision(intent=llm_intent, reason="llm_classifier")

    return RouteDecision(intent=_heuristic_route(t), reason="heuristic_fallback")
