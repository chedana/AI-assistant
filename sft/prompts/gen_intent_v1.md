# gen_intent_v1：非 Search 与带新条件追问

你在为伦敦租房搜索助手制作数据。每个任务指定一种用户消息类型，请写一条真实用户会发的英文消息。标签已经由脚本确定，你只负责写消息。

## 输入

每行一个任务（JSON），只看：`task_id`、`kind`、`context`、`hints`、`conditions`、`style_tags`。忽略其他字段。

`context` 是上一轮助手展示给用户的房源列表；为 null 表示没有展示过房源。

## 输出

每个任务输出一行 JSON，不要输出其他内容：

```json
{"task_id": "Q-00001", "query": "...", "location_keywords": []}
```

只有 `kind = followup` 且条件里有 `location` 时，`location_keywords` 才非空，写 query 中地点的原样片段（必须是 query 的子串）；其他情况一律 `[]`。

## 通用规则

1. 全部英文；一句或两句短话；像真人在聊天框里打字，可以随意、简短。
2. 句子开头和结构要变化，不要套同一个模板。
3. 消息必须**只能**归为本任务的类型，不能模棱两可。

## 各类型

### `specific_qa`：问展示过的某一套房源

- 按 `hints.reference` 的方式指代 `hints.target` 号房源：第几套（"the second one"）、按区域或邮区（"the Clerkenwell one"，必须能唯一指向）、按价格（"the £2,150 one"）、最高级（"the cheapest one"，必须确实指向该房源）、代词（"is that one…"）。
- 问 `hints.topic` 相关的问题，例如 "Does the second one allow pets?"、"What's the deposit on the cheapest one?"。
- 不能提出新的找房条件，不能问"有没有别的……"。

### `compare`：比较展示过的几套房源

- 比较 `hints.targets` 指定的房源（"all" 表示全部），从 `hints.dimension` 的角度比较；"no specific dimension" 时只说比较，例如 "Compare the first two."。
- 不能提出新的找房条件。

### `chitchat`：闲聊

- 按 `hints.subtype` 写：打招呼、道谢或道别、吐槽伦敦房租、与租房无关的问题、关于助手本身的问题、英国租房常识问题（例如 "What's a holding deposit?"，问的是概念，不是找房）、对展示结果的反应（例如 "these all look way out of my budget lol"，不提出新条件）。
- 不能包含任何找房请求或具体条件（地点、预算、户型等）。
- 有 `context` 时可以自然地提到"这些房源"，但不能问某一套的具体信息，也不能要求比较。

### `followup`：带新条件的找房追问

- 用户看完展示的房源后，提出**新的找房条件**，例如 "What about ones with a garden?"、"Any 2 beds in E14 instead?"、"show me furnished ones under £2k pcm"。
- 必须表达 `conditions` 中的每个条件，不多不少；条件写法规则与 `prompts/gen_search_v1.md` 的“各条件的写法”完全相同（预算是上限且周期明确；日期写明月份和年份；没给的户型字段不提；只有一个地点等）。
- **不能**指代某一套展示过的房源（不能说 "like the second one but cheaper"），不能复述上一轮的条件，不能用相对说法（"cheaper"、"bigger"）代替具体数值。
- `style_tags` 规则同 `gen_search_v1.md`。

## 示例

`{"task_id": "X-1", "kind": "specific_qa", "hints": {"target": 2, "reference": "ordinal (e.g. the second one)", "topic": "pets"}, ...}`
→ `{"task_id": "X-1", "query": "Does the second one allow pets?", "location_keywords": []}`

`{"task_id": "X-2", "kind": "followup", "conditions": {"garden": true}, "style_tags": ["casual"], ...}`
→ `{"task_id": "X-2", "query": "hmm any with a garden?", "location_keywords": []}`
