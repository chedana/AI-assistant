"""阶段 2 第 4 项：统计报告 results/listings_stats.md。"""
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
rows = [json.loads(l) for l in (ROOT / "data/listings_clean.jsonl").open()]
rep = json.loads((ROOT / "results/clean_report.json").read_text())
N = len(rows)
FIELDS = ["postcode_district", "bedrooms", "bathrooms", "price_pcm", "furnish_type", "let_type",
          "available_from_month", "pets_allowed", "garden", "parking", "bills_included",
          "student_friendly", "families_allowed", "smokers_allowed", "dss_accepted"]

def rate(f, src=None):
    rs = [r for r in rows if src is None or r["source"] == src]
    return sum(1 for r in rs if r[f] is not None) / len(rs) if rs else 0

L = ["# 清洗后房源库统计", "",
     f"来源文件 SHA-256：`{rep['source_sha256']}`；生成于 {rep['generated_at']}。", "",
     f"保留 {N:,} 条（Rightmove {rep['kept_by_source'].get('rightmove',0):,}，OpenRent {rep['kept_by_source'].get('openrent',0):,}），"
     f"按房型范围排除 {rep['excluded_by_type']:,} 条，原始 {rep['stats']['raw_total']:,} 条。", "",
     "## 字段有效率", "", "| 字段 | 全部 | Rightmove | OpenRent |", "| --- | ---: | ---: | ---: |"]
for f in FIELDS:
    L.append(f"| {f} | {rate(f):.1%} | {rate(f,'rightmove'):.1%} | {rate(f,'openrent'):.1%} |")
L.append(f"| stations（非空） | {sum(1 for r in rows if r['stations'])/N:.1%} | | |")
L += ["", "available_from_month 只统计明显晚于抓取日期（超过 7 天）的房源；"
      f"“现在可入住” {sum(1 for r in rows if r['available_now']):,} 条，日期未知 {sum(1 for r in rows if r['available_now'] is None):,} 条。", ""]
L += ["## 清洗处理计数", "", "| 项目 | 条数 |", "| --- | ---: |"]
for k, v in sorted(rep["stats"].items()):
    if isinstance(v, int):
        L.append(f"| {k} | {v:,} |")
reg = Counter(g for r in rows for g in r["regions"])
L += ["", f"## 区域房源数（前 30，共 {len(reg)} 个区域）", "",
      "一套房源可能带多个区域标签，所以各区域之和大于总数。", "",
      "| 排名 | 区域 | 房源数 | 中位月租 | Studio/1 卧占比 | 3 卧以上占比 |", "| ---: | --- | ---: | ---: | ---: | ---: |"]
for i, (g, c) in enumerate(reg.most_common(30), 1):
    rs = [r for r in rows if g in r["regions"]]
    prices = sorted(r["price_pcm"] for r in rs)
    small = sum(1 for r in rs if (r["bedrooms"] or 0) <= 1) / len(rs)
    big = sum(1 for r in rs if (r["bedrooms"] or 0) >= 3) / len(rs)
    L.append(f"| {i} | {g} | {c:,} | £{prices[len(prices)//2]:,.0f} | {small:.0%} | {big:.0%} |")
(ROOT / "results/listings_stats.md").write_text("\n".join(L) + "\n", encoding="utf-8")
print("\n".join(L))
