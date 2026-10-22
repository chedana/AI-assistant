#!/usr/bin/env bash
# 在 RunPod 上执行（由 Mac 端 runpod.sh 自动通过 SSH 调用，一般不用手动跑）。
# 可重复执行：已装好的自动跳过。不依赖 GitHub。
set -euo pipefail
WS=/workspace
SFT="$WS/AI-assistant/sft"
VENV="$WS/venv"
MODELS="${MODELS:-Qwen/Qwen3.5-2B}"
say() { printf '\n\033[1;32m==> %s\033[0m\n' "$*"; }

say "1/5 显卡"
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
df -h "$WS" | tail -1 | awk '{print "/workspace 剩余空间:", $4}'

say "2/5 系统组件"
if ! python3 -c "import ensurepip" >/dev/null 2>&1 || ! command -v tmux >/dev/null; then
  apt-get update -qq
  PYV=$(python3 -c 'import sys;print(f"{sys.version_info.major}.{sys.version_info.minor}")')
  DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "python${PYV}-venv" tmux >/dev/null
fi
echo ok

say "3/5 Python 环境（推理 + LoRA 训练，一次装齐）"
[[ -x "$VENV/bin/python" ]] || python3 -m venv "$VENV"
source "$VENV/bin/activate"
if ! python -c "import vllm, peft, trl, datasets, jsonschema" >/dev/null 2>&1; then
  echo "下面会逐行显示正在下载/安装的包（vllm、torch 较大，单个可能停留 1–2 分钟属正常）"
  pip install -U pip 2>&1 | grep -E "^(Collecting|Downloading|Installing|Successfully)" || true
  pip install vllm jsonschema peft trl datasets accelerate 2>&1 \
    | grep --line-buffered -E "^(Collecting|  Downloading|Downloading|Installing|Successfully|ERROR|error)" \
    | while IFS= read -r l; do printf '[%s] %s\n' "$(date +%H:%M:%S)" "$l"; done
  python -c "import vllm, peft, trl" || { echo "安装失败，往上看 ERROR 行"; exit 1; }
fi
python -c "import vllm, torch, transformers, peft, trl; print('vllm', vllm.__version__, '| torch', torch.__version__, '| transformers', transformers.__version__, '| peft', peft.__version__, '| trl', trl.__version__, '| cuda', torch.cuda.is_available())"

say "4/5 终端自动进入环境"
cat > "$WS/env.sh" <<'ENV'
source /workspace/venv/bin/activate
export HF_HOME=/workspace/hf_cache
cd /workspace/AI-assistant/sft 2>/dev/null || true
ENV
grep -q "/workspace/env.sh" ~/.bashrc 2>/dev/null || echo '[ -f /workspace/env.sh ] && source /workspace/env.sh' >> ~/.bashrc
mkdir -p "$SFT/results" "$SFT/logs"
echo "以后不管是 SSH 还是网页终端，打开就已激活环境并在 sft 目录"

say "5/5 后台预下载模型（不阻塞，可以直接开始干活）"
export HF_HOME=$WS/hf_cache
for m in $MODELS; do
  nohup python -c "from huggingface_hub import snapshot_download as s; s('$m')" > "$SFT/logs/download_${m//\//_}.log" 2>&1 &
  echo "  $m → logs/download_${m//\//_}.log"
done
say "环境就绪"
