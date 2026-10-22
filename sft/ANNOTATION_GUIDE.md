# SFT 输出标注规范（v1 已确认简化规范）

状态：**负责人已确认的 v1 简化规范**。版本：v1，2026-10-22。规范定稿不等于训练集或测试集已生成、验收或冻结。

依据：[EXECUTION_PLAN.md](EXECUTION_PLAN.md) 第 0.5、1、3、4、5 节；`core/chatbot_config.py` 中的 `SEARCH_EXTRACT_ALL_SYSTEM`；2026-10-22 会话中负责人对四项结构建议及最新简化方案的确认（“全部采用，完成定稿”）。对应结构校验文件为 [schema.json](schema.json)。如原计划或早期建议与本版不一致，以负责人最新确认的本版规则为准。

确认记录：保留全部 15 个 `constraints` 键；房型仅输出 `flat`，明确的 studio 按 `flat + 0b1b`；家具统一三类；支持明确布尔否定，无要求或无所谓为 `null`；只抽取当前轮条件，不合并历史；保留通勤但本次不计 F1；预算须有明确周期，日期须有明确绝对年月。**此前“garden 统一放 soft_preferences”的建议已撤销**：花园等条件按必需或可选语义分别进入硬条件或软偏好，详见第 8 节。

本文件说明模型输出及样本 `gold` 的形状和已确认语义。实际数据的 gold 由生成时选中的字段及取值确定，不另做人工推测标注。以下英文 query 是规则说明示例，**不是基于真实房源生成的数据集样本，不得直接纳入训练集或测试集**。

## 1. 已确认的共通约定

1. 顶层始终包含 `intent`、`constraints`、`soft_preferences`。`constraints` 始终是对象，包含第 2 节列出的全部键。
2. 所有对象禁止额外键，包括非空的 `max_rent` 对象以及 `layout_options` 中每个对象。嵌套对象一旦出现，规定的键必须齐全。
3. 列表没有内容时使用 `[]`；其他没有内容的值使用 `null`。明确不要求或无所谓时，不建立该硬约束。可选偏好放入 `soft_preferences`，对应硬字段保持空值（列表为 `[]`，其他为 `null`）。这不意味着可以省略 `constraints` 父对象，或把它写为 `null`。
4. 没有预算时，整个 `max_rent` 为 `null`。不使用空对象或全空的预算子对象代替它。
5. `intent` 不是 `Search` 时，所有约束均为空：两项列表为 `[]`，其余约束为 `null`；`soft_preferences` 也为 `[]`。不能从已展示房源的属性复制约束进入这些输出。
6. `bedrooms` 为非负整数；`bathrooms` 为非负数；非空预算金额为正数。数值用 JSON 数字，不能用带货币符号的字符串。
7. 地名、邮编和软偏好短语保留 query 中的原文。不得替用户纠错、扩写地名缩写或补全地点。
8. 只有明确提到在某处工作、通勤到某处或经常前往某处，才抽取 `commute_destination`。普通地点偏好不等于通勤目的地。
9. `soft_preferences` 和 `commute_destination` 均不计入本次字段级 F1；后者仍保留在输出结构中并按规则抽取。
10. 只抽取当前 query 的条件，不把上一轮条件合并到本轮输出。带新条件的追问仍可为 `Search`；`Specific_QA` 和 `Compare` 仍可使用已展示房源的上下文识别指代。
11. 房型只输出 `flat` 或 `null`。明确的 studio 搜索按 `bedrooms = 0`、`bathrooms = 1`、`property_type = "flat"`；普通零卧室条件或单独的 flat 不触发这一补全。
12. 支持明确的布尔属性否定：明确要求不具备相应设施或不允许相应租客时填 `false`。没有要求、无所谓或仅表达本人不做某事，不等于要求房源禁止该事项。

本文中“结构有效”只表示值的形状可被 schema 接受，不表示给定 query 的语义正确。所有局部示例均为字段片段，不能单独作为完整模型输出；只有第 9 节的 `json` 代码块是完整输出。v1 主动缩小了覆盖范围；被排除的表达不生成 v1 样本，也不能丢弃其中的信息后伪装成可用 gold。

## 2. 字段目录与空值

