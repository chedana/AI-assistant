#!/bin/bash
# ══════════════════════════════════════════════════════════════════
#  全伦敦抓取启动脚本
#
#  用法：
#    bash start_crawl.sh              # 全量（~60-90 分钟）
#    bash start_crawl.sh resume       # 断点续传
#    bash start_crawl.sh test         # 测试（E1, E2，3页）
#    bash start_crawl.sh dry-run      # 只收集 URL，不爬详情
# ══════════════════════════════════════════════════════════════════

set -e
MODE=${1:-full}
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC}  $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

CRAWL_SCRIPT="$SCRIPT_DIR/crawl_london.py"
[ -f "$CRAWL_SCRIPT" ] || error "crawl_london.py not found"

echo ""
echo "══════════════════════════════════════════════"
echo "  London Rental Crawl  |  $(date '+%Y-%m-%d %H:%M:%S')"
echo "  Mode: $MODE"
echo "══════════════════════════════════════════════"
echo ""

case "$MODE" in
  full)
    info "Full London crawl (~363 queries, 60-90 min)"
    python "$CRAWL_SCRIPT" \
      --max-pages 42 \
      --workers 8 \
      --chunk-size 200 \
      --sleep-sec 0.5
    ;;
  resume)
    warn "Resuming previous run..."
    python "$CRAWL_SCRIPT" \
      --resume \
      --max-pages 42 \
      --workers 8 \
      --chunk-size 200 \
      --sleep-sec 0.5
    ;;
  test)
    warn "TEST MODE: E1, E2 only (3 pages)"
    python "$CRAWL_SCRIPT" \
      --districts E1,E2 \
      --max-pages 3 \
      --workers 4 \
      --chunk-size 50 \
      --sleep-sec 0.5
    ;;
  dry-run)
    info "DRY RUN: URL collection only"
    python "$CRAWL_SCRIPT" --dry-run --max-pages 42
    ;;
  *)
    error "Unknown mode: $MODE\nUsage: bash start_crawl.sh [full|resume|test|dry-run]"
    ;;
esac

if [ $? -eq 0 ]; then
    echo -e "\n${GREEN}✅ Done — $(date '+%H:%M:%S')${NC}"
else
    echo -e "\n${RED}❌ Failed${NC}"
    exit 1
fi
