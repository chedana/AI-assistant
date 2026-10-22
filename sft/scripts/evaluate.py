"""阶段 5/8 评测：字段级 F1、意图准确率与混淆矩阵、多余字段率、JSON 合法率、按 style_tag 拆分 F1、错误样例。

用法：python3 scripts/evaluate.py --test data/test_extract_v1.jsonl --pred results/pred_zeroshot_extract.jsonl --name zeroshot_extract
槽位定义（执行计划阶段 5）：location_keywords 和 layout_options 的每一项各算一个槽位；max_rent、furnish_type、let_type、
available_from 和 8 个布尔字段各算一个槽位。完全匹配为 TP；抽错同时记 FP 和 FN；漏抽记 FN；多抽记 FP。
commute_destination 与 soft_preferences 不计入 F1。所有样本汇总后算微平均。
"""
import argparse, hashlib, json, re
from collections import Counter, defaultdict
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "schema.json").read_text())
FROZEN = {"test_extract_v1.jsonl": "f2f9330dd29ba4f7f4dddadd3242d5a33e54e065bf645884a5a1e472167e7011",
          "test_intent_v1.jsonl": "988c401f33e4d6092b23bbf9afe8c98e127d1d889d7c38c23ba0086b5e8439bc"}
SCALARS = ["max_rent", "furnish_type", "let_type", "available_from", "pets_allowed", "garden", "parking",
           "bills_included", "student_friendly", "families_allowed", "smokers_allowed", "dss_accepted"]
INTENTS = ["Search", "Specific_QA", "Compare", "Chitchat"]


def parse(raw):
    """去掉可能的代码块和空思考块后解析 JSON；失败返回 None。"""
    s = re.sub(r"<think>.*?</think>", "", raw or "", flags=re.S).strip()
    s = re.sub(r"^```(?:json)?\s*|\s*```$", "", s).strip()
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", s, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                return None
    return None


def slots(c):
    """把 constraints 展开成 {字段: [值...]}；值规范化为可比较的字符串。"""
    out = {}
    c = c or {}
    out["location_keywords"] = [str(x).strip() for x in (c.get("location_keywords") or []) if isinstance(x, str)]
    lay = []
    for o in c.get("layout_options") or []:
        if isinstance(o, dict):
            b, ba = o.get("bedrooms"), o.get("bathrooms")
            ba = float(ba) if isinstance(ba, (int, float)) and not isinstance(ba, bool) else ba
            lay.append(json.dumps([b, ba, o.get("property_type")]))
    out["layout_options"] = lay
    for k in SCALARS:
        v = c.get(k)
        if k == "max_rent" and isinstance(v, dict):
            try:
                v = json.dumps([float(v.get("value")), v.get("period")])
            except (TypeError, ValueError):
                v = json.dumps(v, sort_keys=True)
        out[k] = [] if v is None else [json.dumps(v) if not isinstance(v, str) else v]
    return out


def compare(gc, pc):
    """返回每个字段的 (tp, fp, fn) 以及多余字段数、gold 空槽位数。"""
    g, p = slots(gc), slots(pc)
    res, extra, null_slots = {}, 0, 0
    for k in g:
        gm, pm = Counter(g[k]), Counter(p[k])
        tp = sum((gm & pm).values())
        fp = sum(pm.values()) - tp
        fn = sum(gm.values()) - tp
        res[k] = (tp, fp, fn)
        if not g[k]:
            null_slots += 1
            extra += 1 if p[k] else 0
    return res, extra, null_slots


