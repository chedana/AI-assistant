"""阶段 5：零样本错误分析，把错误归因到具体模式，输出 results/zeroshot_errors.md。"""
import json, sys
from collections import Counter, defaultdict
from pathlib import Path

import jsonschema

sys.path.insert(0, str(Path(__file__).resolve().parent))
from evaluate import parse, SCHEMA

ROOT = Path(__file__).resolve().parents[1]


def load(test, pred):
    T = [json.loads(l) for l in (ROOT / test).open()]
    P = {json.loads(l)["id"]: json.loads(l)["raw"] for l in (ROOT / pred).open()}
    return [(t, parse(P[t["id"]]) or {}, P[t["id"]]) for t in T]


ex = load("data/test_extract_v1.jsonl", "results/pred_zeroshot_extract.jsonl")
it = load("data/test_intent_v1.jsonl", "results/pred_zeroshot_intent.jsonl")
both = ex + it
cats = defaultdict(list)


def lay_key(o):
    return (o.get("bedrooms"), float(o["bathrooms"]) if isinstance(o.get("bathrooms"), (int, float)) and not isinstance(o.get("bathrooms"), bool) else o.get("bathrooms"), o.get("property_type"))


# 户型
for t, p, raw in both:
    if t["gold"]["intent"] != "Search":
        continue
    g = [lay_key(o) for o in t["gold"]["constraints"]["layout_options"]]
    pl = [lay_key(o) for o in ((p.get("constraints") or {}).get("layout_options") or []) if isinstance(o, dict)]
    if sorted(map(str, g)) == sorted(map(str, pl)):
        continue
    q = t["query"].lower()
    if not g and pl and all(x == (None, None, None) for x in pl):
        c = "无户型要求却输出全空的户型项"
    elif g and pl and len(g) == len(pl) == 1:
        gb, gba, gt = g[0]; pb, pba, pt = pl[0]
        if (gb, gba) == (pb, pba) and gt != pt:
            c = "property_type 不一致（" + ("没说 flat 却补了 flat" if pt == "flat" else "说了 flat/apartment 却没填") + "）"
        elif gb == pb and gba != pba:
            c = "bathrooms 不一致（" + ("自行补了浴室数" if gba is None else "漏了浴室数或 studio 未补 1 卫") + "）"
        elif "studio" in q:
            c = "studio 没有按 0 卧 1 卫 flat 输出"
        else:
            c = "卧室数不一致"
    elif g and not pl:
        c = "漏抽户型"
    elif not g and pl:
        c = "无户型要求却抽出了户型"
    else:
        c = "其他户型错误"
    cats[("户型", c)].append((t, g, pl))

# 地点
for t, p, raw in both:
    if t["gold"]["intent"] != "Search":
        continue
    g = t["gold"]["constraints"]["location_keywords"]
    pl = (p.get("constraints") or {}).get("location_keywords") or []
    if sorted(g) == sorted(pl):
        continue
    gl, pll = [x.lower() for x in g], [str(x).lower() for x in pl]
    if sorted(gl) == sorted(pll):
        c = "只差大小写"
    elif g and pl and len(g) == len(pl) == 1 and pl[0] not in t["query"]:
        c = "改写了原文（纠正拼写或补全名称）"
    elif g and pl and len(g) == len(pl) == 1 and (g[0] in pl[0] or pl[0] in g[0]):
        c = "片段边界不同（多带或少带了词）"
    elif len(pl) > len(g):
        c = "多抽了地点（如把 London 或软偏好里的地方算进去）"
    elif not pl:
        c = "漏抽地点"
    else:
        c = "其他地点错误"
    cats[("地点", c)].append((t, g, pl))

# schema
sch = Counter(); sch_ex = defaultdict(list)
for t, p, raw in both:
    if not p:
        continue
    try:
        jsonschema.validate(p, SCHEMA)
    except jsonschema.ValidationError as e:
        path = "/".join(str(x) for x in e.absolute_path)
        key = f"{path or '(root)'}: {e.validator}"
        sch[key] += 1; sch_ex[key].append((t["id"], e.message[:120]))

