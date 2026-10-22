# gen_search_v1：把条件写成租房搜索 query

你在为伦敦租房搜索助手制作训练数据。每个任务给出一组**用户的硬性条件**，请写一句真实租客会在搜索框或聊天里输入的英文需求。gold 标签已经由脚本确定，你只负责写 query，以及标出 query 里地点的原样片段。

## 输入

每行一个任务（JSON），只看这几个字段：
- `task_id`
- `conditions`：必须表达的条件
- `style_tags`：写法风格要求

忽略 `gold_constraints_without_location` 等其他字段。

## 输出

每个任务输出一行 JSON，不要输出其他内容：

```json
{"task_id": "P-00001", "query": "...", "location_keywords": ["..."]}
```

`location_keywords` 是 query 中地点文本的**原样片段**（大小写、拼写都和 query 一致，必须是 query 的子串）。没有 `location` 条件时为 `[]`。

## 硬规则

1. **全部英文**，不出现中文；一句话或两句短话。
2. **每个条件都要明确表达，不能多也不能少。** 不得添加任何其他要求：不提通勤或上班地点，不提可选喜好（如 "ideally a balcony"），不提其他设施、价格、日期、人数推断出的户型。
3. 所有条件都必须是**硬性要求**的语气（need、must、only、looking for）。不要用 "would be nice"、"ideally"、"bonus" 之类的可选语气。
4. **只出现一个地点。** 不要在地点前后附加区名、方位或 "London" 等城市名（例如 "Arsenal, North London" 会多出一个地点）。

## 各条件的写法

| 条件 | 要求 |
| --- | --- |
| `location` kind = area | 写出这个区域名。 |
| `location` kind = postcode | 写出这个邮区，如 "E14"，可以说 "in E14"、"E14 area"。 |
| `location` kind = station | 写车站名，可以去掉 "Station" 后缀，如 "near Tower Hill"。 |
| `max_rent` | 必须是**上限**（under、max、up to、no more than、budget of）。数值必须等于给定值，可以写成等值缩写（2000 → "2k"，1800 → "1.8k"），可加 £ 和千位逗号。周期必须明确：pcm 写成 "pcm"、"a month"、"per month"；pw 写成 "pw"、"a week"、"per week"。 |
| `layout` 含 `studio: true` | 写 "studio"，不要再写卧室数或浴室数。 |
| `layout` 含 `bedrooms` | 写出卧室数（如 "2 bed"、"two-bedroom"）。0 以外的卧室数不要写成 studio。 |
| `layout` 含 `bathrooms` | 写出浴室数（如 "2 bath"）。没给就**不要**提浴室。 |
| `layout` 含 `property_type: flat` | 写 "flat" 或 "apartment"。没给就**不要**用 flat/apartment 这两个词，可以用 "place"、"home"、"2 bed" 等。 |
| `furnish_type` | furnished / unfurnished / part-furnished 的自然说法。 |
| `let_type` | long term："long let"、"long-term"；short term："short let"、"short-term"。不要用具体月数代替。 |
| `available_from` (YYYY-MM) | 必须写出**明确的月份和年份**，如 "from July 2026"、"move in Jul 2026"。不能用 "next month"、"ASAP"、只写月份不写年份。 |
| `pets_allowed: true` | 要求允许宠物，可以说 "pet friendly"、"I have a cat so pets must be allowed"。 |
| `garden: true` | 必须有花园。 |
| `parking: true` | 必须有停车位。 |
| `bills_included: true` | 租金含账单，如 "bills included"、"bills inc"。 |
| `student_friendly: true` | 要求接受学生租客。 |
| `families_allowed: true` | 要求接受家庭租客。 |
| `smokers_allowed: false` | 要求房源**不接受吸烟者**，如 "non-smoking property"、"no smokers"。不能写成只描述自己不吸烟（"I don't smoke"）。 |
| `dss_accepted: true` | 要求接受 DSS / housing benefit，如 "DSS welcome"。 |

## 风格标签

| tag | 要求 |
| --- | --- |
| `price_pw` / `price_pcm` | 用该周期的常见写法，如 "£450pw"、"1.8k pcm"。 |
| `price_format` | 用自然语言写上限，如 "no more than £1,800 a month"、"under 2k pcm"。 |
| `abbrev_layout` | 用缩写户型，如 "1b1b"、"2 bed 1 bath"、"2b"、"studio"。 |
| `uk_jargon` | 用英国租房行话，如 "bills inc"、"DSS welcome"。 |
| `loc_postcode` | 地点用邮区。 |
| `loc_station` | 地点用 "near X"、"close to X"、"walking distance to X"。 |
| `loc_typo` | 地点名带一个自然的拼写错误（少字母、多字母或相邻字母颠倒），如 "Shordich"。`location_keywords` 写拼错后的样子。 |
| `negation` | 用否定句表达对应条件。 |
| `casual` | 口语化、可以不完整，可以小写、省略主语。 |
| `multi_constraint` | 一句话塞进所有条件。 |

没有风格标签时，写普通、自然的一句话。

## 多样性

句子开头和结构要变化，不要每句都以 "Looking for" 开头。条件的出现顺序随意。

## 示例

任务：`{"task_id": "X-1", "conditions": {"location": {"kind": "station", "source_value": "Bank Station"}, "max_rent": {"value": 450, "period": "pw"}, "layout": {"bedrooms": 1, "bathrooms": 1}, "pets_allowed": true}, "style_tags": ["abbrev_layout", "price_pw"]}`

输出：`{"task_id": "X-1", "query": "1b1b near Bank, max £450pw, I've got a cat so pets need to be allowed", "location_keywords": ["Bank"]}`
