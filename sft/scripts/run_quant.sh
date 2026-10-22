#!/usr/bin/env bash
# 量化推理对照实验一键运行（设计见 QUANT_INFERENCE_PLAN.md）。在 /workspace/AI-assistant/sft 下执行。
# 用法：bash scripts/run_quant.sh <阶段>
#   q1             2B：BF16 两次（噪声地板，兼 2B 零样本基线）、在线 FP8、bitsandbytes NF4、FP8 KV cache
#   setup-quant    建量化专用虚拟环境 /workspace/venv-quant（只需一次）
#   q2-quantize    离线量化 2B：FP8、INT8（SmoothQuant+GPTQ）、W4A16 的 RTN / GPTQ / AWQ / GPTQ（通用校准）
#   q2             评测 q2-quantize 产出的模型
#   q3             紧凑输出：BF16 与指定的量化配置（第二个参数，默认 2b_fp8_online）
#   report         汇总报告 results/quant/report.md
# 建议放后台运行：nohup bash scripts/run_quant.sh q1 > results/quant/run_q1.log 2>&1 &
set -uo pipefail
cd "$(dirname "$0")/.."
OUT=results/quant; QM=/workspace/quant_models
mkdir -p "$OUT" "$QM"
export HF_HOME=${HF_HOME:-/workspace/hf_cache}
FAILED=()

run() {  # run <tag> <model> [infer.py 的其他参数...]
  local tag=$1 model=$2; shift 2
  echo "===== $tag ($(date +%H:%M:%S)) ====="
  if [[ -f "$OUT/${tag}_extract.meta.json" && -f "$OUT/${tag}_intent.meta.json" ]]; then echo "已存在，跳过"; return; fi
  python3 scripts/infer.py --model "$model" --test data/test_extract_v1.jsonl --out "$OUT/${tag}_extract.jsonl" \
      --n_latency 50 --gpu_mem 0.85 "$@" > "$OUT/${tag}_extract.log" 2>&1 \
    && python3 scripts/infer.py --model "$model" --test data/test_intent_v1.jsonl --out "$OUT/${tag}_intent.jsonl" \
      --n_latency 0 --gpu_mem 0.85 "$@" > "$OUT/${tag}_intent.log" 2>&1 \
    && python3 scripts/evaluate.py --test data/test_extract_v1.jsonl --pred "$OUT/${tag}_extract.jsonl" --name "${tag}_extract" --outdir "$OUT" > /dev/null \
    && python3 scripts/evaluate.py --test data/test_intent_v1.jsonl --pred "$OUT/${tag}_intent.jsonl" --name "${tag}_intent" --outdir "$OUT" > /dev/null \
    && echo "完成" || { echo "失败：$tag，见 $OUT/${tag}_*.log 末尾"; FAILED+=("$tag"); }
}

quant() {  # quant <tag> <base model> <method> [quantize.py 的其他参数...]
  local tag=$1 model=$2 method=$3; shift 3
  echo "===== 量化 $tag ($(date +%H:%M:%S)) ====="
  if [[ -f "$QM/$tag/quant_info.json" ]]; then echo "已存在，跳过"; return; fi
  /workspace/venv-quant/bin/python scripts/quantize.py --model "$model" --method "$method" --out "$QM/$tag" "$@" \
      > "$OUT/quantize_${tag}.log" 2>&1 && echo "完成" || { echo "失败：$tag，见 $OUT/quantize_${tag}.log"; FAILED+=("q:$tag"); }
}

case "${1:-}" in
  q1)
    run 2b_bf16_a     Qwen/Qwen3.5-2B
    run 2b_bf16_b     Qwen/Qwen3.5-2B
    run 2b_fp8_online Qwen/Qwen3.5-2B --quantization fp8
    run 2b_nf4_bnb    Qwen/Qwen3.5-2B --quantization bitsandbytes
    run 2b_bf16_kvfp8 Qwen/Qwen3.5-2B --kv_cache_dtype fp8
    ;;
  setup-quant)
    [[ -x /workspace/venv-quant/bin/python ]] || python3 -m venv /workspace/venv-quant
    /workspace/venv-quant/bin/pip install -q -U pip
    /workspace/venv-quant/bin/pip install -q llmcompressor datasets peft
    /workspace/venv-quant/bin/python -c "import llmcompressor, transformers, torch; print('llmcompressor', llmcompressor.__version__, '| transformers', transformers.__version__, '| torch', torch.__version__, torch.cuda.is_available())"
    ;;
  q2-quantize)
    quant 2b_fp8_offline        Qwen/Qwen3.5-2B fp8
    quant 2b_int8               Qwen/Qwen3.5-2B int8
    quant 2b_w4a16_rtn          Qwen/Qwen3.5-2B rtn
    quant 2b_w4a16_gptq         Qwen/Qwen3.5-2B gptq
    quant 2b_w4a16_awq          Qwen/Qwen3.5-2B awq
    quant 2b_w4a16_gptq_generic Qwen/Qwen3.5-2B gptq --calib generic
    ;;
  q2)
    for t in 2b_fp8_offline 2b_int8 2b_w4a16_rtn 2b_w4a16_gptq 2b_w4a16_awq 2b_w4a16_gptq_generic; do
      [[ -d "$QM/$t" ]] && run "$t" "$QM/$t" || echo "跳过 $t（尚未量化或量化失败）"
    done
    ;;
  q3)
    best=${2:-2b_fp8_online}
    run 2b_bf16_compact Qwen/Qwen3.5-2B --prompt zeroshot_v1_compact
    model=$(python3 -c "import json;print(json.load(open('$OUT/${best}_extract.meta.json'))['model'])")
    q=$(python3 -c "import json;print(json.load(open('$OUT/${best}_extract.meta.json')).get('quantization') or '')")
    kv=$(python3 -c "import json;print(json.load(open('$OUT/${best}_extract.meta.json')).get('kv_cache_dtype') or 'auto')")
    args=(--prompt zeroshot_v1_compact --kv_cache_dtype "$kv"); [[ -n "$q" ]] && args+=(--quantization "$q")
    run "${best}_compact" "$model" "${args[@]}"
    ;;
  report)
    python3 scripts/quant_report.py
    ;;
  *) sed -n '2,11p' "$0"; exit 1 ;;
esac
[[ ${#FAILED[@]} -gt 0 ]] && echo "失败的配置：${FAILED[*]}" || echo "本阶段全部完成"
