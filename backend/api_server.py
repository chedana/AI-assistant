from __future__ import annotations

import json
from typing import AsyncGenerator, Literal

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

VLLM_BASE_URL = "http://127.0.0.1:8002"
DEFAULT_MODEL = "./Qwen3-8B"


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1)


class ChatStreamRequest(BaseModel):
    session_id: str = Field(default="")
    messages: list[ChatMessage] = Field(default_factory=list, min_length=1)
    temperature: float = 0.7
    max_tokens: int = 1024


app = FastAPI(title="AI Assistant Backend Proxy", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.get("/healthz")
async def healthz() -> JSONResponse:
    return JSONResponse({"ok": True, "service": "backend-proxy"})


@app.post("/api/chat/stream")
async def chat_stream(req: ChatStreamRequest, request: Request) -> StreamingResponse:
    async def event_gen() -> AsyncGenerator[str, None]:
        payload = {
            "model": DEFAULT_MODEL,
            "messages": [m.model_dump() for m in req.messages],
            "temperature": req.temperature,
            "max_tokens": req.max_tokens,
            "stream": True,
        }
        timeout = httpx.Timeout(timeout=120.0, connect=10.0)

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream(
                    "POST",
                    f"{VLLM_BASE_URL}/v1/chat/completions",
                    json=payload,
                ) as upstream:
                    if upstream.status_code != 200:
                        detail = await upstream.aread()
                        yield sse_event(
                            "error",
                            {
                                "message": "Upstream vLLM request failed",
                                "status_code": upstream.status_code,
                                "detail": detail.decode("utf-8", errors="ignore"),
                            },
                        )
                        return

                    async for raw_line in upstream.aiter_lines():
                        if await request.is_disconnected():
                            return
                        line = raw_line.strip()
                        if not line or not line.startswith("data:"):
                            continue

                        data_str = line[5:].strip()
                        if data_str == "[DONE]":
                            yield sse_event("done", {"ok": True})
                            return

                        try:
                            packet = json.loads(data_str)
                        except json.JSONDecodeError:
                            continue

                        choices = packet.get("choices", [])
                        if not choices:
                            continue
                        delta = choices[0].get("delta", {})
                        token = delta.get("content")
                        if token:
                            yield sse_event("delta", {"text": token})
        except Exception as exc:  # noqa: BLE001
            yield sse_event("error", {"message": str(exc)})

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )
