# 零样本错误分析（Qwen/Qwen3.5-4B，zeroshot_v1）

数据：`results/pred_zeroshot_{extract,intent}.jsonl`；指标见 `eval_zeroshot_extract.md`、`eval_zeroshot_intent.md`。

## 户型错误（共 89 条样本）

| 类型 | 条数 |
| --- | ---: |
| 无户型要求却输出全空的户型项 | 36 |
| property_type 不一致（没说 flat 却补了 flat） | 26 |
| 卧室数不一致 | 8 |
| bathrooms 不一致（漏了浴室数或 studio 未补 1 卫） | 8 |
| 漏抽户型 | 6 |
| 无户型要求却抽出了户型 | 5 |

**无户型要求却输出全空的户型项**
- `T-00001` 'Furnished place in NW10 that accepts students and DSS, no smokers allowed, no more than £260 a week' — gold `[]`，pred `[(None, None, None)]`
- `T-00011` 'Near Stamford Hill, I need a place that accepts students and DSS but does not allow smokers, costing no more than £340 a week.' — gold `[]`，pred `[(None, None, None)]`
- `T-00032` 'any long lets near Marble Arch? can pay up to £6,410pw' — gold `[]`，pred `[(None, None, None)]`

**property_type 不一致（没说 flat 却补了 flat）**
- `T-00018` 'For a long let near Aldagte East, I need a furnished one-bedroom place with one bathroom costing no more than £610 per week.' — gold `[(1, 1.0, None)]`，pred `[(1, 1.0, 'flat')]`
- `T-00025` '3 bed furnished short let in W2, no more than £3,960 a week' — gold `[(3, None, None)]`，pred `[(3, None, 'flat')]`
- `T-00038` 'Furnished 1b1b within walking distance to Northfields, long let only, up to £370 a week' — gold `[(1, 1.0, None)]`，pred `[(1, 1.0, 'flat')]`

**卧室数不一致**
- `T-00007` '1b1b flat near Batersea Park, £490pw max, must allow pets and accept students and DSS' — gold `[(1, 1.0, 'flat')]`，pred `[(None, None, 'flat')]`
- `T-00037` '3b1b flat near Archway, long-term, £650pw max' — gold `[(3, 1.0, 'flat')]`，pred `[(None, None, 'flat')]`
- `T-00197` '2b1b in Hackny on a long let, no more than £2,250 a month' — gold `[(2, 1.0, None)]`，pred `[(None, None, None)]`

**bathrooms 不一致（漏了浴室数或 studio 未补 1 卫）**
- `T-00014` 'Furnished studio that accepts students, non-smoking property, under £390 a week' — gold `[(0, 1.0, 'flat')]`，pred `[(0, None, 'flat')]`
- `T-00057` 'furnished studio near Putny, no smokers pls' — gold `[(0, 1.0, 'flat')]`，pred `[(0, None, 'flat')]`
- `T-00062` 'Furnished studio in SW6 with a garden, bills inc, no smokers' — gold `[(0, 1.0, 'flat')]`，pred `[(0, None, 'flat')]`

**漏抽户型**
- `T-00009` '1b1b close to Hither Green, DSS welcome, students accepted, pets allowed, no smokers' — gold `[(1, 1.0, None)]`，pred `[]`
- `T-00134` '3b3b near Brent Corss, long let' — gold `[(3, 3.0, None)]`，pred `[]`
- `T-00139` '3b in enfield' — gold `[(3, None, None)]`，pred `[]`

**无户型要求却抽出了户型**
- `T-00173` 'furnished short let in kensington' — gold `[]`，pred `[(None, None, 'flat')]`
- `T-00264` 'Furnished place in SW7, preferably with an en-suite in the main bedroom' — gold `[]`，pred `[(None, None, 'flat')]`
- `T-00282` 'furnished in shordich, ideally lots of cafes nearby' — gold `[]`，pred `[(None, None, 'flat')]`

