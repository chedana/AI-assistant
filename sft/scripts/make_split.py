"""阶段 2 第 5 项：按房源划分 train / test / test_region，写 data/split.json。

负责人 2026-10-22 选定的 4 个检索子库区域见 TEST_REGIONS。
带任一区域标签的房源全部进入 test_region；其余按 listing_id 排序后用固定种子打乱，约 10% 为 test。
划分生成后不再改动；如需改动另存新版本。
"""
import json, random
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEST_REGIONS = ["Shoreditch", "Hampstead", "Knightsbridge", "Enfield"]
SEED = 20261022
TEST_FRACTION = 0.10

rows = [json.loads(l) for l in (ROOT / "data/listings_clean.jsonl").open()]
assign = {}
for r in rows:
    if set(r["regions"]) & set(TEST_REGIONS):
        assign[r["listing_id"]] = "test_region"
rest = sorted(r["listing_id"] for r in rows if r["listing_id"] not in assign)
random.Random(SEED).shuffle(rest)
n_test = round(len(rest) * TEST_FRACTION)
for i, lid in enumerate(rest):
    assign[lid] = "test" if i < n_test else "train"

out = {
    "version": "v1",
    "seed": SEED,
    "test_fraction": TEST_FRACTION,
    "test_regions": TEST_REGIONS,
    "source": "data/listings_clean.jsonl",
    "counts": dict(Counter(assign.values())),
    "assignment": dict(sorted(assign.items())),
}
path = ROOT / "data/split.json"
if path.exists():
    old = json.loads(path.read_text())
    if old["assignment"] != out["assignment"]:
        raise SystemExit("split.json 已存在且内容不同：划分冻结后不能覆盖，请另存新版本。")
path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
print(out["counts"])
