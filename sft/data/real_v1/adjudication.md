# real_v1 分歧裁决（Claude，2026-10-22）

双人独立标注 100 条，完全一致 77 条（77.0%）。23 条分歧逐条裁决：采用 GPT 15 条，采用 Claude 8 条。

最终意图分布：{'Search': 97, 'Chitchat': 3}。

| task_id | 采用 | 理由 |
| --- | --- | --- |
| REAL-013 | gpt | “£1050 with all bills” 统一按 bills_included=true（与 071 一致） |
| REAL-031 | gpt | “open to other areas of London” 构成地点 London |
| REAL-032 | gpt | north/east/west/central 均为原文片段，保留 |
| REAL-034 | gpt | “an hour from Holborn High station” 作为地点锚点，与 013 的 Chiswick 同口径 |
| REAL-039 | gpt | “Which areas in London” 说明在伦敦找房 |
| REAL-040 | claude | 去掉 -ish 后缀：NW、Camden 是地名本身，-ish 是语气词，带后缀无法匹配房源 |
| REAL-042 | claude | 问的是找房方法，没有可执行的找房条件 → Chitchat |
| REAL-045 | gpt | 同句 “found nice flats” 表明找的是 flat |
| REAL-046 | gpt | “moving to London” 计地点；uni 前有 ideally，通勤从严为 null |
| REAL-049 | claude | “moving to London for work” + 到 financial district 30 分钟，通勤关系明确 |
| REAL-054 | gpt | 软偏好补充通勤时长短语 |
| REAL-057 | claude | “lizzy line” 是线路不是地点；3 bedroom 取 GPT 的 []（would so love that as an option 属可选） |
| REAL-058 | claude | 找 house-sitting（替人看房），不是租房 → Chitchat；建议排除 |
| REAL-060 | gpt | 软偏好补充通勤距离短语 |
| REAL-064 | gpt | 通勤目的地保留原文片段 “Mayfair / central London” |
| REAL-065 | claude | “750-800 pounds PCM” 有明确周期，区间取上限，与 005、030 一致 |
| REAL-068 | claude | 问 “What’s your experience”，是交流感想 → Chitchat |
| REAL-070 | gpt | GPT 保留原文弯引号 King’s，Claude 误改成直引号 |
| REAL-071 | gpt | “including bills” 统一按 bills_included=true |
| REAL-073 | gpt | “possibly under” 是保留语气，按可选进软偏好；地点取完整原文片段 |
| REAL-075 | gpt | 软偏好补充交通短语 |
| REAL-089 | claude | “by 1st of may 2025” 是明确绝对年月，按入住月份 2025-05 |
| REAL-099 | gpt | “whole flat” 只是强调整套，不作软偏好 |

## 统一口径（本轮新定，供后续真实数据沿用）

1. 预算区间取上限；无周期仍为 null；“more than / and above” 不是上限。
2. 预算写明 including / with all bills → `bills_included: true`；excluding / before bills 不建约束；ideally including bills → 软偏好。
3. 以求建议开头但给出了可执行条件（户型、预算、地点）→ Search；只问方法、经验或感想 → Chitchat。
4. “moving to London”“in London” 计入地点 London；“an hour from X”“10 miles from X” 的 X 计入地点。
5. 地点去掉 -ish 这类语气后缀；线路名（lizzy line、Jubilee line）不算地点。
6. 多个通勤目的地 → null；带 possibly / ideally 的预算或地点 → 软偏好。
7. 身份陈述（family、student、non-smoker）不推布尔字段；宠物（cat、dog）例外，→ pets_allowed true。

## 建议负责人确认是否排除（exclude_suggested=true）

- REAL-058：house-sitting，非租房
- REAL-061：一个月旅行住宿，原文 long-term 与实际矛盾
- REAL-065：合租单间
- REAL-066：合租单间

排除后剩余 96 条；评测时建议同时报告全部 100 条和排除后 96 条的结果。

`data/real_test_v1.jsonl` SHA-256（未冻结）：`9d1b3025f74cfe6ed641c61adcc3e5b5bf453f8bdd87bd59a44994774c207014`
