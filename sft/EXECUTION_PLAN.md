# SFT 数据构建与 LoRA 微调：执行说明

> 本文档写给执行者（Astra），读完即可开始执行，不需要其他背景。
> 项目负责人：朱衍（Derek）。每个阶段末尾标有 **🛑 停下确认** 的地方，必须先把结果汇报给负责人，等确认后再进入下一阶段。
>
> 版本：v1，2026-10-22

---

## 0. 背景和目标

这是一个伦敦租房搜索助手。用户输入一句英文需求，例如 "1b1b near Canary Wharf, max £450 pw, I have a cat"，系统要用 **Qwen3.5-4B** 一次调用同时输出：

- **意图**（4 类之一）；
- **结构化条件**（地点、预算、户型、宠物等）。

本任务的目标：

1. 构建**测试集**和**训练集**；
2. 用 LoRA 微调 Qwen3.5-4B，提升结构化抽取能力；
3. 评测：字段级 F1（零样本 vs 微调后），以及意图准确率（确认微调前后**没有下降**）。

**意图不是微调目标。** Qwen 零样本做意图分类已经足够好。训练数据里混入少量非搜索样本，只是为了防止模型学成"永远输出 Search"。

---

## 0.5 工作方式：每一步开始前先确认（最重要）

**开始任何一个阶段、或阶段内任何一项新任务之前，必须先发一份"开工前确认"，等负责人回复"可以开始"后才能动手。** 不要自己猜测缺失的信息，也不要用默认值直接往下做。

"开工前确认"的格式：

```
【开工前确认】阶段 X：<任务名称>

1. 我准备做什么：<一两句话>
2. 需要用到的输入：<文件、数据、模型、API、GPU 等>，并逐项标注 ✅ 已具备 / ❌ 缺少
3. 缺少的东西（需要你补充）：
   - <缺什么、为什么需要、你需要提供什么>
4. 需要你决定的事：
   - <问题>（我的建议：<建议>）
5. 我的假设：<如果有不确定的地方，写出你打算怎么理解>
6. 预计产出：<文件名和内容>
```

规则：
- 第 3、4 项有任何内容时，**必须等负责人补充或决定之后再开始**；
- 执行过程中如果发现新的缺失或问题（比如 API 报错、数据和预期不符、某个字段取值很怪），**立刻停下来汇报**，不要自行绕过；
- 每完成一项任务，用一两句话汇报结果和产出的文件，再发下一项任务的"开工前确认"；
- 涉及花钱的操作（批量调用 API、租用 GPU），开工前确认里要写明预计的调用量。

---

## 1. 硬性规则（任何阶段都不能违反）

1. **数据来源**：所有 query 都由 LLM 基于真实房源的**结构化属性**生成。生成 Search query 时，**不能把房源描述原文给生成模型**，避免 query 和描述用词重合。
2. **标签**：生成时选中了哪些字段、取了什么值，就是这条 query 的标准答案（gold JSON），不另外标注。
3. **按房源划分**：一套房源只能属于训练侧或测试侧之一。同一套房源生成的 query 不能同时出现在训练集和测试集里。
4. **检索子库区域只进测试侧**：负责人选定的 4 个区域的全部房源，只能用于生成测试数据。
5. **被测模型不能参与造数据或标注**：Qwen3.5-4B 只做被测对象。
6. **测试集冻结**：测试集一旦冻结，就不能再根据评测结果修改。要改就另存新版本（v2），并在结果里注明版本号。
7. **全部英文**：query 不包含中文，也不中英混杂。
8. **可复现**：所有脚本固定随机种子；记录使用的模型名称、prompt 版本和日期。

---

## 2. 环境和位置

