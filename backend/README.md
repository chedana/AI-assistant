# Backend Proxy (FastAPI)

This service proxies frontend chat requests to local vLLM and converts stream chunks into SSE events.

## Run (RunPod/Linux)
```bash
cd /workspace/AI-assistant/backend
pip install -r requirements.txt
uvicorn api_server:app --host 0.0.0.0 --port 8000
```

## Endpoint
- `POST /api/chat/stream`
  - request: `session_id`, `messages`, `temperature`, `max_tokens`
  - SSE events:
    - `event: delta` with `{"text":"..."}`
    - `event: done` with `{"ok":true}`
    - `event: error` with `{"message":"..."}`
