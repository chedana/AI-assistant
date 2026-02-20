# Frontend (GPT-style chat UI)

## Stack
- React + Vite + TypeScript
- TailwindCSS

## Run (RunPod/Linux)
```bash
cd /workspace/AI-assistant/frontend
npm install
npm run dev -- --host 0.0.0.0 --port 5173
```

`/api/*` requests are proxied by Vite to `http://127.0.0.1:8000`.

## Build
```bash
cd /workspace/AI-assistant/frontend
npm run build
npm run preview -- --host 0.0.0.0 --port 4173
```

## Current features
- Multi-turn chat sessions (saved in `localStorage`)
- Streaming assistant output (SSE)
- Stop generation button