| 路径 | 类型与取值 | 无信息时 |
|---|---|---|
| `intent` | `Search` / `Specific_QA` / `Compare` / `Chitchat` | 不可为空，必须分类 |
| `constraints` | 包含下列全部约束键的对象，无额外键 | 完整的空约束对象 |
| `constraints.location_keywords` | 字符串列表 | `[]` |
| `constraints.commute_destination` | 字符串或 `null` | `null` |
| `constraints.max_rent` | 预算对象或 `null` | `null` |
| `constraints.max_rent.value` | 正数 | 无预算时不用此子对象 |
| `constraints.max_rent.period` | `pcm` / `pw` / `pppw` | 无预算时不用此子对象 |
| `constraints.layout_options` | 户型对象列表，每项包含下述三个键 | `[]` |
| `constraints.layout_options[].bedrooms` | 非负整数或 `null` | `null` |
| `constraints.layout_options[].bathrooms` | 非负数或 `null` | `null` |
| `constraints.layout_options[].property_type` | `flat` 或 `null` | `null` |
| `constraints.furnish_type` | `furnished` / `unfurnished` / `part-furnished` 或 `null` | `null` |
| `constraints.let_type` | `long term` / `short term` 或 `null` | `null` |
| `constraints.available_from` | `YYYY-MM` 字符串或 `null` | `null` |
| `constraints.pets_allowed` | 布尔值或 `null` | `null` |
| `constraints.garden` | 布尔值或 `null` | `null` |
| `constraints.parking` | 布尔值或 `null` | `null` |
| `constraints.bills_included` | 布尔值或 `null` | `null` |
| `constraints.student_friendly` | 布尔值或 `null` | `null` |
| `constraints.families_allowed` | 布尔值或 `null` | `null` |
| `constraints.smokers_allowed` | 布尔值或 `null` | `null` |
| `constraints.dss_accepted` | 布尔值或 `null` | `null` |
| `soft_preferences` | 软偏好原文短语的字符串列表 | `[]` |

`max_rent` 的完整预算对象必须同时具备金额和周期。`"Find a home under 2k pcm."` 可标为 `{"value": 2000, "period": "pcm"}`；裸预算 `"Find a home under 2k."` 不进入 v1，不能擅自假定周期或把预算填成 `null` 后收录。

## 3. 意图与父容器

### 3.1 `intent`

定义：用户这一轮的交互目标。取值必须与第 2 节四个枚举精确一致，大小写固定。

| 意图 | 定义与例子 |
|---|---|
| `Search` | 找房，或带新条件的找房追问，例如 `"Find a one-bedroom home."`、`"What about ones with a garden?"`。后一例只抽取本轮提出的花园条件，不合并之前的地点或预算。 |
| `Specific_QA` | 问已经展示的某一套房源，例如有已展示房源上下文时的 `"Does the second one allow pets?"`。 |
| `Compare` | 比较已经展示的多套房源，例如有已展示房源上下文时的 `"Compare the first two."`。 |
| `Chitchat` | 打招呼、闲聊或与租房无关的提问，例如 `"Hello!"`。仅提到租房的感想也不自动构成搜索请求。 |

正例（局部片段）：

- `"Find a one-bedroom home."` → `"intent": "Search"`。
- 在已展示房源的上下文中，`"Compare the first two."` → `"intent": "Compare"`。
- `"Renting in London is so expensive lol."` → `"intent": "Chitchat"`。

反例（局部片段）：

- `"intent": "search"`：大小写错误，不属于枚举。
- 在已展示房源的上下文中，`"Does the second one allow pets?"` → `"intent": "Search"`：是在询问一套房源，应为 `Specific_QA`。
- `"What about ones with a garden?"` → `"intent": "Specific_QA"`：这是提出新的找房条件，应为 `Search`。

### 3.2 `constraints`

定义：硬条件的父对象。它的全部子键见第 2 节。对象自身不可为 `null`，也不可缺键；非 Search 仍保留相同的完整结构。

正例（引用完整输出）：

- 第 9.1 节 Search 的 `constraints`：包含全部约束键，仅填入明确提到的条件。
- 第 9.2 节 Specific_QA 的 `constraints`：包含全部约束键，两个列表为空，其余值为 `null`。

反例（局部片段）：

- `"constraints": {}`：缺少全部必需子键；不是合法的空约束对象。
- `"constraints": null`：父对象类型错误。
- 在完整约束对象中加入 `"max_rent_pcm": 1950`：该字段属于旧格式，是本 schema 禁止的额外键。

## 4. 地点与通勤

### 4.1 `constraints.location_keywords`

