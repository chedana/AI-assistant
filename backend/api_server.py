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

# Ensure assistant workflow points to OpenAI API when backend is started standalone.
os.environ.setdefault("QWEN_BASE_URL", "https://api.openai.com/v1")
os.environ.setdefault("ROUTER_BASE_URL", os.environ["QWEN_BASE_URL"])
os.environ.setdefault("ROUTER_API_KEY", os.environ.get("OPENAI_API_KEY", ""))

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
    route_hint: dict | None = None


app = FastAPI(title="AI Assistant Backend Proxy", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

_RUNTIME = None
_RUNTIME_LOCK = Lock()

def get_runtime():
    global _RUNTIME
    if _RUNTIME is None:
        with _RUNTIME_LOCK:
            if _RUNTIME is None:
                _RUNTIME = build_search_runtime()
    return _RUNTIME


@app.on_event("startup")
def _preload_runtime():
    """Eagerly load sentence-transformer + Qdrant client at startup."""
    import time as _t
    t0 = _t.perf_counter()
    get_runtime()
    print(f"[TIMING] startup preload={_t.perf_counter()-t0:.2f}s")

ROUTER_DEBUG = str(os.environ.get("ROUTER_DEBUG", "1")).strip().lower() in {"1", "true", "yes", "on"}
SESSIONS: TTLCache = TTLCache(maxsize=50, ttl=3600)  # max 50 sessions, 1-hour TTL
SESSIONS_LOCK = Lock()

SESSION_LOCKS: dict[str, Lock] = {}
SESSION_LOCKS_META = Lock()  # protects SESSION_LOCKS dict itself

MAX_USER_INPUT = 2000


def _json_list(val: object) -> list[str]:
    """Parse a JSON-encoded array string (e.g. image_urls) into list[str]."""
    if isinstance(val, list):
        return [str(x) for x in val if x]
    if isinstance(val, str) and val.strip():
        try:
            parsed = json.loads(val)
            if isinstance(parsed, list):
                return [str(x) for x in parsed if x]
        except Exception:
            pass
    return []


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


def _parse_deposit(val: object) -> float | int | None:
    """Parse deposit which may be a string like '£1,600' or 'Ask agent'."""
    if val is None:
        return None
    import re as _re
    m = _re.search(r'[\d,]+(?:\.\d+)?', str(val).replace(',', ''))
    if m:
        try:
            f = float(m.group().replace(',', ''))
            return int(f) if f == int(f) else round(f, 2)
        except (ValueError, TypeError):
            pass
    return None


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
                "image_url": str(r.get("image_url", "")),
                "address": str(r.get("address", "")),
                "price_pcm": _num(r.get("price_pcm")),
                "bedrooms": _num(r.get("bedrooms")),
                "bathrooms": _num(r.get("bathrooms")),
                "available_from": str(r.get("available_from", "")),
                "description": str(r.get("description", "")),
                "features": str(r.get("features", "")),
                "property_type": str(r.get("property_type", "")),
                "furnish_type": str(r.get("furnish_type", "")),
                "lat": _num(r.get("latitude"), None),
                "lon": _num(r.get("longitude"), None),
                "image_urls": _json_list(r.get("image_urls")),
                "deposit": _num(r.get("deposit")),
                "final_score": _num(r.get("final_score")),
                "penalty_reasons": [p for p in _to_list(r.get("penalty_reasons")) if not p.startswith("unknown_hard(")],
                "preference_hits": _to_list(r.get("preference_hits")),
            })
        total = len(state.search_full_results)
        k = int((state.constraints or {}).get("k") or 5)
        shown_so_far = (state.page_index + 1) * k
        meta["search_results"] = {
            "listings": listings,
            "page_index": state.page_index,
            "has_more": state.has_more,
            "total": total,
            "remaining": max(0, total - shown_so_far),
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
    if state.last_intent == "Compare":
        _compare_source = (
            list(state.shortlist or [])
            if state.last_compare_source == "shortlist"
            else list(state.last_results or [])
        )
        if _compare_source:
            compare_listings = []
            for i, r in enumerate(_compare_source):
                compare_listings.append({
                    "index": i + 1,
                    "title": str(r.get("title", "")),
                    "url": str(r.get("url", "")),
                    "image_url": str(r.get("image_url", "")),
                    "price_pcm": _num(r.get("price_pcm")),
                    "bedrooms": _num(r.get("bedrooms")),
                    "bathrooms": _num(r.get("bathrooms")),
                    "deposit": _parse_deposit(r.get("deposit")),
                    "available_from": str(r.get("available_from", "")),
                    "size_sqm": _num(r.get("size_sqm")),
                    "furnish_type": str(r.get("furnish_type") or ""),
                    "property_type": str(r.get("property_type") or ""),
                    "lat": _num(r.get("latitude"), None),
                    "lon": _num(r.get("longitude"), None),
                })
            meta["compare_data"] = {"listings": compare_listings}

    # Shortlist — always included so frontend can show saved/unsaved state on cards
    shortlist_items = list(state.shortlist or [])
    saved_ids = [
        str(r.get("listing_id") or r.get("url") or "")
        for r in shortlist_items
        if r.get("listing_id") or r.get("url")
    ]
    shortlist_listings = [
        {
            "title": str(r.get("title", "")),
            "url": str(r.get("url", "")),
            "image_url": str(r.get("image_url", "")),
            "address": str(r.get("address") or ""),
            "price_pcm": _num(r.get("price_pcm")),
            "bedrooms": _num(r.get("bedrooms")),
            "bathrooms": _num(r.get("bathrooms")),
            "available_from": str(r.get("available_from") or ""),
            "final_score": _num(r.get("final_score")),
            "penalty_reasons": [p for p in _to_list(r.get("penalty_reasons")) if not p.startswith("unknown_hard(")],
            "preference_hits": _to_list(r.get("preference_hits")),
            "lat": _num(r.get("latitude"), None),
            "lon": _num(r.get("longitude"), None),
        }
        for r in shortlist_items
    ]
    meta["shortlist"] = {
        "count": len(shortlist_items),
        "saved_ids": saved_ids,
        "listings": shortlist_listings,
    }

    # Quick replies — contextual suggestions
    quick: list[dict] = []
    if state.last_results:
        if state.has_more:
            quick.append({"label": "Show more", "text": "show me more", "route_hint": {"intent": "Page_Nav", "page_action": "next"}})
        max_rent = (state.constraints or {}).get("max_rent_pcm")
        if max_rent:
            lower = int(max_rent * 0.8)
            quick.append({"label": "Lower budget", "text": f"lower budget to £{lower}/month", "route_hint": {"intent": "Search", "set_constraints": {"max_rent_pcm": lower}}})
        else:
            quick.append({"label": "Lower budget", "text": "find cheaper options", "route_hint": {"intent": "Search"}})
        if state.last_intent != "Compare":
            quick.append({"label": "Compare all", "text": "compare these listings", "route_hint": {"intent": "Compare"}})
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


def _run_locked(lock: Lock, user_in: str, state: AgentState, runtime, router_debug: bool, route_hint: dict | None = None) -> str:
    with lock:
        return process_turn(user_in, state, runtime, router_debug, route_hint=route_hint)


@app.get("/healthz")
async def healthz() -> JSONResponse:
    return JSONResponse({"ok": True, "service": "backend-proxy", "sessions": len(SESSIONS)})


@app.get("/crawl-status")
async def crawl_status() -> JSONResponse:
    """Return the last crawl pipeline status (written by auto_crawl.sh)."""
    status_path = os.path.join(os.path.dirname(__file__), "..", "crawler", "artifacts", "crawl-status.json")
    try:
        with open(status_path) as f:
            data = json.load(f)
        return JSONResponse(data)
    except FileNotFoundError:
        return JSONResponse({"status": "no_data", "message": "No crawl has run yet"}, status_code=404)
    except json.JSONDecodeError:
        return JSONResponse({"status": "error", "message": "Corrupt status file"}, status_code=500)


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
            import time
            t0 = time.perf_counter()
            state = get_or_create_state(req.session_id)
            session_lock = get_session_lock(req.session_id)
            hint_str = str(req.route_hint.get("intent") if req.route_hint else "none")
            print(f"[TIMING] start intent={hint_str!r} text={user_text[:60]!r}")

            t1 = time.perf_counter()
            reply = await asyncio.to_thread(
                _run_locked,
                session_lock,
                user_text,
                state,
                get_runtime(),
                ROUTER_DEBUG,
                req.route_hint,
            )
            t2 = time.perf_counter()
            print(f"[TIMING] process_turn={t2-t1:.2f}s  total_so_far={t2-t0:.2f}s  reply_len={len(reply)}")

            is_silent = req.route_hint is not None
            chunk_size = 200 if is_silent else 32
            chunk_delay = 0.0 if is_silent else 0.005
            for chunk in split_chunks(reply, size=chunk_size):
                if await request.is_disconnected():
                    return
                yield sse_event("delta", {"text": chunk})
                if chunk_delay:
                    await asyncio.sleep(chunk_delay)

            metadata = build_metadata(state)
            t3 = time.perf_counter()
            if metadata:
                print(f"[TIMING] stream+metadata={t3-t2:.2f}s  total={t3-t0:.2f}s | "
                      f"listings={len(metadata.get('search_results', {}).get('listings', []))} "
                      f"constraints={bool(metadata.get('constraints'))}")
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
