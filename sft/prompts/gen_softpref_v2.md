# gen_softpref_v2：带软偏好的找房 query（只用于测试集）

在 `prompts/gen_search_v1.md` 的基础上，额外加入 1–2 个**可选喜好**（软偏好）。先完整阅读并遵守 `gen_search_v1.md` 的全部规则，本文件只说明增加的部分。

## 输入

任务字段：`task_id`、`conditions`、`style_tags`（含义同 `gen_search_v1.md`），以及：
- `description`：房源描述原文，只用来挑选软偏好的素材；
- `n_soft`：要写几个软偏好（1 或 2）。

## 输出

```json
{"task_id": "Q-00041", "query": "...", "location_keywords": [...], "soft_preferences": ["..."], "soft_pref_weights": [1]}
```

- `soft_preferences`：query 中每个软偏好的**原样短语**（必须是 query 的子串，不改写），数量等于 `n_soft`。
- `soft_pref_weights`：与 `soft_preferences` 一一对应；用了强调语气（must、really need、essential）为 2，否则为 1。

## 软偏好规则

1. 从 `description` 里挑房源**确实具备**的特点，用你自己的话改写成用户的喜好，例如描述里有 "bright reception room with floor-to-ceiling windows"，可以写 "somewhere with lots of natural light"。
2. **不能照抄描述**：软偏好短语与描述原文不能有 3 个或以上连续相同的词（脚本会检查）。
3. 软偏好不能是已有硬字段能表达的内容：不能是地点、车站、通勤、预算、卧室、浴室、房型、家具、租期、入住日期、宠物、花园、停车、账单、学生、家庭、吸烟、DSS。适合的例子：quiet、natural light、modern kitchen、balcony、concierge、gym、lift、high ceilings、close to parks、wooden floors。
4. 语气：硬条件照常用必须的语气；软偏好用可选语气（ideally、would be nice、bonus if、prefer），这样才能和硬条件区分。只有当你想表达强烈但仍属主观的喜好时，才用 "really need"，此时权重为 2。
5. 软偏好不能引入新的地点名。

## 软偏好短语的边界（v2 新增）

`soft_preferences` 只写**内容短语**，不包含表示可选的词：去掉 ideally、would be nice、would be great、would be a bonus、would be a plus、bonus if、I prefer、I'd like、really need 等。
例如 "ideally with a big kitchen for entertaining" → `"a big kitchen for entertaining"`；"a gym in the building would be nice" → `"a gym in the building"`。短语本身仍须是 query 的原样子串。

## 示例

任务：`{"conditions": {"layout": {"bedrooms": 2}, "max_rent": {"value": 2600, "period": "pcm"}}, "n_soft": 2, "description": "...bright reception room with floor-to-ceiling windows... residents' gym on the ground floor..."}`

输出：`{"task_id": "X-3", "query": "2 bed under £2,600 pcm, ideally somewhere with lots of natural light, and a gym in the building would be a bonus", "location_keywords": [], "soft_preferences": ["somewhere with lots of natural light", "a gym in the building"], "soft_pref_weights": [1, 1]}`
