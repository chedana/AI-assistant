# 评测结果：zeroshot_intent

测试集 `test_intent_v1.jsonl`（300 条，SHA-256 校验通过）；预测 `results/pred_zeroshot_intent.jsonl`。

| 指标 | 值 |
| --- | ---: |
| field_f1 | 0.9302 |
| precision | 0.9184 |
| recall | 0.9424 |
| intent_accuracy | 0.8433 |
| extra_field_rate | 0.0007 |
| json_valid_rate | 1.0 |
| schema_valid_rate | 0.88 |
| missing_predictions | 0 |

## 按字段

| 字段 | TP | FP | FN | F1 |
| --- | ---: | ---: | ---: | ---: |
| location_keywords | 61 | 6 | 3 | 0.931 |
| layout_options | 27 | 10 | 8 | 0.750 |
| max_rent | 32 | 0 | 0 | 1.000 |
| furnish_type | 21 | 0 | 0 | 1.000 |
| let_type | 32 | 0 | 0 | 1.000 |
| available_from | 6 | 0 | 0 | 1.000 |
| pets_allowed | 0 | 0 | 0 | 0.000 |
| garden | 0 | 0 | 0 | 0.000 |
| parking | 0 | 0 | 0 | 0.000 |
| bills_included | 0 | 0 | 0 | 0.000 |
| student_friendly | 1 | 0 | 0 | 1.000 |
| families_allowed | 0 | 0 | 0 | 0.000 |
| smokers_allowed | 0 | 0 | 0 | 0.000 |
| dss_accepted | 0 | 0 | 0 | 0.000 |

## 按 style_tag

| 分组 | TP | FP | FN | F1 |
| --- | ---: | ---: | ---: | ---: |
| (none) | 12 | 1 | 0 | 0.960 |
| abbrev_layout | 69 | 5 | 4 | 0.939 |
| casual | 26 | 4 | 3 | 0.881 |
| loc_postcode | 40 | 4 | 2 | 0.930 |
| loc_station | 32 | 4 | 3 | 0.901 |
| loc_typo | 37 | 5 | 4 | 0.892 |
| multi_constraint | 18 | 2 | 2 | 0.900 |
| price_format | 61 | 6 | 4 | 0.924 |
| price_pcm | 28 | 1 | 1 | 0.966 |
| price_pw | 24 | 0 | 0 | 1.000 |

## 按样本类型

| 分组 | TP | FP | FN | F1 |
| --- | ---: | ---: | ---: | ---: |
| chitchat | 0 | 0 | 0 | 0.000 |
| compare | 0 | 0 | 0 | 0.000 |
| followup | 34 | 5 | 4 | 0.883 |
| search | 146 | 10 | 7 | 0.945 |
| specific_qa | 0 | 1 | 0 | 0.000 |

## 按生成方

| 分组 | TP | FP | FN | F1 |
| --- | ---: | ---: | ---: | ---: |
| claude | 99 | 9 | 7 | 0.925 |
| gpt | 81 | 7 | 4 | 0.936 |

## 意图混淆矩阵（行 = gold，列 = 预测）

| gold \ pred | Search | Specific_QA | Compare | Chitchat | INVALID | 召回 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Search | 75 | 0 | 0 | 0 | 0 | 1.000 |
| Specific_QA | 0 | 75 | 0 | 0 | 0 | 1.000 |
| Compare | 0 | 27 | 30 | 18 | 0 | 0.400 |
| Chitchat | 0 | 2 | 0 | 73 | 0 | 0.973 |

## 错误样例（每类最多 3 条）

### __intent__（47 条样本出错）

- `T-00518` 'Between 2 and 3, which is better value?'
  - gold: `"Compare"`；pred: `"Specific_QA"`
- `T-00519` 'How do all five stack up for location and getting around?'
  - gold: `"Compare"`；pred: `"Chitchat"`
- `T-00520` 'Which of these is closest to a tube station?'
  - gold: `"Compare"`；pred: `"Specific_QA"`

### location_keywords（5 条样本出错）

- `T-00350` 'Two-bed long let in Crouch Edn, under £630 a week'
  - gold: `["Crouch Edn"]`；pred: `["Crouch End"]`
- `T-00367` 'somewhere near Finchley Road & Frognal please'
  - gold: `["Finchley Road & Frognal"]`；pred: `["Finchley Road", "Frognal"]`
- `T-00372` '1b1b near Fulham Broadway, can you find anything?'
  - gold: `["Fulham Broadway"]`；pred: `["1b1b", "Fulham Broadway"]`

### layout_options（11 条样本出错）

- `T-00352` 'Furnished long let in Whitechaple for no more than £350 a week'
  - gold: `[]`；pred: `[{"bedrooms": null, "bathrooms": null, "property_type": null}]`
- `T-00372` '1b1b near Fulham Broadway, can you find anything?'
  - gold: `[{"bedrooms": 1, "bathrooms": 1, "property_type": null}]`；pred: `null`
- `T-00378` 'Two-bed, one-bath long let in Knightsbridge for up to £810 a week'
  - gold: `[{"bedrooms": 2, "bathrooms": 1, "property_type": null}]`；pred: `[{"bedrooms": 2, "bathrooms": 1, "property_type": "flat"}]`

