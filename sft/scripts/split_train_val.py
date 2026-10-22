"""阶段 6：把 data/train_v1/accepted.jsonl 按样本类型分层切成训练集与验证集（约 10%），
并从训练集中按固定种子取嵌套子集（500 ⊂ 1000 ⊂ 全量），供数据量消融实验使用。"""
import hashlib, json, random
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEED = 20261023
rows = [json.loads(l) for l in (ROOT / "data/train_v1/accepted.jsonl").open()]
rng = random.Random(SEED)
by = defaultdict(list)
for r in sorted(rows, key=lambda r: r["id"]):
    by[r["kind"]].append(r)
train, val = [], []
for k, rs in sorted(by.items()):
    rng.shuffle(rs)
    n = round(len(rs) * 0.10)
    val += rs[:n]; train += rs[n:]
rng.shuffle(train)
out = {"train_v1": train, "val_v1": val, "train_v1_1000": train[:1000], "train_v1_500": train[:500]}
for name, rs in out.items():
    p = ROOT / f"data/{name}.jsonl"
    with p.open("w") as f:
        for r in rs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"{name}: {len(rs)} 条", dict(Counter(r["kind"] for r in rs)), hashlib.sha256(p.read_bytes()).hexdigest()[:16])
