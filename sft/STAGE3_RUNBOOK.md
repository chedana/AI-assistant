# 阶段 3 执行说明：GPT 与 Claude 交叉生成和审核

共同维护：Claude、Codex。负责人：朱衍（Derek）。依据：`DATA_CLEANING_NOTES.md` 中的决策 D7。

最后更新：2026-10-22，Codex。

## 分工（负责人 2026-10-22 决定，D10）

- **Claude**：规划实验、设计流程与脚本、编写 prompt、布置任务、审核结果（抽样盲审、错误分析）、决定下一步。
- **GPT（Codex）**：消耗大量 token 的重复性工作，例如按既定 prompt 批量生成数据、批量逐条处理。
- 审核与生成必须来自不同厂商：GPT 生成的数据由 Claude 审核。
- 任务通过本文件布置；Codex 完成后在对应进度表打勾、追加更新记录，由负责人通知 Claude 审核。

## 方案

1. `scripts/make_tasks.py` 从房源抽取任务，**gold 由脚本决定**；每套房源按固定种子分给 GPT 或 Claude。
2. 两家各自按 `prompts/gen_search_v1.md` 把自己的任务写成 query。
3. 双方生成完后运行 `prepare`，得到只含 `task_id` 和 `query` 的盲审输入。
4. 双方按 `prompts/review_v1.md` **盲审对方**的 query：只看 query 自己抽取一遍。
5. 运行 `merge`：脚本把盲审结果和 gold 逐字段比较，一致的通过，不一致的进 `rejected.jsonl` 并记录原因；再去重、出报告。

审核方不修改 gold，也不修改对方的 query。

## 当前进度：小样 50 条（`data/pilot/`）

| 步骤 | Claude | GPT（Codex） |
| --- | --- | --- |
| 生成 | ✅ `gen_claude.jsonl` 25 条，格式自检 0 问题 | ✅ `gen_gpt.jsonl` 25 条，格式自检 0 问题 |
| 盲审对方 | ✅ `review_by_claude.jsonl` | ✅ `review_by_gpt.jsonl` |
| 合并 | ✅ 通过 49/50，见下文“小样结果” | |

Codex 已运行 `precheck data/pilot gpt`（25 个任务，格式问题 0 条）及 `prepare data/pilot`（双方盲审输入各 25 条）。GPT 盲审在独立上下文中仅依据 `review_v1.md` 和 `review_input_for_gpt.jsonl` 完成，未读取 Claude 的任务条件、生成文件或 gold；25 条审核输出的 ID 顺序、15 个约束键及 schema 校验通过。`prepare` 前后 GPT 盲审输入内容一致。

第一轮已合并完成，结果见下文“小样结果”。

## Codex 需要做的事

在 `/Users/Shared/LLM_project/AI-assistant/sft` 下：

**第 1 步：生成 GPT 这一半**
1. 读 `prompts/gen_search_v1.md`，严格按其中规则执行。
2. 读 `data/pilot/tasks_gpt.jsonl`，每个任务只使用 `task_id`、`conditions`、`style_tags`。
3. 写 `data/pilot/gen_gpt.jsonl`，每行 `{"task_id", "query", "location_keywords"}`，顺序同任务文件。
4. 运行 `python3 scripts/pipeline.py precheck data/pilot gpt`，格式问题必须为 0；有问题就修正自己的 query 后重跑。
5. 运行 `python3 scripts/pipeline.py prepare data/pilot`，生成给 Claude 的盲审输入。

**第 2 步：盲审 Claude 的 query**（可以和第 1 步同时做）
1. 读 `prompts/review_v1.md`。
2. **只读** `data/pilot/review_input_for_gpt.jsonl`。为保证盲审有效，**不要打开** `tasks_claude.jsonl`、`gen_claude.jsonl`，也不要看任何 gold。
3. 写 `data/pilot/review_by_gpt.jsonl`，每行 `{"task_id", "intent", "constraints"}`，15 个键全部写出。

**第 3 步：通知负责人**，在下方进度表里打勾并追加更新记录。

## Claude 需要做的事