| 项目 | 路径 / 说明 |
|---|---|
| 项目仓库（主线） | `/Users/Shared/LLM_project/AI-assistant` |
| 房源数据 | `crawler/artifacts/merged/properties_merged.jsonl`（29,119 行，每行一套房源） |
| 现有抽取 prompt | `core/chatbot_config.py` 里的 `SEARCH_EXTRACT_ALL_SYSTEM`（作为 schema 和零样本 prompt 的参考） |
| 工作目录 | 在仓库里新建 `sft/`，所有脚本和数据都放在这里 |
| GPU | RunPod，启动步骤见仓库里的 `RUNPOD_SESSION_SETUP.md` |

**git 注意**：这个仓库的 `.git` 引用了一个不存在的目录（`.git/objects-overflow`），部分 git 命令可能报错。开始前先运行 `git status` 检查。如果能正常工作，就新建分支 `sft-data`；如果不能，**不要尝试修复 git**，直接在 `sft/` 目录里工作，并告诉负责人。

建议的目录结构：

```
sft/
  README.md              # 记录每个阶段做了什么、用了哪个模型和 prompt 版本
  config.yaml            # 随机种子、模型名、各类数量
  data/
    listings_clean.jsonl
    split.json           # 每套房源属于 train / test / test_region
    test_intent_v1.jsonl
    test_extract_v1.jsonl
    train_v1.jsonl
    val_v1.jsonl
  prompts/               # 所有生成和核对用的 prompt，文件名带版本号
  scripts/
  results/
```

---

## 3. 房源数据的已知情况

**数量**：Rightmove 23,592 套，OpenRent 5,527 套，`listing_id` 没有重复。

**字段有效率**（有明确取值的比例）：

| 字段 | Rightmove | OpenRent | 说明 |
|---|---|---|---|
| price_pcm / price_pw | 100% | 100% | |
| bedrooms | 99% | 100% | |
| bathrooms | 95% | 100% | |
| property_type | 99% | 100% | 取值很杂，需要归一化，见下表 |
| furnish_type | 87% | 100% | 含 "ask agent"、"Furnished or unfurnished, landlord is flexible" 等，需要归一化 |
| let_type | 94% | 100% | **OpenRent 的这一列混入了家具的值**（Furnished / Unfurnished），只认 "Long term" / "Short term" |
| available_from | 72% | 100% | **大量值等于抓取日期**（即"现在可入住"），见下面的说明 |
| postcode_district | 3% | 100% | Rightmove 要从 `address` 末尾解析邮编区号（如 "..., London, SW1V"） |
| 7 个布尔字段 | **6%** | **98%–100%** | pets_allowed、garden、parking、bills_included、student_friendly、families_allowed、smokers_allowed |
| dss_income_accepted | 0% | 32% | 样本少，需要单独控制比例 |

**无效值**：`None`、空字符串、`nan`、`ask agent`、`Ask agent`，一律视为没有值，生成时不能选这些字段。

**property_type 归一化**（初稿，阶段 1 由负责人确认）：

| 原始值 | 归一化 |
|---|---|
| Flat、Apartment、Penthouse、Maisonette | flat |
| Studio | studio（bedrooms = 0） |
| Room、House Share | room |
| Terraced、Semi-Detached、Detached、End of Terrace、House | house |

**available_from**：如果值等于或接近抓取日期（`scraped_at` 前后 7 天内），视为"现在可入住"，**不作为日期字段使用**。只有明显晚于抓取日期的值才能作为入住日期，精确到月（`YYYY-MM`）。

**区域**：`discovery_paths` 字段是区域列表（如 `["Whitechapel, London", "Shoreditch, London"]`），用来给房源打区域标签、挑选 4 个子库区域。

**stations** 字段可能是字符串形式的列表，需要先解析。

---

## 4. 输出 schema（草案，阶段 1 确认）

模型的输出格式：

```json
{
  "intent": "Search",
  "constraints": {
    "location_keywords": ["Canary Wharf"],
    "commute_destination": null,
    "max_rent": {"value": 450, "period": "pw"},
    "layout_options": [{"bedrooms": 1, "bathrooms": 1, "property_type": null}],
    "furnish_type": null,
    "let_type": null,
    "available_from": null,
    "pets_allowed": true,
    "garden": null,
    "parking": null,
    "bills_included": null,
    "student_friendly": null,
    "families_allowed": null,
    "smokers_allowed": null,
    "dss_accepted": null
  },
  "soft_preferences": []
}
```

