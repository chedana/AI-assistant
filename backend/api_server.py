from __future__ import annotations

import asyncio
import json
import os
from threading import Lock
from typing import AsyncGenerator, Literal

from cachetools import TTLCache
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

# Ensure assistant workflow points to local vLLM when backend is started standalone.
os.environ.setdefault("QWEN_BASE_URL", "http://127.0.0.1:8002/v1")
os.environ.setdefault("ROUTER_BASE_URL", os.environ["QWEN_BASE_URL"])
os.environ.setdefault("OPENAI_API_KEY", "dummy")
os.environ.setdefault("ROUTER_API_KEY", os.environ["OPENAI_API_KEY"])

from orchestration.state import AgentState
from orchestration.workflow import process_turn
from skills.search.agentic import build_search_runtime


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1)


class ChatStreamRequest(BaseModel):
    session_id: str = Field(min_length=1)
    user_text: str | None = None
    messages: list[ChatMessage] = Field(default_factory=list)


app = FastAPI(title="AI Assistant Backend Proxy", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

RUNTIME = build_search_runtime()
ROUTER_DEBUG = str(os.environ.get("ROUTER_DEBUG", "1")).strip().lower() in {"1", "true", "yes", "on"}
SESSIONS: TTLCache = TTLCache(maxsize=500, ttl=3600)  # max 500 sessions, 1-hour TTL
SESSIONS_LOCK = Lock()

SESSION_LOCKS: dict[str, Lock] = {}
SESSION_LOCKS_META = Lock()  # protects SESSION_LOCKS dict itself

MAX_USER_INPUT = 2000


def _to_list(val: object) -> list[str]:
    """Normalise a field that may be str, list, or None into list[str]."""
    if isinstance(val, list):
        return [str(x) for x in val]
    if isinstance(val, str) and val.strip():
        # Split on " and " that is NOT inside parentheses.
        # e.g. "boosted by deposit (0.56) and freshness (1.00)" → two items
        # but  "unknown_hard(bedrooms;+0.16)" stays as one item
        import re
        parts = re.split(r'\)\s+and\s+', val)
        # Re-attach the closing paren we consumed (except on the last piece)
        result = [p.strip() + ")" for p in parts[:-1]] + [parts[-1].strip()]
        return [r for r in result if r]
    return []


def _num(val: object, default: float | int = 0, *, keep_zero: bool = True) -> float | int:
    """Coerce any numeric type (including numpy) to a plain Python number."""
    if val is None:
        return default
    try:
        f = float(val)
        if not keep_zero and f == 0:
            return default
        return int(f) if f == int(f) else round(f, 4)
    except (TypeError, ValueError):
        return default


def build_metadata(state: AgentState) -> dict | None:
    """Extract structured metadata from agent state for the frontend."""
    meta: dict = {}

    # Search results
    if state.last_results:
        listings = []
        for r in state.last_results:
            listings.append({
                "title": str(r.get("title", "")),
                "url": str(r.get("url", "")),
                "address": str(r.get("address", "")),
                "price_pcm": _num(r.get("price_pcm")),
                "bedrooms": _num(r.get("bedrooms")),
                "bathrooms": _num(r.get("bathrooms")),
                "available_from": str(r.get("available_from", "")),
                "final_score": _num(r.get("final_score")),
                "penalty_reasons": [p for p in _to_list(r.get("penalty_reasons")) if not p.startswith("unknown_hard(")],
                "preference_hits": _to_list(r.get("preference_hits")),
            })
        meta["search_results"] = {
            "listings": listings,
            "page_index": state.page_index,
            "has_more": state.has_more,
            "total": len(state.search_full_results),
        }

    # Constraints
    if state.constraints:
        display: dict = {}
        for key, val in state.constraints.items():
            if val is None:
                continue
            if key == "max_rent_pcm" and val:
                display["budget"] = f"\u2264\u00a3{int(val)}/pcm"
            elif key == "location_keywords" and val:
                display["location"] = val
            elif key == "layout_options" and val:
                beds = set()
                for lo in val:
                    b = lo.get("bedrooms")
                    if b is not None:
                        beds.add(int(b))
                if beds:
                    display["bedrooms"] = sorted(beds)
            elif key in ("furnish_type", "let_type", "available_from", "min_tenancy_months"):
                display[key] = val
        if display:
            meta["constraints"] = display

    # Compare data — structured comparison table
    if state.last_intent == "Compare" and state.last_results:
        compare_listings = []
        for i, r in enumerate(state.last_results):
            compare_listings.append({
                "index": i + 1,
                "title": str(r.get("title", "")),
                "url": str(r.get("url", "")),
                "price_pcm": _num(r.get("price_pcm")),
                "bedrooms": _num(r.get("bedrooms")),
                "bathrooms": _num(r.get("bathrooms")),
                "deposit": _num(r.get("deposit")),
                "available_from": str(r.get("available_from", "")),
                "size_sqm": _num(r.get("size_sqm")),
                "furnish_type": str(r.get("furnish_type") or ""),
                "property_type": str(r.get("property_type") or ""),
            })
        meta["compare_data"] = {"listings": compare_listings}

    # Shortlist — always included so frontend can show saved/unsaved state on cards
    saved_ids = [
        str(r.get("listing_id") or r.get("url") or "")
        for r in (state.shortlist or [])
        if r.get("listing_id") or r.get("url")
    ]
    meta["shortlist"] = {
        "count": len(state.shortlist or []),
        "saved_ids": saved_ids,
    }

    # Quick replies — contextual suggestions
    quick: list[dict] = []
    if state.last_results:
        if state.last_intent != "Compare":
            if state.has_more:
                quick.append({"label": "Show more", "text": "show me more"})
            quick.append({"label": "Lower budget", "text": "find cheaper options"})
            quick.append({"label": "Compare all", "text": "compare these listings"})
    if state.shortlist:
        quick.append({"label": "My shortlist", "text": "show my shortlist"})
    if quick:
        meta["quick_replies"] = quick

    return meta if meta else None


def sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def split_chunks(text: str, size: int = 8) -> list[str]:
    if not text:
        return []
    return [text[i : i + size] for i in range(0, len(text), size)]


def resolve_user_text(req: ChatStreamRequest) -> str:
    if req.user_text and req.user_text.strip():
        return req.user_text.strip()

    for msg in reversed(req.messages):
        if msg.role == "user" and msg.content.strip():
            return msg.content.strip()
    return ""


def get_or_create_state(session_id: str) -> AgentState:
    with SESSIONS_LOCK:
        state = SESSIONS.get(session_id)
        if state is None:
            state = AgentState()
            SESSIONS[session_id] = state
        return state


def get_session_lock(session_id: str) -> Lock:
    with SESSION_LOCKS_META:
        if session_id not in SESSION_LOCKS:
            SESSION_LOCKS[session_id] = Lock()
        return SESSION_LOCKS[session_id]


def _run_locked(lock: Lock, user_in: str, state: AgentState, runtime, router_debug: bool) -> str:
    with lock:
        return process_turn(user_in, state, runtime, router_debug)


@app.get("/healthz")
async def healthz() -> JSONResponse:
    return JSONResponse({"ok": True, "service": "backend-proxy", "sessions": len(SESSIONS)})


@app.post("/api/chat/stream")
async def chat_stream(req: ChatStreamRequest, request: Request) -> StreamingResponse:
    async def event_gen() -> AsyncGenerator[str, None]:
        user_text = resolve_user_text(req)
        if not user_text:
            yield sse_event("error", {"message": "Empty user message"})
            return
        if len(user_text) > MAX_USER_INPUT:
            yield sse_event("error", {"message": f"Message too long ({len(user_text)} chars). Please keep under {MAX_USER_INPUT}."})
            return

        try:
            state = get_or_create_state(req.session_id)
            session_lock = get_session_lock(req.session_id)
            reply = await asyncio.to_thread(
                _run_locked,
                session_lock,
                user_text,
                state,
                RUNTIME,
                ROUTER_DEBUG,
            )

            for chunk in split_chunks(reply, size=8):
                if await request.is_disconnected():
                    return
                yield sse_event("delta", {"text": chunk})
                await asyncio.sleep(0.01)

            metadata = build_metadata(state)
            if metadata:
                print(f"[SSE] sending metadata: {len(metadata.get('search_results', {}).get('listings', []))} listings, "
                      f"constraints={bool(metadata.get('constraints'))}, "
                      f"shortlist={metadata.get('shortlist', {}).get('count', 0)}, "
                      f"quick_replies={len(metadata.get('quick_replies', []))}")
                yield sse_event("metadata", metadata)
            else:
                print("[SSE] no metadata to send (last_results empty?)")
            yield sse_event("done", {"ok": True})
        except Exception as exc:  # noqa: BLE001
            yield sse_event("error", {"message": str(exc)})

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )
