"""Contract analysis via LLM."""

import json
import re
from dataclasses import dataclass, asdict
from typing import Optional

from core.llm_client import qwen_client
from core.chatbot_config import QWEN_MODEL, CONTRACT_ANALYSIS_SYSTEM


@dataclass
class ClauseFlag:
    clause_text: str
    issue: str
    severity: str  # "info" | "warning" | "critical"
    advice: str


@dataclass
class ComplianceCheck:
    check: str
    status: str  # "pass" | "fail" | "unknown"
    detail: str


@dataclass
class ContractReport:
    summary: str
    tenancy_type: str
    rent: str
    deposit: str
    break_clause: Optional[str]
    notice_period: str
    clauses: list[ClauseFlag]
    compliance: list[ComplianceCheck]


def analyse_contract(text: str) -> ContractReport:
    """Send contract text to LLM and return a structured ContractReport."""
    # Truncate to ~15000 chars to fit context window
    truncated = text[:15000]

    response = qwen_client.chat.completions.create(
        model=QWEN_MODEL,
        messages=[
            {"role": "system", "content": CONTRACT_ANALYSIS_SYSTEM},
            {"role": "user", "content": f"Analyse this tenancy agreement:\n\n{truncated}"},
        ],
        temperature=0.2,
    )
    raw = response.choices[0].message.content

    # Try to extract JSON from the response (handle markdown fences)
    cleaned = raw.strip()
    m = re.search(r'\{.*\}', cleaned, re.DOTALL)
    if m:
        cleaned = m.group()

    data = json.loads(cleaned)

    _CF = set(ClauseFlag.__dataclass_fields__)
    _CC = set(ComplianceCheck.__dataclass_fields__)
    clauses = [ClauseFlag(**{k: v for k, v in c.items() if k in _CF}) for c in (data.get("clauses") or [])]
    compliance = [ComplianceCheck(**{k: v for k, v in c.items() if k in _CC}) for c in (data.get("compliance") or [])]

    return ContractReport(
        summary=data.get("summary", ""),
        tenancy_type=data.get("tenancy_type", "Unknown"),
        rent=data.get("rent", "Not specified"),
        deposit=data.get("deposit", "Not specified"),
        break_clause=data.get("break_clause"),
        notice_period=data.get("notice_period", "Not specified"),
        clauses=clauses,
        compliance=compliance,
    )
