"""
Topic router for tenant rights questions.

Fast path: keyword regex matching across 9 topics.
Slow path: LLM fallback when keywords return no matches.
"""

from __future__ import annotations

import os
import re
import time
from typing import List, Optional

from openai import OpenAI

# ---------------------------------------------------------------------------
# Topic → reference-file mapping
# ---------------------------------------------------------------------------

TOPIC_FILE_MAP: dict[str, str] = {
    "deposit": "deposits_protection.md",
    "eviction": "eviction_grounds.md",
    "repairs": "repairs_section11.md",
    "rent_increase": "rent_increases.md",
    "harassment": "harassment_quiet_enjoyment.md",
    "fees": "fees_and_charges.md",
    "retaliatory_eviction": "retaliatory_eviction.md",
    "tenancy_types": "tenancy_types.md",
    "pets_discrimination": "pets_discrimination.md",
}

VALID_TOPICS = set(TOPIC_FILE_MAP.keys())

# File included for every query regardless of topic.
UNIVERSAL_FILE = "rra2025_timeline.md"

# Fallback files when no topic is matched at all.
FALLBACK_FILES = ["general_tenant_rights.md", UNIVERSAL_FILE]

# ---------------------------------------------------------------------------
# Compiled keyword patterns per topic (~110 patterns total)
# ---------------------------------------------------------------------------

_I = re.IGNORECASE

