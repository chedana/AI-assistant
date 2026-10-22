"""生成方自查：用规则检查 query 是否表达了且只表达了任务条件（盲审前的粗筛，不替代盲审）。

用法：python3 scripts/lint_gen.py data/test_v1 claude
检查：flat/apartment 只在有 property_type 时出现；studio 只在 studio 任务出现；日期写出月份和年份；
预算数值和周期正确且没有多余预算；租期、家具、八个布尔条件不多不少。
"""
import json, re, sys
from pathlib import Path

d, g = Path(sys.argv[1]), sys.argv[2]
T = {json.loads(l)["task_id"]: json.loads(l) for l in (d / f"tasks_{g}.jsonl").open()}
G = {json.loads(l)["task_id"]: json.loads(l) for l in (d / f"gen_{g}.jsonl").open()}
M = ["january", "february", "march", "april", "may", "june", "july", "august",
     "september", "october", "november", "december"]
BOOL = [("pets_allowed", r"pet"), ("garden", r"garden"), ("parking", r"parking"), ("bills_included", r"bills"),
        ("student_friendly", r"student"), ("families_allowed", r"famil"), ("smokers_allowed", r"smok"),
        ("dss_accepted", r"dss|housing benefit")]
issues = []
for tid, t in T.items():
    if t.get("kind", "search") not in ("search", "followup", "softpref") or tid not in G:
        continue
    q = G[tid]["query"]; ql = q.lower(); c = t["conditions"]; lay = c.get("layout") or {}
    if bool(re.search(r"\b(flat|apartment)s?\b", ql)) != (lay.get("property_type") == "flat"):
        issues.append((tid, "flat/apartment", q))
    if ("studio" in ql) != bool(lay.get("studio")):
        issues.append((tid, "studio", q))
    if "available_from" in c:
        y, m = c["available_from"].split("-"); mn = M[int(m) - 1]
        if y not in q or mn[:3] not in ql:
            issues.append((tid, "date", q))
    elif re.search(r"\b20\d\d\b", q):
        issues.append((tid, "extra date", q))
    if "max_rent" in c:
        v, p = c["max_rent"]["value"], c["max_rent"]["period"]
        vals = {round(float(n.replace(",", "")) * (1000 if k else 1)) for n, k in re.findall(r"(\d[\d,]*(?:\.\d+)?)(k?)", ql)}
        if v not in vals:
            issues.append((tid, "rent value", q))
        pw = bool(re.search(r"pw\b|a week|per week", ql)); pcm = bool(re.search(r"pcm|a month|per month", ql))
        if (p == "pw") != pw or (p == "pcm") != pcm:
            issues.append((tid, "rent period", q))
    elif re.search(r"£|\bpw\b|pcm|a week|a month", ql):
        issues.append((tid, "extra rent", q))
    lt = c.get("let_type")
    if (lt == "long term") != ("long" in ql) or (lt == "short term") != ("short" in ql):
        issues.append((tid, "let_type", q))
    f = c.get("furnish_type")
    hf = {"part-furnished": bool(re.search(r"part[- ]furnished", ql)), "unfurnished": "unfurnished" in ql,
          "furnished": bool(re.search(r"(?<!un)(?<!part-)(?<!part )furnished", ql))}
    if (f is None and any(hf.values())) or (f and not hf[f]):
        issues.append((tid, "furnish_type", q))
    for b, pat in BOOL:
        if (b in c) != bool(re.search(pat, ql)):
            issues.append((tid, b, q))
print(f"{g}: 检查 {sum(1 for t in T.values() if t.get('kind','search') in ('search','followup','softpref') and t['task_id'] in G)} 条，疑似问题 {len(issues)} 条")
for i in issues:
    print(" ", i)
