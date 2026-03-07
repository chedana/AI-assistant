"""
crawl_london.py
---------------
全伦敦房源抓取脚本，按 postcode district/sector 分片搜索。

目录结构：
  rent-chatbot/
    backend/
    frontend/
    crawler/          ← 这里
      crawl_london.py
      london_postcodes.py
      london_regions.py
      geo_utils.py
      start_crawl.sh

特性：
  - 363 个 search query（23 个热门 district 细分到 sector）
  - 每个 query 最多 42 页 × 25 条 = 1050 条，不会被截断
  - 全局去重
  - 断点续传（每个 query 的 URL 单独保存）
  - 分片爬取详情（chunk_size=200，workers=8）
  - 自动注入 listing_id + discovery_paths

用法：
  python crawl_london.py                         # 全量
  python crawl_london.py --resume                # 断点续传
  python crawl_london.py --districts E1,E2,SW1V  # 只跑指定 district
  python crawl_london.py --dry-run               # 只收集 URL，不爬详情
  python crawl_london.py --max-pages 5           # 测试用

输出：
  crawler/artifacts/runs/{run_id}/
    query_urls/            每个 query 的 URL（断点续传用）
    deduped_urls.txt       全局去重后的 listing URL
    chunk_results/         分片爬取结果
    properties_raw.jsonl   合并原始结果
    properties_final.jsonl 注入 listing_id + discovery_paths 的最终结果
    summary.json           统计报告
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

# ── 路径设置 ──────────────────────────────────────────────────────
# 所有依赖（batch_crawl.py, get_urls.py, test_vauxhall_probe.py）
# 都放在 crawler/ 目录内，完全自包含，不依赖外部路径
CRAWLER_DIR  = Path(__file__).parent.resolve()   # crawler/
PROJECT_ROOT = CRAWLER_DIR.parent.resolve()      # AI-assistant/

sys.path.insert(0, str(CRAWLER_DIR))

ARTIFACTS_DIR = CRAWLER_DIR / "artifacts"
ARTIFACTS_DIR.mkdir(exist_ok=True)

from london_postcodes import get_search_queries

MAX_PAGES     = 42
PER_PAGE      = 25
CHUNK_SIZE    = 200
SLEEP_SEC     = 0.5
CRAWL_WORKERS = 8


# ══════════════════════════════════════════════════════════════════
# 工具函数
# ══════════════════════════════════════════════════════════════════

def extract_property_id(url: str) -> str:
    m = re.search(r"/properties/(\d+)", url or "")
    return m.group(1) if m else ""

def normalize_url(url: str) -> str:
    pid = extract_property_id(url)
    return f"https://www.rightmove.co.uk/properties/{pid}#/?channel=RES_LET" if pid else ""

def listing_id(url: str) -> str:
    pid = extract_property_id(url)
    return f"rightmove:{pid}" if pid else ""

def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


# ══════════════════════════════════════════════════════════════════
# Step 1 — 收集 URL
# ══════════════════════════════════════════════════════════════════

def collect_urls_for_query(
    query: str,
    out_file: Path,
    max_pages: int,
    location_cache: dict,
    cache_path: Path,
) -> list[str]:
    from get_urls import resolve_with_typeahead, collect_pages_parallel, build_rightmove_search_url

    if query in location_cache:
        resolved = location_cache[query]
    else:
        try:
            result = resolve_with_typeahead(
                search_location=query,
                radius=0.0,
                verify_final_url=True,
                prefer_region=False,
            )
            if not result.get("location_identifier"):
                print(f"   [WARN] Could not resolve: {query}")
                return []
            resolved = {
                "location_identifier":         result["location_identifier"],
                "display_location_identifier": result.get("display_location_identifier"),
            }
            location_cache[query] = resolved
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(location_cache, f, ensure_ascii=False, indent=2)
            time.sleep(0.15)
        except Exception as e:
            print(f"   [ERROR] resolve {query!r}: {e}")
            return []

    search_url = build_rightmove_search_url(
        search_location=query,
        radius=0.0,
        include_let_agreed=True,
        sort_type=6,
        location_identifier=resolved["location_identifier"],
        display_location_identifier=resolved.get("display_location_identifier"),
    )

    urls = collect_pages_parallel(
        search_url=search_url,
        start_page=0,
        end_page=max_pages,
        per_page=PER_PAGE,
        workers=1,
    )

    clean_urls = [normalize_url(u) for u in urls if normalize_url(u)]
    with open(out_file, "w", encoding="utf-8") as f:
        for u in clean_urls:
            f.write(u + "\n")
    return clean_urls


def step1_collect_all_urls(
    queries: list[dict],
    run_dir: Path,
    max_pages: int,
    resume: bool,
) -> tuple[dict, dict]:
    query_urls_dir = run_dir / "query_urls"
    query_urls_dir.mkdir(exist_ok=True)

    cache_path = ARTIFACTS_DIR / "postcode_location_cache.json"
    location_cache = {}
    if cache_path.exists():
        with open(cache_path, encoding="utf-8") as f:
            location_cache = json.load(f)
    print(f"   Location cache: {len(location_cache)} entries")

    key_to_url:   dict[str, str]       = {}
    key_to_paths: dict[str, list[str]] = {}
    failed_queries: list[str]          = []
    total = len(queries)

    for i, q in enumerate(queries, 1):
        query = q["query"]
        slug  = slugify(query)
        out_file = query_urls_dir / f"{slug}.txt"

        if resume and out_file.exists() and out_file.stat().st_size > 0:
            with open(out_file) as f:
                urls = [l.strip() for l in f if l.strip()]
            print(f"[{i:03d}/{total}] SKIP {query} ({len(urls)} cached)")
        else:
            print(f"[{i:03d}/{total}] {query} ...", end=" ", flush=True)
            urls = collect_urls_for_query(query, out_file, max_pages, location_cache, cache_path)
            print(f"{len(urls)} URLs")
            if not urls:
                failed_queries.append(query)

        for url in urls:
            lid = listing_id(url)
            if not lid:
                continue
            if lid not in key_to_url:
                key_to_url[lid] = url
            if lid not in key_to_paths:
                key_to_paths[lid] = []
            if query not in key_to_paths[lid]:
                key_to_paths[lid].append(query)

    deduped_file = run_dir / "deduped_urls.txt"
    with open(deduped_file, "w", encoding="utf-8") as f:
        for url in key_to_url.values():
            f.write(url + "\n")

    with open(run_dir / "key_to_paths.json", "w", encoding="utf-8") as f:
        json.dump(key_to_paths, f, ensure_ascii=False, indent=2)

    if failed_queries:
        with open(run_dir / "failed_queries.txt", "w", encoding="utf-8") as f:
            for q in failed_queries:
                f.write(q + "\n")
        print(f"   Failed queries:  {len(failed_queries)} → {run_dir}/failed_queries.txt")

    print(f"\n   Unique listings: {len(key_to_url):,}")
    print(f"   → {deduped_file}")
    return key_to_url, key_to_paths


# ══════════════════════════════════════════════════════════════════
# Load step 1 results from disk  (used when starting at step 2 or 3)
# ══════════════════════════════════════════════════════════════════

def load_step1_results(run_dir: Path) -> tuple[dict, dict]:
    deduped = run_dir / "deduped_urls.txt"
    paths_file = run_dir / "key_to_paths.json"

    if not deduped.exists():
        print(f"[ERROR] {deduped} not found — run step 1 first.")
        sys.exit(1)

    key_to_url: dict[str, str] = {}
    with open(deduped, encoding="utf-8") as f:
        for line in f:
            url = line.strip()
            if url:
                lid = listing_id(url)
                if lid:
                    key_to_url[lid] = url

    key_to_paths: dict[str, list[str]] = {}
    if paths_file.exists():
        with open(paths_file, encoding="utf-8") as f:
            key_to_paths = json.load(f)

    print(f"   Loaded {len(key_to_url):,} URLs from {deduped.name}")
    return key_to_url, key_to_paths


# ══════════════════════════════════════════════════════════════════
# Step 2 — 分片爬取详情
# ══════════════════════════════════════════════════════════════════

def step2_crawl_details(key_to_url: dict, run_dir: Path) -> Path:
    from batch_crawl import crawl_urls

    urls = list(key_to_url.values())
    if not urls:
        print("   No URLs to crawl.")
        return run_dir / "properties_raw.jsonl"

    chunk_dir = run_dir / "chunk_results"
    chunk_dir.mkdir(exist_ok=True)
    chunks = [urls[i:i+CHUNK_SIZE] for i in range(0, len(urls), CHUNK_SIZE)]
    print(f"   {len(urls):,} listings → {len(chunks)} chunks (workers={CRAWL_WORKERS})")

    total_ok = total_fail = skipped = 0
    all_failed_urls: list[str] = []

    for i, chunk_urls in enumerate(chunks):
        chunk_file = chunk_dir / f"chunk_{i:03d}.jsonl"

        if chunk_file.exists() and chunk_file.stat().st_size > 0:
            n = sum(1 for _ in open(chunk_file))
            print(f"   [chunk {i+1:03d}/{len(chunks)}] SKIP ({n} records)")
            skipped += 1
            total_ok += n
            continue

        print(f"   [chunk {i+1:03d}/{len(chunks)}] {len(chunk_urls)} listings...", end=" ", flush=True)
        ok, fail, failed = crawl_urls(
            urls=chunk_urls,
            out_jsonl=str(chunk_file),
            source_name="rightmove",
            sleep_sec=SLEEP_SEC,
            workers=CRAWL_WORKERS,
        )
        total_ok += ok
        total_fail += fail
        all_failed_urls.extend(failed)
        print(f"OK={ok} FAIL={fail}")

    raw_jsonl = run_dir / "properties_raw.jsonl"
    print(f"   Merging → {raw_jsonl.name}")
    with open(raw_jsonl, "w", encoding="utf-8") as fout:
        for i in range(len(chunks)):
            cf = chunk_dir / f"chunk_{i:03d}.jsonl"
            if cf.exists():
                for line in open(cf, encoding="utf-8"):
                    line = line.strip()
                    if line:
                        fout.write(line + "\n")

    if all_failed_urls:
        failed_file = run_dir / "failed_urls.txt"
        with open(failed_file, "w", encoding="utf-8") as f:
            for u in all_failed_urls:
                f.write(u + "\n")
        print(f"   Failed URLs:  {len(all_failed_urls)} → {failed_file}")

    print(f"   Done: OK={total_ok:,} FAIL={total_fail} SKIPPED={skipped}")
    return raw_jsonl


# ══════════════════════════════════════════════════════════════════
# Step 3 — 注入 listing_id + discovery_paths
# ══════════════════════════════════════════════════════════════════

def step3_inject_metadata(raw_jsonl: Path, key_to_paths: dict, run_dir: Path) -> Path:
    final_jsonl = run_dir / "properties_final.jsonl"
    written = 0

    with open(raw_jsonl, encoding="utf-8") as fin, \
         open(final_jsonl, "w", encoding="utf-8") as fout:
        for line in fin:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            url = normalize_url(str(rec.get("url", "") or ""))
            lid = listing_id(url)

            rec["url"]             = url
            rec["listing_id"]      = lid
            rec["source_site"]     = str(rec.get("source", "rightmove") or "rightmove")
            rec["discovery_paths"] = key_to_paths.get(lid, [])

            fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
            written += 1

    print(f"   Final JSONL: {written:,} records → {final_jsonl}")
    return final_jsonl


# ══════════════════════════════════════════════════════════════════
# Step 4 — Summary
# ══════════════════════════════════════════════════════════════════

def step4_summary(run_dir: Path, key_to_url: dict, key_to_paths: dict, elapsed: float):
    district_counts: dict[str, int] = {}
    for lid, paths in key_to_paths.items():
        for query in paths:
            district = query.strip().split()[0]
            district_counts[district] = district_counts.get(district, 0) + 1

    summary = {
        "run_id":          run_dir.name,
        "timestamp":       datetime.now().isoformat(),
        "elapsed_sec":     round(elapsed, 1),
        "total_unique":    len(key_to_url),
        "district_counts": dict(sorted(district_counts.items())),
    }
    with open(run_dir / "summary.json", "w") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    m, s = divmod(int(elapsed), 60)
    print(f"""
