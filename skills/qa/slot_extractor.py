import re
from dataclasses import dataclass
from typing import Dict, List, Optional


_TOPIC_PATTERNS = {
    "school": [
        r"\bschool\b",
        r"\bschools\b",
        r"\bprimary\b",
        r"\bsecondary\b",
        r"\bcatchment\b",
        r"\bnursery\b",
        r"\bcollege\b",
        r"\buni(?:versity)?\b",
    ],
    "station": [
        r"\bstation\b",
        r"\btube\b",
        r"\bunderground\b",
        r"\bmetro\b",
        r"\btrain\b",
        r"\btransport\b",
        r"\bwalk(?:ing)?\b",
        r"\bdistance\b",
        r"\bmin(?:ute)?s?\b",
        r"\bcommute\b",
    ],
    "furniture": [
        r"\bfurnish(?:ed|ing)?\b",
        r"\bunfurnished\b",
        r"\bpart[- ]?furnished\b",
        r"\bfurniture\b",
    ],
    "gym": [
        r"\bgym\b",
        r"\bfitness\b",
    ],
    "pet": [
        r"\bpet\b",
        r"\bpets\b",
        r"\bdog\b",
        r"\bcat\b",
    ],
}

_STOPWORDS = {
    "the",
    "a",
    "an",
    "is",
    "are",
    "do",
    "does",
    "it",
    "have",
    "has",
    "with",
    "near",
    "from",
    "to",
    "of",
    "for",
    "on",
    "in",
    "at",
    "this",
    "that",
    "there",
    "any",
    "how",
    "far",
    "away",
    "about",
}

_ORDINAL_MAP = {
    "first": 1,
    "second": 2,
    "third": 3,
    "fourth": 4,
    "fifth": 5,
}


@dataclass
class QASlots:
    topic: str
    target_index: Optional[int]
    keywords: List[str]
    raw_question: str


def _extract_target_index(text: str) -> Optional[int]:
    t = (text or "").strip().lower()
    if not t:
        return None

    m_hash = re.match(r"^#\s*(\d{1,2})\s*$", t)
    if m_hash:
        return int(m_hash.group(1))

    m_listing = re.match(r"^(?:listing|result|option|property|flat)\s*#?\s*(\d{1,2})\s*$", t)
    if m_listing:
        return int(m_listing.group(1))

    if t in _ORDINAL_MAP:
        return _ORDINAL_MAP[t]

    m_ordinal = re.match(r"^(?:the\s+)?(first|second|third|fourth|fifth)(?:\s+one)?\s*$", t)
    if m_ordinal:
        return _ORDINAL_MAP.get(m_ordinal.group(1))

    return None


def _detect_topic(text: str) -> str:
    t = (text or "").lower()
    for topic, patterns in _TOPIC_PATTERNS.items():
        for p in patterns:
            if re.search(p, t):
                return topic
    return "general"


def _extract_keywords(text: str) -> List[str]:
    words = re.findall(r"[a-zA-Z0-9\-\+']+", (text or "").lower())
    out: List[str] = []
    seen = set()
    for w in words:
        if len(w) <= 2:
            continue
        if w in _STOPWORDS:
            continue
        if w in seen:
            continue
        seen.add(w)
        out.append(w)
    return out[:12]


def extract_qa_slots(question: str) -> QASlots:
    q = str(question or "").strip()
    return QASlots(
        topic=_detect_topic(q),
        target_index=_extract_target_index(q),
        keywords=_extract_keywords(q),
        raw_question=q,
    )


def slots_to_dict(slots: QASlots) -> Dict[str, object]:
    return {
        "topic": slots.topic,
        "target_index": slots.target_index,
        "keywords": list(slots.keywords),
        "raw_question": slots.raw_question,
    }
