# 评测结果：zeroshot_extract

测试集 `test_extract_v1.jsonl`（300 条，SHA-256 校验通过）；预测 `results/pred_zeroshot_extract.jsonl`。

| 指标 | 值 |
| --- | ---: |
| field_f1 | 0.923 |
| precision | 0.9042 |
| recall | 0.9426 |
| intent_accuracy | 0.9933 |
| extra_field_rate | 0.0122 |
| json_valid_rate | 1.0 |
| schema_valid_rate | 0.6767 |
| missing_predictions | 0 |

## 按字段

| 字段 | TP | FP | FN | F1 |
| --- | ---: | ---: | ---: | ---: |
| location_keywords | 222 | 27 | 16 | 0.912 |
| layout_options | 116 | 74 | 40 | 0.671 |
| max_rent | 170 | 0 | 0 | 1.000 |
| furnish_type | 125 | 0 | 1 | 0.996 |
| let_type | 123 | 0 | 1 | 0.996 |
| available_from | 30 | 0 | 0 | 1.000 |
| pets_allowed | 10 | 0 | 0 | 1.000 |
| garden | 10 | 0 | 0 | 1.000 |
| parking | 6 | 0 | 0 | 1.000 |
| bills_included | 18 | 0 | 0 | 1.000 |
| student_friendly | 32 | 0 | 0 | 1.000 |
| families_allowed | 27 | 0 | 0 | 1.000 |
| smokers_allowed | 47 | 0 | 0 | 1.000 |
| dss_accepted | 17 | 0 | 0 | 1.000 |

## 按 style_tag

| 分组 | TP | FP | FN | F1 |
| --- | ---: | ---: | ---: | ---: |
| (none) | 21 | 3 | 1 | 0.913 |
| abbrev_layout | 307 | 28 | 26 | 0.919 |
| casual | 152 | 20 | 12 | 0.905 |
| loc_postcode | 161 | 13 | 5 | 0.947 |
| loc_station | 253 | 20 | 9 | 0.946 |
| loc_typo | 221 | 44 | 25 | 0.865 |
| multi_constraint | 209 | 10 | 7 | 0.961 |
| negation | 147 | 8 | 5 | 0.958 |
| price_format | 323 | 32 | 19 | 0.927 |
| price_pcm | 165 | 14 | 8 | 0.938 |
| price_pw | 157 | 16 | 6 | 0.935 |
| uk_jargon | 85 | 4 | 4 | 0.955 |

## 按样本类型

| 分组 | TP | FP | FN | F1 |
| --- | ---: | ---: | ---: | ---: |
| search | 779 | 66 | 44 | 0.934 |
| softpref | 174 | 35 | 14 | 0.877 |

## 按生成方

| 分组 | TP | FP | FN | F1 |
| --- | ---: | ---: | ---: | ---: |
| claude | 453 | 60 | 38 | 0.902 |
| gpt | 500 | 41 | 20 | 0.943 |

## 意图混淆矩阵（行 = gold，列 = 预测）

| gold \ pred | Search | Specific_QA | Compare | Chitchat | INVALID | 召回 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Search | 298 | 0 | 0 | 2 | 0 | 0.993 |

## 错误样例（每类最多 3 条）

### __intent__（2 条样本出错）

- `T-00313` 'after something part-furnished for a long let, solar power for the home would be a nice extra'
  - gold: `"Search"`；pred: `"Chitchat"`
- `T-00334` '1b1b, a smart TV would be a bonus'
  - gold: `"Search"`；pred: `"Chitchat"`

### location_keywords（21 条样本出错）

- `T-00004` 'DSS welcome and bills inc are a must near Marble Acrh; pets must be allowed too, with rent capped at £8,150 a month.'
  - gold: `["Marble Acrh"]`；pred: `["Marble Arch"]`
- `T-00009` '1b1b close to Hither Green, DSS welcome, students accepted, pets allowed, no smokers'
  - gold: `["Hither Green"]`；pred: `["1b1b", "Hither Green"]`
- `T-00016` 'For an April 2026 move, I need an unfurnished four-bedroom home with three bathrooms near Finchley Road & Frognal, up to £1,770pw.'
  - gold: `["Finchley Road & Frognal"]`；pred: `["Finchley Road", "Frognal"]`

### layout_options（79 条样本出错）

- `T-00001` 'Furnished place in NW10 that accepts students and DSS, no smokers allowed, no more than £260 a week'
  - gold: `[]`；pred: `[{"bedrooms": null, "bathrooms": null, "property_type": null}]`
- `T-00007` '1b1b flat near Batersea Park, £490pw max, must allow pets and accept students and DSS'
  - gold: `[{"bedrooms": 1, "bathrooms": 1, "property_type": "flat"}]`；pred: `[{"bedrooms": null, "bathrooms": null, "property_type": "flat"}]`
- `T-00009` '1b1b close to Hither Green, DSS welcome, students accepted, pets allowed, no smokers'
  - gold: `[{"bedrooms": 1, "bathrooms": 1, "property_type": null}]`；pred: `null`

### furnish_type（1 条样本出错）

- `T-00313` 'after something part-furnished for a long let, solar power for the home would be a nice extra'
  - gold: `"part-furnished"`；pred: `null`

### let_type（1 条样本出错）

- `T-00313` 'after something part-furnished for a long let, solar power for the home would be a nice extra'
  - gold: `"long term"`；pred: `null`

