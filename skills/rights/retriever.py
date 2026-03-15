"""
Tenant-rights Tier 2 retriever — fetches chunks from Qdrant `tenant_rights`
collection and returns contextually relevant passages for RAG.

The collection is pre-indexed (147 points, 384-dim COSINE, all-MiniLM-L6-v2).
This module provides the runtime query path:  embed → search → optional
cross-encoder rerank → token-budget trim → return.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import numpy as np

from core.logger import log_message

# ---------------------------------------------------------------------------
# Configuration (env-driven, with sensible defaults)
# ---------------------------------------------------------------------------

_ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

QDRANT_URL: str = os.environ.get(
    "RENT_QDRANT_URL",
    "https://725a9b5a-2732-448b-b094-a06577cfe7bd.europe-west3-0.gcp.cloud.qdrant.io",
)
QDRANT_API_KEY: str = os.environ.get(
    "RENT_QDRANT_API_KEY",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhY2Nlc3MiOiJtIn0.SXmYVOqGgBvuGR-I60m7U4wKUT2zQ-eopChFhO3iVns",
)
RIGHTS_COLLECTION: str = os.environ.get("RIGHTS_QDRANT_COLLECTION", "tenant_rights")
RIGHTS_RETRIEVAL_LIMIT: int = int(os.environ.get("RIGHTS_RETRIEVAL_LIMIT", "15"))
RIGHTS_TOP_K: int = int(os.environ.get("RIGHTS_TOP_K", "5"))
RIGHTS_MAX_CONTEXT_TOKENS: int = int(os.environ.get("RIGHTS_MAX_CONTEXT_TOKENS", "3000"))

_RIGHTS_LOCAL_PATH: str = os.environ.get(
    "RIGHTS_QDRANT_LOCAL_PATH",
    os.path.join(_ROOT_DIR, "artifacts", "skills", "rights", "qdrant_local"),
)
_RENT_LOCAL_PATH: str = os.environ.get(
    "RENT_QDRANT_PATH",
    os.path.join(_ROOT_DIR, "artifacts", "skills", "search", "data", "qdrant_local"),
)

EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
RERANK_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"

# ---------------------------------------------------------------------------
# Lazy singletons
# ---------------------------------------------------------------------------

_qdrant_client = None
_embedder = None
_reranker = None
_reranker_available: Optional[bool] = None  # None = not yet attempted


def _get_qdrant_client():
    """Return (and cache) a QdrantClient connected to Cloud or local storage."""
    global _qdrant_client
    if _qdrant_client is not None:
        return _qdrant_client

    from qdrant_client import QdrantClient

    if QDRANT_URL:
        _qdrant_client = QdrantClient(
            url=QDRANT_URL,
            api_key=QDRANT_API_KEY or None,
        )
        log_message("INFO", f"rights retriever qdrant mode=cloud url={QDRANT_URL}")
    else:
        # Local fallback: prefer rights-specific path, then shared rental path
        local_path = _RIGHTS_LOCAL_PATH if os.path.isdir(_RIGHTS_LOCAL_PATH) else _RENT_LOCAL_PATH
        _qdrant_client = QdrantClient(path=local_path)
        log_message("INFO", f"rights retriever qdrant mode=local path={local_path}")

    # Verify collection exists
    try:
        info = _qdrant_client.get_collection(RIGHTS_COLLECTION)
        log_message("INFO", f"rights retriever collection={RIGHTS_COLLECTION} points={info.points_count}")
    except Exception as exc:
        log_message("WARN", f"rights retriever collection check failed: {exc}")

    return _qdrant_client


def _get_embedder():
    """Return (and cache) a fastembed TextEmbedding model."""
    global _embedder
    if _embedder is not None:
        return _embedder

    from fastembed import TextEmbedding

    _embedder = TextEmbedding(model_name=EMBED_MODEL)
    log_message("INFO", f"rights retriever embedder loaded: {EMBED_MODEL}")
    return _embedder


def _get_reranker():
    """Return (and cache) a cross-encoder reranker, or None if unavailable."""
    global _reranker, _reranker_available
    if _reranker_available is False:
        return None
    if _reranker is not None:
        return _reranker

    try:
        from sentence_transformers import CrossEncoder

        _reranker = CrossEncoder(RERANK_MODEL)
        _reranker_available = True
        log_message("INFO", f"rights retriever reranker loaded: {RERANK_MODEL}")
        return _reranker
    except Exception as exc:
        _reranker_available = False
        log_message("WARN", f"rights retriever reranker unavailable ({exc}), using vector scores only")
        return None


# ---------------------------------------------------------------------------
# Embedding helper
# ---------------------------------------------------------------------------

def _embed_query(query: str) -> List[float]:
    """Embed a single query string and L2-normalize the resulting vector."""
    embedder = _get_embedder()
    raw = np.array(list(embedder.embed([query])), dtype="float32")
    norms = np.linalg.norm(raw, axis=1, keepdims=True)
    norms = np.maximum(norms, 1e-12)
    normalized = (raw / norms)[0]
    return normalized.tolist()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def retrieve_chunks(
    query: str,
    topic_hints: list[str] | None = None,
    top_k: int | None = None,
    max_tokens: int | None = None,
) -> list[dict]:
    """Retrieve the most relevant tenant-rights chunks for *query*.

    Parameters
    ----------
    query : str
        The user question or search phrase.
    topic_hints : list[str] | None
        If provided, pre-filter Qdrant on the ``topic_tags`` payload field
        using a MatchAny condition.  E.g. ``["deposits", "eviction"]``.
    top_k : int | None
        Number of chunks to return after reranking.  Defaults to
        ``RIGHTS_TOP_K`` (env ``RIGHTS_TOP_K``, default 5).
    max_tokens : int | None
        Hard token budget — stop accumulating chunks once this threshold is
        reached.  Never truncates a chunk mid-text.  Defaults to
        ``RIGHTS_MAX_CONTEXT_TOKENS`` (env ``RIGHTS_MAX_CONTEXT_TOKENS``,
        default 3000).

    Returns
    -------
    list[dict]
        Each dict contains: ``text``, ``source_name``, ``source_url``,
        ``section_heading``, ``score``.
    """
    from qdrant_client import models

    effective_top_k = top_k if top_k is not None else RIGHTS_TOP_K
    effective_max_tokens = max_tokens if max_tokens is not None else RIGHTS_MAX_CONTEXT_TOKENS

    # Over-retrieve 3x for reranking headroom
    retrieval_limit = max(RIGHTS_RETRIEVAL_LIMIT, effective_top_k * 3)

    # 1. Embed
    query_vector = _embed_query(query)

    # 2. Build optional topic filter
    # Map router topic names → Qdrant tag names (they differ slightly)
    _TOPIC_TO_TAG = {
        "deposit": "deposits",
        "rent_increase": "rent",
        "retaliatory_eviction": "eviction",
        "tenancy_types": "tenancy_type",
    }
    query_filter: Optional[models.Filter] = None
    if topic_hints:
        mapped = list({_TOPIC_TO_TAG.get(t, t) for t in topic_hints})
        query_filter = models.Filter(
            must=[
                models.FieldCondition(
                    key="topic_tags",
                    match=models.MatchAny(any=mapped),
                ),
            ]
        )

    # 3. Search Qdrant
    client = _get_qdrant_client()
    try:
        if hasattr(client, "search"):
            hits = client.search(
                collection_name=RIGHTS_COLLECTION,
                query_vector=query_vector,
                query_filter=query_filter,
                limit=retrieval_limit,
                with_payload=True,
                with_vectors=False,
            )
        else:
            qp = client.query_points(
                collection_name=RIGHTS_COLLECTION,
                query=query_vector,
                query_filter=query_filter,
                limit=retrieval_limit,
                with_payload=True,
                with_vectors=False,
            )
            hits = list(getattr(qp, "points", []) or [])
    except Exception as exc:
        log_message("ERROR", f"rights retriever search failed: {exc}")

        # If filtering caused a miss, retry without filter
        if query_filter is not None:
            log_message("INFO", "rights retriever retrying without topic filter")
            try:
                if hasattr(client, "search"):
                    hits = client.search(
                        collection_name=RIGHTS_COLLECTION,
                        query_vector=query_vector,
                        query_filter=None,
                        limit=retrieval_limit,
                        with_payload=True,
                        with_vectors=False,
                    )
                else:
                    qp = client.query_points(
                        collection_name=RIGHTS_COLLECTION,
                        query=query_vector,
                        query_filter=None,
                        limit=retrieval_limit,
                        with_payload=True,
                        with_vectors=False,
                    )
                    hits = list(getattr(qp, "points", []) or [])
            except Exception as exc2:
                log_message("ERROR", f"rights retriever retry also failed: {exc2}")
                return []
        else:
            return []

    if not hits:
        log_message("INFO", "rights retriever: 0 hits from Qdrant")
        return []

    log_message("INFO", f"rights retriever: {len(hits)} raw hits from Qdrant")

    # 4. Build candidate list
    candidates: List[Dict[str, Any]] = []
    for hit in hits:
        payload = dict(hit.payload or {})
        candidates.append({
            "text": payload.get("text", ""),
            "source_name": payload.get("source_name", ""),
            "source_url": payload.get("source_url", ""),
            "section_heading": payload.get("section_heading", ""),
            "topic_tags": payload.get("topic_tags", []),
            "token_count": int(payload.get("token_count", 0)),
            "score": float(hit.score),
        })

    # 5. Optional cross-encoder rerank
    reranker = _get_reranker()
    if reranker is not None and len(candidates) > 1:
        try:
            pairs = [(query, c["text"]) for c in candidates]
            rerank_scores = reranker.predict(pairs)
            for i, score in enumerate(rerank_scores):
                candidates[i]["score"] = float(score)
            candidates.sort(key=lambda c: c["score"], reverse=True)
            log_message("INFO", "rights retriever: cross-encoder rerank applied")
        except Exception as exc:
            log_message("WARN", f"rights retriever rerank error ({exc}), keeping vector order")

    # 6. Top-k cut
    candidates = candidates[:effective_top_k]

    # 7. Token budget enforcement — never truncate mid-chunk
    selected: List[Dict[str, Any]] = []
    token_total = 0
    for c in candidates:
        chunk_tokens = c.get("token_count") or _estimate_tokens(c["text"])
        if token_total + chunk_tokens > effective_max_tokens and selected:
            # Already have at least one chunk; stop to respect budget
            break
        selected.append(c)
        token_total += chunk_tokens

    log_message(
        "INFO",
        f"rights retriever: returning {len(selected)} chunks, ~{token_total} tokens "
        f"(budget {effective_max_tokens})",
    )

    # 8. Strip internal fields before returning
    results: List[Dict[str, Any]] = []
    for c in selected:
        results.append({
            "text": c["text"],
            "source_name": c["source_name"],
            "source_url": c["source_url"],
            "section_heading": c["section_heading"],
            "score": c["score"],
        })
    return results


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _estimate_tokens(text: str) -> int:
    """Rough token estimate: ~0.75 words per token for English text."""
    if not text:
        return 0
    word_count = len(text.split())
    return max(1, int(word_count / 0.75))