定义：作为找房地点条件出现的地名或邮编原文片段，类型为字符串列表。只抽取明确表达的找房地点，不补出所属城市或修正拼写。数组无内容时为 `[]`。

正例（局部片段）：

- `"Find a home in Shordich."` → `"location_keywords": ["Shordich"]`。
- `"Find a home in E14 or Canary Wharf."` → `"location_keywords": ["E14", "Canary Wharf"]`。

反例（局部片段）：

- `"Find a home in Shordich."` → `"location_keywords": ["Shoreditch"]`：改了原文拼写。
- `"Find a home in E14."` → `"location_keywords": ["E14", "London"]`：添加了 query 没有出现的地点。
- `"location_keywords": "E14"`：类型错误，单个地点也必须放在列表中。

本版不额外施加列表排序或去重约束，也不根据地点推断额外区域。具体列表匹配算法随评测任务实现；这不阻塞当前结构与语义规则的定稿。

### 4.2 `constraints.commute_destination`

定义：用户明确工作、通勤或经常前往的具体地点，类型为字符串或 `null`。普通偏好地点不能填入本字段；用户只说希望靠近车站，也不等于明确表示通勤到该站。

正例（局部片段）：

- `"Find a home; I commute to Canary Wharf."` → `"commute_destination": "Canary Wharf"`。
- `"Find a home; I work at Oxford Circus."` → `"commute_destination": "Oxford Circus"`。
- `"Find a home; I travel to London Bridge every weekday."` → `"commute_destination": "London Bridge"`。

反例（局部片段）：

- `"Find a home near Canary Wharf."` → `"commute_destination": "Canary Wharf"`：缺少明确的通勤、工作或经常前往关系；本字段应为 `null`。
- `"Find a home near a station."` → `"commute_destination": "London Bridge"`：凭空补出了目的地。

通勤关系本身不建立居住地点条件。只有 query 另行明确要求住在该处，才同时填写 `location_keywords`。当前字段表示单个明确目的地，生成模板不主动扩展到多个目的地的取舍。该字段本次保留抽取，但暂不计入 F1。

## 5. 预算

### 5.1 `constraints.max_rent`

定义：用户明确表达的最高租金，以原 query 使用的数值及周期保存。非空时为对象，且恰好包含 `value` 和 `period`；无预算时整个字段为 `null`。不进行周租/月租/每人周租换算，不从人数推算总预算。

正例（局部片段）：

- `"Find a home for no more than £450 per week."` → `"max_rent": {"value": 450, "period": "pw"}`。
- `"Find a home in E14."` → `"max_rent": null`。
- `"Find a home for no more than £200 per person per week."` → `"max_rent": {"value": 200, "period": "pppw"}`。

反例（局部片段）：

- `"Find a home for no more than £450 per week."` → `"max_rent": {"value": 1950, "period": "pcm"}`：擅自换算了数值与周期。
- `"max_rent": {}`：缺少必需的两个子键。
- 无预算时输出 `"max_rent": {"value": null, "period": null}`：应使用整个字段为 `null`。

### 5.2 `constraints.max_rent.value`

定义：与原 query 周期配套的预算上限金额，取正数。只有建立完整预算对象时才出现，不能单独省略或使用字符串。

正例（局部片段；所属对象还必须包含相应 `period`）：

- `"Find a home for no more than £1,800 per month."` → `"value": 1800`。
- `"Find a home for no more than £450.50 per week."` → `"value": 450.5`。

反例（局部片段）：

- `"value": "£1800"`：不是 JSON 数字。
- `"value": 0`：不满足正数约束。
- `"value": -450`：不满足正数约束。

### 5.3 `constraints.max_rent.period`

定义：与该预算金额对应的租金周期，仅允许 `pcm`（每月）、`pw`（每周）、`pppw`（每人每周）。不能在 query 未说明周期时默认填 `pcm`。

正例（局部片段；所属对象还必须包含相应 `value`）：

- `"Find a home for no more than £1,800 per month."` → `"period": "pcm"`。
- `"Find a home for no more than £450 per week."` → `"period": "pw"`。
- `"Find a home for no more than £200 per person per week."` → `"period": "pppw"`。

反例（局部片段）：

- `"period": "weekly"`：不在枚举中，应以 `pw` 表示明确的周租。
- `"Find a home for no more than £200 per person per week."` → `"period": "pw"`：遗漏了每人的含义。

## 6. 户型、家具和租期

### 6.1 `constraints.layout_options`