1. `gen_gpt.jsonl` 和 `review_input_for_claude.jsonl` 就绪后，只读 `review_input_for_claude.jsonl` 盲审，写 `review_by_claude.jsonl`（同样不看 `tasks_gpt.jsonl`、`gen_gpt.jsonl`）。
2. 双方盲审都完成后运行 `python3 scripts/pipeline.py merge data/pilot`，把 `report.md` 交给负责人。

## 小样结果（2026-10-22）

通过 49 / 50（98%）：Claude 25/25，GPT 24/25。报告见 `data/pilot/report.md`。

唯一丢弃的是 P-00034（GPT）：车站原始名带线路括号 “Edgware Road (Circle, District, Hammersmith & City)”，GPT 把括号整段算作地点，Claude 盲审只抽了 “Edgawre Road”。属于任务设计歧义，不是生成错误。已修复：`make_tasks.py` 给出车站名前先去掉括号和 “Station” 后缀。

需要注意的局限：两家审核都依据同一份规则，规则本身若有错，交叉审核发现不了。测试集仍需按阶段 4 做人工抽检。

## 第二轮小样：非 Search、追问、软偏好（`data/pilot2/`）

新增三份 prompt：
- `prompts/gen_intent_v1.md`：`specific_qa`、`compare`、`chitchat`、`followup` 四类；
- `prompts/gen_softpref_v1.md`：`softpref`，在 `gen_search_v1.md` 基础上加 1–2 个软偏好（只用于测试集，房源来自四个测试区）；
- `prompts/review_v2.md`：盲审全部意图，输入带上下文，输出增加 `soft_preferences`。

每家 25 条：问某一套 5、比较 5、闲聊 5、带新条件追问 5、软偏好 5。

| 步骤 | Claude | GPT（Codex） |
| --- | --- | --- |
| 生成 | ✅ 25 条，格式自检 0 问题 | ✅ `gen_gpt.jsonl` 25 条，格式自检 0 问题 |
| 盲审对方 | ✅ `review_by_claude.jsonl` | ✅ `review_by_gpt.jsonl` |
| 合并 | ✅ 通过 50/50，`data/pilot2/report.md` | |

Codex 第二轮已运行 `precheck data/pilot2 gpt`：25 个任务，格式问题 0 条；5 条软偏好的数量、权重、原样片段和连续三词重合检查通过。已运行 `prepare data/pilot2`，双方盲审输入各 25 条，仅含 `task_id`、`context`、`query`。

GPT 本轮盲审在独立上下文中只读取 `review_v2.md` 和 `data/pilot2/review_input_for_gpt.jsonl`，未查看 Claude 的任务、生成文件或 gold。审核结果共 25 条（Search 10、Specific_QA 5、Compare 5、Chitchat 5），完整 schema、ID 顺序及原样片段校验通过；`prepare` 前后盲审输入内容一致。

下一步由 Claude 按 `review_v2.md` 只读 `data/pilot2/review_input_for_claude.jsonl` 完成盲审，写入 `data/pilot2/review_by_claude.jsonl`，再运行 `python3 scripts/pipeline.py merge data/pilot2`。本轮交叉审核通过率尚未确定；测试集生成仍等待小样合并和负责人确认。

### Codex 第二轮要做的事

在 `/Users/Shared/LLM_project/AI-assistant/sft` 下：

1. **生成**：读 `data/pilot2/tasks_gpt.jsonl`。按每个任务的 `kind` 选 prompt：`specific_qa`、`compare`、`chitchat`、`followup` 用 `prompts/gen_intent_v1.md`；`softpref` 用 `prompts/gen_softpref_v1.md`（同时遵守 `prompts/gen_search_v1.md`）。写 `data/pilot2/gen_gpt.jsonl`。
2. 运行 `python3 scripts/pipeline.py precheck data/pilot2 gpt`，格式问题必须为 0（软偏好与描述有 3 个以上连续相同词也会报错，请改写）。
3. 运行 `python3 scripts/pipeline.py prepare data/pilot2`。
4. **盲审**：读 `prompts/review_v2.md`，**只读** `data/pilot2/review_input_for_gpt.jsonl`，写 `data/pilot2/review_by_gpt.jsonl`，每行 `{"task_id", "intent", "constraints", "soft_preferences"}`。不要打开 `tasks_claude.jsonl`、`gen_claude.jsonl`。
5. 在上表打勾并追加更新记录。

