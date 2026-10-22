# 清洗后房源库统计

来源文件 SHA-256：`6204d6001adbfdda37d09b06ba9d1c1c2054987e69cb84c25968c4a98da75fc7`；生成于 2026-10-22T14:30:29+00:00。

保留 21,965 条（Rightmove 18,903，OpenRent 3,062），按房型范围排除 7,154 条，原始 29,119 条。

## 字段有效率

| 字段 | 全部 | Rightmove | OpenRent |
| --- | ---: | ---: | ---: |
| postcode_district | 80.9% | 77.8% | 100.0% |
| bedrooms | 100.0% | 100.0% | 100.0% |
| bathrooms | 97.4% | 96.9% | 100.0% |
| price_pcm | 100.0% | 100.0% | 100.0% |
| furnish_type | 77.4% | 75.8% | 87.4% |
| let_type | 81.2% | 94.4% | 0.0% |
| available_from_month | 23.7% | 23.6% | 24.1% |
| pets_allowed | 19.2% | 6.1% | 100.0% |
| garden | 19.2% | 6.1% | 100.0% |
| parking | 19.2% | 6.1% | 100.0% |
| bills_included | 19.2% | 6.1% | 100.0% |
| student_friendly | 19.0% | 6.1% | 98.9% |
| families_allowed | 19.2% | 6.1% | 100.0% |
| smokers_allowed | 19.2% | 6.1% | 100.0% |
| dss_accepted | 4.9% | 0.0% | 35.4% |
| stations（非空） | 99.8% | | |

available_from_month 只统计明显晚于抓取日期（超过 7 天）的房源；“现在可入住” 11,291 条，日期未知 5,478 条。

## 清洗处理计数

| 项目 | 条数 |
| --- | ---: |
| address_page_text | 354 |
| address_replaced_by_title | 354 |
| available_future_month | 5,196 |
| available_now | 11,291 |
| bathrooms_nulled_gt10 | 3 |
| derived_price_pw | 3,062 |
| let_type_non_tenancy_value | 3,080 |
| postcode_district_address | 14,158 |
| postcode_district_missing | 4,194 |
| postcode_district_source | 3,607 |
| postcode_district_title | 6 |
| price_outlier_flagged | 55 |
| raw_total | 29,119 |
| studio_bathrooms_overridden | 162 |
| studio_bedrooms_overridden | 705 |

## 区域房源数（前 30，共 132 个区域）

一套房源可能带多个区域标签，所以各区域之和大于总数。

| 排名 | 区域 | 房源数 | 中位月租 | Studio/1 卧占比 | 3 卧以上占比 |
| ---: | --- | ---: | ---: | ---: | ---: |
| 1 | Kensington | 794 | £4,498 | 37% | 27% |
| 2 | Wandsworth | 746 | £2,750 | 37% | 18% |
| 3 | Southwark | 710 | £2,650 | 40% | 17% |
| 4 | Canary Wharf | 702 | £2,750 | 46% | 11% |
| 5 | Vauxhall | 700 | £4,550 | 24% | 22% |
| 6 | Paddington | 665 | £5,200 | 27% | 47% |
| 7 | Fulham | 651 | £3,200 | 46% | 13% |
| 8 | Greenwich | 643 | £2,100 | 39% | 12% |
| 9 | Mayfair | 642 | £11,483 | 27% | 36% |
| 10 | Islington | 579 | £2,700 | 51% | 16% |
| 11 | Hackney | 565 | £2,749 | 43% | 16% |
| 12 | Notting Hill | 564 | £3,532 | 48% | 19% |
| 13 | Marylebone | 560 | £4,983 | 42% | 29% |
| 14 | Hounslow | 461 | £1,850 | 46% | 12% |
| 15 | Croydon | 449 | £1,500 | 55% | 7% |
| 16 | Earls Court | 449 | £3,300 | 51% | 15% |
| 17 | Lewisham | 414 | £1,825 | 44% | 10% |
| 18 | Harrow | 408 | £1,700 | 44% | 8% |
| 19 | Maida Vale | 374 | £3,500 | 35% | 26% |
| 20 | Richmond | 358 | £2,200 | 39% | 23% |
| 21 | Knightsbridge | 346 | £9,967 | 17% | 49% |
| 22 | Hampstead | 337 | £3,000 | 40% | 30% |
| 23 | Shoreditch | 326 | £3,046 | 47% | 12% |
| 24 | Pimlico | 325 | £3,575 | 42% | 24% |
| 25 | Hammersmith | 315 | £3,497 | 37% | 10% |
| 26 | Whitechapel | 313 | £2,709 | 47% | 17% |
| 27 | Ladbroke Grove | 278 | £3,250 | 46% | 17% |
| 28 | Ealing | 278 | £2,200 | 37% | 16% |
| 29 | Enfield | 255 | £1,750 | 44% | 18% |
| 30 | Holloway | 247 | £2,200 | 50% | 15% |
