"""
Tenant-rights handler — main entry point for answering tenant rights questions.

Combines Tier 1 (curated reference files) + Tier 2 (Qdrant vector retrieval)
with LLM-based answer generation.
"""

from __future__ import annotations

import os
import re
import time
from typing import List, Optional

from openai import OpenAI

from skills.rights import topic_router
from skills.rights import retriever

# ---------------------------------------------------------------------------
# LLM configuration (env-driven)
# ---------------------------------------------------------------------------

_RIGHTS_BASE_URL = os.environ.get("RIGHTS_BASE_URL", "http://localhost:8800/v1")
_RIGHTS_API_KEY = os.environ.get("RIGHTS_API_KEY", "proxy")
_RIGHTS_MODEL_QUICK = os.environ.get("RIGHTS_MODEL_QUICK", "gpt-5.1")
_RIGHTS_MODEL_DEEP = os.environ.get("RIGHTS_MODEL_DEEP", "gpt-5.4")

_SYSTEM_PROMPT = (
    "You are a UK tenant rights advisor. Answer based ONLY on the provided legal context. "
    "Cite specific Acts and section numbers. If unsure, say so and recommend Shelter or Citizens Advice."
)

_DISCLAIMER = "\n\n---\n*This is general guidance, not legal advice.*"

# ---------------------------------------------------------------------------
# Lazy LLM client
# ---------------------------------------------------------------------------

_llm_client: OpenAI | None = None


def _get_llm_client() -> OpenAI:
    global _llm_client
    if _llm_client is None:
        _llm_client = OpenAI(
            base_url=_RIGHTS_BASE_URL,
            api_key=_RIGHTS_API_KEY,
            timeout=60.0,
        )
    return _llm_client


# ---------------------------------------------------------------------------
# Reference file directory
# ---------------------------------------------------------------------------

_REFERENCES_DIR = os.path.join(os.path.dirname(__file__), "references")

# ---------------------------------------------------------------------------
# Escalation patterns
# ---------------------------------------------------------------------------

_ESCALATION_URGENT = [
    re.compile(r"bailiff", re.IGNORECASE),
    re.compile(r"court\s*date", re.IGNORECASE),
    re.compile(r"locked\s*out", re.IGNORECASE),
    re.compile(r"illegal\s*eviction", re.IGNORECASE),
    re.compile(r"changed?\s*(the\s*)?locks?", re.IGNORECASE),
    re.compile(r"thrown?\s*out", re.IGNORECASE),
    re.compile(r"belongings?\s*(removed|thrown|outside)", re.IGNORECASE),
]

_ESCALATION_LEGAL = [
    re.compile(r"tribunal", re.IGNORECASE),
    re.compile(r"solicitor", re.IGNORECASE),
    re.compile(r"barrister", re.IGNORECASE),
    re.compile(r"legal\s*proceedings?", re.IGNORECASE),
    re.compile(r"court\s*hearing", re.IGNORECASE),
    re.compile(r"court\s*order", re.IGNORECASE),
]


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _load_references(file_names: list[str]) -> str:
    """Read reference files from skills/rights/references/ and concatenate."""
    parts: list[str] = []
    for fname in file_names:
        fpath = os.path.join(_REFERENCES_DIR, fname)
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                content = f.read().strip()
            if content:
                parts.append(f"--- {fname} ---\n{content}")
        except FileNotFoundError:
            pass  # skip missing files silently
        except Exception:
            pass
    return "\n\n".join(parts)


def _retrieve_tier2(question: str, topic_hints: list[str] | None) -> str:
    """Call the Qdrant retriever and format chunks as a context string."""
    try:
        chunks = retriever.retrieve_chunks(question, topic_hints=topic_hints)
    except Exception:
        return ""

    if not chunks:
        return ""

    parts: list[str] = []
    for i, chunk in enumerate(chunks, 1):
        source = chunk.get("source_name", "unknown source")
        section = chunk.get("section_heading", "")
        text = chunk.get("text", "")
        header = f"[Chunk {i}] {source}"
        if section:
            header += f" — {section}"
        parts.append(f"{header}\n{text}")

    return "\n\n".join(parts)


def _check_escalation(question: str) -> str | None:
    """Check for urgent or legal escalation keywords. Return warning or None."""
    for pat in _ESCALATION_URGENT:
        if pat.search(question):
            return (
                "**Urgent situation detected.** If you are being illegally evicted or locked out, "
                "call the **Shelter helpline immediately: 0808 800 4444** (free, 8am-8pm weekdays, "
                "8am-5pm weekends). If you feel unsafe, call **999**.\n\n"
            )

    for pat in _ESCALATION_LEGAL:
        if pat.search(question):
            return (
                "**This may involve legal proceedings.** The guidance below is general information only. "
                "For tribunal or court matters, consider getting advice from a solicitor, "
                "your local Citizens Advice, or the **Shelter helpline: 0808 800 4444**.\n\n"
            )

    return None


