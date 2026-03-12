# crawler/

全伦敦租房数据抓取，独立于 backend / frontend。

## 目录结构

```
rent-chatbot/
  backend/
  frontend/
  crawler/                        ← 这里
    crawl_london.py               # 主脚本
    london_postcodes.py           # 258 个 district + 细分策略
    london_regions.py             # 97 个 mental region + 坐标
    geo_utils.py                  # 地理工具函数
    start_crawl.sh                # 一键启动
    artifacts/                    # 输出（自动生成）
      postcode_location_cache.json
      runs/
        run_YYYYMMDD_HHMMSS/
          query_urls/
          deduped_urls.txt
          chunk_results/
          properties_raw.jsonl
          properties_final.jsonl  ← 给 build_qdrant 用
          summary.json
```

## 启动

```bash
cd /workspace/rent-chatbot/crawler
chmod +x start_crawl.sh

bash start_crawl.sh test    # 先测试
bash start_crawl.sh full    # 全量
bash start_crawl.sh resume  # 断点续传
```

## 数量预估

| 模式       | Queries | 预计 Listings | 时间       |
|-----------|---------|--------------|-----------|
| test      | 13      | ~500         | 5 分钟    |
| 全量       | 363     | ~25,000      | 60-90 分钟 |

## 接入 Qdrant

```bash
python scripts/build_qdrant_from_source.py \
  --source crawler/artifacts/runs/{run_id}/properties_final.jsonl
```
