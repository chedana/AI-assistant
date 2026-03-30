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

---

## Phase 2: Data Quality & Viewing Checklist

### B-P2 Unify Listing Fields

**Team:** bp2-dev → bp2-debug → bp2-validate
**Commits:** `ae51b43` (merged via `3fa86c6`)
**Status:** Code complete, team-validated. Awaiting lead sign-off.

| # | Check | Agent 结果 | Lead 验收 |
|---|-------|-----------|----------|
| 1 | `python3 -m py_compile backend/api_server.py` 通过 | PASS | [ ] |
| 2 | `cd frontend && npx tsc --noEmit` 通过（排除 ListingsPanel 预存问题） | PASS | [ ] |
| 3 | `_map_listing()` 和 compare path 使用相同字段名（compare 复用 `_map_listing()` + 加 `index`） | PASS | [ ] |
| 4 | 输出值中无 `"nan"` / `"NaN"` / `"None"` 字符串（仅在 `_safe_str` guard 中出现） | PASS | [ ] |
| 5 | `deposit`: `_parse_deposit()` → 始终 `int|float|None` → TS 中 `number|null` | PASS | [ ] |
| 6 | `size_sqm`: `_num(val, None)` → 始终 `number|None` | PASS | [ ] |
| 7 | `openrent_url`: `_safe_str()` 处理 → 始终 string | PASS | [ ] |
| 8 | `ListingData` 覆盖 `_map_listing()` 输出的全部 26 个字段 | PASS | [ ] |
| 9 | 无新增 debug print 语句 | PASS | [ ] |

---

### F-F5 Viewing Checklist

**Team:** ff5-dev → ff5-debug → ff5-validate
**Commits:** `33c5277` (merged via `bcce2b4`)
**Status:** Code complete, team-validated. Awaiting lead sign-off.

| # | Check | Agent 结果 | Lead 验收 |
|---|-------|-----------|----------|
| 1 | `cd frontend && npx tsc --noEmit` 通过（排除 ListingsPanel 预存问题） | PASS | [ ] |
| 2 | `viewingChecklist.ts` 有 3 个分类：Legal (7) + Physical (10) + Questions (8) = 25 项 | PASS | [ ] |
| 3 | Legal 项目准确：gas cert (annual), EICR (5yr), EPC (min E), smoke/CO, deposit protection, How to Rent, landlord ID | PASS | [ ] |
| 4 | `useViewingChecklist.ts` 按 `openclaw-viewing-${encodeURIComponent(listingUrl)}` 存储到 localStorage | PASS | [ ] |
| 5 | Checkbox 状态持久化：`useState` 从 `loadChecked()` 读取 localStorage 初始化；`toggle` 每次调用 `saveChecked` | PASS | [ ] |
| 6 | 进度指示器显示 `{catChecked}/{catTotal}` per category | PASS | [ ] |
| 7 | `ViewingChecklist.tsx` 有关闭按钮（X icon，调用 `onClose`） | PASS | [ ] |
| 8 | `ListingCard.tsx` 有 clipboard icon 按钮，点击 `setChecklistOpen(true)`，带绿色进度点 | PASS | [ ] |
| 9 | 无后端 API 调用（grep fetch/axios → 0 matches） | PASS | [ ] |
| 10 | 无 `console.log` 调试语句 | PASS | [ ] |

---

## Phase 2 通用验收

| # | Check | Agent 结果 | Lead 验收 |
|---|-------|-----------|----------|
| 1 | Python 编译通过（api_server.py） | PASS | [ ] |
| 2 | TypeScript 编译通过（排除预存问题） | PASS | [ ] |
| 3 | 无 `console.log` / `print()` 调试残留 | PASS | [ ] |
| 4 | 无 hardcoded secrets | PASS | [ ] |
| 5 | 无 merge conflict markers（`grep -r "<<<<<<" orchestration/ backend/ frontend/src/`） | PASS | [ ] |
| 6 | Worktree 分支已合并到 openclaw | PASS | [ ] |

---

## Phase 3: Contact Features

### B-F4 Draft Viewing Request Email

**Team:** bf4-dev → bf4-debug → bf4-validate
**Commit:** `90ec023`
**Status:** Code complete, team-validated. Awaiting lead sign-off.

| # | Check | Agent 结果 | Lead 验收 |
|---|-------|-----------|----------|
| 1 | `python3 -m py_compile backend/api_server.py` 通过 | PASS | [ ] |
| 2 | `python3 -m py_compile core/chatbot_config.py` 通过 | PASS | [ ] |
| 3 | `cd frontend && npx tsc --noEmit` 通过（排除预存问题） | PASS | [ ] |
| 4 | `POST /api/contact/draft` 端点存在（api_server.py line 525） | PASS | [ ] |
| 5 | 端点读取 `session_id` + `listing_index` | PASS | [ ] |
| 6 | `listing_index` 类型检查 + 范围检查 → 400 错误 | PASS | [ ] |
| 7 | `DRAFT_VIEWING_EMAIL_SYSTEM` prompt 存在（chatbot_config.py line 340） | PASS | [ ] |
| 8 | Prompt 指定 "under 150 words" + "do NOT include personal details" | PASS | [ ] |
| 9 | `DraftEmailModal.tsx` 有可编辑 subject input + body textarea | PASS | [ ] |
| 10 | Copy 使用 `navigator.clipboard.writeText`（带 fallback） | PASS | [ ] |
| 11 | `ListingCard.tsx` 有 envelope SVG 按钮 + loading spinner | PASS | [ ] |
| 12 | `DraftEmailResponse` 类型存在于 `types/chat.ts` | PASS | [ ] |
| 13 | 无 `console.log` / `print()` 调试语句 | PASS | [ ] |
| 14 | 无 hardcoded API keys 或 secrets | PASS | [ ] |