定义：明确要求的一个或多个户型选项，类型为列表。每项恰好包含 `bedrooms`、`bathrooms`、`property_type`，未提到的子字段填 `null`；明确 studio 的已确认特殊映射见第 6.4 节。没有户型要求时为 `[]`。

正例（局部片段）：

- `"Find a 1b1b home."` → `"layout_options": [{"bedrooms": 1, "bathrooms": 1, "property_type": null}]`。
- `"Find a 1b1b or 2b2b home."` → `"layout_options": [{"bedrooms": 1, "bathrooms": 1, "property_type": null}, {"bedrooms": 2, "bathrooms": 2, "property_type": null}]`。
- `"Find a home in E14."` → `"layout_options": []`。

反例（局部片段）：

- `"layout_options": {"bedrooms": 1, "bathrooms": 1, "property_type": null}`：应为列表，单个选项也必须包在列表中。
- `"layout_options": [{"bedrooms": 1}]`：每项都必须有全部三个键。
- 在户型项中加入 `"layout_tag": "1b1b"` 或 `"max_rent_pcm": 1800`：均为禁止的额外键，不能沿用旧 prompt 的结构。

当前只有全局预算，没有户型级预算。生成模板不主动使用不同户型分别对应不同预算的表达；非布尔房型排除条件不进入 v1。多轮追问仅抽取当前轮表达的户型，不执行历史选项的替换或追加。

### 6.2 `constraints.layout_options[].bedrooms`

定义：该户型选项的卧室数，取非负整数或 `null`。明确 studio 时按已确认规则为 0；除此之外未提到卧室数时为 `null`，不能依据入住人数推算。

正例（局部片段；所在户型项仍须带齐其他两个键）：

- `"Find a two-bedroom home."` → `"bedrooms": 2`。
- `"Find a home with one bathroom."` → `"bedrooms": null`。
- `"Find a studio."` → `"bedrooms": 0`，同一项的 `bathrooms` 为 1、`property_type` 为 `"flat"`。

反例（局部片段）：

- `"bedrooms": 1.5`：不是整数。
- `"bedrooms": -1`：不是非负数。
- `"bedrooms": "2"`：数字字符串不符合类型。

### 6.3 `constraints.layout_options[].bathrooms`

定义：该户型选项的浴室数，取非负数或 `null`；不强制为整数。明确 studio 时按已确认规则为 1；其余未提到浴室数时为 `null`，不从卧室数或 flat 房型推算。

正例（局部片段；所在户型项仍须带齐其他两个键）：

- `"Find a home with one bathroom."` → `"bathrooms": 1`。
- `"Find a home with 1.5 bathrooms."` → `"bathrooms": 1.5`。
- `"Find a two-bedroom home."` → `"bathrooms": null`。

反例（局部片段）：

- `"bathrooms": -0.5`：不是非负数。
- `"bathrooms": "1"`：数字字符串不符合类型。
- `"Find a two-bedroom home."` → `"bathrooms": 2`：未经 query 支持而推断。

### 6.4 `constraints.layout_options[].property_type`

定义：该户型选项的房产类型，v1 仅允许 `"flat"` 或 `null`。没有提到房型时仍为 `null`，不能因为本版只支持 flat 就自动填入它。

正例（局部片段）：

- `"Find a 1b1b home."` → `"property_type": null`：未提及房产类型。
- `"Find an apartment."` → `"property_type": "flat"`。
- `"Find a studio."` → `"property_type": "flat"`，同一项的卧室数为 0、浴室数为 1。

反例（局部片段）：

- `"property_type": "studio"`：不属于 v1 输出枚举，明确 studio 应按 `flat + 0b1b`。
- `"Find a 1b1b home."` → `"property_type": "flat"`：没有提到房型，不能补填。
- `"property_type": "house"`：不属于 v1 输出枚举；不得把 house 改写成 flat 来通过校验。

v1 归一化如下；studio 的表示取代原计划初稿中的单独 `studio` 类型：

| 明确的房型表达 | v1 归一化 |
|---|---|
| Flat / Apartment / Penthouse / Maisonette | `flat` |
| Studio | `flat`，同时 `bedrooms = 0`、`bathrooms = 1` |
| Room / House Share / House 等非 flat 房型 | 不属于 v1 房型输出范围；不重编码为 flat |

