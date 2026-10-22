# review_v3：盲审抽取（全部意图）

你只看用户消息（以及可能存在的上一轮展示房源），按下面的规则输出结构化结果。你看不到标准答案；只按消息字面意思抽取。审核脚本会把你的结果和标准答案逐字段比较。

## 输入

每行 `{"task_id": "...", "context": "..." 或 null, "query": "..."}`。`context` 是上一轮展示给用户的房源；null 表示没有。

## 输出

每个输入输出一行 JSON，不要输出其他内容：

```json
{"task_id": "...", "intent": "...", "constraints": { ...15 个键全部写出... }, "soft_preferences": []}
```

`constraints` 的 15 个键和空值：

```json
{"location_keywords": [], "commute_destination": null, "max_rent": null, "layout_options": [],
 "furnish_type": null, "let_type": null, "available_from": null, "pets_allowed": null,
 "garden": null, "parking": null, "bills_included": null, "student_friendly": null,
 "families_allowed": null, "smokers_allowed": null, "dss_accepted": null}
```

## 意图

| intent | 含义 |
| --- | --- |
| `Search` | 找房，或带新条件的找房追问（如 "What about ones with a garden?"）。 |
| `Specific_QA` | 问已展示的某一套房源（如 "Does the second one allow pets?"）。 |
| `Compare` | 比较已展示的多套房源（如 "Compare the first two."）。 |
| `Chitchat` | 打招呼、闲聊、与找房无关的问题、租房常识问题、只表达感想。 |

`intent` 不是 `Search` 时，`constraints` 全部为空值，`soft_preferences` 为 `[]`。

## Search 的抽取规则

1. 只抽本条消息明确表达的硬性条件，不合并上一轮条件，不从展示房源复制条件；没提到的保持空值。
2. `location_keywords`：地点、邮区、车站名在消息中的**原样片段**，不纠正拼写、不扩写、不加 "Station"。
3. `commute_destination`：只有明确说通勤或上班地点时才填，否则 null。
4. `max_rent`：`{"value": 数字, "period": "pcm" | "pw" | "pppw"}`。"2k" 解析为 2000，不做周月换算。没有明确周期就整个为 null。
5. `layout_options`：每项 `{"bedrooms", "bathrooms", "property_type"}`，未提及的子字段为 null。"studio" → `{"bedrooms": 0, "bathrooms": 1, "property_type": "flat"}`。说了 flat/apartment 才填 `"property_type": "flat"`。不要从人数推断卧室数。
6. `furnish_type`：`furnished` / `unfurnished` / `part-furnished`。
7. `let_type`：`long term` / `short term`；不能从月数推断。
8. `available_from`：明确的绝对年月写成 `YYYY-MM`；相对时间或缺年份为 null。
9. 布尔字段：明确要求具备或允许 → `true`；明确要求不具备或不允许 → `false`（"no smokers" → `smokers_allowed: false`）；只描述自己（"I don't smoke"）不算。"I have a cat" 表示需要允许宠物 → `pets_allowed: true`。
10. `soft_preferences`：可选喜好（ideally、would be nice、bonus、prefer）的**原样短语**列表。有对应硬字段的属性（如花园）只是可选时，放进 `soft_preferences`，硬字段保持 null；明确必须时填硬字段，不重复放进软偏好。没有软偏好时为 `[]`。
11. 软偏好短语只写内容部分，不包含 ideally、would be nice、would be a bonus、I prefer、really need 等表示可选或强调的词，例如 "ideally with a big kitchen" → `"a big kitchen"`。
