from dataclasses import dataclass


@dataclass
class RouteDecision:
    branch: str
    reason: str


def route_turn(user_text: str, mode: str = "search") -> RouteDecision:
    t = (user_text or "").strip().lower()
    if t.startswith("/"):
        return RouteDecision(branch="control", reason="command")
    if mode == "listing_qa":
        return RouteDecision(branch="qa", reason="listing_qa_mode_default")
    return RouteDecision(branch="search", reason="default_search")