studio 联动只由 Search query 明确表达 studio 触发：`"Find a zero-bedroom home."` 的户型为 `{"bedrooms": 0, "bathrooms": null, "property_type": null}`；`"Find a flat."` 为 `{"bedrooms": null, "bathrooms": null, "property_type": "flat"}`。不能从普通 `bedrooms = 0` 或 `property_type = "flat"` 反推浴室数为 1。JSON Schema 看不到 query，不能将“零卧室必有一个浴室”设为通用校验约束。

本次不访问或筛选房源数据。来源中的 house、room 等不能重编码成 flat；实际清洗时保留哪些来源房源，按下一项数据任务的开工前确认确定，不影响本版输出规则定稿。

### 6.5 `constraints.furnish_type`

定义：家具配置要求，只允许 `furnished`、`unfurnished`、`part-furnished` 或 `null`。明确的 Furnished / Fully furnished 统一为 `furnished`，Unfurnished 统一为 `unfurnished`，Part furnished / Part-furnished 统一为 `part-furnished`。来源数据中的 `ask agent` 等无效值不能作为有效生成条件。

正例（局部片段）：

- `"Find a furnished home."` → `"furnish_type": "furnished"`。
- `"Find an unfurnished home."` → `"furnish_type": "unfurnished"`。
- `"Find a part-furnished home."` → `"furnish_type": "part-furnished"`。

反例（局部片段）：

- `"furnish_type": true`：不是字符串或 `null`。
- `"furnish_type": ["furnished", "unfurnished"]`：不是当前字段允许的类型。
- `"furnish_type": "flexible"`：不属于三类家具枚举。

未提及家具或明确对家具无要求时为 `null`。对于 `Furnished or unfurnished, landlord is flexible` 一类灵活来源值，不能强选三类中的某一类；v1 生成时暂不把该来源值选作家具条件。

### 6.6 `constraints.let_type`

定义：租赁类别要求，只允许 `long term`、`short term` 或 `null`。来源按计划只认 `Long term` / `Short term`，输出统一为相应的小写标签；不能从租赁月数推断类别。

正例（局部片段）：

- `"Find a home for a long-term let."` → `"let_type": "long term"`。
- `"Find a home for a short-term let."` → `"let_type": "short term"`。
- `"Find a home in E14."` → `"let_type": null`：未提及租赁类别。

反例（局部片段）：

- `"let_type": 12`：不是字符串或 `null`，也不能擅自以月份代替类别。
- `"Find a furnished home."` → `"let_type": "Furnished"`：把家具要求放进了租赁类别，也不符合枚举。
- `"Find a home for six months."` → `"let_type": "short term"`：擅自根据月数判断租赁类别。

当前 schema 不含 `min_tenancy_months`。生成模板不主动使用只能由具体月数承载的租期条件，不能补成额外键或擅自映射成租赁类别。

## 7. 入住月份

### 7.1 `constraints.available_from`

定义：用户明确提出的绝对入住年月，类型为 `YYYY-MM` 字符串或 `null`，月份范围为 `01`–`12`。不输出日精度，不使用当前系统日期补出年份。

正例（局部片段）：

- `"Find a home available from March 2027."` → `"available_from": "2027-03"`。
- `"Find a home available from November 2027."` → `"available_from": "2027-11"`。
- `"Find a home in E14."` → `"available_from": null`。

反例（局部片段）：

- `"available_from": "2027-03-15"`：包含日，不是 `YYYY-MM`。
- `"available_from": "2027-13"`：月份超出有效范围。
- `"available_from": "2027-3"`：月份没有补足两位。

必须区分来源筛选与 query 抽取：执行计划第 3 节的 `scraped_at` 前后 7 天规则用于判断**房源数据**是否只是“现在可入住”。接近抓取日期的来源值不作为日期条件生成 query；只有明显晚于抓取日期的值才用于生成日期条件。这不是给模型输入 query 后可直接执行的日期判断，也不能把运行当天当作 `scraped_at`。

v1 日期样本只使用明确绝对年月。`"now"`、`"next month"`、只有月份没有年份等日期条件不进入 v1；不默认使用系统日期，不自行换算，也不把这些日期信息静默丢掉后填 `null` 收录。

## 8. 布尔条件与软偏好

### 8.1 八个布尔条件

共同取值：JSON `true`、`false` 或 `null`。

