"""阶段 3.2、3.3：非 Search、带新条件追问、软偏好的生成任务。

kind 取值：
  specific_qa  上下文 5 套房源，问其中一套          gold intent = Specific_QA，约束全空
  compare      上下文 5 套房源，比较其中几套或全部    gold intent = Compare，约束全空
  chitchat     可带可不带上下文的闲聊               gold intent = Chitchat，约束全空
  followup     上下文 5 套房源，提出新的找房条件      gold intent = Search，只含本轮条件
  softpref     测试区房源 + 描述，硬条件 + 1–2 个软偏好  gold intent = Search，软偏好由生成方给出原文
生成方按任务交替分配，保证两家数量一致。

用法：python3 scripts/make_extra_tasks.py --pool train --counts specific_qa=10,compare=10,chitchat=10,followup=10 --out data/pilot2 --seed 11
      python3 scripts/make_extra_tasks.py --pool test_region --counts softpref=10 --out data/pilot2 --seed 11 --append
"""
import argparse, json, random, re
from collections import Counter
from pathlib import Path

from make_tasks import EMPTY_CONSTRAINTS, make_task, TEST_REGIONS

ROOT = Path(__file__).resolve().parents[1]

QA_TOPICS = ["pets", "bills", "deposit", "move-in date", "parking", "garden or outdoor space",
             "nearest station", "furniture", "council tax", "floor / lift", "viewing", "size",
             "minimum tenancy", "whether students are accepted", "broadband"]
QA_REFS = ["ordinal (e.g. the second one)", "by area or postcode", "by price",
           "superlative (e.g. the cheapest one)", "pronoun after mentioning it (e.g. that one / it)"]
CMP_DIMS = ["price", "location / commute", "size and layout", "overall value", "which is better for a couple",
            "which is closer to a station", "no specific dimension"]
CHAT_TYPES = ["greeting", "thanks or goodbye", "venting about London rent", "off-topic question (not about renting)",
              "question about the assistant itself", "general UK renting knowledge question (not a search)",
              "reaction to the shown results without asking anything"]


def summarize(i, l):
    beds = "Studio" if l["is_studio"] else (f"{l['bedrooms']} bed" if l["bedrooms"] is not None else "Home")
    where = l["regions"][0] if l["regions"] else (l["postcode_district"] or "London")
    if l["regions"] and l["postcode_district"]:
        where = f"{where} ({l['postcode_district']})"
    parts = [f"{beds} flat", where, f"£{l['price_pcm']:,.0f} pcm"]
    if l["furnish_type"]:
        parts.append(l["furnish_type"])
    return f"{i}. " + ", ".join(parts)


def make_context(pool, rng):
    """模拟一次真实搜索结果：5 套房源来自同一区域（区域不足 5 套时退回全池）。"""
    anchor = rng.choice(pool)
    same = [r for r in pool if anchor["regions"] and anchor["regions"][0] in r["regions"]]
    shown = rng.sample(same if len(same) >= 5 else pool, 5)
    text = "Previously shown listings:\n" + "\n".join(summarize(i, l) for i, l in enumerate(shown, 1))
    return shown, text


def empty_gold(intent):
    return {"intent": intent, "constraints": json.loads(json.dumps(EMPTY_CONSTRAINTS)), "soft_preferences": []}