TOPIC_PATTERNS: dict[str, list[re.Pattern]] = {
    "deposit": [
        re.compile(r"deposit", _I),
        re.compile(r"\bdps\b", _I),
        re.compile(r"mydeposits", _I),
        re.compile(r"\btds\b", _I),
        re.compile(r"tenancy\s*deposit\s*scheme", _I),
        re.compile(r"protection\s*scheme", _I),
        re.compile(r"deposit\s*protect", _I),
        re.compile(r"protect.*deposit", _I),
        re.compile(r"deduct", _I),
        re.compile(r"\bbond\b", _I),
        re.compile(r"return.*deposit", _I),
        re.compile(r"deposit.*return", _I),
        re.compile(r"holding\s*deposit", _I),
        re.compile(r"security\s*deposit", _I),
        re.compile(r"prescribed\s*information", _I),
        re.compile(r"custodial\s*scheme", _I),
        re.compile(r"insured\s*scheme", _I),
    ],
    "eviction": [
        re.compile(r"evict", _I),
        re.compile(r"section\s*21", _I),
        re.compile(r"section\s*8", _I),
        re.compile(r"s\.?\s*21", _I),
        re.compile(r"s\.?\s*8\b", _I),
        re.compile(r"notice\s*to\s*quit", _I),
        re.compile(r"kick.*out", _I),
        re.compile(r"leave.*property", _I),
        re.compile(r"force.*out", _I),
        re.compile(r"\bpossession\b", _I),
        re.compile(r"possession\s*order", _I),
        re.compile(r"possession\s*proceedings", _I),
        re.compile(r"no[_\-\s]*fault", _I),
        re.compile(r"grounds?\s*for\s*eviction", _I),
        re.compile(r"mandatory\s*ground", _I),
        re.compile(r"discretionary\s*ground", _I),
        re.compile(r"notice\s*period", _I),
        re.compile(r"bailiff", _I),
        re.compile(r"court\s*order", _I),
    ],
    "repairs": [
        re.compile(r"repair", _I),
        re.compile(r"\bdamp\b", _I),
        re.compile(r"damp(ness)?", _I),
        re.compile(r"mould", _I),
        re.compile(r"\bmold\b", _I),
        re.compile(r"broken", _I),
        re.compile(r"\bfix(es|ed|ing)?\b", _I),
        re.compile(r"maintenance", _I),
        re.compile(r"\bhhsrs\b", _I),
        re.compile(r"fitness\s*for\s*habitation", _I),
        re.compile(r"habitable", _I),
        re.compile(r"awaab", _I),
        re.compile(r"awaab.s\s*law", _I),
        re.compile(r"disrepair", _I),
        re.compile(r"condensation", _I),
        re.compile(r"leak(ing|s|y)?", _I),
        re.compile(r"boiler", _I),
        re.compile(r"heating", _I),
        re.compile(r"plumbing", _I),
        re.compile(r"structural", _I),
        re.compile(r"section\s*11", _I),
        re.compile(r"hazard\s*rating", _I),
    ],
    "rent_increase": [
        re.compile(r"rent.*increase", _I),
        re.compile(r"increase.*rent", _I),
        re.compile(r"raise.*rent", _I),
        re.compile(r"rent.*raise", _I),
        re.compile(r"rent.*go(es|ing|ne)?\s*up", _I),
        re.compile(r"put.*rent\s*up", _I),
        re.compile(r"section\s*13", _I),
        re.compile(r"s\.?\s*13\b", _I),
        re.compile(r"rent\s*review", _I),
        re.compile(r"rent\s*tribunal", _I),
        re.compile(r"market\s*rent", _I),
        re.compile(r"above.*advertised", _I),
        re.compile(r"advertised.*price.*higher", _I),
        re.compile(r"bidding\s*war", _I),
        re.compile(r"rent\s*hik", _I),
        re.compile(r"excessive\s*rent", _I),
        re.compile(r"rent.*cap", _I),
        re.compile(r"rent.*freeze", _I),
    ],
    "harassment": [
        re.compile(r"harass", _I),
        re.compile(r"quiet\s*enjoy", _I),
        re.compile(r"enter.*without", _I),
        re.compile(r"without.*permission.*enter", _I),
        re.compile(r"enter.*whenever", _I),
        re.compile(r"landlord.*access", _I),
        re.compile(r"access.*landlord", _I),
        re.compile(r"chang.*lock", _I),
        re.compile(r"lock.*chang", _I),
        re.compile(r"intimidat", _I),
        re.compile(r"threaten", _I),
        re.compile(r"illegal\s*entry", _I),
        re.compile(r"trespass", _I),
        re.compile(r"bully", _I),
        re.compile(r"unlawful.*entry", _I),
        re.compile(r"turn.*off.*utilit", _I),
        re.compile(r"cut.*off.*(gas|electric|water)", _I),
    ],
    "fees": [
        re.compile(r"\bfee\b", _I),
        re.compile(r"\bfees\b", _I),
        re.compile(r"\bcharge[sd]?\b", _I),
        re.compile(r"admin.*fee", _I),
        re.compile(r"fee.*admin", _I),
        re.compile(r"check\s*-?\s*out\s*fee", _I),
        re.compile(r"reference\s*fee", _I),
        re.compile(r"tenant\s*fee", _I),
        re.compile(r"fee.*ban", _I),
        re.compile(r"banned\s*fee", _I),
        re.compile(r"inventory\s*fee", _I),
        re.compile(r"renewal\s*fee", _I),
        re.compile(r"exit\s*fee", _I),
        re.compile(r"permitted\s*payment", _I),
    ],
    "retaliatory_eviction": [
        re.compile(r"retaliat", _I),
        re.compile(r"revenge\s*evict", _I),
        re.compile(r"evict.*revenge", _I),
        re.compile(r"complain.*evict", _I),
        re.compile(r"evict.*complain", _I),
        re.compile(r"report.*evict", _I),
        re.compile(r"evict.*report", _I),
        re.compile(r"section\s*33", _I),
        re.compile(r"deregulation\s*act.*2015", _I),
    ],
    "tenancy_types": [
        re.compile(r"assured\s*shorthold", _I),
        re.compile(r"\bast\b", _I),
        re.compile(r"\bperiodic\b", _I),
        re.compile(r"rolling\s*tenancy", _I),
        re.compile(r"fixed\s*term", _I),
        re.compile(r"joint\s*tenan", _I),
        re.compile(r"break\s*clause", _I),
        re.compile(r"\blodger\b", _I),
        re.compile(r"\blicence\b", _I),
        re.compile(r"\blicense\b", _I),
        re.compile(r"excluded\s*tenancy", _I),
        re.compile(r"regulated\s*tenancy", _I),
        re.compile(r"assured\s*tenancy", _I),
        re.compile(r"type\s*of\s*tenancy", _I),
        re.compile(r"tenancy\s*type", _I),
        re.compile(r"tenancy\s*agreement", _I),
    ],
    "pets_discrimination": [
        re.compile(r"\bpet\b", _I),
        re.compile(r"\bpets\b", _I),
        re.compile(r"\bdog\b", _I),
        re.compile(r"\bdogs\b", _I),
        re.compile(r"\bcat\b", _I),
        re.compile(r"\bcats\b", _I),
        re.compile(r"\banimal\b", _I),
        re.compile(r"\banimals\b", _I),
        re.compile(r"discriminat", _I),
        re.compile(r"\bdss\b", _I),
        re.compile(r"\bbenefits?\b", _I),
        re.compile(r"\blha\b", _I),
        re.compile(r"housing\s*benefit", _I),
        re.compile(r"universal\s*credit", _I),
        re.compile(r"\bchildren\b", _I),
        re.compile(r"\bfamil(y|ies)\b", _I),
        re.compile(r"no\s*dss", _I),
        re.compile(r"blanket\s*ban", _I),
    ],
}

