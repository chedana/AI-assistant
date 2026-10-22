"""阶段 4：从合并通过的样本中按目标数截取两个测试集（固定种子），检查配额。

extract：普通 Search 220（每个 style_tag ≥ 15，DSS ≥ 10）+ 软偏好 80（四区各 20）
intent ：Search 50 + 带新条件追问 25 + Specific_QA 75 + Compare 75 + Chitchat 75
每类尽量两家各半。输出 data/test_extract_v1.jsonl、data/test_intent_v1.jsonl（冻结前为待抽检状态）。
"""
import json, random
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEED = 2026
TAGS = ["price_pw", "price_pcm", "price_format", "abbrev_layout", "uk_jargon", "loc_postcode",
        "loc_station", "loc_typo", "negation", "casual", "multi_constraint"]
acc = [json.loads(l) for l in (ROOT / "data/test_v1/accepted.jsonl").open()]
tasks = {}
for g in ("claude", "gpt"):
    for l in (ROOT / f"data/test_v1/tasks_{g}.jsonl").open():
        t = json.loads(l); tasks[t["task_id"]] = t
rng = random.Random(SEED)
for r in acc:
    t = tasks[r["id"]]
    r["_set"], r["_region"] = t["target_set"], t.get("region")
    r["_dss"] = r["gold"]["constraints"]["dss_accepted"] is not None
rng.shuffle(acc)


def balanced(pool, n):
    """两家交替取，保证各半；一家不够时由另一家补。"""
    by = {g: [r for r in pool if r["generator"] == g] for g in ("claude", "gpt")}
    out, i = [], 0
    while len(out) < n and (by["claude"] or by["gpt"]):
        g = ("claude", "gpt")[i % 2]; i += 1
        if by[g]:
            out.append(by[g].pop(0))
    return out


def pick_search(pool, n):
    need = Counter({t: 15 for t in TAGS}); need["dss"] = 10
    chosen = []
    for _ in range(n):
        def gain(r):
            keys = list(r["style_tags"]) + (["dss"] if r["_dss"] else [])
            return sum(1 for k in keys if need[k] > 0)
        cands = [r for r in pool if r not in chosen]
        best = max(cands, key=gain)
        if gain(best) == 0:
            break
        chosen.append(best)
        for k in list(best["style_tags"]) + (["dss"] if best["_dss"] else []):
            need[k] -= 1
    rest = [r for r in pool if r not in chosen]
    chosen += balanced(rest, n - len(chosen))
    return chosen


extract = pick_search([r for r in acc if r["_set"] == "extract" and r["kind"] == "search"], 220)
for reg in ("Shoreditch", "Hampstead", "Knightsbridge", "Enfield"):
    extract += balanced([r for r in acc if r["kind"] == "softpref" and r["_region"] == reg], 20)
intent = []
for kind, n in (("search", 50), ("followup", 25), ("specific_qa", 75), ("compare", 75), ("chitchat", 75)):
    intent += balanced([r for r in acc if r["_set"] == "intent" and r["kind"] == kind], n)


def clean(r):
    return {k: v for k, v in r.items() if not k.startswith("_") and k != "review_warnings"}


for name, rows in (("test_extract_v1", extract), ("test_intent_v1", intent)):
    rows = sorted(rows, key=lambda r: r["id"])
    with (ROOT / f"data/{name}.jsonl").open("w") as f:
        for r in rows:
            f.write(json.dumps(clean(r), ensure_ascii=False) + "\n")
    print(f"== {name}: {len(rows)} 条")
    print("  类型", dict(Counter(r["kind"] for r in rows)))
    print("  意图", dict(Counter(r["gold"]["intent"] for r in rows)))
    print("  生成方", dict(Counter(r["generator"] for r in rows)))
    if name == "test_extract_v1":
        st = Counter(s for r in rows if r["kind"] == "search" for s in r["style_tags"])
        print("  风格标签（普通 Search）", dict(st), "最少", min(st[t] for t in TAGS))
        print("  DSS", sum(1 for r in rows if r["_dss"]),
              "软偏好区域", dict(Counter(r["_region"] for r in rows if r["kind"] == "softpref")))
        bools = ["pets_allowed", "garden", "parking", "bills_included", "student_friendly", "families_allowed", "smokers_allowed", "dss_accepted"]
        print("  含布尔条件", sum(1 for r in rows if any(r["gold"]["constraints"][b] is not None for b in bools)))
