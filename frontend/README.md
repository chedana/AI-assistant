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

## Build
```bash
cd /workspace/AI-assistant/frontend
npm run build
npm run preview -- --host 0.0.0.0 --port 4173
```

## Current features
- Multi-turn chat sessions (saved in `localStorage`)
- Streaming assistant output (mock stream)
- Stop generation button

## Next step: real backend
Replace `src/lib/mockStream.ts` with your real streaming API adapter.