- 明确要求该住房属性存在、许可成立：`true`。
- 明确要求该属性不存在或许可不成立：`false`。否定必须针对住房条件，不能从用户本人身份或行为的否定推断。
- 未提及、明确不要求或无所谓：`null`。例如 `"I don't need a garden."`、`"I don't mind whether there is a garden."` 都不建立花园硬约束；不能误写为 `false`。
- 仅表示有则更好：硬字段为 `null`，把可选偏好原文放入 `soft_preferences`。例如 `"A garden would be nice."` 不是必须有花园。

以下每行分别给出字段定义、三个正例和两个反例。所有箭头后的内容均为局部字段值；“未提及”正例的 query 统一为 `"Find a home in E14."`。

| 字段及定义 | 正例 1：明确正向要求 | 正例 2：明确否定要求 | 正例 3：未提及 | 反例 1：类型错误 | 反例 2：无依据填值 |
|---|---|---|---|---|---|
| `pets_allowed`：允许养宠物 | `"I need a home that allows pets."` → `true` | `"I need a home where pets are not allowed."` → `false` | `null` | `"pets_allowed": "true"` | `"Find a home in E14."` → `"pets_allowed": true` |
| `garden`：有花园 | `"I need a home with a garden."` → `true` | `"I need a home without a garden."` → `false` | `null` | `"garden": "yes"` | `"Find a home in E14."` → `"garden": true` |
| `parking`：有停车位或停车条件 | `"I need a home with parking."` → `true` | `"I need a home without parking."` → `false` | `null` | `"parking": 1` | `"Find a home in E14."` → `"parking": true` |
| `bills_included`：租金包含账单费用 | `"I need a home with bills included."` → `true` | `"I need a home where bills are not included in the rent."` → `false` | `null` | `"bills_included": "included"` | `"Find a home in E14."` → `"bills_included": true` |
| `student_friendly`：接受学生租客 | `"I need a home that accepts students."` → `true` | `"I need a home where student tenants are not accepted."` → `false` | `null` | `"student_friendly": "true"` | `"Find a home in E14."` → `"student_friendly": true` |
| `families_allowed`：接受家庭租客 | `"I need a home that allows families."` → `true` | `"I need a home where families are not allowed."` → `false` | `null` | `"families_allowed": "yes"` | `"Find a home in E14."` → `"families_allowed": true` |
| `smokers_allowed`：接受吸烟租客 | `"I need a home that allows smokers."` → `true` | `"I need a home where smokers are not allowed."` → `false` | `null` | `"smokers_allowed": 1` | `"Find a home in E14."` → `"smokers_allowed": true` |
| `dss_accepted`：接受 DSS 条件对应的租客 | `"I need a home that accepts tenants receiving DSS benefits."` → `true` | `"I need a home that does not accept tenants receiving DSS benefits."` → `false` | `null` | `"dss_accepted": "accepted"` | `"Find a home in E14."` → `"dss_accepted": true` |

`"Find a home with a no-smokers policy."` 明确要求房源不接受吸烟者，因此 `smokers_allowed = false`；`"I don't smoke."` 只描述本人行为，不能据此填 `false`。这类没有明确许可条件的身份或行为陈述不在本轮生成模板中主动使用。原计划的找房示例 `"1b1b near Canary Wharf, max £450 pw, I have a cat"` 可沿用其宠物需求含义，填写 `pets_allowed = true`；不得据此扩展一套未经确认的身份推断白名单。

来源属性 `dss_income_accepted` 与输出键 `dss_accepted` 名称不同；输出时只能使用本 schema 的键，不能增加 `dss_income_accepted`。

v1 只覆盖上述明确布尔属性否定；`"not a house share"`、`"not ground floor"` 等非布尔属性排除条件暂不进入 v1，不得改写成其他类型或隐去否定后收录。预算的 `"no more than £450 per week"` 是已支持的金额上限表达，不属于这里排除的房型、楼层等属性否定。

### 8.2 `soft_preferences`

定义：query 中的软偏好原文短语，类型为字符串列表。对有对应硬字段的属性，必须满足时填硬字段，仅有则更好时填软偏好且硬字段保持空值；明确的硬要求不再重复放进软偏好。`quiet`、`lots of natural light` 等没有对应硬字段的偏好仍使用本列表，不新增键。没有软偏好时为 `[]`，非 Search 时也必须为 `[]`。不计入字段级 F1。

正例（局部片段）：

- `"Find a home; quiet would be nice."` → `"soft_preferences": ["quiet"]`。
- `"Find a home; lots of natural light would be nice."` → `"soft_preferences": ["lots of natural light"]`。
- `"Find a home; a garden would be nice."` → `"soft_preferences": ["a garden would be nice"]`，同时 `garden = null`。

