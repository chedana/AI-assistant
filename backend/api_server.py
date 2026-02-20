from __future__ import annotations

import asyncio
import json
import os
from threading import Lock
from typing import AsyncGenerator, Literal

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from agent.state import AgentState
from agent.workflow import process_turn
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
ROUTER_DEBUG = str(os.environ.get("ROUTER_DEBUG", "0")).strip().lower() in {"1", "true", "yes", "on"}
SESSIONS: dict[str, AgentState] = {}
SESSIONS_LOCK = Lock()


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

        try:
            state = get_or_create_state(req.session_id)
            reply = await asyncio.to_thread(
                process_turn,
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
