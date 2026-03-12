from __future__ import annotations

import asyncio
import json
import json as _json_mod
import os
import re
import time as _time
import urllib.request as _urllib_request
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from typing import AsyncGenerator, Dict, List, Literal, Optional, Union

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
    user_text: Optional[str] = None
    messages: List[ChatMessage] = Field(default_factory=list)
    route_hint: Optional[Dict] = None


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


def _features_list(val: object) -> list[str]:
    """Parse features — handles JSON arrays, Python lists, and newline/semicolon-separated strings."""
    _skip = {"ask agent", "n/a", "none", ""}
    def _clean(s: str) -> str:
        return re.sub(r"^[\-–•]\s*", "", s).strip()
    if isinstance(val, list):
        return [_clean(str(x)) for x in val if _clean(str(x)).lower() not in _skip]
    if isinstance(val, str) and val.strip():
        if val.strip().lower() in _skip:
            return []
        # Try JSON array first
        if val.strip().startswith("["):
            try:
                parsed = json.loads(val)
                if isinstance(parsed, list):
                    return [_clean(str(x)) for x in parsed if _clean(str(x)).lower() not in _skip]
            except Exception:
                pass
        # Newline or semicolon separated; strip leading "- " or "• " list markers
        return [_clean(x) for x in val.replace(";", "\n").split("\n")
                if _clean(x) and _clean(x).lower() not in _skip]
    return []


def _safe_str(val: object) -> str:
    """Convert to string, treating None/NaN/nan as empty."""
    if val is None:
        return ""
    s = str(val)
    if s in ("nan", "None", "NaN"):
        return ""
    return s


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


def _is_real_image(url: str) -> bool:
    """Filter out placeholder/logo images — only keep real property photos."""
    if not url:
        return False
    low = url.lower()
    # OpenRent logo served from staticcdn, or static map images
    if "staticcdn.openrent" in low:
        return False
    if "staticmapphoto" in low:
        return False
    # Generic placeholder patterns
    if "logo" in low or "placeholder" in low or "noimage" in low:
        return False
    return True


# --- Commute time enrichment via TfL Journey API ---
_COMMUTE_CACHE: Dict[tuple, tuple] = {}  # key -> (result_dict, timestamp)
_COMMUTE_CACHE_TTL = 3600  # 1 hour
_COMMUTE_CACHE_MAX = 2000


def _commute_cache_key(from_lat, from_lon, to_lat, to_lon):
    return (round(from_lat, 3), round(from_lon, 3), round(to_lat, 3), round(to_lon, 3))


def _fetch_commute_time(from_lat: float, from_lon: float, to_lat: float, to_lon: float) -> Optional[dict]:
    """Fetch commute time from TfL Journey API. Returns {minutes, summary} or None."""
    key = _commute_cache_key(from_lat, from_lon, to_lat, to_lon)

    # Check cache
    cached = _COMMUTE_CACHE.get(key)
    if cached:
        result, ts = cached
        if _time.time() - ts < _COMMUTE_CACHE_TTL:
            return result
        else:
            del _COMMUTE_CACHE[key]

    try:
        url = (
            f"https://api.tfl.gov.uk/Journey/JourneyResults/"
            f"{from_lat},{from_lon}/to/{to_lat},{to_lon}"
            f"?time=0900&timeIs=Departing"
        )
        req = _urllib_request.Request(url, headers={"User-Agent": "RentSearch/1.0"})
        with _urllib_request.urlopen(req, timeout=4) as resp:
            data = _json_mod.loads(resp.read().decode())

        journeys = data.get("journeys") or []
        if not journeys:
            return None

        # Pick the fastest journey
        best = min(journeys, key=lambda j: j.get("duration", 9999))
        duration = best.get("duration")
        if duration is None:
            return None

        # Build summary from legs (e.g. "25 min via Victoria line")
        legs = best.get("legs") or []
        tube_legs = [l for l in legs if l.get("mode", {}).get("name") in ("tube", "elizabeth-line", "dlr", "overground-train")]
        if tube_legs:
            line_name = tube_legs[0].get("routeOptions", [{}])[0].get("name", "")
            if line_name:
                summary = f"{duration} min via {line_name}"
            else:
                mode_name = tube_legs[0].get("mode", {}).get("name", "transit")
                summary = f"{duration} min via {mode_name}"
        else:
            # Bus or walking only
            modes = list(set(l.get("mode", {}).get("name", "") for l in legs if l.get("mode", {}).get("name") != "walking"))
            if modes:
                summary = f"{duration} min via {modes[0]}"
            else:
                summary = f"{duration} min (walking)"

        result = {"minutes": int(duration), "summary": summary}

        # Store in cache (with LRU eviction)
        if len(_COMMUTE_CACHE) >= _COMMUTE_CACHE_MAX:
            # Remove oldest entry
            oldest_key = min(_COMMUTE_CACHE, key=lambda k: _COMMUTE_CACHE[k][1])
            del _COMMUTE_CACHE[oldest_key]
        _COMMUTE_CACHE[key] = (result, _time.time())

        return result
    except Exception:
        return None


