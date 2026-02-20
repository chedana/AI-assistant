# Backend Proxy (FastAPI)

This service runs the existing assistant workflow (`agent/workflow.py`) and converts full replies into pseudo-streamed SSE chunks.

## Run (RunPod/Linux)
```bash
cd /workspace/AI-assistant
source /workspace/AI-assistant/.venv/bin/activate
pip install -r /workspace/AI-assistant/backend/requirements.txt

# If vLLM is running on port 8002 (recommended with frontend/backend stack):
export QWEN_BASE_URL=http://127.0.0.1:8002/v1
export ROUTER_BASE_URL=${QWEN_BASE_URL}
export OPENAI_API_KEY=dummy
export ROUTER_API_KEY=${OPENAI_API_KEY}

cd /workspace/AI-assistant/backend
uvicorn api_server:app --host 0.0.0.0 --port 8000
```

## Endpoint
- `POST /api/chat/stream`
  - request: `session_id`, `user_text` (or `messages` with a latest user turn)
  - SSE events:
    - `event: delta` with `{"text":"..."}`
    - `event: done` with `{"ok":true}`
    - `event: error` with `{"message":"..."}`