def _rights_chat(
    question: str,
    context: str,
    history: list | None,
    deep: bool,
) -> str:
    """Call the LLM to answer a tenant rights question given context."""
    client = _get_llm_client()
    model = _RIGHTS_MODEL_DEEP if deep else _RIGHTS_MODEL_QUICK

    messages: list[dict] = [{"role": "system", "content": _SYSTEM_PROMPT}]

    # Include recent chat history for conversational context
    if history:
        for user_msg, assistant_msg in history[-4:]:
            messages.append({"role": "user", "content": user_msg})
            messages.append({"role": "assistant", "content": assistant_msg})

    # Build the user message with context
    user_content = f"Legal context:\n{context}\n\nQuestion: {question}"
    messages.append({"role": "user", "content": user_content})

    t0 = time.perf_counter()
    try:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.2,
        )
        answer = response.choices[0].message.content.strip()
        elapsed = time.perf_counter() - t0
        print(f"[TIMING] rights_chat model={model} elapsed={elapsed:.2f}s")
        return answer
    except Exception as exc:
        print(f"[ERROR] rights_chat failed: {exc}")
        return (
            "I'm sorry, I wasn't able to generate an answer right now. "
            "For urgent tenant rights questions, please contact **Shelter** on 0808 800 4444 "
            "or visit **citizensadvice.org.uk**."
        )


# ---------------------------------------------------------------------------
# Fallback menu — shown when no context is found
# ---------------------------------------------------------------------------

_FALLBACK_MENU = (
    "I can help with the following UK tenant rights topics:\n\n"
    "- **Deposits** — protection schemes, deductions, getting your deposit back\n"
    "- **Eviction** — Section 21, Section 8, notice periods, grounds for possession\n"
    "- **Repairs** — landlord obligations, damp & mould, Section 11, Awaab's Law\n"
    "- **Rent increases** — Section 13 notices, challenging above-market increases\n"
    "- **Harassment** — quiet enjoyment, illegal entry, utility cut-offs\n"
    "- **Fees** — Tenant Fees Act, permitted payments\n"
    "- **Retaliatory eviction** — protections after complaints\n"
    "- **Tenancy types** — AST, periodic, fixed-term, break clauses\n"
    "- **Pets & discrimination** — pet clauses, DSS discrimination, blanket bans\n\n"
    "Ask me a specific question about any of these topics."
)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def answer_rights_question(
    question: str,
    chat_history: list | None = None,
    deep: bool = False,
) -> str:
    """Answer a tenant rights question using Tier 1 + Tier 2 context.

    Parameters
    ----------
    question : str
        The user's tenant rights question.
    chat_history : list | None
        List of (user_msg, assistant_msg) tuples for conversational context.
    deep : bool
        If True, use the deep (more capable) model for answer generation.

    Returns
    -------
    str
        The assembled response with optional escalation warning, mode label,
        answer, and disclaimer.
    """
    # 1. Classify the question into topics
    topics = topic_router.classify(question)
    print(f"[RIGHTS] topics={topics}")

    # 2. Tier 1: curated reference files
    tier1_context = ""
    if topics:
        ref_files = topic_router.get_reference_files(topics)
        tier1_context = _load_references(ref_files)

    # 3. Tier 2: Qdrant vector retrieval
    tier2_context = _retrieve_tier2(question, topic_hints=topics or None)

    # 4. Combine contexts
    context_parts: list[str] = []
    if tier1_context:
        context_parts.append("=== PRIMARY LEGAL REFERENCES ===\n" + tier1_context)
    if tier2_context:
        context_parts.append("=== SUPPLEMENTARY CONTEXT ===\n" + tier2_context)

    combined_context = "\n\n".join(context_parts)

    # If both tiers are empty, return fallback menu
    if not combined_context.strip():
        return _FALLBACK_MENU

    # 5. Escalation check
    escalation = _check_escalation(question)

    # 6. LLM answer generation
    answer = _rights_chat(question, combined_context, chat_history, deep)

    # 7. Assemble response
    parts: list[str] = []
    if escalation:
        parts.append(escalation)

    mode_label = "*Deep mode*" if deep else "*Quick mode*"
    parts.append(mode_label)
    parts.append(answer)
    parts.append(_DISCLAIMER)

    return "\n\n".join(parts)
