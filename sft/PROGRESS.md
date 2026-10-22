# SFT 实验每日进展

每天一节，最新的放在最上面。每节固定四部分：完成了什么、关键数字、踩坑记录、待决事项与下一步。
详细过程见 `DATA_CLEANING_NOTES.md`（阶段 2）、`STAGE3_RUNBOOK.md`（阶段 3–4）、`README.md`（测试集冻结信息与脚本说明）。

---

## 2026-10-22（第 1 天）

### 完成了什么

| 阶段 | 内容 | 产出 |
| --- | --- | --- |
| 2 数据清洗 | 房型筛选、价格换算、异常值处理、邮区解析、区域标签、统计报告 | `data/listings_clean.jsonl`（21,965 套）、`results/listings_stats.md` |
| 2 划分 | 选定 4 个测试区（Shoreditch、Hampstead、Knightsbridge、Enfield），按房源划分 | `data/split.json` v1：train 18,631 / test 2,070 / test_region 1,264 |
| 3 生成流水线 | 脚本决定 gold，GPT 与 Claude 各写一半 query，交叉盲审，合并去重 | `scripts/make_tasks.py` 等、`scripts/pipeline.py`、`scripts/lint_gen.py`、6 份 prompt |
| 3 小样 | 两轮各 50 条 | 第 1 轮 49/50 通过，第 2 轮 50/50 |
| 4 测试集 | 689 条全部通过交叉盲审，按配额截取，人工抽检后冻结 | `data/test_extract_v1.jsonl`、`data/test_intent_v1.jsonl` 各 300 条（SHA-256 见 README） |
| 5 零样本基线 | RunPod 上用 vLLM 跑 Qwen3.5-4B，评测并做错误分析 | `results/eval_zeroshot_*.md`、`results/zeroshot_errors.md` |

### 关键数字（Qwen3.5-4B 零样本，prompt `zeroshot_v1`）

| 指标 | 抽取测试集 | 意图测试集 |
| --- | ---: | ---: |
| 字段级 F1 | 0.923 | 0.930 |
| 意图准确率 | 0.993 | **0.843** |
| schema 合规率 | **0.677** | 0.880 |
| 多余字段率 | 1.2% | 0.07% |
| JSON 合法率 | 100% | 100% |
| 单条延迟 p50 | 4.7 s | 4.7 s |

错误集中在三处：
- **户型 F1 0.671**：无户型要求却输出全空户型项 36、没说 flat 却补 flat 26、缩写（1b1b、3b）抽错 14、studio 未补 1 卫 8；另有 130 条把空户型写成 `null`，是 schema 不合规的全部原因。
- **地点 F1 0.912**：自动纠正拼写 11（"Marble Acrh" → "Marble Arch"）、拆分复合站名或多抽 14（"Finchley Road & Frognal" 被拆开）。
- **比较意图召回 0.40**：“哪个最……”被判成 Specific_QA（27），“排个序”被判成 Chitchat（18）。其余意图接近满分。
- 预算、家具、租期、日期、8 个布尔字段接近满分；软偏好 80 条抽出 79 条。
- 输出为带缩进的 JSON，平均 518 字符，是延迟偏高的原因之一。

运行环境：RunPod，RTX PRO 6000 Blackwell 的 MIG 分片（24 GB），vLLM 0.32.0，torch 2.13（CUDA 13），每个测试集生成约 60 秒。