---

## Phase 4: Contract Analysis

### B-F6 Contract Analysis Endpoint

**Team:** bf6-dev → bf6-debug (发现 2 bug → 修复 → 复审通过) → bf6-validate
**Commits:** `c8a66fb`, `0486d19` (bug fix)
**Status:** Code complete, team-validated. Awaiting lead sign-off.

| # | Check | Agent 结果 | Lead 验收 |
|---|-------|-----------|----------|
| 1 | `python3 -m py_compile backend/api_server.py` 通过 | PASS | [ ] |
| 2 | `python3 -m py_compile core/chatbot_config.py` 通过 | PASS | [ ] |
| 3 | `python3 -m py_compile skills/contract/extractor.py` 通过 | PASS | [ ] |
| 4 | `python3 -m py_compile skills/contract/analyser.py` 通过 | PASS | [ ] |
| 5 | `POST /api/contract/analyse` 端点存在（api_server.py line 601） | PASS | [ ] |
| 6 | 文件类型验证：仅 PDF → 400（content_type check） | PASS | [ ] |
| 7 | 文件大小验证：<= 10MB → 400 | PASS | [ ] |
| 8 | `CONTRACT_ANALYSIS_SYSTEM` prompt 存在（chatbot_config.py line 349） | PASS | [ ] |
| 9 | Prompt 反幻觉："Quote exact clause text — do not paraphrase" | PASS | [ ] |
| 10 | 合规检查覆盖 5 项：押金上限、禁止费用、押金保护、break clause、access rights | PASS | [ ] |
| 11 | `ContractReport` dataclass 有全部 8 个字段 | PASS | [ ] |
| 12 | 无文本错误处理：ValueError + 清晰提示 | PASS | [ ] |
| 13 | 免责声明："This is not legal advice" | PASS | [ ] |
| 14 | 无 debug print 语句 | PASS | [ ] |
| 15 | 无 hardcoded secrets | PASS | [ ] |

**Debug 发现的问题及修复：**
- `data.get("clauses", [])` 当 LLM 返回 `"clauses": null` 时返回 None → TypeError → 改为 `data.get("clauses") or []`
- `ClauseFlag(**c)` 在 LLM 返回额外字段时崩溃 → 改为过滤已知字段

---

### F-F6 Contract Upload UI

**Team:** ff6-dev → ff6-debug → ff6-validate
**Commit:** `7a042a3`
**Status:** Code complete, team-validated. Awaiting lead sign-off.

| # | Check | Agent 结果 | Lead 验收 |
|---|-------|-----------|----------|
| 1 | `cd frontend && npx tsc --noEmit` 通过（排除预存问题） | PASS | [ ] |
| 2 | `ContractUpload.tsx` 有拖拽 drop zone + file picker | PASS | [ ] |
| 3 | 文件验证：仅 PDF（content_type check）+ <= 10MB | PASS | [ ] |
| 4 | Fetch 调用 `POST /api/contract/analyse` with FormData | PASS | [ ] |
| 5 | Loading 状态：dot 动画 + "Analysing contract..." | PASS | [ ] |
| 6 | Error 状态：红色内联错误提示（非崩溃） | PASS | [ ] |
| 7 | `ContractReportView` 渲染：summary + key terms + clause flags + compliance | PASS | [ ] |
| 8 | 严重度颜色：info=绿 / warning=琥珀 / critical=红 | PASS | [ ] |
| 9 | 合规图标：pass=✓ / fail=✗ / unknown=? | PASS | [ ] |
| 10 | 免责声明文本存在 | PASS | [ ] |
| 11 | "Upload another" 按钮可用 | PASS | [ ] |
| 12 | `Header.tsx` 有文档图标按钮（onContractToggle） | PASS | [ ] |
| 13 | Overlay 响应式（mobile-friendly，max-w-lg，mx-4） | PASS | [ ] |
| 14 | 无 `console.log` 调试语句 | PASS | [ ] |
| 15 | 无 hardcoded secrets | PASS | [ ] |

---

## Phase 5: 待开发

| Phase | 任务 | 状态 |
|-------|------|------|
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

# 4. Check no "nan" in field mapping
grep -n '"nan"\|"NaN"' backend/api_server.py

# 5. Start backend + frontend, test manually
cd backend && uvicorn api_server:app --host 0.0.0.0 --port 8000
cd frontend && npm run dev -- --host 0.0.0.0 --port 5174

# 6. In browser:
#    Phase 1:
#    - Toggle Quick/Deep button visible next to send
#    - Send a search query → check SSE metadata has thinking_mode
#    - Ask "how long to King's Cross" → commute QA works
#    - Ask "is this pet-friendly" → no commute extraction fired
#    Phase 2:
#    - Search results → no "nan" in any listing field
#    - Compare 2 listings → same fields as search results
#    - Click clipboard icon on listing → viewing checklist opens
#    - Check items → close → reopen → items still checked
#    - Switch to different listing → checklist is independent
```

---

*每项 `[ ]` 由 Lead 手动验收后改为 `[x]`。全部通过后 push 到 origin/main。*
