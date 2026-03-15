# Tenant Rights Skill — Dev Progress

> Tier 1 (curated Markdown references + keyword/LLM topic router) + Tier 2 (Qdrant vector search over 147 chunks).

---

## Architecture

```
User question
    → topic_router.classify(question)     # keyword regex → LLM fallback
    → get_reference_files(topics)         # curated Markdown from references/
    → retriever.retrieve_chunks(query)    # Qdrant Cloud: embed → search → rerank → trim
    → handler.answer_rights_question()    # LLM synthesis (gpt-5.1 quick / gpt-5.4 deep)
```

### Key Files

| File | Role |
|------|------|
| `handler.py` | Main entry point — combines Tier 1 + Tier 2, escalation detection, LLM answer |
| `topic_router.py` | 9-topic classifier (keyword regex + LLM fallback), reference file mapping |
| `retriever.py` | Qdrant vector search with fastembed + optional cross-encoder rerank |
| `ingest.py` | Chunks curated Markdown + scrapes GOV.UK/Shelter → `data/chunks.jsonl` |
| `index_qdrant.py` | Embeds chunks, upserts to Qdrant Cloud `tenant_rights` collection |
| `references/` | 11 curated Markdown files covering core UK tenant rights topics |

### Qdrant Collection

- **Collection:** `tenant_rights` (Qdrant Cloud)
- **Points:** 147
- **Dimensions:** 384 (COSINE)
- **Embedding model:** `sentence-transformers/all-MiniLM-L6-v2`
- **Rerank model:** `cross-encoder/ms-marco-MiniLM-L-6-v2` (optional)

---

## Commit Log

| Commit | Date | Type | Description |
|--------|------|------|-------------|
| `af1bc23` | 2026-03-15 | feat | Rebuild tenant rights RAG (B-F7) — Tier 1 + Tier 2 + LangGraph integration |