### 踩坑记录

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 354 条 Rightmove 地址是“请开启 JavaScript”提示文字 | 爬虫缺陷 | 用 title 替代并打标记 |
| 705 条 Studio 原始卧室数为 1 | 来源口径不一 | 按 0b1b 规则统一 |
| 车站名带线路括号，两家对地点片段理解不同 | 任务设计歧义 | 给生成模型前去掉括号和 “Station” |
| 软偏好短语是否包含 ideally、would be nice 不统一 | 规范示例不一致 | D8：只取内容短语，prompt 升级 v2/v3 |
| 合并时 “Good morning!” 两家写得完全一样 | 闲聊句式短 | 去重脚本自动丢弃 |
| `push.sh` 切分支中途失败，82 个文件被删 | 仓库部分文件属于另一个 Mac 用户，`claudeapi` 无权限 | `git checkout -- .` 恢复；改为在 `~/AI-assistant-sft` 另克隆，只推 `sft/` 到 `sft-experiment` 分支 |
| `push.sh` 用 `git add -A`，`.env` 当时未被忽略 | 分支切换中途 `.gitignore` 被替换 | 改用只 `git add sft`，避免密钥上传 |
| GitHub SSH 连接被断开 | 本机代理拦截 22 端口 | `~/.ssh/config` 改走 `ssh.github.com:443` |
| RunPod 上 pip 往系统 Python 装，PyJWT 卸载失败 | 镜像缺 `python3.12-venv`，虚拟环境没建成 | 先装 `python3.12-venv` 再建 venv |
| 网页终端断开 | 浏览器连接中断 | 改用 `nohup … &` 后台运行 |
| 测试集只读权限设置无效 | 文件夹挂载方式不支持 chmod | README 记录 SHA-256，评测脚本运行前校验 |
| 人工抽检表未逐条填写 | 负责人整体确认 | 如实记录为“无测得的人工错误率” |

### 决策记录

- D1–D8：见 `DATA_CLEANING_NOTES.md`、`STAGE3_RUNBOOK.md`。
- 生成用订阅额度：Claude（claude.ai 会话）与 GPT（Codex）各生成一半、交叉盲审。
- 推理统一在 RunPod 上用 vLLM，基线和微调同一环境；不使用第三方 API 的 FP8 版本作为基线。
- 代码同步：`~/AI-assistant-sft` 的 `sft-experiment` 分支；RunPod 结果推回后拷入 `/Users/Shared/LLM_project/AI-assistant/sft/results/`。

### 晚间补充：训练集任务已就绪

- `data/train_v1/tasks_gpt.jsonl`：3,564 个任务（普通 Search 2,495、软偏好 356、追问 178、Compare 249、Specific_QA 143、Chitchat 143），只用 train 房源，按零样本错误加权。
- 流水线新增 `--sample` 模式：未抽中盲审的样本只需通过格式与 schema 检查。
- **下一步：交给 Codex 按 `STAGE3_RUNBOOK.md` “训练集” 一节生成。**

### 深夜补充：训练集完成

- GPT 生成 3,552 / 3,564 条（12 条软偏好任务缺少描述素材，放弃）；Claude 抽样盲审 355 条，**不一致 0 条**，软偏好措辞差异 0 条。
- 切分：`data/train_v1.jsonl` 3,197 条、`data/val_v1.jsonl` 355 条；消融子集 500、1000 条。
- 踩坑：合并去重对 3,500 条两两比较超时 → 加长度与粗略相似度预筛，结果等价。
- **下一步**：Claude 写 SFT 数据格式转换（chat template、紧凑 JSON、只对回答计算 loss）和 LoRA 训练脚本；负责人在 RunPod 先跑 Qwen3.5-2B 零样本，再决定主实验模型并开训。

### 新任务：真实用户 query 测试集（real_v1）

- 负责人决定（D11）：从公开网页收集约 100 条真实伦敦租房需求，作为只用于评测的真实测试集。
- 说明：`REAL_QUERY_COLLECTION.md`（来源、隐私与合规、保留原话、输出格式）；脚本 `scripts/real_queries.py`（check / prepare / compare，已自测）。
- 流程：Codex 收集并标注初稿 → Claude 独立盲标 → 计算双人一致率、逐条裁决分歧 → 负责人确认后冻结 `data/real_test_v1.jsonl`。

### 新任务：量化推理对照实验（Q 系列，只用 2B）

- 负责人决定（D12）：量化实验只用 Qwen3.5-2B，不再包含 4B；Red Hat 没有 2B 预量化版本，所有量化格式均由我们用 llmcompressor 自行量化。
- 设计：`QUANT_INFERENCE_PLAN.md`（6 个研究问题、控制变量、噪声地板、Q1–Q4 配置、测量方法、判定标准、实验前预期）。
- 脚本：`scripts/infer.py` 升级（量化与 KV cache 选项、先写预测再测速、TTFT/TPOT/吞吐）；`scripts/quantize.py`（llmcompressor：RTN / GPTQ / AWQ / FP8 / INT8，校准只用训练集）；`scripts/run_quant.sh`（分阶段一键运行，失败跳过、可续跑）；`scripts/quant_report.py`（配对 bootstrap 置信区间、意图翻转、按字段与风格定位损失）。
- 报告脚本已用人为改坏的预测自测，能正确检出 −1.19 个点并定位到户型字段。vLLM 与 llmcompressor 相关部分需要在 RunPod 上首次运行时验证。

