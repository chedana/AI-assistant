# 质检报告：pilot2

通过 50 / 50（100%）

| 生成方 | 通过 | 丢弃 |
| --- | ---: | ---: |
| claude | 25 | 0 |
| gpt | 25 | 0 |

## 通过样本的类型

| 类型 | 条数 |
| --- | ---: |
| specific_qa | 10 |
| compare | 10 |
| chitchat | 10 |
| followup | 10 |
| softpref | 10 |

## 丢弃原因（按字段）

| 原因 | 次数 |
| --- | ---: |

## 通过样本的风格标签

| tag | 条数 |
| --- | ---: |
| (none) | 32 |
| casual | 8 |
| loc_typo | 6 |
| loc_station | 5 |
| abbrev_layout | 3 |
| loc_postcode | 2 |
| price_format | 2 |
| price_pcm | 1 |

## 通过但有提示的样本

- `Q-00041` 'Furnished studio on a long let, no more than £3,100 a month; a gym in the building would be nice'
  - 软偏好措辞不同：gold=['a gym in the building'] review=['a gym in the building would be nice']
- `Q-00043` 'Need a furnished place on a long-term let, somewhere with a view would be great'
  - 软偏好措辞不同：gold=['somewhere with a view'] review=['somewhere with a view would be great']
- `Q-00045` '2 bed 1 bath near hoxton, wooden floors would be a plus'
  - 软偏好措辞不同：gold=['wooden floors'] review=['wooden floors would be a plus']
- `Q-00047` 'Furnished 3b2b in SW3 on a long let, ideally with a big kitchen for entertaining'
  - 软偏好措辞不同：gold=['a big kitchen for entertaining'] review=['ideally with a big kitchen for entertaining']
- `Q-00049` 'Something in Whitechaple; ideally a balcony, and an en-suite would be a bonus'
  - 软偏好措辞不同：gold=['a balcony', 'an en-suite'] review=['ideally a balcony', 'an en-suite would be a bonus']

## 丢弃样本明细