反例（局部片段）：

- `"Find a home; lots of natural light would be nice."` → `"soft_preferences": ["bright"]`：改写了 query 中的短语。
- `"Find a home; it must have a garden."` → `"soft_preferences": ["a garden"]`：这是明确的花园硬要求，应填 `garden = true`，不重复放进软偏好。
- `"soft_preferences": "quiet"`：类型错误，单个短语也要用列表。

本 schema 不包含旧 `semantic_terms` 对象及其三类子列表，也不包含强调权重。没有对应硬字段的主观偏好即便以 `must` 或 `really need` 强调，也仍保留原文短语在 `soft_preferences`；不能因此新增 `constraints` 键。强调程度按计划第 3.3 节在外层 `soft_pref_weights` 中记录：强调为 2，其余为 1，不进入本输出对象。

## 9. 四类意图与关键语义的完整输出示例

以下每个 `json` 代码块均是完整的模型输出对象，可独立交给 `schema.json` 校验。query 和上下文说明在代码块外，不属于模型输出。所有示例只是规范说明，不是已生成的数据集记录。

### 9.1 Search

Query：`Find a 1b1b home in Canary Wharf for no more than £450 per week. I need a home that allows pets.`

```json
{
  "intent": "Search",
  "constraints": {
    "location_keywords": ["Canary Wharf"],
    "commute_destination": null,
    "max_rent": {"value": 450, "period": "pw"},
    "layout_options": [{"bedrooms": 1, "bathrooms": 1, "property_type": null}],
    "furnish_type": null,
    "let_type": null,
    "available_from": null,
    "pets_allowed": true,
    "garden": null,
    "parking": null,
    "bills_included": null,
    "student_friendly": null,
    "families_allowed": null,
    "smokers_allowed": null,
    "dss_accepted": null
  },
  "soft_preferences": []
}
```

### 9.2 Specific_QA

上下文：上一轮已经展示多套房源。Query：`Does the second one allow pets?`

```json
{
  "intent": "Specific_QA",
  "constraints": {
    "location_keywords": [],
    "commute_destination": null,
    "max_rent": null,
    "layout_options": [],
    "furnish_type": null,
    "let_type": null,
    "available_from": null,
    "pets_allowed": null,
    "garden": null,
    "parking": null,
    "bills_included": null,
    "student_friendly": null,
    "families_allowed": null,
    "smokers_allowed": null,
    "dss_accepted": null
  },
  "soft_preferences": []
}
```

### 9.3 Compare

上下文：上一轮已经展示多套房源。Query：`Compare the first two.`

```json
{
  "intent": "Compare",
  "constraints": {
    "location_keywords": [],
    "commute_destination": null,
    "max_rent": null,
    "layout_options": [],
    "furnish_type": null,
    "let_type": null,
    "available_from": null,
    "pets_allowed": null,
    "garden": null,
    "parking": null,
    "bills_included": null,
    "student_friendly": null,
    "families_allowed": null,
    "smokers_allowed": null,
    "dss_accepted": null
  },
  "soft_preferences": []
}
```

### 9.4 Chitchat

Query：`Hello!`

```json
{
  "intent": "Chitchat",
  "constraints": {
    "location_keywords": [],
    "commute_destination": null,
    "max_rent": null,
    "layout_options": [],
    "furnish_type": null,
    "let_type": null,
    "available_from": null,
    "pets_allowed": null,
    "garden": null,
    "parking": null,
    "bills_included": null,
    "student_friendly": null,
    "families_allowed": null,
    "smokers_allowed": null,
    "dss_accepted": null
  },
  "soft_preferences": []
}
```

### 9.5 Search：明确 studio

Query：`Find a studio in E14.`

本例按已确认的 studio 特殊映射输出 `flat + 0b1b`。没有明确 studio 的普通零卧室或 flat 条件不适用该映射。

```json
{
  "intent": "Search",
  "constraints": {
    "location_keywords": ["E14"],
    "commute_destination": null,
    "max_rent": null,
    "layout_options": [{"bedrooms": 0, "bathrooms": 1, "property_type": "flat"}],
    "furnish_type": null,
    "let_type": null,
    "available_from": null,
    "pets_allowed": null,
    "garden": null,
    "parking": null,
    "bills_included": null,
    "student_friendly": null,
    "families_allowed": null,
    "smokers_allowed": null,
    "dss_accepted": null
  },
  "soft_preferences": []
}
```