## 测试集（`data/test_v1/`）

`scripts/make_test_tasks.py --seed 2026` 生成 689 个任务（含约 15% 超量）：Claude 338、GPT 351。

| 测试集 | 类型 | 目标 | 任务数 |
| --- | --- | ---: | ---: |
| extract | 普通 Search | 220 | 253 |
| extract | 软偏好（四区各 23） | 80 | 92 |
| intent | 普通 Search | 50 | 57 |
| intent | 带新条件追问 | 25 | 29 |
| intent | 问某一套 / 比较 / 闲聊 | 各 75 | 各 86 |

配额核对：extract 中每个风格标签 ≥ 20 条（最少为 uk_jargon 20），DSS 19 条；含布尔条件的任务 71 条来自 OpenRent、12 条来自 Rightmove。

第二轮小样结果：通过 50/50。唯一问题是软偏好短语边界不统一（是否包含 ideally、would be nice 等词），5 条只产生提示。决定（D8，Claude 提出、负责人可否决）：软偏好只取内容短语，不含表示可选或强调的词。为此 prompt 升级为 `gen_softpref_v2.md` 和 `review_v3.md`。规范 8.2 节花园示例与此不一致，但测试集软偏好任务禁止使用有硬字段的属性，该情形不会出现。

### 测试集执行步骤（两家可以同时开始）

**生成**：读 `data/test_v1/tasks_{自己}.jsonl`，按 `kind` 选 prompt——`search` 用 `gen_search_v1.md`；`specific_qa`、`compare`、`chitchat`、`followup` 用 `gen_intent_v1.md`；`softpref` 用 **`gen_softpref_v2.md`**（同时遵守 `gen_search_v1.md`）。写 `data/test_v1/gen_{自己}.jsonl`。任务多，可以分批追加写入，每批后运行 `python3 scripts/pipeline.py precheck data/test_v1 {自己}` 检查已写部分（未写的任务显示“缺少生成结果”属正常）。

**语义自查**：生成完成后再运行 `python3 scripts/lint_gen.py data/test_v1 {自己}`，按规则检查房型词、studio、日期、预算数值和周期、租期、家具、布尔条件是否多写或漏写。它是粗筛，报出的条目逐条判断，确属错误就改写 query。

**盲审**：双方生成都完成后运行 `prepare`，然后用 **`prompts/review_v3.md`** 只读 `review_input_for_{自己}.jsonl`，写 `review_by_{自己}.jsonl`。不打开对方的 tasks 和 gen 文件。

**合并**：`python3 scripts/pipeline.py merge data/test_v1`。

### 测试集结果（2026-10-22）

- 交叉盲审：689 条全部通过（Claude 生成 338/338，GPT 生成 351/351）；去重丢弃 2 条，余 687 条；3 条软偏好措辞差异仅为提示。
- `scripts/select_test_sets.py`（种子 2026）截取：
  - `data/test_extract_v1.jsonl` 300 条：普通 Search 220 + 软偏好 80（四区各 20）；每个风格标签 ≥ 18，DSS 17，含布尔条件 74；Claude 145 / GPT 155。
  - `data/test_intent_v1.jsonl` 300 条：四类意图各 75（Search = 普通 50 + 追问 25）；Claude 152 / GPT 148。
- 泄漏检查：两个测试集引用的房源（含上下文房源）中 train 房源 0 套。
- **待负责人人工抽检**：`results/spotcheck_test_v1.xlsx`，每个测试集 15%（各 45 条，种子 15）。抽检通过后设为只读、写入 `sft/README.md`，即冻结 v1。
- 注意：交叉盲审通过率接近 100%，说明两家对同一份规则理解一致，但规则本身的问题只能靠人工抽检发现。之后按目标数截取、导出 15% 抽检表交负责人核对，再冻结。

**维护进度表时只改自己那一列，不改写其他章节。**

| 步骤 | Claude（338） | GPT（351） |
| --- | --- | --- |
| 生成 | ✅ 338 条，格式自检 0 问题，规则语义自查后修正 1 条 | ✅ 351 条，格式自检 0 问题；语义自查 1 条误报（T-00277 的 short stroll 非租期），人工核对通过 |
| 盲审对方 | ✅ `review_by_claude.jsonl` 351 条；GPT 生成部分合并结果 351/351 通过 | ✅ `review_by_gpt.jsonl` 338 条 |
| 合并 | ✅ 通过 689/689，去重后 687 条，`data/test_v1/report.md` | |

