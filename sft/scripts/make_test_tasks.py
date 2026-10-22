"""阶段 4：测试集生成任务（test + test_region 房源）。

两个测试集（执行计划阶段 4）：
  extract：约 300 条，普通 Search 220 + 软偏好 80（四个测试区各 20）
           每个 style_tag 至少 15 条，DSS 至少 10 条，布尔字段主要来自 OpenRent
  intent ：300 条，四类意图各 75；Search 75 = 普通 50 + 带新条件追问 25
每类按约 15% 超量生成，抵消质检丢弃；冻结时再按配额截取。

用法：python3 scripts/make_test_tasks.py --out data/test_v1 --seed 2026
"""
import argparse, json, random
from collections import Counter
from pathlib import Path

from make_tasks import make_task, TEST_REGIONS
from make_extra_tasks import build

ROOT = Path(__file__).resolve().parents[1]
OVER = 1.15
TAGS = ["price_pw", "price_pcm", "price_format", "abbrev_layout", "uk_jargon", "loc_postcode",
        "loc_station", "loc_typo", "negation", "casual", "multi_constraint"]
TAG_MIN, DSS_MIN = 15, 10


def pick_extract_search(pool, n, rng, seed, split_of):
    """按配额贪心挑选：先补不足的风格标签和 DSS，再随机补满；每套房源最多一条。"""
    cands = []
    for rep in range(4):
        for l in pool:
            t = make_task(l, split_of[l["listing_id"]], rng, seed)
            if t:
                cands.append(t)
    rng.shuffle(cands)
    need = {tag: int(TAG_MIN * OVER) + 1 for tag in TAGS}
    need["dss"] = int(DSS_MIN * OVER) + 1
    chosen, used = [], set()

    def gain(t):
        keys = list(t["style_tags"]) + (["dss"] if "dss_accepted" in t["conditions"] else [])
        return sum(1 for k in keys if need.get(k, 0) > 0)

    while len(chosen) < n:
        best = max((t for t in cands if t["listing_id"] not in used), key=gain, default=None)
        if best is None:
            break
        if gain(best) == 0:
            break
        chosen.append(best); used.add(best["listing_id"])
        for k in list(best["style_tags"]) + (["dss"] if "dss_accepted" in best["conditions"] else []):
            if k in need:
                need[k] -= 1
    # 随机补满；布尔条件更多来自 OpenRent，这里让 OpenRent 房源有更高的入选机会
    rest = [t for t in cands if t["listing_id"] not in used]
    rest.sort(key=lambda t: rng.random() * (0.4 if t["listing_id"].startswith("openrent") else 1.0))
    for t in rest:
        if len(chosen) >= n:
            break
        if t["listing_id"] not in used:
            chosen.append(t); used.add(t["listing_id"])
    return chosen, used


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=2026)
    a = ap.parse_args()
    rows = [json.loads(x) for x in (ROOT / "data/listings_clean.jsonl").open()]
    split_of = json.loads((ROOT / "data/split.json").read_text())["assignment"]
    pool = sorted([r for r in rows if split_of[r["listing_id"]] in ("test", "test_region")], key=lambda r: r["listing_id"])
    region_pool = [r for r in pool if split_of[r["listing_id"]] == "test_region"]
    rng = random.Random(a.seed)
    tasks = []

    # extract：普通 Search
    s, used = pick_extract_search(pool, round(220 * OVER), rng, a.seed, split_of)
    for t in s:
        t["kind"], t["target_set"] = "search", "extract"
    tasks += s
    # extract：软偏好，四区均分
    for k in range(round(80 * OVER)):
        reg = TEST_REGIONS[k % 4]
        sub = [r for r in region_pool if reg in r["regions"] and r["listing_id"] not in used]
        t = build("softpref", sub, rng, a.seed, split_of)
        used.add(t["source_listing_ids"][0])
        t["target_set"] = "extract"
        tasks.append(t)
    # intent：普通 Search 50（不与 extract 共用房源）
    rest = [r for r in pool if r["listing_id"] not in used]
    rng.shuffle(rest)
    n = 0
    for l in rest:
        if n >= round(50 * OVER):
            break
        t = make_task(l, split_of[l["listing_id"]], rng, a.seed)
        if t:
            t["kind"], t["target_set"] = "search", "intent"
            tasks.append(t); n += 1
    # intent：追问 25、问某一套 75、比较 75、闲聊 75
    for kind, cnt in (("followup", 25), ("specific_qa", 75), ("compare", 75), ("chitchat", 75)):
        for _ in range(round(cnt * OVER)):
            t = build(kind, pool, rng, a.seed, split_of)
            t["target_set"] = "intent"
            tasks.append(t)

    # 生成方：普通 Search 已按房源分配；其余按类型交替分配，保证每类两家各半
    turn = Counter()
    for t in tasks:
        if t["kind"] != "search":
            t["generator"] = ("claude", "gpt")[turn[(t["kind"], t["target_set"])] % 2]
            turn[(t["kind"], t["target_set"])] += 1
            t["split"] = "/".join(sorted({split_of[x] for x in t["source_listing_ids"]})) or "none"
    out = ROOT / a.out
    out.mkdir(parents=True, exist_ok=True)
    i = 0
    files = {g: (out / f"tasks_{g}.jsonl").open("w") for g in ("claude", "gpt")}
    for t in tasks:
        i += 1
        t["task_id"] = f"T-{i:05d}"
        files[t["generator"]].write(json.dumps(t, ensure_ascii=False) + "\n")
    for f in files.values():
        f.close()

    # 统计
    print("总任务", len(tasks))
    print("按集合/类型/生成方", Counter((t["target_set"], t["kind"], t["generator"]) for t in tasks))
    ex = [t for t in tasks if t["target_set"] == "extract"]
    print("extract 风格标签", Counter(s for t in ex for s in t.get("style_tags", [])))
    print("extract DSS", sum(1 for t in ex if "dss_accepted" in t.get("conditions", {})),
          "布尔条件来源", Counter(t.get("listing_id", t.get("source_listing_ids", [""])[0]).split(":")[0]
                                for t in ex if any(k in t.get("conditions", {}) for k in
                                ["pets_allowed", "garden", "parking", "bills_included", "student_friendly",
                                 "families_allowed", "smokers_allowed", "dss_accepted"])))
    print("softpref 区域", Counter(t.get("region") for t in ex if t["kind"] == "softpref"))


if __name__ == "__main__":
    main()
