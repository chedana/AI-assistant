# Modular Migration Notes

## New Entry
- `python3 /workspace/AI-assistant/main.py`

## Legacy Compatibility
- Old command remains usable via shim:
- `python3 /workspace/rent-chatbot/chat_bot.py`

## Current Phase
- Phase 1 complete: structure migration + compatibility wrappers.
- Search workflow is kept behavior-compatible by reusing existing implementation under `skills/search/handler.py`.
- Router/QA are scaffolded for Phase 2 integration.