- **intent**：Search、Specific_QA、Compare、Chitchat 之一。
  - Search：找房，包括带新条件的追问，如 "what about ones with a garden?"；
  - Specific_QA：问已展示的某一套房源，如 "does the second one allow pets?"；
  - Compare：比较已展示的几套房源，如 "compare the first two"；
  - Chitchat：打招呼、闲聊、和租房无关的问题。
- **非 Search 时**，constraints 全部为 null 或空列表。
- **location_keywords**：原样抽取 query 里的地名或邮编，**不纠正拼写**。query 里写了 "Shordich"，标准答案就是 "Shordich"。
- **max_rent**：数值 + 周期（`pcm` / `pw` / `pppw`），**不换算**，换算交给代码。
- **用户没提到的字段一律为 null**。
- **soft_preferences**：软偏好的原文短语，如 "quiet"、"lots of natural light"，**不计入 F1**。

**和现有代码的区别**：现有 prompt 用的是 `max_rent_pcm`（让模型自己换算成月租），SFT 改为数值 + 周期；另外新增了 8 个布尔字段和 intent。

---

## 5. 执行阶段

### 阶段 1：定规则

**任务**
1. 读 `core/chatbot_config.py` 的 `SEARCH_EXTRACT_ALL_SYSTEM`，对照第 4 节的 schema 草案，列出差异。
2. 写 `sft/schema.json`（JSON Schema）和 `sft/ANNOTATION_GUIDE.md`（标注规范：每个字段的定义、取值、正反例各 2–3 个）。
3. 列出需要负责人拍板的问题，至少包括：
   - property_type 和 furnish_type 的归一化表；
   - 否定条件怎么表示（如 "not a house share"、"not ground floor"）；
   - 是否覆盖多轮修改（建议本次**不做**）；
   - commute_destination 是否保留在本次的 F1 字段里。

**🛑 停下确认**：提交 schema、标注规范和问题清单。

### 阶段 2：整理房源数据

**任务**
1. 写 `scripts/clean_listings.py`，输出 `data/listings_clean.jsonl`，每套房源只保留生成需要的字段，已经归一化，无效值统一为 null。另外保留 `description`（只用于软偏好）。
2. Rightmove 从 `address` 解析邮编区号（正则匹配末尾的 outcode，如 `E14`、`SW1V`）。
3. 给每套房源打区域标签（来自 `discovery_paths`）。
4. 统计报告 `results/listings_stats.md`：每个字段的有效率；每个区域的房源数（按房源数排序，列出前 30 个区域）。
5. 负责人选定 4 个区域后，写 `data/split.json`：
   - 4 个区域的全部房源 → `test_region`；
   - 其余房源按 `listing_id` 随机划分：约 10% → `test`，其余 → `train`；
   - 固定随机种子，划分之后不再改动。

**验收**
- `listings_clean.jsonl` 行数 = 29,119（或说明剔除了多少、为什么）；
- 每套房源在 `split.json` 中有且只有一个归属。

**🛑 停下确认**：提交统计报告。负责人选 4 个区域（建议风格各不相同，每区约 250 套）。

### 阶段 3：写生成流水线

#### 3.1 Search query

1. 从一套房源中**随机选 k 个有效字段**，k 在 1–6 之间随机。地点类字段（区域名、邮编、附近车站，三选一）出现的概率要高一些。
2. 随机指定写法风格（每条 1–3 个），作为 `style_tags` 记录下来：