# ---------------------------------------------------------------------------
# LLM client configuration (lazy-initialised)
# ---------------------------------------------------------------------------

_RIGHTS_BASE_URL = os.environ.get("RIGHTS_BASE_URL", "http://localhost:8800/v1")
_RIGHTS_API_KEY = os.environ.get("RIGHTS_API_KEY", "proxy")
_RIGHTS_MODEL_QUICK = os.environ.get("RIGHTS_MODEL_QUICK", "gpt-5-codex")

_llm_client: Optional[OpenAI] = None


def _get_llm_client() -> OpenAI:
    global _llm_client
    if _llm_client is None:
        _llm_client = OpenAI(
            base_url=_RIGHTS_BASE_URL,
            api_key=_RIGHTS_API_KEY,
            timeout=30.0,
        )
    return _llm_client


# ---------------------------------------------------------------------------
# Classification functions
# ---------------------------------------------------------------------------

def classify_by_keywords(question: str) -> list[str]:
    """
    Fast-path classification using compiled regex patterns.

    Returns a list of matched topic names (may match multiple topics).
    """
    matched: list[str] = []
    for topic, patterns in TOPIC_PATTERNS.items():
        for pat in patterns:
            if pat.search(question):
                matched.append(topic)
                break  # one match per topic is enough
    return matched


_CLASSIFY_SYSTEM_PROMPT = f"""\
You are a topic classifier for UK tenant rights questions.

Given a user question, classify it into one or more of the following topics:
{', '.join(sorted(VALID_TOPICS))}

Rules:
- Return ONLY a comma-separated list of matching topic names.
- If the question matches multiple topics, include all that apply.
- If the question does not match any topic, return: none
- Do NOT include any explanation, just the topic names.

Examples:
- "Can my landlord keep my deposit?" → deposit
- "I've been served a Section 21 after complaining about mould" → eviction, repairs, retaliatory_eviction
- "What type of tenancy do I have?" → tenancy_types
- "Can my landlord charge me for cleaning?" → fees, deposit
"""


def classify_by_llm(question: str) -> list[str]:
    """
    LLM fallback classification. Called when keyword matching returns empty.

    Uses the RIGHTS_* env vars for OpenAI-compatible endpoint configuration.
    """
    client = _get_llm_client()
    t0 = time.perf_counter()
    try:
        response = client.chat.completions.create(
            model=_RIGHTS_MODEL_QUICK,
            messages=[
                {"role": "system", "content": _CLASSIFY_SYSTEM_PROMPT},
                {"role": "user", "content": question},
            ],
            temperature=0.0,
        )
        raw = response.choices[0].message.content.strip()
        elapsed = time.perf_counter() - t0
        print(f"[TIMING] rights_topic_classify={elapsed:.2f}s")
    except Exception as exc:
        print(f"[WARN] rights topic LLM classification failed: {exc}")
        return []

    # Parse comma-separated topic names from LLM response.
    raw_lower = raw.lower().strip()
    if raw_lower in {"none", "n/a", ""}:
        return []

    topics: list[str] = []
    for part in raw_lower.split(","):
        candidate = part.strip()
        if candidate in VALID_TOPICS:
            topics.append(candidate)

    return topics


def get_reference_files(topics: list[str]) -> list[str]:
    """
    Map topic names to reference file names.

    Always includes rra2025_timeline.md.  Falls back to general_tenant_rights.md
    + rra2025_timeline.md when no topics are provided.
    """
    if not topics:
        return list(FALLBACK_FILES)

    seen: set[str] = set()
    files: list[str] = []
    for topic in topics:
        fname = TOPIC_FILE_MAP.get(topic)
        if fname and fname not in seen:
            seen.add(fname)
            files.append(fname)

    # Always include the universal timeline file.
    if UNIVERSAL_FILE not in seen:
        files.append(UNIVERSAL_FILE)

    return files


def classify(question: str) -> list[str]:
    """
    Main entry point: classify a tenant rights question into topics.

    Tries keyword regex first (fast). Falls back to LLM if no keywords match.
    Returns a list of topic names.
    """
    topics = classify_by_keywords(question)
    if topics:
        return topics
    return classify_by_llm(question)
