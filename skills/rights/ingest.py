"""
Tenant-rights ingest pipeline — chunks curated Markdown files and scrapes
authoritative UK web sources into a JSONL file ready for Qdrant indexing.

Usage:
    python -m skills.rights.ingest            # run from project root
    python skills/rights/ingest.py            # or directly

Output: skills/rights/data/chunks.jsonl
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_THIS_DIR = Path(__file__).resolve().parent
_REFERENCES_DIR = _THIS_DIR / "references"
_DATA_DIR = _THIS_DIR / "data"
_OUTPUT_PATH = _DATA_DIR / "chunks.jsonl"

# ---------------------------------------------------------------------------
# Web sources
# ---------------------------------------------------------------------------

GOV_UK_URLS: List[str] = [
    "https://www.gov.uk/private-renting",
    "https://www.gov.uk/private-renting/repairs",
    "https://www.gov.uk/tenancy-deposit-protection",
    "https://www.gov.uk/deposit-protection-schemes-and-landlords",
    "https://www.gov.uk/evicting-tenants/section-21-and-section-8-notices",
    "https://www.gov.uk/private-renting/rent-increases",
    "https://www.gov.uk/government/publications/tenant-fees-act-2019-guidance",
    "https://www.gov.uk/government/publications/retaliatory-eviction-and-the-deregulation-act-2015-a-guidance-note",
]

SHELTER_URLS: List[str] = [
    "https://england.shelter.org.uk/housing_advice/private_renting",
    "https://england.shelter.org.uk/housing_advice/private_renting/assured_shorthold_tenancies_with_private_landlords",
    "https://england.shelter.org.uk/housing_advice/private_renting/landlord_responsibilities",
    "https://england.shelter.org.uk/housing_advice/private_renting/renters_rights_act_changes_for_private_renters",
    "https://england.shelter.org.uk/housing_advice/repairs/landlord_and_tenant_responsibilities_for_repairs",
    "https://england.shelter.org.uk/housing_advice/private_renting/tenancy_rights_if_your_landlord_sells_your_home",
    "https://england.shelter.org.uk/housing_advice/private_renting/what_to_look_for_in_your_tenancy_agreement/deposits_charges_and_fees",
    "https://england.shelter.org.uk/housing_advice/private_renting/what_to_look_for_in_your_tenancy_agreement/landlord_access",
]

# ---------------------------------------------------------------------------
# Topic tag auto-detection
# ---------------------------------------------------------------------------

_TOPIC_KEYWORDS: Dict[str, List[str]] = {
    "deposits": ["deposit", "dps", "mydeposits", "tds", "tenancy_deposit", "holding_deposit"],
    "eviction": ["evict", "section_21", "section_8", "notice", "possession", "retaliatory"],
    "repairs": ["repair", "maintenance", "disrepair", "damp", "mould", "hazard"],
    "rent": ["rent_increase", "rent_rises", "fair_rent", "rent_review"],
    "fees": ["fees", "tenant_fees", "charges", "admin_fee", "reference_fee"],
    "tenancy_agreements": ["tenancy_agreement", "ast", "assured_shorthold", "periodic", "fixed_term"],
    "landlord_responsibilities": ["landlord_responsib", "gas_safety", "electrical", "epc", "fire_safety"],
    "tenant_rights": ["tenant_right", "renter", "renters_rights", "right_to_rent"],
    "landlord_access": ["landlord_access", "right_of_entry", "inspection", "24_hours"],
    "property_sale": ["sell", "sale", "new_landlord", "transfer"],
}


def detect_topic_tags(text: str) -> List[str]:
    """Derive topic tags from text content and source identifiers."""
    text_lower = text.lower()
    # Normalise separators for keyword matching
    text_norm = re.sub(r"[\s/\-]+", "_", text_lower)
    tags: set[str] = set()
    for tag, keywords in _TOPIC_KEYWORDS.items():
        for kw in keywords:
            if kw in text_norm:
                tags.add(tag)
                break
    return sorted(tags) if tags else ["general"]


def _tags_from_url(url: str) -> List[str]:
    """Extract topic hints from a URL path."""
    path = url.split("//", 1)[-1].split("?")[0]
    return detect_topic_tags(path)


def _tags_from_filename(filename: str) -> List[str]:
    """Extract topic hints from a filename (without extension)."""
    stem = Path(filename).stem
    return detect_topic_tags(stem)


# ---------------------------------------------------------------------------
# Token counting
# ---------------------------------------------------------------------------

def _count_tokens(text: str) -> int:
    """Approximate token count (words / 0.75 for English)."""
    if not text:
        return 0
    return max(1, int(len(text.split()) / 0.75))


# ---------------------------------------------------------------------------
# Markdown chunking
# ---------------------------------------------------------------------------

_HEADING_RE = re.compile(r"^(#{2,3})\s+(.+)$", re.MULTILINE)

MIN_CHUNK_TOKENS = 50
MAX_CHUNK_TOKENS = 512


def _chunk_markdown(text: str, source_name: str, source_url: str) -> List[Dict[str, Any]]:
    """Split Markdown at ## / ### boundaries into chunks of 50-512 tokens.

    Undersized sections are merged with the next section.  Oversized sections
    are split on paragraph boundaries.
    """
    chunks: List[Dict[str, Any]] = []
    # Split into (heading, body) pairs
    parts: List[tuple[str, str]] = []
    headings = list(_HEADING_RE.finditer(text))

    if not headings:
        # No headings — treat entire file as one chunk
        parts.append(("", text.strip()))
    else:
        # Text before first heading
        pre = text[: headings[0].start()].strip()
        if pre:
            parts.append(("", pre))
        for i, m in enumerate(headings):
            heading = m.group(2).strip()
            start = m.end()
            end = headings[i + 1].start() if i + 1 < len(headings) else len(text)
            body = text[start:end].strip()
            parts.append((heading, body))

    # Merge undersized sections
    merged: List[tuple[str, str]] = []
    buffer_heading = ""
    buffer_body = ""
    for heading, body in parts:
        combined = (buffer_body + "\n\n" + body).strip() if buffer_body else body
        if _count_tokens(combined) < MIN_CHUNK_TOKENS:
            buffer_heading = buffer_heading or heading
            buffer_body = combined
        else:
            if buffer_body and _count_tokens(buffer_body) >= MIN_CHUNK_TOKENS:
                merged.append((buffer_heading, buffer_body))
                buffer_heading = heading
                buffer_body = body
            else:
                buffer_heading = buffer_heading or heading
                buffer_body = combined

    if buffer_body:
        merged.append((buffer_heading, buffer_body))

    # Split oversized sections on paragraph boundaries
    for heading, body in merged:
        if _count_tokens(body) <= MAX_CHUNK_TOKENS:
            chunks.append(_make_chunk(body, source_name, source_url, heading))
        else:
            paragraphs = re.split(r"\n{2,}", body)
            current = ""
            for para in paragraphs:
                candidate = (current + "\n\n" + para).strip() if current else para
                if _count_tokens(candidate) > MAX_CHUNK_TOKENS and current:
                    chunks.append(_make_chunk(current, source_name, source_url, heading))
                    current = para
                else:
                    current = candidate
            if current:
                chunks.append(_make_chunk(current, source_name, source_url, heading))

    return chunks


def _make_chunk(
    text: str,
    source_name: str,
    source_url: str,
    section_heading: str,
) -> Dict[str, Any]:
    """Construct a single chunk dict."""
    # Combine source + heading + text for topic detection
    tag_input = f"{source_name} {section_heading} {text}"
    return {
        "chunk_id": _deterministic_id(source_name, section_heading, text),
        "text": text,
        "source_type": "curated",
        "source_name": source_name,
        "source_url": source_url,
        "section_heading": section_heading,
        "topic_tags": detect_topic_tags(tag_input),
        "token_count": _count_tokens(text),
    }


def _deterministic_id(source: str, heading: str, text: str) -> str:
    """SHA-256-based deterministic chunk id."""
    blob = f"{source}||{heading}||{text[:200]}"
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Curated file ingestion
# ---------------------------------------------------------------------------

def ingest_curated_files() -> List[Dict[str, Any]]:
    """Read all *.md files from the references/ directory and chunk them."""
    all_chunks: List[Dict[str, Any]] = []
    if not _REFERENCES_DIR.is_dir():
        print(f"[WARN] References directory not found: {_REFERENCES_DIR}")
        return all_chunks

    for md_file in sorted(_REFERENCES_DIR.glob("*.md")):
        text = md_file.read_text(encoding="utf-8")
        source_name = md_file.stem.replace("_", " ").title()
        chunks = _chunk_markdown(text, source_name=source_name, source_url="")
        print(f"  [curated] {md_file.name}: {len(chunks)} chunks")
        all_chunks.extend(chunks)

    return all_chunks


# ---------------------------------------------------------------------------
# Web scraping
# ---------------------------------------------------------------------------

def _fetch_page(url: str) -> Optional[str]:
    """Fetch a web page and return its text content, or None on failure."""
    try:
        import requests
    except ImportError:
        print(f"  [SKIP] requests not installed, cannot fetch {url}")
        return None

    try:
        resp = requests.get(url, timeout=30, headers={
            "User-Agent": "Mozilla/5.0 (compatible; TenantRightsBot/1.0)"
        })
        resp.raise_for_status()
        return resp.text
    except Exception as exc:
        print(f"  [FAIL] {url}: {exc}")
        return None


def _extract_main_content(html: str, url: str) -> str:
    """Extract main text content from HTML using BeautifulSoup."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        print("  [WARN] beautifulsoup4 not installed, falling back to raw HTML strip")
        return re.sub(r"<[^>]+>", " ", html)

    soup = BeautifulSoup(html, "html.parser")

    # Remove script, style, nav, footer, header elements
    for tag in soup.find_all(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()

    # GOV.UK: main content is typically in <main> or <div class="govuk-width-container">
    if "gov.uk" in url:
        main = soup.find("main") or soup.find("div", class_="govuk-width-container")
        if main:
            return main.get_text(separator="\n", strip=True)

    # Shelter: main content in <main> or <article>
    if "shelter.org.uk" in url:
        main = soup.find("main") or soup.find("article")
        if main:
            return main.get_text(separator="\n", strip=True)

    # Generic fallback
    main = soup.find("main") or soup.find("article") or soup.find("body")
    if main:
        return main.get_text(separator="\n", strip=True)

    return soup.get_text(separator="\n", strip=True)


def _source_name_from_url(url: str) -> str:
    """Derive a human-readable source name from a URL."""
    if "gov.uk" in url:
        prefix = "GOV.UK"
    elif "shelter.org.uk" in url:
        prefix = "Shelter"
    else:
        prefix = "Web"

    # Extract last meaningful path segment
    path = url.rstrip("/").split("/")[-1]
    title = path.replace("-", " ").replace("_", " ").title()
    return f"{prefix}: {title}"


def _chunk_web_content(
    text: str,
    source_name: str,
    source_url: str,
) -> List[Dict[str, Any]]:
    """Chunk scraped web text using paragraph-based splitting."""
    chunks: List[Dict[str, Any]] = []

    # Split on double newlines (paragraph boundaries)
    paragraphs = re.split(r"\n{2,}", text.strip())
    current = ""
    section = ""

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        # Detect heading-like lines (short lines ending without punctuation)
        if len(para) < 100 and not para.endswith((".", "!", "?", ":")):
            if current and _count_tokens(current) >= MIN_CHUNK_TOKENS:
                chunk = _make_web_chunk(current, source_name, source_url, section)
                chunks.append(chunk)
                current = ""
            section = para
            continue

        candidate = (current + "\n\n" + para).strip() if current else para
        if _count_tokens(candidate) > MAX_CHUNK_TOKENS and current:
            chunk = _make_web_chunk(current, source_name, source_url, section)
            chunks.append(chunk)
            current = para
        else:
            current = candidate

    if current and _count_tokens(current) >= MIN_CHUNK_TOKENS:
        chunks.append(_make_web_chunk(current, source_name, source_url, section))
    elif current and chunks:
        # Merge undersized trailing content into the last chunk
        last = chunks[-1]
        last["text"] = last["text"] + "\n\n" + current
        last["token_count"] = _count_tokens(last["text"])
        last["topic_tags"] = detect_topic_tags(
            f"{source_name} {last['section_heading']} {last['text']}"
        )

    return chunks


def _make_web_chunk(
    text: str,
    source_name: str,
    source_url: str,
    section_heading: str,
) -> Dict[str, Any]:
    tag_input = f"{source_name} {section_heading} {source_url} {text}"
    return {
        "chunk_id": _deterministic_id(source_name, section_heading, text),
        "text": text,
        "source_type": "web",
        "source_name": source_name,
        "source_url": source_url,
        "section_heading": section_heading,
        "topic_tags": detect_topic_tags(tag_input),
        "token_count": _count_tokens(text),
    }


def ingest_web_pages() -> List[Dict[str, Any]]:
    """Scrape and chunk all configured web URLs."""
    all_chunks: List[Dict[str, Any]] = []
    all_urls = GOV_UK_URLS + SHELTER_URLS

    for url in all_urls:
        print(f"  [fetch] {url}")
        html = _fetch_page(url)
        if html is None:
            continue

        text = _extract_main_content(html, url)
        if not text or _count_tokens(text) < 20:
            print(f"  [SKIP] too little content from {url}")
            continue

        source_name = _source_name_from_url(url)
        chunks = _chunk_web_content(text, source_name, url)
        print(f"  [web] {source_name}: {len(chunks)} chunks")
        all_chunks.extend(chunks)

        # Polite crawl delay
        time.sleep(1.0)

    return all_chunks


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_ingest() -> str:
    """Execute the full ingest pipeline. Returns the output file path."""
    print("=== Tenant Rights Ingest Pipeline ===\n")

    # 1. Curated files
    print("[Step 1] Chunking curated Markdown files...")
    curated_chunks = ingest_curated_files()
    print(f"  Total curated chunks: {len(curated_chunks)}\n")

    # 2. Web scraping
    print("[Step 2] Scraping and chunking web pages...")
    web_chunks = ingest_web_pages()
    print(f"  Total web chunks: {len(web_chunks)}\n")

    # 3. Combine and deduplicate by chunk_id
    all_chunks = curated_chunks + web_chunks
    seen_ids: set[str] = set()
    deduped: List[Dict[str, Any]] = []
    for c in all_chunks:
        cid = c["chunk_id"]
        if cid not in seen_ids:
            seen_ids.add(cid)
            deduped.append(c)
    print(f"[Step 3] Deduplication: {len(all_chunks)} -> {len(deduped)} chunks\n")

    # 4. Write JSONL
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(_OUTPUT_PATH, "w", encoding="utf-8") as f:
        for c in deduped:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")

    print(f"[Done] Written {len(deduped)} chunks to {_OUTPUT_PATH}")

    # Summary stats
    curated_count = sum(1 for c in deduped if c["source_type"] == "curated")
    web_count = sum(1 for c in deduped if c["source_type"] == "web")
    total_tokens = sum(c["token_count"] for c in deduped)
    all_tags = set()
    for c in deduped:
        all_tags.update(c.get("topic_tags", []))
    print(f"  curated={curated_count}  web={web_count}  total_tokens={total_tokens}")
    print(f"  topic_tags: {sorted(all_tags)}")

    return str(_OUTPUT_PATH)


if __name__ == "__main__":
    run_ingest()