| tag | 写法示例 |
|---|---|
| price_pw / price_pcm / price_pppw | "£450pw"、"1.8k pcm"、"£200 pppw" |
| price_format | "under 2k"、"no more than £1,800 a month" |
| abbrev_layout | "1b1b"、"2 bed 1 bath"、"studio"、"double room in a house share" |
| uk_jargon | "bills inc"、"DSS welcome"、"en-suite"、"no guarantor" |
| loc_postcode | "E14"、"SW9" |
| loc_station | "near Bank"、"close to Angel" |
| loc_typo | 地名带拼写错误，如 "Shordich" |
| negation | "not a house share"、"no smokers" |
| casual | 口语、不完整的句子 |
| multi_constraint | 一句话包含 5 个以上条件 |

3. 生成模型的输入：选中的字段和取值 + 风格要求。**不提供房源描述。**
4. 生成模型的输出：`{"query": "...", "gold": {...}}`。地点类字段的 gold 必须是 query 里**原样出现**的文本。
5. 价格可以写成 pw 或 pcm（房源里两者都有），gold 记录 query 里实际使用的数值和周期。

#### 3.2 非 Search 样本

- **Specific_QA / Compare**：先随机抽 5 套房源，组成"上一轮展示的结果"作为上下文，再让 LLM 写追问或比较。
- **Chitchat**：LLM 直接写，覆盖打招呼、无关问题、带租房词的闲聊（如 "renting in London is so expensive lol"）。
- **边界样本**：带新条件的追问，gold 意图为 Search，并抽取新条件。

#### 3.3 软偏好 query（只用于测试集，共 80 条）

- 只从 `test_region` 的房源生成，4 个区域各约 20 条。
- 在 3.1 的基础上，**额外**把房源描述给生成模型，让它挑 1–2 个特点，**用自己的话改写**成软偏好写进 query。要求改写后的说法和描述原文**没有 3 个以上连续相同的词**，用脚本检查。
- 记录每个软偏好的强调程度：强调语气（must、really need）权重 2，其余 1。

#### 3.4 每条样本的格式

```json
{
  "id": "X-000123",
  "source_listing_id": "openrent:123456",
  "split": "test",
  "context": null,
  "query": "...",
  "gold": {"intent": "Search", "constraints": {...}, "soft_preferences": []},
  "style_tags": ["price_pw", "abbrev_layout"],
  "soft_pref_weights": null,
  "gen_model": "...",
  "prompt_version": "gen_search_v1"
}
```

非 Search 样本的 `context` 是上一轮展示的房源摘要，`source_listing_id` 记录用到的房源 ID 列表。

#### 3.5 质检流水线

1. **schema 校验**：不通过的直接丢弃。
2. **反向核对**：用另一个模型（**和生成模型不同厂商**，且不能是 Qwen3.5-4B）只看 query 抽一遍，和 gold 逐字段比较。不一致的样本先保存到 `rejected.jsonl` 并记录原因，不进入数据集。
3. **去重**：去掉近似重复的 query（如字符级相似度 > 0.9）。
4. **统计**：通过率、丢弃原因分布、各 style_tag 的数量。

**🛑 停下确认**：先小批量生成 50 条，把样本、反向核对结果和通过率交给负责人看，确认 prompt 没问题后再批量生成。

### 阶段 4：生成测试集

**数量**

| 文件 | 内容 | 来源房源 |
|---|---|---|
| `test_intent_v1.jsonl` | 4 类意图各 75 条，共 300 条 | `test` + `test_region` |
| `test_extract_v1.jsonl` | 约 300 条，以 Search 为主，包含 3.3 的 80 条软偏好 query | `test` + `test_region` |

- 抽取测试集里，每个 style_tag 至少 15 条；
- 含布尔字段的 query 主要来自 OpenRent 房源；DSS 至少 10 条。

**人工抽检**：从两个测试集里各随机抽 15%，导出成表格（query、gold、style_tags），交给负责人逐条核对，记录错误率。

**冻结**：负责人确认后，把文件设为只读，在 `sft/README.md` 里记录条数、意图分布、style_tag 分布、生成和核对用的模型、日期。

**🛑 停下确认**：提交抽检表和统计。

