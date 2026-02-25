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

            yield sse_event("done", {"ok": True})
        except Exception as exc:  # noqa: BLE001
            yield sse_event("error", {"message": str(exc)})

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )
