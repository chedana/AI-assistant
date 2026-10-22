"""阶段 6：训练集生成任务（只用 train 房源），全部由 GPT 生成（D9）。

目标 3,300 条（训练 3,000 + 验证 300），按约 8% 超量生成任务：
  普通 Search 70%、软偏好 10%、带新条件追问 5%、Compare 7%、Specific_QA 4%、Chitchat 4%。
依据零样本错误分析（results/zeroshot_errors.md）加权：
  普通 Search 中提高缩写户型、拼写错误地名、含 “&” 的复合站名、完全不提户型、提户型但不说 flat 的比例；
  Compare 中加重“哪个最……”和“排个序”两种问法。
用法：python3 scripts/make_train_tasks.py --out data/train_v1 --seed 6
"""
import argparse, json, random
from collections import Counter
from pathlib import Path

import make_extra_tasks as mx
from make_tasks import make_task

ROOT = Path(__file__).resolve().parents[1]
OVER = 1.08
TARGET = 3300
MIX = {"search": 0.70, "softpref": 0.10, "followup": 0.05, "compare": 0.07, "specific_qa": 0.04, "chitchat": 0.04}
# 零样本最弱的两种比较问法，各加两份权重
mx.CMP_DIMS = mx.CMP_DIMS + ["pick the single best one by some criterion (e.g. which is closest / cheapest / biggest)"] * 2 \
    + ["rank them in order by some criterion"] * 2


def weight(t):
    c, s = t["conditions"], set(t["style_tags"])
    w = 1.0
    w += 1.0 if "abbrev_layout" in s else 0
    w += 1.0 if "loc_typo" in s else 0
    loc = c.get("location") or {}
    w += 1.5 if loc.get("kind") == "station" and "&" in loc.get("source_value", "") else 0
    w += 0.5 if "layout" not in c else 0
    lay = c.get("layout") or {}
    w += 0.3 if lay and not lay.get("studio") and "property_type" not in lay else 0
    return w


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=6)
    a = ap.parse_args()
    rows = [json.loads(x) for x in (ROOT / "data/listings_clean.jsonl").open()]
    split_of = json.loads((ROOT / "data/split.json").read_text())["assignment"]
    pool = sorted([r for r in rows if split_of[r["listing_id"]] == "train"], key=lambda r: r["listing_id"])
    rng = random.Random(a.seed)
    n = {k: round(TARGET * v * OVER) for k, v in MIX.items()}
    tasks = []

    # 普通 Search：每套房源一个候选，按权重无放回抽样（Efraimidis–Spirakis）
    cands = []
    for l in pool:
        t = make_task(l, "train", rng, a.seed)
        if t:
            t["kind"] = "search"
            cands.append(t)
    cands.sort(key=lambda t: -rng.random() ** (1 / weight(t)))
    used = set()
    for t in cands[: n["search"]]:
        used.add(t["listing_id"]); tasks.append(t)

    rest = [l for l in pool if l["listing_id"] not in used]
    for kind in ("softpref", "followup", "compare", "specific_qa", "chitchat"):
        for _ in range(n[kind]):
            tasks.append(mx.build(kind, rest, rng, a.seed, split_of))

    out = ROOT / a.out
    out.mkdir(parents=True, exist_ok=True)
    with (out / "tasks_gpt.jsonl").open("w") as f:
        for i, t in enumerate(tasks, 1):
            t["task_id"] = f"R-{i:05d}"
            t["generator"] = "gpt"
            t["target_set"] = "train"
            if t["kind"] != "search":
                t["split"] = "/".join(sorted({split_of[x] for x in t["source_listing_ids"]})) or "none"
            f.write(json.dumps(t, ensure_ascii=False) + "\n")
    (out / "tasks_claude.jsonl").write_text("")

    print("任务总数", len(tasks), dict(Counter(t["kind"] for t in tasks)))
    s = [t for t in tasks if t["kind"] == "search"]
    print("普通 Search 风格标签", dict(Counter(x for t in s for x in t["style_tags"]).most_common()))
    print("普通 Search：不提户型", sum(1 for t in s if "layout" not in t["conditions"]),
          "含 & 站名", sum(1 for t in s if "&" in (t["conditions"].get("location") or {}).get("source_value", "")),
          "条件数分布", dict(sorted(Counter(len(t["conditions"]) for t in s).items())))
    print("Compare 维度", dict(Counter(t["hints"]["dimension"][:30] for t in tasks if t["kind"] == "compare")))
    bad = [t for t in tasks for x in (t.get("source_listing_ids") or [t.get("listing_id")]) if x and split_of[x] != "train"]
    print("引用非 train 房源的任务", len(bad))


if __name__ == "__main__":
    main()