══════════════════════════════════════════════
  Crawl complete  ({m}m {s}s)
  Unique listings:  {len(key_to_url):,}
  Summary:          {run_dir}/summary.json
══════════════════════════════════════════════""")


# ══════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--step",       default="all", choices=["1", "2", "3", "all"],
                   help="Which step to run: 1=collect URLs, 2=crawl details, 3=inject metadata, all=full pipeline")
    p.add_argument("--resume",     action="store_true")
    p.add_argument("--districts",  default=None, help="e.g. E1,E2,SW1V")
    p.add_argument("--dry-run",    action="store_true")
    p.add_argument("--max-pages",  type=int,   default=MAX_PAGES)
    p.add_argument("--workers",    type=int,   default=CRAWL_WORKERS)
    p.add_argument("--chunk-size", type=int,   default=CHUNK_SIZE)
    p.add_argument("--sleep-sec",  type=float, default=SLEEP_SEC)
    return p.parse_args()


def main():
    global CRAWL_WORKERS, CHUNK_SIZE, SLEEP_SEC
    args = parse_args()
    CRAWL_WORKERS = args.workers
    CHUNK_SIZE    = args.chunk_size
    SLEEP_SEC     = args.sleep_sec

    start_time = time.time()
    runs_root  = ARTIFACTS_DIR / "runs"
    runs_root.mkdir(parents=True, exist_ok=True)

    # 确定 run_dir
    # Steps 2/3 always resume the latest run; step 1 / all create a new one unless --resume
    need_existing = args.step in ("2", "3")
    if args.resume or need_existing:
        existing = sorted(runs_root.glob("run_*"))
        if not existing:
            print("[ERROR] No previous run found.")
            sys.exit(1)
        run_dir = existing[-1]
        print(f"[resume] {run_dir.name}")
    else:
        run_dir = runs_root / f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        run_dir.mkdir()
        print(f"[run] {run_dir.name}")

    # ── Step 1 ────────────────────────────────────────────────────
    if args.step in ("1", "all"):
        all_queries = get_search_queries()
        if args.districts:
            filter_set  = {d.strip().upper() for d in args.districts.split(",")}
            all_queries = [q for q in all_queries if q["district"].upper() in filter_set]
            print(f"[run] Districts filter: {filter_set} → {len(all_queries)} queries")
        else:
            print(f"[run] Full London: {len(all_queries)} queries")

        print(f"\n── Step 1: Collect URLs (max_pages={args.max_pages}) ──")
        key_to_url, key_to_paths = step1_collect_all_urls(
            queries=all_queries,
            run_dir=run_dir,
            max_pages=args.max_pages,
            resume=args.resume,
        )

        if args.dry_run:
            print(f"\n[dry-run] Done. {len(key_to_url):,} unique listings collected.")
            step4_summary(run_dir, key_to_url, key_to_paths, time.time()-start_time)
            return

        if args.step == "1":
            step4_summary(run_dir, key_to_url, key_to_paths, time.time()-start_time)
            return
    else:
        key_to_url, key_to_paths = load_step1_results(run_dir)

    # ── Step 2 ────────────────────────────────────────────────────
    if args.step in ("2", "all"):
        print(f"\n── Step 2: Crawl details ──")
        raw_jsonl = step2_crawl_details(key_to_url, run_dir)

        if args.step == "2":
            step4_summary(run_dir, key_to_url, key_to_paths, time.time()-start_time)
            return
    else:
        raw_jsonl = run_dir / "properties_raw.jsonl"

    # ── Step 3 ────────────────────────────────────────────────────
    if args.step in ("3", "all"):
        print(f"\n── Step 3: Inject metadata ──")
        step3_inject_metadata(raw_jsonl, key_to_paths, run_dir)

    # ── Summary ───────────────────────────────────────────────────
    step4_summary(run_dir, key_to_url, key_to_paths, time.time()-start_time)


if __name__ == "__main__":
    main()