# 意图（比较）
cmp_err = Counter(); cmp_ex = defaultdict(list)
for t, p, raw in it:
    if t["gold"]["intent"] == "Compare" and p.get("intent") != "Compare":
        cmp_err[p.get("intent")] += 1; cmp_ex[p.get("intent")].append(t)
cmp_ok = [t for t, p, _ in it if t["gold"]["intent"] == "Compare" and p.get("intent") == "Compare"]
other_int = [(t, p.get("intent")) for t, p, _ in both if t["gold"]["intent"] not in ("Compare",) and p.get("intent") != t["gold"]["intent"]]

# 软偏好
sp = Counter()
for t, p, raw in ex:
    if t["kind"] != "softpref":
        continue
    ps = p.get("soft_preferences") or []
    sp["软偏好样本"] += 1
    sp["抽出了软偏好"] += bool(ps)
    c = (p.get("constraints") or {})
    hard_leak = any(isinstance(x, str) and any(w in x.lower() for w in [s.lower() for s in t["gold"]["soft_preferences"]]) for x in c.get("location_keywords") or [])
    sp["软偏好混进地点字段"] += hard_leak
nonsoft_with_soft = sum(1 for t, p, _ in ex if t["kind"] == "search" and (p.get("soft_preferences") or []))

# 输出长度
toks = [len(raw) for t, p, raw in both]

L = ["# 零样本错误分析（Qwen/Qwen3.5-4B，zeroshot_v1）", "",
     "数据：`results/pred_zeroshot_{extract,intent}.jsonl`；指标见 `eval_zeroshot_extract.md`、`eval_zeroshot_intent.md`。", ""]
for field in ("户型", "地点"):
    items = sorted([(k[1], v) for k, v in cats.items() if k[0] == field], key=lambda x: -len(x[1]))
    L += [f"## {field}错误（共 {sum(len(v) for _, v in items)} 条样本）", "", "| 类型 | 条数 |", "| --- | ---: |"]
    L += [f"| {c} | {len(v)} |" for c, v in items]
    L.append("")
    for c, v in items:
        L.append(f"**{c}**")
        for t, g, pl in v[:3]:
            L.append(f"- `{t['id']}` {t['query']!r} — gold `{g}`，pred `{pl}`")
        L.append("")
L += ["## 不符合 schema 的原因", "", "| 位置: 规则 | 条数 |", "| --- | ---: |"]
L += [f"| {k} | {v} |" for k, v in sch.most_common()]
L.append("")
for k, v in sch.most_common(4):
    L.append(f"- {k}：例 `{v and sch_ex[k][0][0]}` {sch_ex[k][0][1]!r}")
L += ["", "## 意图错误", "", f"比较类 75 条中判对 {len(cmp_ok)} 条；误判为：" + "，".join(f"{k} {v} 条" for k, v in cmp_err.items()), ""]
for k, ts in cmp_ex.items():
    L.append(f"**比较 → {k}**")
    for t in ts[:5]:
        L.append(f"- `{t['id']}` {t['query']!r}")
    L.append("")
L.append("其他意图错误：")
for t, pi in other_int:
    L.append(f"- `{t['id']}` gold {t['gold']['intent']} → pred {pi}：{t['query']!r}")
L += ["", "## 软偏好", "",
      f"- 软偏好样本 {sp['软偏好样本']} 条，抽出软偏好 {sp['抽出了软偏好']} 条；软偏好内容混进地点字段 {sp['软偏好混进地点字段']} 条。",
      f"- 普通 Search 样本（gold 无软偏好）中输出了软偏好的 {nonsoft_with_soft} 条。",
      "", "## 输出长度", "",
      f"- 原始输出平均 {sum(toks)/len(toks):.0f} 个字符（格式化缩进的 JSON），最长 {max(toks)}。"]
(ROOT / "results/zeroshot_errors.md").write_text("\n".join(L) + "\n", encoding="utf-8")
print("\n".join(L))
