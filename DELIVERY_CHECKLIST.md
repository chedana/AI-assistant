# Delivery Validation Checklist

> **Last updated:** 2026-03-30 15:20
> **Reviewer:** Lead (pending evening review)
> **Branch:** `openclaw`

---

## Phase 1: Quick Wins

### F-F8 Quick/Deep Toggle

**Team:** ff8-dev → ff8-debug → ff8-validate
**Commits:** `e517f00`, `cd22995`, `3299287`
**Status:** Code complete, team-validated. Awaiting lead sign-off.

| # | Check | Agent 结果 | Lead 验收 |
|---|-------|-----------|----------|
| 1 | `cd frontend && npx tsc --noEmit` 零错误（排除 ListingsPanel 预存问题） | PASS | [ ] |
| 2 | `python3 -m py_compile backend/api_server.py` 通过 | PASS | [ ] |
| 3 | ChatInput.tsx 中存在 toggle 按钮（grep `thinkingMode\|onToggleMode`） | PASS | [ ] |
| 4 | `SessionMetadata` 中有 `thinking_mode` 字段 | PASS | [ ] |
| 5 | `build_metadata()` 输出包含 `thinking_mode` | PASS | [ ] |
| 6 | Stream endpoint 读取 `route_hint.thinking_mode` 并设置到 `AgentState` | PASS | [ ] |
| 7 | `useChat.ts` 有 `thinkingMode` 状态，默认 `"quick"` | PASS | [ ] |
| 8 | `useChat.ts` session 切换时 thinkingMode 跟随 session（session-persisted） | PASS | [ ] |
| 9 | `sendMessage` 和 `sendSilentAction` 的 routeHint 均包含 `thinking_mode` | PASS | [ ] |
| 10 | `App.tsx` 将 thinkingMode + onToggleMode 传递给 ChatInput | PASS | [ ] |
| 11 | 生成中 toggle 按钮 disabled（JS 级别 `!isGenerating` guard） | PASS (修复后) | [ ] |
| 12 | Quick 模式 = bolt SVG，Deep 模式 = sparkle SVG | PASS | [ ] |
| 13 | 无 `console.log` / `print()` 调试语句 | PASS | [ ] |
| 14 | 无 hardcoded secrets | PASS | [ ] |

**Debug 发现的问题及修复：**
- toggle 按钮的 `onClick` 缺少 JS 级别 `isGenerating` guard（CSS `pointer-events-none` 可被键盘绕过）→ `cd22995` 修复

**已知限制：**
- `thinking_mode` 后端已存储但 orchestration pipeline 中尚无行为差异（deep 模式效果需后续实现）
- ListingsPanel.tsx 有 3 个预存 TSC 错误（引用已删除的文件），与本功能无关

---

### B-F5b Commute LLM Merge into Router

**Team:** bf5b-dev → bf5b-debug → bf5b-validate
**Commits:** `37c252f`
**Status:** Code complete, team-validated. Awaiting lead sign-off.

| # | Check | Agent 结果 | Lead 验收 |
|---|-------|-----------|----------|
| 1 | `python3 -m py_compile orchestration/router.py` 通过 | PASS | [ ] |
| 2 | `python3 -m py_compile orchestration/nodes.py` 通过 | PASS | [ ] |
| 3 | `python3 -m py_compile orchestration/state.py` 通过 | PASS | [ ] |
| 4 | `grep -rn "_try_extract_commute_destination_via_llm" orchestration/` → 0 matches | PASS | [ ] |
| 5 | `RouteDecision` 有 `commute_destination: Optional[str]` 字段 | PASS | [ ] |
| 6 | No-listings router prompt 包含 commute 提取指令 + few-shot | PASS | [ ] |
| 7 | With-listings router prompt 包含 commute 提取指令 + few-shot | PASS | [ ] |
| 8 | 两条 response parsing 路径都 sanitize `commute_destination` | PASS | [ ] |
| 9 | `qa_execute_node` 从 GraphState 读取 `commute_destination`（非独立 LLM 调用） | PASS | [ ] |
| 10 | Regex fallback `_try_extract_commute_destination_regex()` 存在（5 个 pattern） | PASS | [ ] |
| 11 | `_try_answer_commute_question()` 完整保留，接受 `dest_name` 参数 | PASS | [ ] |
| 12 | 无新增 debug print 语句（仅保留已有的 `_debug_print`） | PASS | [ ] |
| 13 | 所有 import 有效，无循环依赖 | PASS | [ ] |

**已知限制：**
- 公司/大学名称解析（如 "Google London" → King's Cross）依赖下游 geocoder，router 只提取原始文本
- 非典型表述（如 "is this place well connected"）可能漏过 regex，但 router LLM 应能覆盖

---

## Phase 1 通用验收

| # | Check | Agent 结果 | Lead 验收 |
|---|-------|-----------|----------|
| 1 | Python 编译通过（api_server, router, nodes, state） | PASS | [ ] |
| 2 | TypeScript 编译通过（排除预存 ListingsPanel 问题） | PASS | [ ] |
| 3 | 无 `console.log` / `print()` 调试语句残留 | PASS | [ ] |
| 4 | 无 hardcoded secrets | PASS | [ ] |
| 5 | Git 合并无残留冲突（`grep -r "<<<<<<" orchestration/ backend/ frontend/src/`） | PASS | [ ] |
| 6 | 两个 worktree 已合并到 openclaw | PASS | [ ] |

---

## Phase 2-5: 待开发

> Phase 2-5 的详细 checklist 见 `DEVELOPMENT_PLAN.md`。
> 开发完成后将同样格式追加到本文件。

| Phase | 任务 | 状态 |
|-------|------|------|
| Phase 2 | B-B2 Rightmove 重爬 + B-P2 字段统一 | 未开始 |
| Phase 3 | B-F4 看房邮件草稿 | 未开始 |
| Phase 4 | B-F6 合同分析 + F-F6 上传 UI + F-F5 看房 Checklist | 未开始 |
| Phase 5 | Crime / Flood / EPC / Rent Stats APIs | 未开始 |

---

## How to review

```bash
# 1. Quick compile check
python3 -m py_compile backend/api_server.py orchestration/router.py orchestration/nodes.py orchestration/state.py
cd frontend && npx tsc --noEmit

# 2. Check old function deleted
grep -rn "_try_extract_commute_destination_via_llm" orchestration/

# 3. Check no merge conflict markers
grep -r "<<<<<<" orchestration/ backend/ frontend/src/

# 4. Start backend + frontend, test manually
cd backend && uvicorn api_server:app --host 0.0.0.0 --port 8000
cd frontend && npm run dev -- --host 0.0.0.0 --port 5174

# 5. In browser:
#    - Toggle Quick/Deep button visible next to send
#    - Send a search query → check SSE metadata has thinking_mode
#    - Ask "how long to King's Cross" → commute QA works without extra delay
#    - Ask "is this pet-friendly" → no commute extraction fired
```

---

*每项 `[ ]` 由 Lead 手动验收后改为 `[x]`。全部通过后 push 到 origin/main。*