### 阶段 5：零样本基线和错误分析

1. 在 RunPod 上部署 Qwen3.5-4B（关闭思考模式，temperature = 0）。
2. 零样本 prompt：以 `SEARCH_EXTRACT_ALL_SYSTEM` 为基础，改成第 4 节的 schema 并加入意图说明，保存为 `prompts/zeroshot_v1.txt`。**之后微调模型的评测也用同一个 prompt。**
3. 写评测脚本 `scripts/evaluate.py`：
   - **字段级 F1**：每个字段（列表的每一项、每个布尔键值对）算一个槽位，和 gold **完全匹配**才算 TP；抽错同时记 FP 和 FN；漏抽记 FN；多抽（gold 为 null 而模型输出了值）记 FP；所有样本汇总后算微平均 F1。soft_preferences 不计入。
   - **意图准确率** + 各类召回 + 混淆矩阵。
   - **多余字段率** = 多抽的槽位数 ÷ gold 为 null 的槽位总数。
   - **JSON 合法率**。
   - **按 style_tag 拆分**的 F1。
4. **错误分析**：输出 `results/zeroshot_errors.md`，按字段和 style_tag 统计错误，每类附 3 个例子。

**🛑 停下确认**：提交零样本结果和错误分析。负责人据此决定训练数据的配比。

### 阶段 6：生成训练集

1. 只从 `train` 房源生成，使用同一套生成和质检流水线。
2. 规模：起步 4,000 条（以负责人确认的数字为准），其中 10% 划为验证集 `val_v1.jsonl`。
3. 配比：
   - Search 约 85%，其余约 15% 为 Specific_QA、Compare、Chitchat；
   - 按阶段 5 的错误分布，**加大错误多的 style_tag 的比例**；
   - 包含负样本：只提 1–2 个条件的短 query，其余字段为 null。
4. **泄漏检查**：训练集和两个测试集之间，没有相同的 `source_listing_id`，也没有近似重复的 query。

**🛑 停下确认**：提交训练集统计和泄漏检查结果。

### 阶段 7：LoRA 训练

- 工具：transformers + PEFT + TRL 的 SFTTrainer（或 LLaMA-Factory）。
- 起始配置：r = 16，α = 32，dropout = 0.05，学习率 1e-4，2–3 个 epoch，最大长度 1024，**loss 只算输出部分**。
- 使用 Qwen 自带的 chat template；system prompt 与 `zeroshot_v1.txt` 一致。
- 每个 epoch 在验证集上算字段级 F1 和意图准确率，选 F1 最高、且意图准确率没有下降的 checkpoint。
- 记录：数据量、显卡型号、训练时长、每个 epoch 的验证集结果、最终选用的 checkpoint。

### 阶段 8：评测和报告

1. 用 `evaluate.py` 和 `zeroshot_v1.txt` 在两个冻结的测试集上评测微调后的模型。
2. 输出 `results/final_report.md`，包括：

| 指标 | 零样本 | LoRA 微调 |
|---|---|---|
| 字段级 F1 | | |
| 意图准确率 | | |
| 多余字段率 | | |
| JSON 合法率 | | |
| 单次推理延迟 p50 | | |

   另附：按 style_tag 拆分的 F1 对比、意图混淆矩阵对比、**微调后仍出错的例子**（每类 2–3 个）。
3. **如实报告数字**，不要为了接近某个目标值去调整测试集或评测规则。

**🛑 停下确认**：提交最终报告。

---

## 6. 需要负责人提供或决定的事项

| 事项 | 在哪个阶段需要 |
|---|---|
| schema、归一化表、否定的表示方式 | 阶段 1 |
| 4 个检索子库区域 | 阶段 2 |
| 生成模型和反向核对模型（必须来自不同厂商） | 阶段 3 |
| 人工抽检（每个测试集约 45 条） | 阶段 4 |
| RunPod GPU（24GB 显存以上） | 阶段 5 |
| 训练集规模 | 阶段 6 |