def f1(tp, fp, fn):
    pr = tp / (tp + fp) if tp + fp else 0.0
    rc = tp / (tp + fn) if tp + fn else 0.0
    return (2 * pr * rc / (pr + rc) if pr + rc else 0.0), pr, rc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", required=True)
    ap.add_argument("--pred", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--examples", type=int, default=3)
    a = ap.parse_args()
    tpath = Path(a.test)
    h = hashlib.sha256(tpath.read_bytes()).hexdigest()
    if tpath.name in FROZEN and h != FROZEN[tpath.name]:
        raise SystemExit(f"{tpath.name} 与冻结版本的 SHA-256 不一致，测试集已被改动。")
    tests = [json.loads(l) for l in tpath.open()]
    preds = {}
    for l in open(a.pred):
        r = json.loads(l); preds[r["id"]] = r["raw"]

    tot = defaultdict(lambda: [0, 0, 0]); by_tag = defaultdict(lambda: [0, 0, 0]); by_kind = defaultdict(lambda: [0, 0, 0])
    by_gen = defaultdict(lambda: [0, 0, 0])
    conf = Counter(); json_ok = schema_ok = 0; extra = null_slots = 0
    errors = defaultdict(list)
    for t in tests:
        raw = preds.get(t["id"])
        out = parse(raw) if raw is not None else None
        if isinstance(out, dict):
            json_ok += 1
            try:
                jsonschema.validate(out, SCHEMA); schema_ok += 1
            except jsonschema.ValidationError:
                pass
        out = out if isinstance(out, dict) else {}
        gi, pi = t["gold"]["intent"], out.get("intent")
        conf[(gi, pi if pi in INTENTS else "INVALID")] += 1
        res, e, n = compare(t["gold"]["constraints"], out.get("constraints"))
        extra += e; null_slots += n
        tags = (t.get("style_tags") or []) or ["(none)"]
        for k, (tp, fp, fn) in res.items():
            for agg in (tot[k], tot["__all__"], by_kind[t["kind"]], by_gen[t["generator"]]):
                agg[0] += tp; agg[1] += fp; agg[2] += fn
            for tag in tags:
                by_tag[tag][0] += tp; by_tag[tag][1] += fp; by_tag[tag][2] += fn
            if fp or fn:
                errors[k].append((t, out))
        if gi != pi:
            errors["__intent__"].append((t, out))

    n = len(tests)
    F, P, R = f1(*tot["__all__"])
    acc = sum(v for (g, p), v in conf.items() if g == p) / n
    summary = {"name": a.name, "test": tpath.name, "test_sha256": h, "n": n,
               "field_f1": round(F, 4), "precision": round(P, 4), "recall": round(R, 4),
               "intent_accuracy": round(acc, 4),
               "extra_field_rate": round(extra / null_slots, 4) if null_slots else None,
               "json_valid_rate": round(json_ok / n, 4), "schema_valid_rate": round(schema_ok / n, 4),
               "missing_predictions": sum(1 for t in tests if t["id"] not in preds)}
    L = [f"# 评测结果：{a.name}", "", f"测试集 `{tpath.name}`（{n} 条，SHA-256 校验通过）；预测 `{a.pred}`。", "",
         "| 指标 | 值 |", "| --- | ---: |"]
    for k in ("field_f1", "precision", "recall", "intent_accuracy", "extra_field_rate", "json_valid_rate", "schema_valid_rate", "missing_predictions"):
        L.append(f"| {k} | {summary[k]} |")
    L += ["", "## 按字段", "", "| 字段 | TP | FP | FN | F1 |", "| --- | ---: | ---: | ---: | ---: |"]
    for k in ["location_keywords", "layout_options"] + SCALARS:
        tp, fp, fn = tot[k]; L.append(f"| {k} | {tp} | {fp} | {fn} | {f1(tp, fp, fn)[0]:.3f} |")
    for title, d in (("按 style_tag", by_tag), ("按样本类型", by_kind), ("按生成方", by_gen)):
        L += ["", f"## {title}", "", "| 分组 | TP | FP | FN | F1 |", "| --- | ---: | ---: | ---: | ---: |"]
        for k in sorted(d):
            tp, fp, fn = d[k]; L.append(f"| {k} | {tp} | {fp} | {fn} | {f1(tp, fp, fn)[0]:.3f} |")
    L += ["", "## 意图混淆矩阵（行 = gold，列 = 预测）", "", "| gold \\ pred | " + " | ".join(INTENTS + ["INVALID"]) + " | 召回 |",
          "| --- |" + " ---: |" * (len(INTENTS) + 2)]
    for g in INTENTS:
        row = [conf[(g, p)] for p in INTENTS + ["INVALID"]]
        if sum(row):
            L.append(f"| {g} | " + " | ".join(map(str, row)) + f" | {conf[(g, g)] / sum(row):.3f} |")
    L += ["", f"## 错误样例（每类最多 {a.examples} 条）", ""]
    for k in ["__intent__", "location_keywords", "layout_options"] + SCALARS:
        if not errors[k]:
            continue
        L.append(f"### {k}（{len(errors[k])} 条样本出错）"); L.append("")
        for t, out in errors[k][:a.examples]:
            gv = t["gold"]["intent"] if k == "__intent__" else t["gold"]["constraints"].get(k)
            pv = out.get("intent") if k == "__intent__" else (out.get("constraints") or {}).get(k)
            L.append(f"- `{t['id']}` {t['query']!r}")
            L.append(f"  - gold: `{json.dumps(gv, ensure_ascii=False)}`；pred: `{json.dumps(pv, ensure_ascii=False)}`")
        L.append("")
    res_dir = ROOT / "results"
    (res_dir / f"eval_{a.name}.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    (res_dir / f"eval_{a.name}.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1))
    print(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
