"""阶段 5/8：用 vLLM 跑模型推理（关闭思考模式，temperature=0），输出预测 jsonl。

用法（RunPod 上）：
  python3 scripts/infer.py --model <HF 模型名或本地路径> --test data/test_extract_v1.jsonl --out results/pred_zeroshot_extract.jsonl
  可加 --lora <adapter 路径> 评测微调模型。基座模型为 Qwen/Qwen3.5-4B。
"""
import argparse, json, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SYSTEM = (ROOT / "prompts/zeroshot_v1.txt").read_text()


def user_message(rec):
    if rec.get("context"):
        return f"{rec['context']}\n\nUser message: {rec['query']}"
    return rec["query"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--test", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--lora")
    ap.add_argument("--max_tokens", type=int, default=512)
    a = ap.parse_args()
    from vllm import LLM, SamplingParams
    from vllm.lora.request import LoRARequest
    llm = LLM(model=a.model, enable_lora=bool(a.lora), max_model_len=4096, seed=0)
    tok = llm.get_tokenizer()
    recs = [json.loads(l) for l in open(a.test)]
    prompts = [tok.apply_chat_template([{"role": "system", "content": SYSTEM},
                                        {"role": "user", "content": user_message(r)}],
                                       tokenize=False, add_generation_prompt=True, enable_thinking=False)
               for r in recs]
    sp = SamplingParams(temperature=0, max_tokens=a.max_tokens)
    lora = LoRARequest("adapter", 1, a.lora) if a.lora else None
    t0 = time.time()
    outs = llm.generate(prompts, sp, lora_request=lora)
    total = time.time() - t0
    # 单条延迟：逐条再跑 30 条测 p50
    lat = []
    for p in prompts[:30]:
        s = time.time(); llm.generate([p], sp, lora_request=lora, use_tqdm=False); lat.append(time.time() - s)
    with open(a.out, "w") as f:
        for r, o in zip(recs, outs):
            f.write(json.dumps({"id": r["id"], "raw": o.outputs[0].text}, ensure_ascii=False) + "\n")
    meta = {"model": a.model, "lora": a.lora, "test": a.test, "n": len(recs), "batch_seconds": round(total, 2),
            "latency_p50_s": round(sorted(lat)[len(lat) // 2], 3), "prompt": "zeroshot_v1", "temperature": 0}
    Path(a.out).with_suffix(".meta.json").write_text(json.dumps(meta, indent=1))
    print(meta)


if __name__ == "__main__":
    main()