## 训练集（`data/train_v1/`，D9：全部由 GPT 生成）

`scripts/make_train_tasks.py --seed 6` 生成 3,564 个任务（目标 3,300 条，训练 3,000 + 验证 300，约 8% 超量），只用 train 房源，引用非 train 房源 0：

| 类型 | 任务数 | prompt |
| --- | ---: | --- |
| 普通 Search | 2,495 | `gen_search_v1.md` |
| 软偏好 | 356 | `gen_softpref_v2.md`（同时遵守 `gen_search_v1.md`） |
| 带新条件追问 | 178 | `gen_intent_v1.md` |
| Compare | 249 | `gen_intent_v1.md` |
| Specific_QA | 143 | `gen_intent_v1.md` |
| Chitchat | 143 | `gen_intent_v1.md` |

按零样本错误分析加权：缩写户型 874、拼写错误地名 752、完全不提户型 1,087、含 “&” 的站名 46；Compare 中“选最优”52、“排序”56。

### Codex 执行步骤

在 `/Users/Shared/LLM_project/AI-assistant/sft` 下：

1. 读 `data/train_v1/tasks_gpt.jsonl`，按 `kind` 选 prompt（见上表），**分批追加**写入 `data/train_v1/gen_gpt.jsonl`（建议每批 200–300 条）。每批后运行：
   - `python3 scripts/pipeline.py precheck data/train_v1 gpt`：只看已写部分的问题，未写任务显示“缺少生成结果”属正常；
   - `python3 scripts/lint_gen.py data/train_v1 gpt`：逐条判断，确属错误就改写。
2. 句式要多样：同一类任务不要反复使用相同的开头和模板；`hints` 与 `style_tags` 是写法要求，必须遵守。
3. 全部写完、两项检查都无问题后运行 `python3 scripts/pipeline.py prepare data/train_v1 --sample`，生成给 Claude 的 10% 抽样盲审输入。
4. 在下表打勾，并在更新记录追加一行。

### Claude 执行步骤

只读 `data/train_v1/review_input_for_claude.jsonl` 盲审，写 `review_by_claude.jsonl`，然后 `python3 scripts/pipeline.py merge data/train_v1 --sample`。估计错误率不超过 3% 则整体接受；否则定位问题模式，改 prompt 后重做相关部分。

| 步骤 | GPT（Codex） | Claude |
| --- | --- | --- |
| 生成 3,564 条 | ✅ 3,552 条；12 条软偏好任务因描述缺少素材未生成，按负责人决定放弃（软偏好仍有 344 条，超过目标 330） | |
| 10% 抽样盲审 | | ✅ 355 条，不一致 0 条，软偏好措辞差异 0 条 |
| 合并 | | ✅ 通过 3,552 条，无近似重复；`data/train_v1/report.md` |

### 训练集结果（2026-10-22）

- 估计错误率 0.0%（355 条抽样，95% 置信上限约 1%），低于 3% 门槛，整体接受。
- `scripts/split_train_val.py`（种子 20261023）按类型分层切分：`data/train_v1.jsonl` 3,197 条、`data/val_v1.jsonl` 355 条；数据量消融子集 `data/train_v1_1000.jsonl`、`data/train_v1_500.jsonl`（嵌套于全量训练集）。
- 意图分布：Search 3,017（含软偏好 344、追问 178）、Compare 249、Specific_QA 143、Chitchat 143。
- `scripts/pipeline.py` 去重加入长度与粗略相似度预筛，结果与原算法等价（测试集重跑一致），3,500 条合并从超时降到数秒。

## 小样之后

负责人看过小样报告、确认 prompt 和审核标准没问题后，再按同样流程批量生成：测试集约 600 条（阶段 4），训练集约 3,000 条（阶段 6），并考虑 500 / 1,000 / 3,000 条的数据量消融。非 Search 样本（阶段 3.2）和软偏好样本（阶段 3.3）的生成 prompt 尚未编写。

