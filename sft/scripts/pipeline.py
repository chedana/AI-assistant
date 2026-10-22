"""阶段 3 质检流水线（D7：两家各生成一半，交叉盲审，合并）。

目录约定（以 data/pilot 为例）：
  tasks_{claude,gpt}.jsonl         make_tasks.py 生成的任务（含 gold）
  gen_{claude,gpt}.jsonl           各自生成的 query：{"task_id","query","location_keywords"}
  review_input_for_{gpt,claude}.jsonl  prepare 生成：只有 task_id 和 query，交给另一家盲审
  review_by_{gpt,claude}.jsonl     盲审结果：{"task_id","intent","constraints"}
  accepted.jsonl / rejected.jsonl / report.md   merge 输出

用法：
  python3 scripts/pipeline.py prepare data/pilot   # 生成双方都完成后执行
  python3 scripts/pipeline.py merge data/pilot     # 双方盲审都完成后执行
  python3 scripts/pipeline.py precheck data/pilot claude   # 只做本方格式自检
"""
import difflib, json, re, sys
from collections import Counter
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "schema.json").read_text())
OTHER = {"claude": "gpt", "gpt": "claude"}
MODEL_NAME = {"claude": "Claude Opus 5.5 (claude.ai)", "gpt": "GPT via Codex"}
PROMPT_VERSION = {"search": "gen_search_v1", "specific_qa": "gen_intent_v1", "compare": "gen_intent_v1",
                  "chitchat": "gen_intent_v1", "followup": "gen_intent_v1", "softpref": "gen_softpref_v2"}
NON_SEARCH = {"specific_qa", "compare", "chitchat"}


def kind_of(task):
    return task.get("kind", "search")


def words(text):
    return re.findall(r"[a-z0-9']+", text.lower())


def ngram_overlap(phrase, text, n=3):
    a, b = words(phrase), words(text)
    grams = {tuple(b[i:i + n]) for i in range(len(b) - n + 1)}
    return [" ".join(a[i:i + n]) for i in range(len(a) - n + 1) if tuple(a[i:i + n]) in grams]
DUP_THRESHOLD = 0.9


def load(path):
    if not path.exists():
        return {}
    out = {}
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.strip():
            try:
                d = json.loads(line)
            except json.JSONDecodeError as e:
                raise SystemExit(f"{path.name} 第 {n} 行不是合法 JSON：{e}")
            out[d["task_id"]] = d
    return out


def format_problems(task, gen):
    """不依赖审核方的检查：结构、英文、地点原样。"""
    p = []
    q = gen.get("query")
    kws = gen.get("location_keywords")
    if not isinstance(q, str) or not q.strip():
        return ["query 为空"]
    if not isinstance(kws, list) or not all(isinstance(k, str) and k for k in kws):
        return ["location_keywords 格式错误"]
    if any(ord(c) > 127 and c not in "£’‘“”–—" for c in q):
        p.append("query 含非英文字符")
    kind = kind_of(task)
    if kind in NON_SEARCH:
        return p + (["非 Search 样本不应有地点片段"] if kws else [])
    loc = task["conditions"].get("location")
    if loc and len(kws) != 1:
        p.append(f"应有 1 个地点片段，实际 {len(kws)}")
    if not loc and kws:
        p.append("没有地点条件却写了地点")
    for k in kws:
        if k not in q:
            p.append(f"地点片段不是 query 的原样子串：{k!r}")
    if loc and "loc_typo" in task["style_tags"] and kws:
        src = loc["source_value"].lower().replace(" station", "")
        if kws[0].lower() == src:
            p.append("要求拼写错误但地名拼写正确")
    if kind == "softpref":
        sp, w = gen.get("soft_preferences"), gen.get("soft_pref_weights")
        if not isinstance(sp, list) or len(sp) != task["n_soft"]:
            p.append(f"软偏好数量应为 {task['n_soft']}")
        elif not isinstance(w, list) or len(w) != len(sp) or any(x not in (1, 2) for x in w):
            p.append("soft_pref_weights 与软偏好不对应或取值不是 1/2")
        else:
            for x in sp:
                if x not in q:
                    p.append(f"软偏好不是 query 的原样子串：{x!r}")
                ov = ngram_overlap(x, task["description"])
                if ov:
                    p.append(f"软偏好与描述有 3 个以上连续相同的词：{ov[0]!r}")
    return p


