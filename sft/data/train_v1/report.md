# 质检报告：train_v1

通过 3552 / 3564（100%）

抽样盲审：审了 355 条，不一致 0 条，估计错误率 0.0%；未抽中的样本只经过格式与 schema 检查。

| 生成方 | 通过 | 丢弃 |
| --- | ---: | ---: |
| claude | 0 | 0 |
| gpt | 3552 | 0 |

## 通过样本的类型

| 类型 | 条数 |
| --- | ---: |
| search | 2495 |
| softpref | 344 |
| compare | 249 |
| followup | 178 |
| specific_qa | 143 |
| chitchat | 143 |

## 丢弃原因（按字段）

| 原因 | 次数 |
| --- | ---: |
| 缺少生成结果 | 12 |

## 通过样本的风格标签

| tag | 条数 |
| --- | ---: |
| abbrev_layout | 967 |
| loc_typo | 870 |
| price_format | 819 |
| loc_station | 775 |
| (none) | 717 |
| casual | 692 |
| loc_postcode | 430 |
| price_pcm | 410 |
| price_pw | 400 |
| multi_constraint | 339 |
| negation | 120 |
| uk_jargon | 26 |

## 丢弃样本明细

- `R-02540`（gpt）None
  - 缺少生成结果
- `R-02560`（gpt）None
  - 缺少生成结果
- `R-02584`（gpt）None
  - 缺少生成结果
- `R-02594`（gpt）None
  - 缺少生成结果
- `R-02600`（gpt）None
  - 缺少生成结果
- `R-02613`（gpt）None
  - 缺少生成结果
- `R-02631`（gpt）None
  - 缺少生成结果
- `R-02663`（gpt）None
  - 缺少生成结果
- `R-02687`（gpt）None
  - 缺少生成结果
- `R-02710`（gpt）None
  - 缺少生成结果
- `R-02764`（gpt）None
  - 缺少生成结果
- `R-02847`（gpt）None
  - 缺少生成结果
