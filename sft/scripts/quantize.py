"""用 llmcompressor 对 Qwen3.5 做训练后量化（PTQ），输出 vLLM 可直接加载的 compressed-tensors 格式。
在单独的虚拟环境中运行（见 scripts/run_quant.sh setup-quant），避免与推理环境的依赖冲突。

用法：
  python3 scripts/quantize.py --model Qwen/Qwen3.5-2B --method gptq --out /workspace/quant_models/2b_w4a16_gptq
  --method：rtn（W4A16 直接取整，无校准）| gptq（W4A16）| awq（W4A16 非对称）| fp8（FP8 动态，无校准）| int8（SmoothQuant + GPTQ W8A8）
  --calib：indomain（默认，取 data/train_v1.jsonl）| generic（通用对话数据 ultrachat_200k）
  --lora：微调后使用，先把 LoRA 合并进 BF16 权重再量化（Q4）
校准数据只取训练集，绝不使用测试集。
"""
import argparse, json, random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# 不量化的层：输出层、视觉部分、MTP 头、线性注意力层（Qwen3.5 混合注意力，社区量化配方的常见做法）
IGNORE = ["re:.*lm_head", "re:.*visual.*", "re:.*mtp.*", "re:.*linear_attn.*"]


def calib_texts(tok, kind, n, seed=0):
    rng = random.Random(seed)
    if kind == "indomain":
        system = (ROOT / "prompts/zeroshot_v1.txt").read_text()
        rows = [json.loads(l) for l in (ROOT / "data/train_v1.jsonl").open()]
        rows = rng.sample(rows, min(n, len(rows)))
        out = []
        for r in rows:
            user = f"{r['context']}\n\nUser message: {r['query']}" if r.get("context") else r["query"]
            ans = json.dumps(r["gold"], ensure_ascii=False, separators=(",", ":"))
            msgs = [{"role": "system", "content": system}, {"role": "user", "content": user},
                    {"role": "assistant", "content": ans}]
            out.append(tok.apply_chat_template(msgs, tokenize=False, enable_thinking=False))
        return out
    from datasets import load_dataset
    ds = load_dataset("HuggingFaceH4/ultrachat_200k", split="train_sft").shuffle(seed=seed).select(range(n))
    return [tok.apply_chat_template(x["messages"], tokenize=False) for x in ds]


def load_model(name):
    import transformers
    from transformers import AutoModelForCausalLM
    errs = []
    for cls_name in ("Qwen3_5ForConditionalGeneration", "AutoModelForImageTextToText"):
        cls = getattr(transformers, cls_name, None)
        if cls is None:
            continue
        try:
            return cls.from_pretrained(name, dtype="auto")
        except Exception as e:  # 记录后尝试下一种加载方式
            errs.append(f"{cls_name}: {e}")
    try:
        return AutoModelForCausalLM.from_pretrained(name, dtype="auto")
    except Exception as e:
        raise SystemExit("模型加载失败：\n" + "\n".join(errs + [f"AutoModelForCausalLM: {e}"]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--method", required=True, choices=["rtn", "gptq", "awq", "fp8", "int8"])
    ap.add_argument("--out", required=True)
    ap.add_argument("--calib", default="indomain", choices=["indomain", "generic"])
    ap.add_argument("--n_calib", type=int, default=256)
    ap.add_argument("--max_len", type=int, default=2048)
    ap.add_argument("--lora")
    a = ap.parse_args()

    from transformers import AutoProcessor, AutoTokenizer
    from llmcompressor import oneshot
    from llmcompressor.modifiers.quantization import GPTQModifier, QuantizationModifier

    tok = AutoTokenizer.from_pretrained(a.model)
    model = load_model(a.model)
    if a.lora:
        from peft import PeftModel
        model = PeftModel.from_pretrained(model, a.lora).merge_and_unload()

    if a.method == "rtn":
        recipe = QuantizationModifier(targets="Linear", scheme="W4A16", ignore=IGNORE)
    elif a.method == "fp8":
        recipe = QuantizationModifier(targets="Linear", scheme="FP8_DYNAMIC", ignore=IGNORE)
    elif a.method == "gptq":
        recipe = GPTQModifier(targets="Linear", scheme="W4A16", ignore=IGNORE)
    elif a.method == "awq":
        from llmcompressor.modifiers.awq import AWQModifier
        recipe = AWQModifier(targets=["Linear"], scheme="W4A16_ASYM", ignore=IGNORE)
    else:
        from llmcompressor.modifiers.smoothquant import SmoothQuantModifier
        recipe = [SmoothQuantModifier(smoothing_strength=0.8),
                  GPTQModifier(targets="Linear", scheme="W8A8", ignore=IGNORE)]

    kwargs = dict(model=model, recipe=recipe)
    if a.method in ("gptq", "awq", "int8"):
        from datasets import Dataset
        texts = calib_texts(tok, a.calib, a.n_calib)
        ds = Dataset.from_dict({"text": texts}).map(
            lambda x: tok(x["text"], max_length=a.max_len, truncation=True, add_special_tokens=False),
            remove_columns=["text"])
        kwargs.update(dataset=ds, max_seq_length=a.max_len, num_calibration_samples=len(texts))
    oneshot(**kwargs)

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(out, save_compressed=True)
    tok.save_pretrained(out)
    try:
        AutoProcessor.from_pretrained(a.model).save_pretrained(out)  # 视觉语言模型在 vLLM 中加载需要处理器配置
    except Exception as e:
        print("处理器配置未保存：", e)
    (out / "quant_info.json").write_text(json.dumps(vars(a), indent=1))
    print("已保存到", out)


if __name__ == "__main__":
    main()