def build_gold(task, gen):
    if kind_of(task) in NON_SEARCH:
        return json.loads(json.dumps(task["gold"]))
    c = json.loads(json.dumps(task["gold_constraints_without_location"]))
    c["location_keywords"] = list(gen["location_keywords"])
    soft = list(gen.get("soft_preferences") or []) if kind_of(task) == "softpref" else []
    return {"intent": "Search", "constraints": c, "soft_preferences": soft}


def norm(field, v):
    if field == "location_keywords":
        return sorted(x.strip().lower() for x in v or [])
    if field == "layout_options":
        return sorted(json.dumps(o, sort_keys=True) for o in v or [])
    if field == "max_rent" and v:
        return (float(v["value"]), v["period"])
    return v


def compare(gold, review, kind="search"):
    """返回 (丢弃原因, 提示)。软偏好只在数量上判定，措辞差异只作提示。"""
    diffs, warns = [], []
    if review.get("intent") != gold["intent"]:
        diffs.append(f"intent: gold={gold['intent']} review={review.get('intent')}")
    rc = review.get("constraints") or {}
    for f, gv in gold["constraints"].items():
        if norm(f, gv) != norm(f, rc.get(f)):
            diffs.append(f"{f}: gold={json.dumps(gv, ensure_ascii=False)} review={json.dumps(rc.get(f), ensure_ascii=False)}")
    if "soft_preferences" in review:
        rs, gs = review.get("soft_preferences") or [], gold["soft_preferences"]
        if bool(rs) != bool(gs):
            diffs.append(f"soft_preferences: gold={json.dumps(gs, ensure_ascii=False)} review={json.dumps(rs, ensure_ascii=False)}")
        elif sorted(x.lower() for x in rs) != sorted(x.lower() for x in gs):
            warns.append(f"软偏好措辞不同：gold={gs} review={rs}")
    return diffs, warns


def precheck(d, g):
    tasks, gens = load(d / f"tasks_{g}.jsonl"), load(d / f"gen_{g}.jsonl")
    bad = 0
    for tid, t in tasks.items():
        if tid not in gens:
            print(tid, "缺少生成结果"); bad += 1; continue
        p = format_problems(t, gens[tid])
        if not p:
            try:
                jsonschema.validate(build_gold(t, gens[tid]), SCHEMA)
            except jsonschema.ValidationError as e:
                p = [f"schema: {e.message}"]
        if p:
            bad += 1; print(tid, p, gens[tid]["query"])
    print(f"{g}: {len(tasks)} 个任务，格式问题 {bad} 条")


def prepare(d):
    for g in ("claude", "gpt"):
        gens = load(d / f"gen_{g}.jsonl")
        tasks = load(d / f"tasks_{g}.jsonl")
        with (d / f"review_input_for_{OTHER[g]}.jsonl").open("w") as f:
            for tid in sorted(gens):
                f.write(json.dumps({"task_id": tid, "context": tasks[tid].get("context"),
                                    "query": gens[tid]["query"]}, ensure_ascii=False) + "\n")
        print(f"review_input_for_{OTHER[g]}.jsonl: {len(gens)} 条")