## 更新记录

| 日期 | 维护者 | 内容 |
| --- | --- | --- |
| 2026-10-22 | Claude | 创建：任务抽样、生成和审核 prompt、质检流水线；完成 Claude 一半的 25 条小样并通过格式自检；准备好给 GPT 的盲审输入。 |
| 2026-10-22 | Codex | 完成 GPT 一半的 25 条生成，格式自检 0 问题；独立盲审 Claude 的 25 条 query 并保存 `review_by_gpt.jsonl`；执行 prepare，给 Claude 的 25 条盲审输入已就绪；更新进度，等待 Claude 盲审及合并。 |
| 2026-10-22 | Claude | 盲审 GPT 的 25 条并合并：通过 49/50；修复车站名带线路括号的任务歧义。 |
| 2026-10-22 | Claude | 第二轮小样：新增非 Search、追问、软偏好三类任务和三份 prompt，流水线支持上下文与软偏好；Claude 一半 25 条完成并自检；写明 Codex 第二轮步骤。 |
| 2026-10-22 | Claude | 生成测试集任务 `data/test_v1`（689 个，配额全部满足），等待第二轮小样结果后开始生成。 |
| 2026-10-22 | Codex | 完成第二轮 GPT 25 条生成（五类各 5 条），格式自检 0 问题，软偏好改写检查通过；独立盲审 Claude 的 25 条并保存 `data/pilot2/review_by_gpt.jsonl`；执行 prepare，给 Claude 的 25 条盲审输入已就绪；更新第二轮进度，等待 Claude 盲审及合并。 |
| 2026-10-22 | Claude | 第二轮小样盲审并合并：通过 50/50；记录 D8 软偏好短语边界，prompt 升级为 gen_softpref_v2、review_v3；修正被回退的第一轮进度表；写明测试集执行步骤。 |
| 2026-10-22 | Claude | 测试集 Claude 一半 338 条生成完成，格式自检 0 问题；规则语义自查发现并修正 1 条（软偏好中出现 flat）。 |
| 2026-10-22 | Claude | 盲审 GPT 生成的 351 条（只读 review_input_for_claude），预合并显示 GPT 生成部分 351/351 通过；等待 GPT 盲审 Claude 的 338 条后正式合并。 |
| 2026-10-22 | Claude | 正式合并 689/689 通过；截取 test_extract_v1、test_intent_v1 各 300 条，配额满足、无泄漏；导出人工抽检表 results/spotcheck_test_v1.xlsx。 |
| 2026-10-22 | Claude | D9：训练集全部由 GPT 生成、Claude 10% 抽样盲审；生成训练任务 `data/train_v1`（3,564 个），流水线增加 `--sample` 抽样模式；写明 Codex 执行步骤。 |
| 2026-10-22 | Claude | 记录 D10 分工：Claude 规划、审核、布置任务；GPT 负责批量生成等重复性工作。 |
| 2026-10-22 | Codex | 按训练集步骤并行逐条生成并分 15 批写入 `data/train_v1/gen_gpt.jsonl`：3,552/3,564 条（Search 2,495、softpref 344、followup 178、Compare 249、Specific_QA 143、Chitchat 143）；12 条描述无法支持规定数量的非硬字段软偏好，未编造或修改任务，清单为 `data/train_v1/generation_issues_gpt.jsonl`。每批执行 precheck 和 lint；有效行格式/schema 无问题，最终缺少项恰为上述 12 条；lint 提示经核对为词根误报（站名 Garden/Shortlands、along、short stroll、weekly cleaning），无实际条件增漏。修正 7 条近似重复句式、1 处指代歧义及软偏好无来源修饰，最终 3,552 条按合并阈值无近似重复；344 条软偏好均完成独立来源自查。尚未执行 prepare --sample，待负责人确认不足任务的处理方式或 Claude 补充任务后再准备抽审。 |
| 2026-10-22 | Claude | 训练集 10% 抽样盲审 355 条全部一致；合并 3,552 条；分层切分训练 3,197 / 验证 355，并生成 500、1000 条消融子集；去重提速。 |
| 2026-10-22 | Claude | 新增真实 query 收集任务（D11），说明见 `REAL_QUERY_COLLECTION.md`。 |
