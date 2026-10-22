# 质检报告：pilot

通过 49 / 50（98%）

| 生成方 | 通过 | 丢弃 |
| --- | ---: | ---: |
| claude | 25 | 0 |
| gpt | 24 | 1 |

## 通过样本的类型

| 类型 | 条数 |
| --- | ---: |
| search | 49 |

## 丢弃原因（按字段）

| 原因 | 次数 |
| --- | ---: |
| location_keywords | 1 |

## 通过样本的风格标签

| tag | 条数 |
| --- | ---: |
| loc_station | 17 |
| abbrev_layout | 16 |
| price_format | 14 |
| casual | 12 |
| multi_constraint | 11 |
| price_pw | 10 |
| loc_postcode | 9 |
| loc_typo | 7 |
| price_pcm | 4 |
| negation | 4 |
| (none) | 2 |
| uk_jargon | 1 |

## 丢弃样本明细

- `P-00034`（gpt）"I'm after a four-bedroom place near Edgawre Road (Circle, District, Hammersmith & City) station, for a long let, at no more than £2,610 a week."
  - location_keywords: gold=["Edgawre Road (Circle, District, Hammersmith & City)"] review=["Edgawre Road"]
