"""阶段 3.1：从房源抽取 Search 生成任务。gold 由本脚本决定，生成模型只负责写 query。

每个任务给出：选中的条件（除地点外的 gold 已经确定）、地点提示（类型 + 来源值）、风格标签。
生成模型返回 query 和 location_keywords（query 中地点的原样片段），合并脚本再组装完整 gold。

用法：python3 scripts/make_tasks.py --split train --n 50 --out data/pilot --seed 7
"""
import argparse, json, random, re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEST_REGIONS = ["Shoreditch", "Hampstead", "Knightsbridge", "Enfield"]
BOOL_FIELDS = ["pets_allowed", "garden", "parking", "bills_included",
               "student_friendly", "families_allowed", "smokers_allowed", "dss_accepted"]
# 只有这些布尔字段会生成“要求为 false”的条件；其余 false 不符合真实用户习惯
FALSE_OK = {"smokers_allowed"}
EMPTY_CONSTRAINTS = {
    "location_keywords": [], "commute_destination": None, "max_rent": None, "layout_options": [],
    "furnish_type": None, "let_type": None, "available_from": None, "pets_allowed": None,
    "garden": None, "parking": None, "bills_included": None, "student_friendly": None,
    "families_allowed": None, "smokers_allowed": None, "dss_accepted": None,
}


def generator_of(listing_id, seed):
    """按房源固定分配生成方：同一房源永远归同一家。"""
    return "gpt" if random.Random(f"{seed}:{listing_id}").random() < 0.5 else "claude"


def nice_budget(price, period, rng):
    """预算略高于房源价格，并取整到真实用户会说的数字。"""
    step = 50 if period == "pcm" else 10
    bump = rng.choice([0, 0, 1, 2, 4]) * step
    return int((int(price) // step + 1) * step + bump)


def location_options(l, split):
    opts = []
    for g in l["regions"]:
        if split != "train" or g not in TEST_REGIONS:
            opts.append(("area", g))
    if l["postcode_district"]:
        opts.append(("postcode", l["postcode_district"]))
    for s in l["stations"][:2]:
        # 去掉线路括号和 Station 后缀：真实用户不会写 "Edgware Road (Bakerloo) Station"（小样 P-00034）
        name = re.sub(r"\s*\([^)]*\)", "", s["name"])
        name = re.sub(r"\s+Station$", "", name).strip()
        if not name:
            continue
        if split == "train" and any(g.lower() in name.lower() for g in TEST_REGIONS):
            continue
        opts.append(("station", name))
    return opts


def candidate_fields(l, split):
    c = {}
    loc = location_options(l, split)
    if loc:
        c["location"] = loc
    if not l["price_outlier"]:
        c["max_rent"] = True
    if l["is_studio"] or (l["bedrooms"] or 0) >= 1:
        c["layout"] = True
    if l["furnish_type"]:
        c["furnish_type"] = l["furnish_type"]
    if l["let_type"]:
        c["let_type"] = l["let_type"]
    if l["available_from_month"]:
        c["available_from"] = l["available_from_month"]
    for f in BOOL_FIELDS:
        v = l[f]
        if v is True or (v is False and f in FALSE_OK):
            c[f] = v
    return c


def make_task(l, split, rng, seed):
    cand = candidate_fields(l, split)
    if not cand:
        return None
    k = min(rng.randint(1, 6), len(cand))
    keys = [x for x in cand if x != "location"]
    chosen = []
    if "location" in cand and rng.random() < 0.8:      # 地点类出现概率更高
        chosen.append("location")
    rng.shuffle(keys)
    chosen += keys[: max(0, k - len(chosen))]
    if not chosen:
        chosen = [rng.choice(list(cand))]

    gold = json.loads(json.dumps(EMPTY_CONSTRAINTS))
    spec, styles = {}, []
    for f in chosen:
        if f == "location":
            kind, value = rng.choice(cand["location"])
            spec["location"] = {"kind": kind, "source_value": value}
            styles.append({"area": rng.choice(["", "", "loc_typo"]),
                           "postcode": "loc_postcode",
                           "station": rng.choice(["loc_station", "loc_station", "loc_typo"])}[kind])
        elif f == "max_rent":
            period = rng.choice(["pcm", "pw"])
            value = nice_budget(l["price_pcm"] if period == "pcm" else l["price_pw"], period, rng)
            gold["max_rent"] = {"value": value, "period": period}
            spec["max_rent"] = gold["max_rent"]
            styles.append(rng.choice([f"price_{period}", "price_format"]))
        elif f == "layout":
            if l["is_studio"]:
                opt = {"bedrooms": 0, "bathrooms": 1, "property_type": "flat"}
                spec["layout"] = {"studio": True}
            else:
                with_bath = l["bathrooms"] is not None and rng.random() < 0.5
                with_type = rng.random() < 0.3
                opt = {"bedrooms": l["bedrooms"],
                       "bathrooms": l["bathrooms"] if with_bath else None,
                       "property_type": "flat" if with_type else None}
                spec["layout"] = {k2: v for k2, v in opt.items() if v is not None}
            gold["layout_options"] = [opt]
            if rng.random() < 0.5:
                styles.append("abbrev_layout")
        else:
            gold[f] = cand[f]
            spec[f] = cand[f]
            if f in ("bills_included", "dss_accepted") and rng.random() < 0.5:
                styles.append("uk_jargon")
            if cand[f] is False:
                styles.append("negation")
    if len(chosen) >= 5:
        styles.append("multi_constraint")
    if rng.random() < 0.3:
        styles.append("casual")
    styles = [s for s in dict.fromkeys(styles) if s][:3]
    return {"listing_id": l["listing_id"], "split": split,
            "generator": generator_of(l["listing_id"], seed),
            "conditions": spec, "style_tags": styles,
            "gold_constraints_without_location": gold}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", required=True)
    ap.add_argument("--n", type=int, required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--prefix", default="P")
    a = ap.parse_args()
    rows = [json.loads(x) for x in (ROOT / "data/listings_clean.jsonl").open()]
    split = json.loads((ROOT / "data/split.json").read_text())["assignment"]
    pool = sorted([r for r in rows if split[r["listing_id"]] == a.split], key=lambda r: r["listing_id"])
    rng = random.Random(a.seed)
    rng.shuffle(pool)
    tasks = {"gpt": [], "claude": []}
    for l in pool:
        if sum(len(v) for v in tasks.values()) >= a.n:
            break
        t = make_task(l, a.split, rng, a.seed)
        if t and len(tasks[t["generator"]]) < a.n // 2:
            tasks[t["generator"]].append(t)
    out = ROOT / a.out
    out.mkdir(parents=True, exist_ok=True)
    i = 0
    for g in ("claude", "gpt"):
        with (out / f"tasks_{g}.jsonl").open("w") as f:
            for t in tasks[g]:
                i += 1
                t["task_id"] = f"{a.prefix}-{i:05d}"
                f.write(json.dumps(t, ensure_ascii=False) + "\n")
        print(g, len(tasks[g]))


if __name__ == "__main__":
    main()