## 地点错误（共 26 条样本）

| 类型 | 条数 |
| --- | ---: |
| 多抽了地点（如把 London 或软偏好里的地方算进去） | 14 |
| 改写了原文（纠正拼写或补全名称） | 11 |
| 片段边界不同（多带或少带了词） | 1 |

**多抽了地点（如把 London 或软偏好里的地方算进去）**
- `T-00009` '1b1b close to Hither Green, DSS welcome, students accepted, pets allowed, no smokers' — gold `['Hither Green']`，pred `['1b1b', 'Hither Green']`
- `T-00016` 'For an April 2026 move, I need an unfurnished four-bedroom home with three bathrooms near Finchley Road & Frognal, up to £1,770pw.' — gold `['Finchley Road & Frognal']`，pred `['Finchley Road', 'Frognal']`
- `T-00022` 'A 1b1b close to Finchley Road & Frognl for a long let, max £1,750 pcm, please.' — gold `['Finchley Road & Frognl']`，pred `['Finchley Road', 'Frognl']`

**改写了原文（纠正拼写或补全名称）**
- `T-00004` 'DSS welcome and bills inc are a must near Marble Acrh; pets must be allowed too, with rent capped at £8,150 a month.' — gold `['Marble Acrh']`，pred `['Marble Arch']`
- `T-00018` 'For a long let near Aldagte East, I need a furnished one-bedroom place with one bathroom costing no more than £610 per week.' — gold `['Aldagte East']`，pred `['Aldgate East']`
- `T-00045` 'got anything in Hackeny for £2,650 pcm max?' — gold `['Hackeny']`，pred `['Hackney']`

**片段边界不同（多带或少带了词）**
- `T-00140` 'need somewhere near mitcham eastfields w a garden, must take students n DSS' — gold `['mitcham eastfields']`，pred `['mitcham eastfields w']`

## 不符合 schema 的原因

| 位置: 规则 | 条数 |
| --- | ---: |
| constraints/layout_options: type | 130 |
| soft_preferences: maxItems | 2 |
| constraints/layout_options: const | 1 |

- constraints/layout_options: type：例 `T-00004` "None is not of type 'array'"
- soft_preferences: maxItems：例 `T-00334` "['smart TV'] is too long"
- constraints/layout_options: const：例 `T-00447` '[] was expected'

## 意图错误

比较类 75 条中判对 30 条；误判为：Specific_QA 27 条，Chitchat 18 条

**比较 → Specific_QA**
- `T-00518` 'Between 2 and 3, which is better value?'
- `T-00520` 'Which of these is closest to a tube station?'
- `T-00527` "What's the difference in size and room layout between the last two?"
- `T-00528` 'Which of the five has the best location?'
- `T-00529` 'Of all five, which has the shortest walk to a station?'

**比较 → Chitchat**
- `T-00519` 'How do all five stack up for location and getting around?'
- `T-00521` 'Would the fourth or fifth place work better for a couple?'
- `T-00524` 'Can you rank these by size?'
- `T-00526` 'Put them in order from cheapest to most expensive'
- `T-00537` 'How would you rank options two, three and four for a couple living together?'

其他意图错误：
- `T-00313` gold Search → pred Chitchat：'after something part-furnished for a long let, solar power for the home would be a nice extra'
- `T-00334` gold Search → pred Chitchat：'1b1b, a smart TV would be a bonus'
- `T-00628` gold Chitchat → pred Specific_QA：'What does EPC rating mean on a listing?'
- `T-00660` gold Chitchat → pred Specific_QA："What does 'let agreed' mean?"

## 软偏好

- 软偏好样本 80 条，抽出软偏好 79 条；软偏好内容混进地点字段 0 条。
- 普通 Search 样本（gold 无软偏好）中输出了软偏好的 3 条。

## 输出长度

- 原始输出平均 518 个字符（格式化缩进的 JSON），最长 653。
