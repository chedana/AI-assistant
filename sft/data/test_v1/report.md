# 质检报告：test_v1

通过 687 / 689（100%）

| 生成方 | 通过 | 丢弃 |
| --- | ---: | ---: |
| claude | 338 | 0 |
| gpt | 351 | 0 |

## 通过样本的类型

| 类型 | 条数 |
| --- | ---: |
| search | 309 |
| softpref | 92 |
| specific_qa | 86 |
| compare | 86 |
| chitchat | 85 |
| followup | 29 |

## 丢弃原因（按字段）

| 原因 | 次数 |
| --- | ---: |
| 近似重复 | 2 |

## 通过样本的风格标签

| tag | 条数 |
| --- | ---: |
| (none) | 283 |
| abbrev_layout | 121 |
| price_format | 115 |
| loc_station | 114 |
| loc_typo | 100 |
| casual | 88 |
| price_pcm | 66 |
| loc_postcode | 63 |
| price_pw | 56 |
| multi_constraint | 54 |
| negation | 34 |
| uk_jargon | 20 |

## 通过但有提示的样本

- `T-00254` '3b3b flat in Shoreditch, ideally somewhere with canal views and a high-end kitchen'
  - 软偏好措辞不同：gold=['somewhere with canal views', 'a high-end kitchen'] review=['canal views', 'a high-end kitchen']
- `T-00326` '1b in aldgate from may 2026, under £530 a week, ideally somewhere newly built'
  - 软偏好措辞不同：gold=['somewhere newly built'] review=['newly built']
- `T-00342` 'Near Shoreditch High Street from April 2026, ideally a gym and a rooftop lounge in the building'
  - 软偏好措辞不同：gold=['a gym', 'a rooftop lounge'] review=['a gym', 'a rooftop lounge in the building']

## 丢弃样本明细

- `T-00377`（claude）'2 bed long let under 1.8k a month'
  - 近似重复
- `T-00609`（gpt）'Good morning!'
  - 近似重复