def build(kind, pool, rng, seed, split_of):
    t = {"kind": kind}
    if kind in ("specific_qa", "compare", "followup") or (kind == "chitchat" and rng.random() < 0.4):
        shown, ctx = make_context(pool, rng)
        t["context"] = ctx
        t["source_listing_ids"] = [l["listing_id"] for l in shown]
    else:
        t["context"] = None
        t["source_listing_ids"] = []
    if kind == "specific_qa":
        t["hints"] = {"target": rng.randint(1, 5), "reference": rng.choice(QA_REFS), "topic": rng.choice(QA_TOPICS)}
        t["gold"] = empty_gold("Specific_QA")
    elif kind == "compare":
        n = rng.choice([2, 2, 3, 5])
        t["hints"] = {"targets": "all" if n == 5 else sorted(rng.sample(range(1, 6), n)), "dimension": rng.choice(CMP_DIMS)}
        t["gold"] = empty_gold("Compare")
    elif kind == "chitchat":
        t["hints"] = {"subtype": rng.choice(CHAT_TYPES if t["context"] else CHAT_TYPES[:-1])}
        t["gold"] = empty_gold("Chitchat")
    elif kind == "followup":
        # 新条件来自上下文以外的一套房源，1–2 个条件
        for _ in range(50):
            l = rng.choice(pool)
            st = make_task(l, split_of[l["listing_id"]], rng, seed)
            if st and 1 <= len(st["conditions"]) <= 2:
                break
        t["conditions"] = st["conditions"]
        t["style_tags"] = [s for s in st["style_tags"] if s != "multi_constraint"]
        t["gold_constraints_without_location"] = st["gold_constraints_without_location"]
        t["condition_listing_id"] = l["listing_id"]
        t["gold"] = None
    elif kind == "softpref":
        for _ in range(50):
            l = rng.choice(pool)
            st = make_task(l, split_of[l["listing_id"]], rng, seed)
            if st and len(st["conditions"]) <= 4 and l["description"] and len(l["description"]) > 200:
                break
        t["context"] = None
        t["source_listing_ids"] = [l["listing_id"]]
        t["conditions"] = st["conditions"]
        t["style_tags"] = [s for s in st["style_tags"] if s != "multi_constraint"]
        t["gold_constraints_without_location"] = st["gold_constraints_without_location"]
        t["region"] = next((g for g in l["regions"] if g in TEST_REGIONS), None)
        t["description"] = re.sub(r"\s*<PARA>\s*", "\n", l["description"])[:2500]
        t["n_soft"] = rng.choice([1, 2])
        t["gold"] = None
    return t


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pool", required=True, help="train / test / test_region，可用逗号连接")
    ap.add_argument("--counts", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--prefix", default="Q")
    ap.add_argument("--append", action="store_true")
    ap.add_argument("--region_balance", action="store_true", help="softpref 在四个测试区之间均分")
    a = ap.parse_args()
    rows = [json.loads(x) for x in (ROOT / "data/listings_clean.jsonl").open()]
    split_of = json.loads((ROOT / "data/split.json").read_text())["assignment"]
    pools = set(a.pool.split(","))
    pool = sorted([r for r in rows if split_of[r["listing_id"]] in pools], key=lambda r: r["listing_id"])
    rng = random.Random(a.seed)
    out = ROOT / a.out
    out.mkdir(parents=True, exist_ok=True)
    existing = 0
    if a.append:
        for g in ("claude", "gpt"):
            p = out / f"tasks_{g}.jsonl"
            if p.exists():
                existing += sum(1 for _ in p.open())
    mode = "a" if a.append else "w"
    files = {g: (out / f"tasks_{g}.jsonl").open(mode) for g in ("claude", "gpt")}
    n = existing
    turn = 0
    for item in a.counts.split(","):
        kind, cnt = item.split("=")
        regions = TEST_REGIONS if (kind == "softpref" and a.region_balance) else [None]
        for k in range(int(cnt)):
            sub = pool
            if regions[0]:
                reg = regions[k % len(regions)]
                sub = [r for r in pool if reg in r["regions"]]
            t = build(kind, sub, rng, a.seed, split_of)
            n += 1
            t["task_id"] = f"{a.prefix}-{n:05d}"
            t["split"] = "/".join(sorted({split_of[x] for x in t["source_listing_ids"]})) or a.pool
            g = ("claude", "gpt")[turn % 2]
            turn += 1
            t["generator"] = g
            files[g].write(json.dumps(t, ensure_ascii=False) + "\n")
    for f in files.values():
        f.close()
    for g in ("claude", "gpt"):
        ts = [json.loads(x) for x in (out / f"tasks_{g}.jsonl").open()]
        print(g, len(ts), dict(Counter(t["kind"] for t in ts)))


if __name__ == "__main__":
    main()
