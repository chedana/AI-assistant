# 评测结果：selftest_broken

测试集 `test_extract_v1.jsonl`（300 条，SHA-256 校验通过）；预测 `/tmp/ev/extract_broken.jsonl`。

| 指标 | 值 |
| --- | ---: |
| field_f1 | 0.996 |
| precision | 0.998 |
| recall | 0.9941 |
| intent_accuracy | 0.9967 |
| extra_field_rate | 0.0003 |
| json_valid_rate | 0.9967 |
| schema_valid_rate | 0.9967 |
| missing_predictions | 0 |

## 按字段

| 字段 | TP | FP | FN | F1 |
| --- | ---: | ---: | ---: | ---: |
| location_keywords | 238 | 0 | 0 | 1.000 |
| layout_options | 155 | 0 | 1 | 0.997 |
| max_rent | 168 | 1 | 2 | 0.991 |
| furnish_type | 126 | 0 | 0 | 1.000 |
| let_type | 124 | 0 | 0 | 1.000 |
| available_from | 30 | 0 | 0 | 1.000 |
| pets_allowed | 10 | 0 | 0 | 1.000 |
| garden | 10 | 1 | 0 | 0.952 |
| parking | 5 | 0 | 1 | 0.909 |
| bills_included | 18 | 0 | 0 | 1.000 |
| student_friendly | 31 | 0 | 1 | 0.984 |
| families_allowed | 27 | 0 | 0 | 1.000 |
| smokers_allowed | 47 | 0 | 0 | 1.000 |
| dss_accepted | 16 | 0 | 1 | 0.970 |

## 按 style_tag

| 分组 | TP | FP | FN | F1 |
| --- | ---: | ---: | ---: | ---: |
| (none) | 22 | 0 | 0 | 1.000 |
| abbrev_layout | 333 | 1 | 0 | 0.999 |
| casual | 164 | 0 | 0 | 1.000 |
| loc_postcode | 165 | 2 | 1 | 0.991 |
| loc_station | 262 | 0 | 0 | 1.000 |
| loc_typo | 246 | 0 | 0 | 1.000 |
| multi_constraint | 211 | 0 | 5 | 0.988 |
| negation | 151 | 1 | 1 | 0.993 |
| price_format | 341 | 2 | 1 | 0.996 |
| price_pcm | 168 | 0 | 5 | 0.985 |
| price_pw | 163 | 0 | 0 | 1.000 |
| uk_jargon | 84 | 0 | 5 | 0.971 |

## 按样本类型

| 分组 | TP | FP | FN | F1 |
| --- | ---: | ---: | ---: | ---: |
| search | 817 | 2 | 6 | 0.995 |
| softpref | 188 | 0 | 0 | 1.000 |

## 按生成方

| 分组 | TP | FP | FN | F1 |
| --- | ---: | ---: | ---: | ---: |
| claude | 490 | 1 | 1 | 0.998 |
| gpt | 515 | 1 | 5 | 0.994 |

## 意图混淆矩阵（行 = gold，列 = 预测）

| gold \ pred | Search | Specific_QA | Compare | Chitchat | INVALID | 召回 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Search | 299 | 0 | 0 | 0 | 1 | 0.997 |

## 错误样例（每类最多 3 条）

### __intent__（1 条样本出错）

- `T-00003` 'I need a 3 bed 2 bath place with parking for no more than £2,300 pcm, with students accepted and DSS welcome.'
  - gold: `"Search"`；pred: `null`

### layout_options（1 条样本出错）

- `T-00003` 'I need a 3 bed 2 bath place with parking for no more than £2,300 pcm, with students accepted and DSS welcome.'
  - gold: `[{"bedrooms": 3, "bathrooms": 2, "property_type": null}]`；pred: `null`

### max_rent（2 条样本出错）

- `T-00001` 'Furnished place in NW10 that accepts students and DSS, no smokers allowed, no more than £260 a week'
  - gold: `{"value": 260, "period": "pw"}`；pred: `{"value": 1.0, "period": "pcm"}`
- `T-00003` 'I need a 3 bed 2 bath place with parking for no more than £2,300 pcm, with students accepted and DSS welcome.'
  - gold: `{"value": 2300, "period": "pcm"}`；pred: `null`

### garden（1 条样本出错）

- `T-00002` 'Need a furnished 2 bed in SW5 for no more than £1,310 a week, with smokers and DSS tenants accepted.'
  - gold: `null`；pred: `true`

### parking（1 条样本出错）

- `T-00003` 'I need a 3 bed 2 bath place with parking for no more than £2,300 pcm, with students accepted and DSS welcome.'
  - gold: `true`；pred: `null`

### student_friendly（1 条样本出错）

- `T-00003` 'I need a 3 bed 2 bath place with parking for no more than £2,300 pcm, with students accepted and DSS welcome.'
  - gold: `true`；pred: `null`

### dss_accepted（1 条样本出错）

- `T-00003` 'I need a 3 bed 2 bath place with parking for no more than £2,300 pcm, with students accepted and DSS welcome.'
  - gold: `true`；pred: `null`

