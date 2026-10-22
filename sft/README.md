# SFT 数据与实验记录

本目录为 AI-assistant 租房助手的意图识别与结构化抽取 SFT 实验。执行计划见 `EXECUTION_PLAN.md`，数据清洗记录见 `DATA_CLEANING_NOTES.md`，生成流水线见 `STAGE3_RUNBOOK.md`。

## 测试集 v1（2026-10-22 冻结，只读）

冻结后不得修改；如需修改另存 v2，并在结果中注明版本号。

| 文件 | 条数 | SHA-256 |
| --- | ---: | --- |
| `data/test_extract_v1.jsonl` | 300 | `f2f9330dd29ba4f7f4dddadd3242d5a33e54e065bf645884a5a1e472167e7011` |
| `data/test_intent_v1.jsonl` | 300 | `988c401f33e4d6092b23bbf9afe8c98e127d1d889d7c38c23ba0086b5e8439bc` |

### 组成

- **test_extract_v1**：普通 Search 220，软偏好 80（Shoreditch、Hampstead、Knightsbridge、Enfield 各 20，来自 test_region 房源）。
- **test_intent_v1**：Search 75，Specific_QA 75，Compare 75，Chitchat 75；其中 Search 含带新条件追问 25 条。

抽取测试集普通 Search 的风格标签分布：

| tag | 条数 |
| --- | ---: |
| price_format | 68 |
| abbrev_layout | 65 |
| loc_station | 60 |
| loc_typo | 55 |
| casual | 48 |
| multi_constraint | 41 |
| price_pw | 36 |
| loc_postcode | 35 |
| price_pcm | 33 |
| negation | 32 |
| uk_jargon | 18 |

抽取测试集中含 DSS 条件 17 条，含任一布尔条件 74 条。

### 生成与质检

| 项目 | 内容 |
| --- | --- |
| 房源来源 | `data/listings_clean.jsonl`，划分 `data/split.json` v1（种子 20261022）；测试集只用 test 与 test_region 房源，泄漏检查 0 |
| gold | 由 `scripts/make_tasks.py`、`make_extra_tasks.py`、`make_test_tasks.py`（种子 2026）按房源结构化属性决定；生成模型只写 query 和地点、软偏好的原样片段 |
| 生成模型 | Claude（Claude Opus 5.5，claude.ai 会话）297 条；GPT（经 Codex）303 条 |
| prompt | gen_search_v1、gen_intent_v1、gen_softpref_v2；盲审 review_v3 |
| 交叉盲审 | 对方只看 query（和上下文）独立抽取，与 gold 逐字段比较；689 条全部通过，去重后 687 条，按配额截取 600 条（`scripts/select_test_sets.py`） |
| 人工抽检 | 抽检表 `results/spotcheck_test_v1.xlsx`（每个测试集 15%，种子 15）。负责人于 2026-10-22 浏览后整体确认无问题，未逐条标注，因此**没有测得的人工错误率** |
| 生成日期 | 2026-10-22 |


## 阶段 5 准备：零样本基线（2026-10-22）

- 零样本 prompt：`prompts/zeroshot_v1.txt`（基于 `core/chatbot_config.py` 的 `SEARCH_EXTRACT_ALL_SYSTEM`，改为 v1 schema 并加入意图说明）。微调后评测使用同一 prompt。
- 推理：`scripts/infer.py`（vLLM，关闭思考模式，temperature 0；带上下文的样本以 “上一轮房源 + User message” 作为用户消息；另测 30 条单条延迟的 p50）。
- 评测：`scripts/evaluate.py`。评测前校验测试集 SHA-256，与冻结版本不一致即拒绝运行。字段级微平均 F1、意图准确率与混淆矩阵、多余字段率、JSON 与 schema 合法率、按 style_tag / 样本类型 / 生成方拆分，并输出错误样例。
- 自测：以 gold 作为预测时两个测试集 F1 与意图准确率均为 1.0；人为加入 3 处错误（预算改错、多抽花园、非法 JSON）后，F1 0.996、精确率 0.998、召回 0.9941，与手算一致。自测结果在 `results/selftest/`。
