"""汇总量化推理对照实验（QUANT_INFERENCE_PLAN.md），输出 results/quant/report.md。

每个配置与参照组逐条配对比较：字段 F1 差值的 95% bootstrap 置信区间、意图翻转、按字段 / style_tag 的 F1 差值；
并汇总速度（端到端 p50/p90、TTFT、TPOT、批量吞吐）与显存（权重、KV cache）。
参照组：所有配置对 2b_bf16_a；紧凑输出的量化配置对 2b_bf16_compact。
用法：python3 scripts/quant_report.py [结果目录，默认 results/quant]
"""
import json, random, re, sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from evaluate import parse, compare, f1

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / (sys.argv[1] if len(sys.argv) > 1 else "results/quant")
TESTS = {"extract": ROOT / "data/test_extract_v1.jsonl", "intent": ROOT / "data/test_intent_v1.jsonl"}
TEST = {k: [json.loads(l) for l in p.open()] for k, p in TESTS.items()}
B = 1000


def ref_of(tag):
    """2B 量化实验的参照组：紧凑输出的量化配置对 2b_bf16_compact，其余对 2b_bf16_a。"""
    if tag == "2b_bf16_a":
        return None
    if tag.endswith("_compact") and tag != "2b_bf16_compact":
        return "2b_bf16_compact"
    return "2b_bf16_a"


def per_sample(tag, part):
    p = OUT / f"{tag}_{part}.jsonl"
    if not p.exists():
        return None
    raw = {json.loads(l)["id"]: json.loads(l)["raw"] for l in p.open()}
    rows = {}
    for t in TEST[part]:
        out = parse(raw.get(t["id"])) or {}
        res, _, _ = compare(t["gold"]["constraints"], out.get("constraints"))
        tp = sum(v[0] for v in res.values()); fp = sum(v[1] for v in res.values()); fn = sum(v[2] for v in res.values())
        rows[t["id"]] = {"tp": tp, "fp": fp, "fn": fn, "field": res, "tags": t.get("style_tags") or ["(none)"],
                         "intent_ok": out.get("intent") == t["gold"]["intent"]}
    return rows


def micro(rows, ids):
    tp = sum(rows[i]["tp"] for i in ids); fp = sum(rows[i]["fp"] for i in ids); fn = sum(rows[i]["fn"] for i in ids)
    return f1(tp, fp, fn)[0]


def boot_ci(a, b):
    ids = sorted(a)
    rng = random.Random(0)
    ds = sorted(micro(b, s) - micro(a, s) for s in ([rng.choice(ids) for _ in ids] for _ in range(B)))
    return ds[int(0.025 * B)], ds[int(0.975 * B) - 1]


def mem(tag):
    log = OUT / f"{tag}_extract.log"
    if not log.exists():
        return None, None
    s = log.read_text(errors="ignore")
    w = re.findall(r"Actual usage is ([\d.]+) GiB for consumed memory", s) or re.findall(r"Model loading took ([\d.]+) GiB", s)
    k = re.findall(r"kv cache memory in use is ([\d.]+) GiB", s, re.I) or re.findall(r"Available KV cache memory: ([\d.]+) GiB", s)
    return (float(w[-1]) if w else None), (float(k[-1]) if k else None)


def load_json(p):
    return json.loads(p.read_text()) if p.exists() else {}


tags = sorted({p.name[: -len("_extract.meta.json")] for p in OUT.glob("*_extract.meta.json")})
first = ["2b_bf16_a", "2b_bf16_b", "2b_fp8_online", "2b_fp8_offline", "2b_int8", "2b_bf16_kvfp8", "2b_nf4_bnb",
         "2b_w4a16_rtn", "2b_w4a16_gptq", "2b_w4a16_awq", "2b_w4a16_gptq_generic", "2b_bf16_compact"]
order = [t for t in first if t in tags] + sorted(t for t in tags if t not in first)
tags = [t for t in order if t in tags]
PS = {(t, part): per_sample(t, part) for t in tags for part in TEST}