def _enrich_commute_times(listings: list, dest: dict) -> None:
    """Add commute_time_minutes and commute_summary to each listing dict."""
    dest_lat = dest.get("lat")
    dest_lon = dest.get("lon")
    if dest_lat is None or dest_lon is None:
        return

    def _fetch_for_listing(listing):
        lat = listing.get("lat")
        lon = listing.get("lon")
        if lat is None or lon is None:
            return listing, None
        return listing, _fetch_commute_time(float(lat), float(lon), float(dest_lat), float(dest_lon))

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(_fetch_for_listing, l): l for l in listings}
        for future in as_completed(futures, timeout=8):
            try:
                listing, result = future.result(timeout=5)
                if result:
                    listing["commute_time_minutes"] = result["minutes"]
                    listing["commute_summary"] = result["summary"]
                else:
                    listing["commute_time_minutes"] = None
                    listing["commute_summary"] = None
            except Exception:
                listing = futures[future]
                listing["commute_time_minutes"] = None
                listing["commute_summary"] = None


def build_metadata(state: AgentState) -> dict | None:
    """Extract structured metadata from agent state for the frontend."""
    meta: dict = {}

    def _map_listing(r: dict) -> dict:
        raw_cover = str(r.get("image_url", ""))
        cover = raw_cover if _is_real_image(raw_cover) else ""
        raw_gallery = _json_list(r.get("image_urls"))
        gallery = [u for u in raw_gallery if _is_real_image(u)]
        # If cover was filtered out but gallery has real images, use first as cover
        if not cover and gallery:
            cover = gallery[0]
        return {
            "title": str(r.get("title", "")),
            "url": str(r.get("url", "")),
            "image_url": cover,
            "address": str(r.get("address", "")),
            "price_pcm": _num(r.get("price_pcm")),
            "bedrooms": _num(r.get("bedrooms")),
            "bathrooms": _num(r.get("bathrooms")),
            "available_from": str(r.get("available_from", "")),
            "description": str(r.get("description", "")),
            "features": _features_list(r.get("features")),
            "property_type": str(r.get("property_type", "")),
            "furnish_type": str(r.get("furnish_type", "")),
            "lat": _num(r.get("latitude"), None),
            "lon": _num(r.get("longitude"), None),
            "image_urls": gallery,
            "deposit": _num(r.get("deposit")),
            "final_score": _num(r.get("final_score")),
            "penalty_reasons": [p for p in _to_list(r.get("penalty_reasons")) if not p.startswith("unknown_hard(")],
            "preference_hits": _to_list(r.get("preference_hits")),
            "red_flags": _to_list(r.get("red_flags")),
            "match_pct": int(_num(r.get("match_pct"), 100)),
            "source_site": _safe_str(r.get("source_site") or r.get("source")),
            "openrent_url": _safe_str(r.get("openrent_url")),
            "commute_time_minutes": r.get("commute_time_minutes"),
            "commute_summary": r.get("commute_summary"),
        }

    def _map_listing_light(r: dict) -> dict:
        """Lightweight listing for map pins — only fields needed for markers + popups."""
        return {
            "title": str(r.get("title", "")),
            "url": str(r.get("url", "")),
            "image_url": str(r.get("image_url", "")),
            "price_pcm": _num(r.get("price_pcm")),
            "bedrooms": _num(r.get("bedrooms")),
            "bathrooms": _num(r.get("bathrooms")),
            "property_type": str(r.get("property_type", "")),
            "lat": _num(r.get("latitude"), None),
            "lon": _num(r.get("longitude"), None),
        }

    # Search results
    if state.last_results:
        listings = [_map_listing(r) for r in state.last_results]
        # Enrich with commute times if destination is set
        commute_dest = (state.constraints or {}).get("commute_destination")
        if isinstance(commute_dest, dict) and commute_dest.get("lat"):
            _enrich_commute_times(listings, commute_dest)
            # Adjust match_pct based on commute time
            for l in listings:
                ct = l.get("commute_time_minutes")
                if ct is not None:
                    if ct <= 30:
                        pass  # full match
                    elif ct <= 45:
                        l["match_pct"] = max(50, (l.get("match_pct") or 100) - 7)
                    else:
                        l["match_pct"] = max(50, (l.get("match_pct") or 100) - 15)
                else:
                    l["match_pct"] = max(50, (l.get("match_pct") or 100) - 5)
        # Re-sort: match_pct descending first, then final_score descending as tiebreaker
        listings.sort(key=lambda l: (-(l.get("match_pct") or 0), -(l.get("final_score") or 0)))
        all_listings = [_map_listing_light(r) for r in state.search_full_results] if state.search_full_results else listings
        total = len(state.search_full_results)
        k = int((state.constraints or {}).get("k") or 5)
        shown_so_far = (state.page_index + 1) * k
        meta["search_results"] = {
            "listings": listings,
            "all_listings": all_listings,
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
            elif key == "bool_preferences" and isinstance(val, dict) and val:
                display["preferences"] = [k.replace("_", " ") for k, v in val.items() if v]
            elif key == "commute_destination" and isinstance(val, dict) and val.get("name"):
                display["commute_destination"] = val["name"]
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
            "red_flags": _to_list(r.get("red_flags")),
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

            metadata = build_metadata(state)
            t3 = time.perf_counter()
            has_search = bool(metadata and metadata.get("search_results", {}).get("listings"))

            if has_search:
                # Search response: send metadata first so listing cards appear immediately.
                # Skip streaming the listing-dump text — the frontend replaces it with
                # "Found X properties..." anyway via onMetadata, and we avoid messy concat.
                print(f"[TIMING] pipeline+metadata={t3-t2:.2f}s  total={t3-t0:.2f}s | "
                      f"listings={len(metadata['search_results']['listings'])} "
                      f"constraints={bool(metadata.get('constraints'))}")
                yield sse_event("metadata", metadata)
            else:
                # Non-search (QA, Explain, Chitchat, etc.): stream text first, then metadata.
                is_silent = req.route_hint is not None
                chunk_size = 200 if is_silent else 32
                chunk_delay = 0.0 if is_silent else 0.005
                for chunk in split_chunks(reply, size=chunk_size):
                    if await request.is_disconnected():
                        return
                    yield sse_event("delta", {"text": chunk})
                    if chunk_delay:
                        await asyncio.sleep(chunk_delay)
                if metadata:
                    print(f"[TIMING] stream+metadata={t3-t2:.2f}s  total={t3-t0:.2f}s | "
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
