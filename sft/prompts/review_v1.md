# review_v1：盲审抽取

你只看一句英文租房 query，按下面的规则抽取结构化条件。你看不到标准答案，也不需要猜它；只按 query 字面意思抽取。审核脚本会把你的结果和标准答案逐字段比较。

## 输入

每行 `{"task_id": "...", "query": "..."}`。

## 输出

每个输入输出一行 JSON，不要输出其他内容：

```json
{"task_id": "...", "intent": "Search", "constraints": { ...15 个键全部写出... }}
```

`constraints` 的 15 个键和空值：

```json
{"location_keywords": [], "commute_destination": null, "max_rent": null, "layout_options": [],
 "furnish_type": null, "let_type": null, "available_from": null, "pets_allowed": null,
 "garden": null, "parking": null, "bills_included": null, "student_friendly": null,
 "families_allowed": null, "smokers_allowed": null, "dss_accepted": null}
```

## 规则

1. **只抽 query 明确表达的硬性条件**，没提到的保持空值。可选喜好（ideally、would be nice）不进入这些字段。
2. `location_keywords`：地点、邮区、车站名在 query 中的**原样片段**，不纠正拼写、不扩写、不加 "Station"。
3. `commute_destination`：只有明确说通勤或上班地点时才填，否则 null。
4. `max_rent`：`{"value": 数字, "period": "pcm" | "pw" | "pppw"}`。"2k" 解析为 2000，不做周月换算。没有明确周期就整个为 null。
5. `layout_options`：每项 `{"bedrooms", "bathrooms", "property_type"}`，未提及的子字段为 null。"studio" → `{"bedrooms": 0, "bathrooms": 1, "property_type": "flat"}`。说了 flat/apartment 才填 `"property_type": "flat"`。不要从人数推断卧室数。
6. `furnish_type`：`furnished` / `unfurnished` / `part-furnished`。
7. `let_type`：`long term` / `short term`；不能从月数推断。
8. `available_from`：明确的绝对年月写成 `YYYY-MM`；相对时间（next month、ASAP）或缺年份为 null。
9. 布尔字段：明确要求具备或允许 → `true`；明确要求不具备或不允许 → `false`（例如 "no smokers" → `smokers_allowed: false`）；只描述自己（"I don't smoke"）不算。"I have a cat" 表示需要允许宠物 → `pets_allowed: true`。
10. `intent`：找房或带条件的搜索为 `Search`。