L = ["# 量化推理对照实验报告", "", "设计见 `QUANT_INFERENCE_PLAN.md`。ΔF1 与置信区间均相对于参照组（同一测试样本逐条配对，bootstrap 1,000 次）。", "",
     "## 总表", "",
     "| 配置 | 参照 | 抽取 F1 | ΔF1 [95% CI] | 意图准确率 | 意图 对→错 / 错→对 | schema 合规 | 延迟 p50 / p90 (s) | TTFT (s) | TPOT (ms) | 批量吞吐 (tok/s) | 平均输出 token | 权重+非 torch (GiB) | KV cache (GiB) |",
     "| --- | --- | ---: | --- | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
for t in tags:
    r = ref_of(t)
    ee, ei = load_json(OUT / f"eval_{t}_extract.json"), load_json(OUT / f"eval_{t}_intent.json")
    m = load_json(OUT / f"{t}_extract.meta.json")
    a, b = PS.get((r, "extract")) if r else None, PS[(t, "extract")]
    if a and b:
        lo, hi = boot_ci(a, b); d = micro(b, list(b)) - micro(a, list(a))
        dtxt = f"{d*100:+.2f} [{lo*100:+.2f}, {hi*100:+.2f}]"
    else:
        dtxt = "—"
    ai, bi = PS.get((r, "intent")) if r else None, PS[(t, "intent")]
    flips = f"{sum(1 for i in bi if ai[i]['intent_ok'] and not bi[i]['intent_ok'])} / {sum(1 for i in bi if not ai[i]['intent_ok'] and bi[i]['intent_ok'])}" if ai and bi else "—"
    sv = (ee.get("schema_valid_rate", 0) + ei.get("schema_valid_rate", 0)) / 2 if ee and ei else None
    w, k = mem(t)
    L.append(f"| `{t}` | {r or '—'} | {ee.get('field_f1', '—')} | {dtxt} | {ei.get('intent_accuracy', '—')} | {flips} | "
             f"{'—' if sv is None else f'{sv:.3f}'} | {m.get('latency_p50_s', '—')} / {m.get('latency_p90_s', '—')} | {m.get('ttft_p50_s', '—')} | "
             f"{m.get('tpot_p50_ms', '—')} | {m.get('batch_output_tok_per_s', '—')} | {m.get('mean_output_tokens', '—')} | {w or '—'} | {k or '—'} |")

if "2b_bf16_b" in tags and "2b_bf16_a" in tags:
    a, b = PS[("2b_bf16_a", "extract")], PS[("2b_bf16_b", "extract")]
    diff_samples = sum(1 for i in a if (a[i]["tp"], a[i]["fp"], a[i]["fn"]) != (b[i]["tp"], b[i]["fp"], b[i]["fn"]))
    L += ["", f"**噪声地板**：两次 BF16 在抽取集上有 {diff_samples} 条样本的槽位结果不同；`2b_bf16_b` 一行的 ΔF1 即为运行间波动幅度。"]

FIELDS = ["location_keywords", "layout_options", "max_rent", "furnish_type", "let_type", "available_from",
          "pets_allowed", "garden", "parking", "bills_included", "student_friendly", "families_allowed", "smokers_allowed", "dss_accepted"]
L += ["", "## 抽取集按字段的 F1 变化（百分点，只列有变化的字段）", ""]
for t in tags:
    r = ref_of(t)
    if not r or not PS.get((r, "extract")):
        continue
    a, b = PS[(r, "extract")], PS[(t, "extract")]
    rows = []
    for f in FIELDS:
        fa = f1(*[sum(a[i]["field"][f][j] for i in a) for j in range(3)])[0]
        fb = f1(*[sum(b[i]["field"][f][j] for i in b) for j in range(3)])[0]
        if abs(fb - fa) >= 0.001:
            rows.append(f"{f} {fa:.3f}→{fb:.3f} ({(fb-fa)*100:+.1f})")
    L.append(f"- `{t}`（对 {r}）：" + ("；".join(rows) if rows else "无变化"))
L += ["", "## 抽取集按 style_tag 的 F1 变化（百分点）", ""]
for t in tags:
    r = ref_of(t)
    if not r or not PS.get((r, "extract")):
        continue
    a, b = PS[(r, "extract")], PS[(t, "extract")]
    by = defaultdict(list)
    for i in a:
        for tg in a[i]["tags"]:
            by[tg].append(i)
    rows = [f"{tg} {(micro(b, ids)-micro(a, ids))*100:+.1f}" for tg, ids in sorted(by.items()) if abs(micro(b, ids) - micro(a, ids)) >= 0.001]
    L.append(f"- `{t}`：" + ("；".join(rows) if rows else "无变化"))
(OUT / "report.md").write_text("\n".join(L) + "\n", encoding="utf-8")
print("\n".join(L[:8 + len(tags)]))
