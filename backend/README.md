# Backend Proxy (FastAPI)

This service runs the existing assistant workflow (`agent/workflow.py`) and converts full replies into pseudo-streamed SSE chunks.

## Run (RunPod/Linux)
```bash
cd /workspace/AI-assistant/backend
pip install -r requirements.txt
uvicorn api_server:app --host 0.0.0.0 --port 8000
```

## Endpoint
- `POST /api/chat/stream`
  - request: `session_id`, `user_text` (or `messages` with a latest user turn)
  - SSE events:
    - `event: delta` with `{"text":"..."}`
    - `event: done` with `{"ok":true}`
    - `event: error` with `{"message":"..."}`
