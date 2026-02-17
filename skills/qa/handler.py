import json
from typing import Any, Dict

from core.llm_client import qwen_chat


def answer_single_listing_question(question: str, listing_payload: Dict[str, Any]) -> str:
    if not listing_payload:
        return "I don't have the selected listing details yet."

    distilled = {
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
        "url": listing_payload.get("url"),
    }
    system_prompt = (
        "You are a rental property QA assistant.\n"
        "Answer ONLY using the provided listing JSON.\n"
        "If info is not present, say it is not provided and suggest asking agent.\n"
        "Keep the answer concise."
    )
    try:
        return qwen_chat(
            [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": "Question:\n"
                    + question
                    + "\n\nListing JSON:\n"
                    + json.dumps(distilled, ensure_ascii=False),
                },
            ],
            temperature=0.0,
        )
    except Exception:
        station = distilled.get("nearest_station") or "not provided"
        distance = distilled.get("distance_to_station_m") or "not provided"
        return (
            f"I can only answer from known fields. Nearest station: {station}; "
            f"distance_to_station_m: {distance}. Other details may require asking agent."
        )
