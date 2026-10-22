"""用 vLLM 推理并测速（关闭思考模式，temperature 0）。先写预测文件，再测速，测速出错不影响预测。

基本用法（与零样本基线相同）：
  python3 scripts/infer.py --model Qwen/Qwen3.5-4B --test data/test_extract_v1.jsonl --out results/pred_zeroshot_extract.jsonl
量化实验用法（见 QUANT_INFERENCE_PLAN.md）：
  python3 scripts/infer.py --model Qwen/Qwen3.5-4B --quantization fp8 --test ... --out results/quant/4b_fp8_online_extract.jsonl \
      --n_latency 100 --gpu_mem 0.85
可选：--lora <adapter>、--kv_cache_dtype fp8、--prompt zeroshot_v1_compact、--n_latency 0（跳过测速）。
"""
import argparse, json, platform, statistics, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def user_message(rec):
    if rec.get("context"):
        return f"{rec['context']}\n\nUser message: {rec['query']}"
    return rec["query"]


def pct(xs, p):
    xs = sorted(xs)
    return round(xs[min(len(xs) - 1, int(round(p / 100 * (len(xs) - 1))))], 4) if xs else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--test", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--lora")
    ap.add_argument("--quantization", help="传给 vLLM，例如 fp8、bitsandbytes；预量化模型通常不需要填")
    ap.add_argument("--kv_cache_dtype", default="auto")
    ap.add_argument("--prompt", default="zeroshot_v1", help="prompts/ 下的文件名（不含 .txt）")
    ap.add_argument("--max_tokens", type=int, default=512)
    ap.add_argument("--n_latency", type=int, default=30, help="逐条测速的样本数，0 表示不测")
    ap.add_argument("--gpu_mem", type=float, help="gpu_memory_utilization，不填用 vLLM 默认值")
    a = ap.parse_args()

    import vllm
    from vllm import LLM, SamplingParams
    from vllm.lora.request import LoRARequest

    system = (ROOT / f"prompts/{a.prompt}.txt").read_text()
    kw = dict(model=a.model, enable_lora=bool(a.lora), max_model_len=4096, seed=0, kv_cache_dtype=a.kv_cache_dtype)
    if a.quantization:
        kw["quantization"] = a.quantization
    if a.gpu_mem:
        kw["gpu_memory_utilization"] = a.gpu_mem
    t_load = time.time()
    llm = LLM(**kw)
    load_s = time.time() - t_load
    tok = llm.get_tokenizer()
    recs = [json.loads(l) for l in open(a.test)]
    prompts = [tok.apply_chat_template([{"role": "system", "content": system},
                                        {"role": "user", "content": user_message(r)}],
                                       tokenize=False, add_generation_prompt=True, enable_thinking=False)
               for r in recs]
    sp = SamplingParams(temperature=0, max_tokens=a.max_tokens)
    lora = LoRARequest("adapter", 1, a.lora) if a.lora else None

    # 1) 批量推理并立即写出预测
    t0 = time.time()
    outs = llm.generate(prompts, sp, lora_request=lora)
    batch_s = time.time() - t0
    out_tokens = [len(o.outputs[0].token_ids) for o in outs]
    in_tokens = [len(o.prompt_token_ids) for o in outs]
    with open(a.out, "w") as f:
        for r, o, n in zip(recs, outs, out_tokens):
            f.write(json.dumps({"id": r["id"], "raw": o.outputs[0].text, "out_tokens": n}, ensure_ascii=False) + "\n")
    meta = {"model": a.model, "lora": a.lora, "quantization": a.quantization, "kv_cache_dtype": a.kv_cache_dtype,
            "prompt": a.prompt, "test": a.test, "n": len(recs), "temperature": 0, "max_tokens": a.max_tokens,
            "vllm": vllm.__version__, "host": platform.node(), "load_seconds": round(load_s, 1),
            "batch_seconds": round(batch_s, 2), "batch_output_tok_per_s": round(sum(out_tokens) / batch_s, 1),
            "mean_input_tokens": round(statistics.mean(in_tokens), 1), "mean_output_tokens": round(statistics.mean(out_tokens), 1)}
    meta_path = Path(a.out).with_suffix(".meta.json")
    meta_path.write_text(json.dumps(meta, indent=1))
    print(meta, flush=True)

    # 2) 逐条测速：预热 5 条，再测 n 条端到端；同样 n 条只生成 1 个 token 近似 TTFT
    if a.n_latency > 0:
        sub = prompts[: a.n_latency]
        for p in prompts[:5]:
            llm.generate([p], sp, lora_request=lora, use_tqdm=False)
        e2e, toks, ttft = [], [], []
        for p in sub:
            s = time.time(); o = llm.generate([p], sp, lora_request=lora, use_tqdm=False); e2e.append(time.time() - s)
            toks.append(len(o[0].outputs[0].token_ids))
        sp1 = SamplingParams(temperature=0, max_tokens=1)
        for p in sub:
            s = time.time(); llm.generate([p], sp1, lora_request=lora, use_tqdm=False); ttft.append(time.time() - s)
        tpot = [(e - t) / max(n - 1, 1) for e, t, n in zip(e2e, ttft, toks)]
        meta.update({"latency_n": len(sub), "latency_p50_s": pct(e2e, 50), "latency_p90_s": pct(e2e, 90),
                     "ttft_p50_s": pct(ttft, 50), "tpot_p50_ms": round(pct(tpot, 50) * 1000, 2),
                     "latency_mean_output_tokens": round(statistics.mean(toks), 1)})
        meta_path.write_text(json.dumps(meta, indent=1))
        print({k: meta[k] for k in meta if k.startswith(("latency", "ttft", "tpot"))}, flush=True)


if __name__ == "__main__":
    main()
