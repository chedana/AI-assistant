# 评测结果：selftest_perfect_extract

测试集 `test_extract_v1.jsonl`（300 条，SHA-256 校验通过）；预测 `/tmp/ev/test_extract_v1_perfect.jsonl`。

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
| location_keywords | 238 | 0 | 0 | 1.000 |
| layout_options | 156 | 0 | 0 | 1.000 |
| max_rent | 170 | 0 | 0 | 1.000 |
| furnish_type | 126 | 0 | 0 | 1.000 |
| let_type | 124 | 0 | 0 | 1.000 |
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
| (none) | 22 | 0 | 0 | 1.000 |
| abbrev_layout | 333 | 0 | 0 | 1.000 |
| casual | 164 | 0 | 0 | 1.000 |
| loc_postcode | 166 | 0 | 0 | 1.000 |
| loc_station | 262 | 0 | 0 | 1.000 |
| loc_typo | 246 | 0 | 0 | 1.000 |
| multi_constraint | 216 | 0 | 0 | 1.000 |
| negation | 152 | 0 | 0 | 1.000 |
| price_format | 342 | 0 | 0 | 1.000 |
| price_pcm | 173 | 0 | 0 | 1.000 |
| price_pw | 163 | 0 | 0 | 1.000 |
| uk_jargon | 89 | 0 | 0 | 1.000 |

## 按样本类型

| 分组 | TP | FP | FN | F1 |
| --- | ---: | ---: | ---: | ---: |
| search | 823 | 0 | 0 | 1.000 |
| softpref | 188 | 0 | 0 | 1.000 |

## 按生成方

| 分组 | TP | FP | FN | F1 |
| --- | ---: | ---: | ---: | ---: |
| claude | 491 | 0 | 0 | 1.000 |
| gpt | 520 | 0 | 0 | 1.000 |

## 意图混淆矩阵（行 = gold，列 = 预测）

| gold \ pred | Search | Specific_QA | Compare | Chitchat | INVALID | 召回 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Search | 300 | 0 | 0 | 0 | 0 | 1.000 |

## 错误样例（每类最多 3 条）

