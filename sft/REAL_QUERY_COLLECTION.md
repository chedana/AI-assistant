# 真实用户 query 收集说明（real_v1，100 条）

共同维护：Claude（规划、审核）、Codex（收集、初标）。负责人：朱衍（Derek）。依据：D10 分工。最后更新：2026-10-22，Claude、Codex。

## 目的

现有测试集全部由模型合成，句式比真实用户规整。本任务从公开网页收集约 100 条**真实用户写的伦敦租房需求**，作为独立的“真实测试集”，检验微调模型在真实输入上是否同样有效。它**只用于评测，绝不进入训练集**。

## 来源（按优先级）

| 来源 | 说明 | 上限 |
| --- | --- | ---: |
| Gumtree “Property Wanted / Flats & Houses Wanted”（伦敦） | 用户发布的求租广告，最接近搜索输入 | 50 |
| Reddit：r/london、r/HousingUK、r/LondonHousing 等的找房帖 | 只取帖子里陈述找房需求的句子 | 40 |
| 其他公开论坛、问答站中伦敦租房求助帖 | 补充 | 20 |
| SpareRoom 等合租平台 | 大多是找房间，不在范围内，只收明确找整套房的帖子 | 10 |

单一来源不超过 50 条。

## 必须遵守

1. **只读公开页面**：不登录、不注册、不绕过付费墙或反爬限制、不使用自动爬虫批量抓取；逐页人工式阅读，100 条即止。
2. **不收集个人信息**：去掉人名、用户名、电话、邮箱、链接、具体门牌地址、工作单位等能识别个人的内容。用户自己的身份描述（“I'm a student”“we have a dog”）可以保留，因为它可能表达条件。
3. **保留原话**：`query` 必须是用户的原文，只允许：
   - 截取与找房需求相关的连续一到三句（`trimmed` 标为 true）；
   - 删除个人信息，用 `[removed]` 替换；
   - 不改拼写、不改大小写、不补标点、不翻译、不润色。
4. **范围**：伦敦（含周边通勤区）、租房、英文。找整套房（flat、studio、apartment、house）优先；合租找房间的帖子只收少量，并标 `in_scope: false`。
5. **去重**：同一用户、同一帖子只取一条；明显的模板化中介广告不收。
6. **时间**：任何年份的帖子都可以；记录发帖日期（能看到的话），因为“from next month”这类相对日期按规范不抽取。

## 输出

### 第 1 步：`data/real_v1/collected.jsonl`

每行一条：

```json
{"id": "REAL-001", "source": "gumtree", "url": "https://...", "post_date": "2025-11-03", "collected_at": "2026-10-23",
 "query": "用户原文（已去除个人信息）", "trimmed": false, "in_scope": true, "notes": "可选：截取说明等"}
```

`url` 只用于追溯来源，不进入评测输入。

### 第 2 步：`data/real_v1/gold_gpt.jsonl`

按 `ANNOTATION_GUIDE.md` 和 `schema.json`，为每条 query 标注标准答案初稿：

```json
{"task_id": "REAL-001", "intent": "Search", "constraints": { ...15 个键全部写出... }, "soft_preferences": ["..."]}
```

规则要点：只抽硬性条件；地点原样；预算保留用户写的周期，没写周期则 `max_rent` 为 null；相对日期为 null；可选喜好进 `soft_preferences`（只取内容短语，不含 ideally、would be nice 等词）；不从人数推断卧室数。拿不准的写进 `notes`，不要猜。

### 第 3 步：检查并准备盲审

```bash
python3 scripts/real_queries.py check data/real_v1
python3 scripts/real_queries.py prepare data/real_v1
```

`check` 必须 0 问题（个人信息、格式、重复、来源比例）。`prepare` 生成只含 `task_id` 和 `query` 的 `review_input_for_claude.jsonl`。完成后在下表打勾并通知负责人。

## Claude 的部分

只读 `review_input_for_claude.jsonl`，按同一规范**独立盲标**，写 `gold_claude.jsonl`；运行 `python3 scripts/real_queries.py compare data/real_v1` 得到两人一致率与分歧清单；逐条裁决分歧，写出最终 `data/real_test_v1.jsonl`，由负责人确认后冻结。

## 进度

| 步骤 | Codex | Claude |
| --- | --- | --- |
| 收集 100 条 | ✅ | |
| 标注初稿 | ✅ | |
| check + prepare | ✅ | |
| 独立盲标、比对、裁决 | | ✅ |
| 冻结 real_test_v1 | | ⏳ 待负责人确认 |

本轮完成记录（Codex，2026-10-22）：

- 已写入 `data/real_v1/collected.jsonl`、`gold_gpt.jsonl`、`review_input_for_claude.jsonl`，各 100 条，ID 为 `REAL-001` 至 `REAL-100`。
- 来源：Gumtree 30、Reddit 40、其他公开论坛 20、SpareRoom 网络 10（SpareRoom 9 + Findaflat 1），各类别与单站均未超上限。98 条 `in_scope: true`，2 条含合租单间的需求已标 `false`。
- 逐页人工式读取公开内容并核对可见作者，未登录或批量爬取；21 条依据公开搜索索引返回的完整正文核验，详情页工具返回 Cache miss 或未显示正文，未声称已验证实时在线，均在 `notes` 中说明。返回封禁、robots 限制或明确失效的页面跳过。
- 91 条截取连续原句，9 条保留完整描述；非 Reddit 每页摘录不超过 25 词，因此短句占比较高。45 条可确认发帖日期，其余为 null；不把 Date Wanted 当发帖日期，不推算相对时间。3 条替换了姓名，均使用 `[removed]`。
- 已复核初稿的硬软区分、预算周期、相对日期、身份与许可区别。无法由单值字段确定的多个通勤地点等情况标 null 并写入 notes，留待盲标裁决。初稿不等于冻结 gold。
- 已执行 `python3 -B scripts/real_queries.py check data/real_v1`：100 条、问题 0 条；另核验精确总数、四类来源配额、ID/URL/query 唯一、标注一一对应、全部 15 键及原文短语匹配。
- 已执行 `python3 -B scripts/real_queries.py prepare data/real_v1`。脚本附带的 `context: null` 已从本轮生成文件移除，使盲标输入严格只含 `task_id`、`query`；不含来源、notes 或 GPT 标签。重新运行现有 prepare 脚本会再次附带空 context。
- 附加核验记录：`source_provenance.jsonl`（链接、读取方式、原句哈希及定位）、`reddit_source_quotes.md`（原文引用与链接）、`collection_check.json`（统计与文件哈希）。这些文件供追溯，不作为 Claude 盲标输入。Claude 下一步只读 `review_input_for_claude.jsonl` 独立标注；本数据仅用于评测，未加入训练集。

## 更新记录

| 日期 | 维护者 | 内容 |
| --- | --- | --- |
| 2026-10-22 | Claude | 创建：来源、合规要求、输出格式、检查与双人标注流程。 |
| 2026-10-22 | Codex | 完成第 1–3 步：100 条真实 query、100 条初稿标注，check 0 问题，准备 100 条 Claude 盲标输入；来源配额、索引证据限制及附加追溯文件见完成记录。 |
| 2026-10-22 | Claude | 独立盲标 100 条（`gold_claude.jsonl`），一致率 77%；裁决 23 条分歧（GPT 15、Claude 8），定 7 条真实数据口径；输出 `data/real_test_v1.jsonl`（未冻结），见 `data/real_v1/adjudication.md`。 |