def merge(d):
    accepted, rejected = [], []
    reasons, by_gen, style_count, kind_count = Counter(), Counter(), Counter(), Counter()
    for g in ("claude", "gpt"):
        tasks = load(d / f"tasks_{g}.jsonl")
        gens = load(d / f"gen_{g}.jsonl")
        reviews = load(d / f"review_by_{OTHER[g]}.jsonl")
        for tid, t in tasks.items():
            kind = kind_of(t)
            rec = {"id": tid, "kind": kind,
                   "source_listing_id": t.get("listing_id") or t.get("condition_listing_id") or t.get("source_listing_ids"),
                   "context_listing_ids": t.get("source_listing_ids") if kind != "softpref" else None,
                   "split": t["split"], "context": t.get("context"),
                   "query": None, "gold": None, "style_tags": t.get("style_tags", []), "soft_pref_weights": None,
                   "generator": g, "gen_model": MODEL_NAME[g], "review_model": MODEL_NAME[OTHER[g]],
                   "prompt_version": PROMPT_VERSION[kind]}
            gen = gens.get(tid)
            if not gen:
                reasons["缺少生成结果"] += 1; rejected.append({**rec, "reasons": ["缺少生成结果"]}); continue
            rec["query"] = gen["query"]
            if kind == "softpref":
                rec["soft_pref_weights"] = gen.get("soft_pref_weights")
            p = format_problems(t, gen)
            if not p:
                rec["gold"] = build_gold(t, gen)
                try:
                    jsonschema.validate(rec["gold"], SCHEMA)
                except jsonschema.ValidationError as e:
                    p = [f"schema: {e.message}"]
            if not p:
                r = reviews.get(tid)
                if r is None:
                    p = ["缺少盲审结果"]
                else:
                    p, w = compare(rec["gold"], r, kind)
                    if w:
                        rec["review_warnings"] = w
            if p:
                for x in p:
                    reasons[x.split(":")[0]] += 1
                by_gen[(g, "rejected")] += 1
                rejected.append({**rec, "reasons": p})
            else:
                by_gen[(g, "accepted")] += 1
                accepted.append(rec)
    # 去重：字符级相似度 > 0.9 只保留第一条
    kept = []
    for rec in accepted:
        if any(difflib.SequenceMatcher(None, rec["query"].lower(), k["query"].lower()).ratio() > DUP_THRESHOLD for k in kept):
            reasons["近似重复"] += 1
            rejected.append({**rec, "reasons": ["近似重复"]})
        else:
            kept.append(rec)
    for rec in kept:
        style_count.update(rec["style_tags"] or ["(none)"])
        kind_count[rec["kind"]] += 1
    for name, rows in (("accepted", kept), ("rejected", rejected)):
        with (d / f"{name}.jsonl").open("w") as f:
            for rec in rows:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    total = len(kept) + len(rejected)
    L = [f"# 质检报告：{d.name}", "",
         f"通过 {len(kept)} / {total}（{len(kept)/max(total,1):.0%}）", "",
         "| 生成方 | 通过 | 丢弃 |", "| --- | ---: | ---: |"]
    for g in ("claude", "gpt"):
        L.append(f"| {g} | {by_gen[(g,'accepted')]} | {by_gen[(g,'rejected')]} |")
    L += ["", "## 通过样本的类型", "", "| 类型 | 条数 |", "| --- | ---: |"]
    L += [f"| {k} | {v} |" for k, v in kind_count.most_common()]
    L += ["", "## 丢弃原因（按字段）", "", "| 原因 | 次数 |", "| --- | ---: |"]
    L += [f"| {k} | {v} |" for k, v in reasons.most_common()]
    L += ["", "## 通过样本的风格标签", "", "| tag | 条数 |", "| --- | ---: |"]
    L += [f"| {k} | {v} |" for k, v in style_count.most_common()]
    warned = [r for r in kept if r.get("review_warnings")]
    if warned:
        L += ["", "## 通过但有提示的样本", ""]
        for rec in warned:
            L.append(f"- `{rec['id']}` {rec['query']!r}")
            L += [f"  - {x}" for x in rec["review_warnings"]]
    L += ["", "## 丢弃样本明细", ""]
    for rec in rejected:
        L.append(f"- `{rec['id']}`（{rec['generator']}）{rec['query']!r}")
        L += [f"  - {x}" for x in rec["reasons"]]
    (d / "report.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L[:12]))


if __name__ == "__main__":
    cmd, d = sys.argv[1], ROOT / sys.argv[2]
    {"prepare": lambda: prepare(d), "merge": lambda: merge(d),
     "precheck": lambda: precheck(d, sys.argv[3])}[cmd]()