### 分工（D10）

Claude 负责规划、审核、布置任务；GPT（Codex）负责批量生成等消耗 token 的重复性工作。审核与生成保持不同厂商。

### 待决事项与下一步

**训练集尚未开始生成。** 负责人决定（D9）：训练数据全部交给 GPT（Codex）生成，因为其额度更多；Claude 随机抽 10% 盲审估计错误率，满足“核对模型与生成模型不同厂商”的规定。训练数据句式只来自 GPT，评测时按生成方拆分 F1 观察是否偏向 GPT 写法。

计划配比：

1. 训练集配比（Claude 提议）：
   - 规模 3,000 条，另留 10% 验证集；
   - Search 约 85%：加大缩写户型、拼写错误地名、含 “&” 的复合站名、完全不提户型、不说 flat 的样本；
   - 非 Search 约 15%：以 Compare 为主（“哪个最……”、“排个序”），其余 Specific_QA、Chitchat；
   - **训练集也放约 10% 软偏好样本**（用 train 房源），避免微调后丢掉软偏好抽取能力；
   - 训练目标使用紧凑 JSON。
2. 模型尺寸（负责人倾向）：主实验考虑 Qwen3.5-2B 或 0.8B，目标是“小模型微调后追平或超过 4B 零样本”，并降低延迟。下次开 RunPod 先跑 2B 零样本再定。零样本基线始终使用 `zeroshot_v1`，不削弱基线。
3. 可选：微调模型使用短 system prompt（prompt 蒸馏），单独报告延迟变化；以 4B 为老师做 logit 蒸馏对比。
4. 简历上的 0.84 → 0.95 与实测不符，改用实测数字和具体改进点。

### RunPod 流程（2026-10-22 更新）

改为 Mac 端 `scripts/runpod.sh` 经 SSH 直接上传 sft/ 并装环境，不再依赖 GitHub 推送和 Pod 上的 SSH key。命令：`up`（新 Pod）/`push`/`run`/`sh`/`pull`。`runpod_setup.sh` 改为由 `up` 自动远程调用，一次装齐推理和 LoRA 训练依赖，并后台预下载 Qwen3.5-2B。

- 2026-10-22：负责人决定当前只做 Qwen3.5-2B（零样本 + LoRA），4B 暂不考虑。

### 2026-10-22 夜：real_v1 盲标与裁决（Claude）

- Claude 只读 `review_input_for_claude.jsonl` 独立盲标 100 条 → `data/real_v1/gold_claude.jsonl`。
- 与 GPT 初稿比对（`agreement.md`）：完全一致 77/100。分歧主要在地点片段 10、通勤 4、意图 3、户型 5、预算 2、bills 2。
- 逐条裁决（`adjudication.md`）：采用 GPT 15 条、Claude 8 条；新定 7 条真实数据口径（预算区间取上限、including bills → true、求建议但有条件 → Search、-ish 后缀与线路名不算地点等）。
- 输出 `data/real_test_v1.jsonl`：100 条，Search 97、Chitchat 3；字段兼容 `infer.py` / `evaluate.py`（kind=real、generator=real），gold 自测通过。
- 建议排除 4 条（`exclude_suggested`）：058 house-sitting、061 一个月旅行、065/066 合租单间；评测时同时报 100 条与 96 条。
- **待负责人**：确认 4 条是否排除 → 冻结并把 SHA-256 写入 `evaluate.py` 的 FROZEN。
- 观察：真实 query 与合成数据差异明显——有 15 条给了预算却没写周期（v1 规则下 max_rent 为 null）、大量“求建议”句式、身份陈述多、相对日期多。零样本与微调模型在这批数据上的 intent 与 max_rent 表现值得单独看。
