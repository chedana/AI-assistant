"""真实 query 测试集（real_v1）：格式与个人信息检查、准备盲审、双人标注比对。

用法：
  python3 scripts/real_queries.py check   data/real_v1
  python3 scripts/real_queries.py prepare data/real_v1
  python3 scripts/real_queries.py compare data/real_v1
"""
import json, re, sys
from collections import Counter
from pathlib import Path

import jsonschema

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pipeline import compare as field_compare  # 与合成数据相同的逐字段比较

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "schema.json").read_text())
PII = [(r"[\w.+-]+@[\w-]+\.[\w.]+", "邮箱"), (r"(?:\+44|\b0)\s?\d{3,4}\s?\d{3}\s?\d{3,4}\b", "电话"),
       (r"https?://|www\.", "链接"), (r"\bu/[A-Za-z0-9_-]{3,}", "Reddit 用户名")]
REQ = {"id", "source", "url", "collected_at", "query", "trimmed", "in_scope"}


def rows(p):
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()] if p.exists() else []


def check(d):
    col = rows(d / "collected.jsonl"); gold = {r["task_id"]: r for r in rows(d / "gold_gpt.jsonl")}
    probs = []
    ids = [r.get("id") for r in col]
    if len(ids) != len(set(ids)): probs.append("id 重复")
    seen_q = {}
    for r in col:
        miss = REQ - r.keys()
        if miss: probs.append(f"{r.get('id')}: 缺字段 {sorted(miss)}")
        q = r.get("query", "")
        for pat, name in PII:
            if re.search(pat, q, re.I): probs.append(f"{r['id']}: query 疑似含{name}")
        if any(ord(c) > 127 and c not in "£’‘“”–—…€" for c in q): probs.append(f"{r['id']}: query 含非英文字符")
        if not 3 <= len(q.split()) <= 120: probs.append(f"{r['id']}: query 长度异常（{len(q.split())} 词）")
        k = re.sub(r"\W+", " ", q.lower()).strip()
        if k in seen_q: probs.append(f"{r['id']}: 与 {seen_q[k]} 重复")
        seen_q[k] = r["id"]
        g = gold.get(r["id"])
        if g is None:
            probs.append(f"{r['id']}: 缺标注初稿")
        else:
            try:
                jsonschema.validate({"intent": g["intent"], "constraints": g["constraints"], "soft_preferences": g.get("soft_preferences", [])}, SCHEMA)
            except jsonschema.ValidationError as e:
                probs.append(f"{r['id']}: 标注不符合 schema：{e.message[:80]}")
            for kw in g["constraints"].get("location_keywords") or []:
                if kw not in q: probs.append(f"{r['id']}: 地点 {kw!r} 不是 query 原文子串")
            for sp in g.get("soft_preferences") or []:
                if sp not in q: probs.append(f"{r['id']}: 软偏好 {sp!r} 不是 query 原文子串")
    src = Counter(r.get("source") for r in col)
    for s, n in src.items():
        if n > 50: probs.append(f"来源 {s} 有 {n} 条，超过 50")
    print(f"共 {len(col)} 条；来源 {dict(src)}；in_scope {sum(1 for r in col if r.get('in_scope'))}；trimmed {sum(1 for r in col if r.get('trimmed'))}")
    print(f"问题 {len(probs)} 条"); [print(" ", x) for x in probs]


def prepare(d):
    col = rows(d / "collected.jsonl")
    with (d / "review_input_for_claude.jsonl").open("w") as f:
        for r in col:
            f.write(json.dumps({"task_id": r["id"], "context": None, "query": r["query"]}, ensure_ascii=False) + "\n")
    print(f"review_input_for_claude.jsonl：{len(col)} 条")


def compare(d):
    a = {r["task_id"]: r for r in rows(d / "gold_gpt.jsonl")}
    b = {r["task_id"]: r for r in rows(d / "gold_claude.jsonl")}
    col = {r["id"]: r for r in rows(d / "collected.jsonl")}
    agree, L = 0, []
    field_dis = Counter()
    for tid in sorted(a):
        if tid not in b: continue
        g = {"intent": a[tid]["intent"], "constraints": a[tid]["constraints"], "soft_preferences": a[tid].get("soft_preferences", [])}
        diffs, _ = field_compare(g, b[tid])
        if diffs:
            for x in diffs: field_dis[x.split(":")[0]] += 1
            L.append(f"- `{tid}` {col.get(tid, {}).get('query', '')!r}")
            L += [f"  - {x.replace('gold=', 'gpt=').replace('review=', 'claude=')}" for x in diffs]
        else:
            agree += 1
    n = len(set(a) & set(b))
    head = [f"# 真实 query 双人标注比对", "", f"共同标注 {n} 条，完全一致 {agree} 条（{agree/max(n,1):.1%}）。", "",
            "| 分歧字段 | 次数 |", "| --- | ---: |"] + [f"| {k} | {v} |" for k, v in field_dis.most_common()] + ["", "## 分歧明细", ""]
    (d / "agreement.md").write_text("\n".join(head + L) + "\n", encoding="utf-8")
    print("\n".join(head[:4]))


if __name__ == "__main__":
    {"check": check, "prepare": prepare, "compare": compare}[sys.argv[1]](ROOT / sys.argv[2])
