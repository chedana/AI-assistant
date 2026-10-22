#!/usr/bin/env bash
# Mac 端一键操作 RunPod。在项目根目录执行：  bash sft/scripts/runpod.sh <命令>
#
#   up "ssh root@IP -p 端口 -i ~/.ssh/id_ed25519"   新 Pod：上传 sft、装环境、进入终端（粘贴 RunPod 给的 SSH 命令）
#   up                                               同一个 Pod 再来一次（地址已记住）
#   push                                             只同步 Mac 上改过的代码和数据（秒级）
#   run "python3 scripts/xxx.py ..."                 在 Pod 上后台跑任务（断网/合盖不中断），并实时看日志
#   sh                                               打开 Pod 终端（已激活环境、在 sft 目录）
#   pull [目录...]                                   把结果拉回 Mac，默认 results logs
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SFT_LOCAL="$ROOT/sft"
REMOTE_PROJ=/workspace/AI-assistant
TARGET_FILE="$HOME/.runpod_target"
say() { printf '\n\033[1;36m[mac] %s\033[0m\n' "$*"; }
die() { printf '\n\033[1;31m%s\033[0m\n' "$*"; exit 1; }

load_target() {
  [[ -f "$TARGET_FILE" ]] || die "还没有 Pod 地址。先执行：bash sft/scripts/runpod.sh up \"<RunPod 的 SSH over exposed TCP 命令>\""
  read -r -a SSH_ARGS < "$TARGET_FILE"
}
rssh() { ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR \
             -o ServerAliveInterval=30 -o ConnectTimeout=15 "${SSH_ARGS[@]}" "$@"; }

upload() {
  say "上传 sft/（不含 listings_clean.jsonl、results、logs、训练产物）"
  COPYFILE_DISABLE=1 tar czf - -C "$ROOT" \
    --exclude='sft/data/listings_clean.jsonl' --exclude='__pycache__' --exclude='.DS_Store' \
    --exclude='sft/results' --exclude='sft/logs' --exclude='sft/outputs' --exclude='sft/checkpoints' \
    sft | rssh "mkdir -p $REMOTE_PROJ && tar xzf - -C $REMOTE_PROJ --no-same-owner --warning=no-unknown-keyword"
  echo "ok"
}

cmd="${1:-}"; shift || true
case "$cmd" in
  up)
    if [[ $# -ge 1 ]]; then
      s="$*"; s="${s#ssh }"
      [[ "$s" == *ssh.runpod.io* ]] && die "这是代理 SSH，不能传文件。请在 Connect 里复制 \"SSH over exposed TCP\" 那一行（形如 ssh root@1.2.3.4 -p 12345 -i ...）"
      s="${s/#\~/$HOME}"; s="${s// \~/ $HOME}"
      echo "$s" > "$TARGET_FILE"
    fi
    load_target
    say "连接 Pod：${SSH_ARGS[*]}"
    if ! rssh -o BatchMode=yes true 2>/dev/null; then
      KEY="$HOME/.ssh/id_ed25519"
      [[ -f "$KEY" ]] || ssh-keygen -t ed25519 -N "" -f "$KEY" -C "mac-runpod" >/dev/null
      die "连不上 Pod。若是第一次用：
  1) 把下面这行公钥加到 RunPod 网页 → Settings → SSH Public Keys：
$(cat "$KEY.pub")
  2) 加完后需要【重新 Deploy 一个 Pod】（公钥只在创建时注入），再执行 up。
若之前能连：Pod 可能还在启动，等 30 秒重试。"
    fi
    upload
    say "在 Pod 上装环境（首次约 5–10 分钟，之后几秒）"
    rssh 'bash -s' < "$SFT_LOCAL/scripts/runpod_setup.sh"
    say "进入 Pod 终端（输入 exit 回到 Mac）"
    rssh -t 'bash -l'
    ;;
  push) load_target; upload ;;
  sh)   load_target; rssh -t 'bash -l' ;;
  run)
    [[ $# -ge 1 ]] || die "用法：run \"python3 scripts/xxx.py ...\""
    load_target
    LOG="logs/run_$(date +%m%d_%H%M%S).log"
    rssh "source /workspace/env.sh && mkdir -p logs && nohup bash -c $(printf '%q' "$*") > $LOG 2>&1 & echo \"后台运行中，日志 $LOG（Ctrl+C 只停止查看，不停任务）\""
    rssh -t "cd $REMOTE_PROJ/sft && sleep 1 && tail -n +1 -f $LOG"
    ;;
  pull)
    load_target
    DIRS="${*:-results logs}"
    say "拉回：$DIRS → $SFT_LOCAL/"
    rssh "cd $REMOTE_PROJ/sft && tar czf - --ignore-failed-read $DIRS 2>/dev/null" | tar xzf - -C "$SFT_LOCAL"
    echo "ok"
    ;;
  *) sed -n '2,10p' "$0"; exit 1 ;;
esac
