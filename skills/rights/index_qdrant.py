"""
Tenant-rights Qdrant indexer — reads chunks from JSONL, embeds with
fastembed all-MiniLM-L6-v2, and upserts to the ``tenant_rights`` collection.

Supports both Qdrant Cloud and local storage.

Usage:
    python -m skills.rights.index_qdrant          # from project root
    python skills/rights/index_qdrant.py           # or directly
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any, Dict, List

import numpy as np

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_ROOT_DIR = Path(__file__).resolve().parent.parent.parent

QDRANT_URL: str = os.environ.get(
    "RENT_QDRANT_URL",
    "https://725a9b5a-2732-448b-b094-a06577cfe7bd.europe-west3-0.gcp.cloud.qdrant.io",
)
QDRANT_API_KEY: str = os.environ.get(
    "RENT_QDRANT_API_KEY",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhY2Nlc3MiOiJtIn0.SXmYVOqGgBvuGR-I60m7U4wKUT2zQ-eopChFhO3iVns",
)
RIGHTS_COLLECTION: str = os.environ.get("RIGHTS_QDRANT_COLLECTION", "tenant_rights")
RIGHTS_LOCAL_PATH: str = os.environ.get(
    "RIGHTS_QDRANT_LOCAL_PATH",
    str(_ROOT_DIR / "artifacts" / "skills" / "rights" / "qdrant_local"),
)

EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
VECTOR_DIM = 384
BATCH_SIZE = 64

CHUNKS_PATH = Path(__file__).resolve().parent / "data" / "chunks.jsonl"

# UUID v5 namespace for deterministic IDs
_UUID_NAMESPACE = uuid.UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _chunk_id_to_uuid(chunk_id: str) -> str:
    """Deterministic UUID v5 from chunk_id string — deduplicates on re-run."""
    return str(uuid.uuid5(_UUID_NAMESPACE, chunk_id))


def _load_chunks(path: Path) -> List[Dict[str, Any]]:
    """Read chunks from JSONL file."""
    if not path.exists():
        raise FileNotFoundError(f"Chunks file not found: {path}")

    chunks: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                chunks.append(json.loads(line))
            except json.JSONDecodeError as exc:
                print(f"  [WARN] Skipping malformed line {line_no}: {exc}")
    return chunks


def _embed_texts(texts: List[str]) -> np.ndarray:
    """Embed a list of texts with fastembed and L2-normalize."""
    from fastembed import TextEmbedding

    embedder = TextEmbedding(model_name=EMBED_MODEL)
    # fastembed.embed() returns a generator of arrays
    vectors = np.array(list(embedder.embed(texts)), dtype="float32")
    # L2 normalize
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms = np.maximum(norms, 1e-12)
    vectors = vectors / norms
    return vectors


def _get_qdrant_client():
    """Connect to Qdrant Cloud or local storage."""
    from qdrant_client import QdrantClient

    if QDRANT_URL:
        client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY or None)
        print(f"  [qdrant] Connected to cloud: {QDRANT_URL}")
    else:
        os.makedirs(RIGHTS_LOCAL_PATH, exist_ok=True)
        client = QdrantClient(path=RIGHTS_LOCAL_PATH)
        print(f"  [qdrant] Using local storage: {RIGHTS_LOCAL_PATH}")
    return client


def _ensure_collection(client) -> None:
    """Create the collection if it doesn't already exist."""
    from qdrant_client import models

    try:
        info = client.get_collection(RIGHTS_COLLECTION)
        print(f"  [qdrant] Collection '{RIGHTS_COLLECTION}' exists with {info.points_count} points")
        return
    except Exception:
        pass

    print(f"  [qdrant] Creating collection '{RIGHTS_COLLECTION}' ({VECTOR_DIM}-dim, COSINE)")
    client.create_collection(
        collection_name=RIGHTS_COLLECTION,
        vectors_config=models.VectorParams(
            size=VECTOR_DIM,
            distance=models.Distance.COSINE,
        ),
    )


def _create_payload_index(client) -> None:
    """Create keyword payload index on topic_tags for filtered search."""
    from qdrant_client import models

    try:
        client.create_payload_index(
            collection_name=RIGHTS_COLLECTION,
            field_name="topic_tags",
            field_schema=models.PayloadSchemaType.KEYWORD,
        )
        print("  [qdrant] Payload index created on 'topic_tags'")
    except Exception as exc:
        # Index may already exist — that's fine
        print(f"  [qdrant] Payload index on 'topic_tags': {exc}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_index(chunks_path: Path | None = None) -> None:
    """Embed chunks and upsert to Qdrant."""
    from qdrant_client import models

    path = chunks_path or CHUNKS_PATH
    print(f"=== Tenant Rights Qdrant Indexer ===\n")

    # 1. Load chunks
    print(f"[Step 1] Loading chunks from {path}")
    chunks = _load_chunks(path)
    print(f"  Loaded {len(chunks)} chunks\n")

    if not chunks:
        print("[Done] No chunks to index.")
        return

    # 2. Embed
    print(f"[Step 2] Embedding {len(chunks)} chunks with {EMBED_MODEL}")
    texts = [c["text"] for c in chunks]
    vectors = _embed_texts(texts)
    print(f"  Embedding complete: shape={vectors.shape}\n")

    # 3. Connect and ensure collection
    print("[Step 3] Connecting to Qdrant")
    client = _get_qdrant_client()
    _ensure_collection(client)
    _create_payload_index(client)
    print()

    # 4. Build points with deterministic UUIDs
    print(f"[Step 4] Upserting {len(chunks)} points in batches of {BATCH_SIZE}")
    points: List[models.PointStruct] = []
    for i, chunk in enumerate(chunks):
        point_id = _chunk_id_to_uuid(chunk["chunk_id"])
        payload = {
            "text": chunk["text"],
            "source_type": chunk.get("source_type", ""),
            "source_name": chunk.get("source_name", ""),
            "source_url": chunk.get("source_url", ""),
            "section_heading": chunk.get("section_heading", ""),
            "topic_tags": chunk.get("topic_tags", []),
            "token_count": chunk.get("token_count", 0),
        }
        points.append(models.PointStruct(
            id=point_id,
            vector=vectors[i].tolist(),
            payload=payload,
        ))

    # Batch upsert
    total_upserted = 0
    for batch_start in range(0, len(points), BATCH_SIZE):
        batch = points[batch_start : batch_start + BATCH_SIZE]
        client.upsert(
            collection_name=RIGHTS_COLLECTION,
            points=batch,
        )
        total_upserted += len(batch)
        print(f"  Upserted batch {batch_start // BATCH_SIZE + 1}: "
              f"{total_upserted}/{len(points)} points")

    print()

    # 5. Summary
    info = client.get_collection(RIGHTS_COLLECTION)
    print(f"[Done] Collection '{RIGHTS_COLLECTION}' now has {info.points_count} points")

    # Stats breakdown
    source_types: Dict[str, int] = {}
    all_tags: set[str] = set()
    total_tokens = 0
    for c in chunks:
        st = c.get("source_type", "unknown")
        source_types[st] = source_types.get(st, 0) + 1
        all_tags.update(c.get("topic_tags", []))
        total_tokens += c.get("token_count", 0)

    print(f"  Sources: {source_types}")
    print(f"  Total tokens: {total_tokens}")
    print(f"  Topic tags: {sorted(all_tags)}")


if __name__ == "__main__":
    run_index()
