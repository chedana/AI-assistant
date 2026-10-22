# 评测结果：selftest_perfect_intent

测试集 `test_intent_v1.jsonl`（300 条，SHA-256 校验通过）；预测 `/tmp/ev/test_intent_v1_perfect.jsonl`。

| 指标 | 值 |
| --- | ---: |
| field_f1 | 1.0 |
| precision | 1.0 |
| recall | 1.0 |
| intent_accuracy | 1.0 |
| extra_field_rate | 0.0 |
| json_valid_rate | 1.0 |
| schema_valid_rate | 1.0 |
| missing_predictions | 0 |

## 按字段

| 字段 | TP | FP | FN | F1 |
| --- | ---: | ---: | ---: | ---: |
| location_keywords | 64 | 0 | 0 | 1.000 |
| layout_options | 35 | 0 | 0 | 1.000 |
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
| (none) | 12 | 0 | 0 | 1.000 |
| abbrev_layout | 73 | 0 | 0 | 1.000 |
| casual | 29 | 0 | 0 | 1.000 |
| loc_postcode | 42 | 0 | 0 | 1.000 |
| loc_station | 35 | 0 | 0 | 1.000 |
| loc_typo | 41 | 0 | 0 | 1.000 |
| multi_constraint | 20 | 0 | 0 | 1.000 |
| price_format | 65 | 0 | 0 | 1.000 |
| price_pcm | 29 | 0 | 0 | 1.000 |
| price_pw | 24 | 0 | 0 | 1.000 |

## 按样本类型

| 分组 | TP | FP | FN | F1 |
| --- | ---: | ---: | ---: | ---: |
| chitchat | 0 | 0 | 0 | 0.000 |
| compare | 0 | 0 | 0 | 0.000 |
| followup | 38 | 0 | 0 | 1.000 |
| search | 153 | 0 | 0 | 1.000 |
| specific_qa | 0 | 0 | 0 | 0.000 |

## 按生成方

| 分组 | TP | FP | FN | F1 |
| --- | ---: | ---: | ---: | ---: |
| claude | 106 | 0 | 0 | 1.000 |
| gpt | 85 | 0 | 0 | 1.000 |

## 意图混淆矩阵（行 = gold，列 = 预测）

| gold \ pred | Search | Specific_QA | Compare | Chitchat | INVALID | 召回 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Search | 75 | 0 | 0 | 0 | 0 | 1.000 |
| Specific_QA | 0 | 75 | 0 | 0 | 0 | 1.000 |
| Compare | 0 | 0 | 75 | 0 | 0 | 1.000 |
| Chitchat | 0 | 0 | 0 | 75 | 0 | 1.000 |

## 错误样例（每类最多 3 条）