### 9.6 Search：花园必须具备

Query：`Find a flat in E14. It must have a garden.`

明确的花园硬要求填 `garden = true`，不重复放入软偏好；单独的 flat 不补卧室数或浴室数。

```json
{
  "intent": "Search",
  "constraints": {
    "location_keywords": ["E14"],
    "commute_destination": null,
    "max_rent": null,
    "layout_options": [{"bedrooms": null, "bathrooms": null, "property_type": "flat"}],
    "furnish_type": null,
    "let_type": null,
    "available_from": null,
    "pets_allowed": null,
    "garden": true,
    "parking": null,
    "bills_included": null,
    "student_friendly": null,
    "families_allowed": null,
    "smokers_allowed": null,
    "dss_accepted": null
  },
  "soft_preferences": []
}
```

### 9.7 Search：花园有则更好

Query：`Find a flat in E14; a garden would be nice.`

花园为可选偏好，所以 `garden = null`，软偏好保留 query 的原文短语。

```json
{
  "intent": "Search",
  "constraints": {
    "location_keywords": ["E14"],
    "commute_destination": null,
    "max_rent": null,
    "layout_options": [{"bedrooms": null, "bathrooms": null, "property_type": "flat"}],
    "furnish_type": null,
    "let_type": null,
    "available_from": null,
    "pets_allowed": null,
    "garden": null,
    "parking": null,
    "bills_included": null,
    "student_friendly": null,
    "families_allowed": null,
    "smokers_allowed": null,
    "dss_accepted": null
  },
  "soft_preferences": ["a garden would be nice"]
}
```

## 10. 校验边界与后续使用条件

`schema.json` 只校验输出结构与局部值约束，例如必需键、额外键、类型、数值范围、意图、房型、家具、租赁类别和预算周期枚举、日期形状以及非 Search 的空值要求。它无法核实以下内容：

- 地点和软偏好是否确实来自 query 原文，是否擅自改写或纠错；
- query 是否全部英文，是否真实表达了对应意图、通勤关系或硬条件；
- 符合枚举的标签是否对应 query，studio 是否明确出现，花园等条件究竟是必需还是可选，否定是否针对房源属性；
- 是否错误合并历史条件，或把用户本人行为误当成房源的许可限制；
- query 是否来自真实房源的结构化属性，gold 是否对应生成时选择的字段；
- 训练与测试是否按房源隔离，是否存在近似重复、描述词语泄漏或其他泄漏。

生成样本时仍须遵守执行计划的来源、英文、按房源划分、模型隔离、记录版本及冻结规则。普通 Search 生成只使用真实房源的结构化属性，不提供房源描述原文；软偏好测试样本依执行计划第 3.3 节的专门流程使用描述，由生成模型改写为软偏好，并按计划检查与原描述的连续词语重合。

样本外层的 `id`、`source_listing_id`、`split`、`context`、`query`、`gold`、`style_tags`、`soft_pref_weights`、`gen_model`、`prompt_version` 等不属于本输出 schema。校验样本时应将其 `gold` 对象交给本 schema，不能把整个外层记录当作模型输出，也不能向输出添加这些元数据。

v1 支持带新条件的找房追问，但只抽取当前轮条件：例如上一轮有 E14 地点和预算，本轮 `"What about ones with a garden?"` 只填 `garden = true`，地点为 `[]`、预算为 `null`。不执行多轮状态合并、删除、追加或重置。旧 prompt 的 `update_scope`、`location_update_mode` 和 `layout_update_mode` 不在本 schema 中，不能额外输出。`Specific_QA` 与 `Compare` 仍可带上一轮展示的房源上下文，但输出约束及软偏好保持全空。

本版确定的覆盖缩减包括：不支持非 flat 房型输出、不生成非布尔属性排除条件、未明确周期的预算或相对/缺年份日期条件；不主动使用家具灵活来源值作为家具条件、不用月数猜租赁类别、不扩展只有身份陈述的许可推断模板。它们是 v1 的范围边界，不是阻塞本次定稿的问题清单。实际来源筛选和后续生成、评测仍在各自任务的授权范围内进行。

**本版规则已确认；通过结构校验仍不代表 gold 语义正确或数据集已通过验收。** 数据集冻结、反向核对、泄漏检查与评测按执行计划的后续任务执行。本次只定稿既有 schema 和本规范，不生成正式数据集。
