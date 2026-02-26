"""domain_router — top-level domain classifier.

Sits above all skill-specific routers. Classifies the user's message into a
high-level domain so the graph can dispatch to the right sub-pipeline.

Domains (current):
  "Rental"  — property search, listing QA, pagination, constraint refinement
  "General" — greetings, capability questions, small talk, off-topic

New skills (future) = add a new domain string and a graph branch; nothing
else in this file changes.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from core.chatbot_config import DOMAIN_ROUTER_SYSTEM
from core.llm_client import qwen_router_chat
from orchestration.router import _extract_first_json_obj

_DOMAINS = {"Rental", "General"}
_DEFAULT_DOMAIN = "Rental"  # safe fallback — rental pipeline handles ambiguity


@dataclass
class DomainDecision:
    domain: str   # "Rental" | "General"
    reason: str


def domain_route_turn(
    user_text: str,
    history_hint: Optional[str] = None,
    has_listings: bool = False,
) -> DomainDecision:
    """Classify user_text into a top-level domain.

    Falls back to "Rental" on any LLM or parse error so the existing
    rental pipeline always handles ambiguous input gracefully.
    """
    text = (user_text or "").strip()
    if not text:
        return DomainDecision(domain=_DEFAULT_DOMAIN, reason="empty_input")

    context_lines = []
    if history_hint:
        context_lines.append(f"Conversation so far:\n{history_hint}")
    if has_listings:
        context_lines.append("(Rental listings are currently displayed to the user.)")
    context = "\n".join(context_lines)

    user_payload = f"{context}\n\nUser message:\n{text}".strip()

    try:
        raw = qwen_router_chat(
            [
                {"role": "system", "content": DOMAIN_ROUTER_SYSTEM},
                {"role": "user", "content": user_payload},
            ],
            temperature=0.0,
        ).strip()
    except Exception:
        return DomainDecision(domain=_DEFAULT_DOMAIN, reason="llm_error")

    obj = _extract_first_json_obj(raw)
    if not obj:
        return DomainDecision(domain=_DEFAULT_DOMAIN, reason="parse_error")

    domain = str(obj.get("domain") or "").strip()
    if domain not in _DOMAINS:
        return DomainDecision(domain=_DEFAULT_DOMAIN, reason="invalid_domain")

    reason = str(obj.get("reason") or "llm").strip()
    return DomainDecision(domain=domain, reason=reason)
