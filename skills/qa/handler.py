from typing import Any, Dict


def answer_single_listing_question(question: str, listing_payload: Dict[str, Any]) -> str:
    _ = listing_payload
    return (
        "Stage E QA is scaffolded but not fully enabled yet. "
        "Use search mode for now, or complete router integration to activate listing QA."
    )
