"""Search handler: pipeline assembly and interactive CLI.

Heavy lifting has been extracted to focused modules:
  - text_utils.py         — text normalization helpers
  - location_match.py     — location keyword matching
  - constraint_extraction.py — rule-based constraint parsing
  - constraint_ops.py     — constraint merge / normalize / diff
  - signals.py            — Stage A query signal building
  - hard_filter.py        — Stage B hard filtering
  - soft_rank.py          — Stage C soft ranking
  - evidence.py           — Stage D evidence building
  - structured_policy.py  — LLM vs rule arbitration
  - formatter.py          — listing row formatting
"""

import json
import re
from typing import Any, Dict, Optional, Tuple

from sentence_transformers import SentenceTransformer

from core.chatbot_config import QWEN_BASE_URL, QWEN_MODEL
from core.llm_client import (
    format_grounded_evidence,
    llm_extract,
    llm_extract_all_signals,
    llm_grounded_explain,
    render_stage_d_for_user,
)
from core.logger import (
    LOG_LEVEL,
    RANKING_LOG_DETAIL,
    append_ranking_log_entry,
    log_message,
)
from core.settings import (
    EMBED_MODEL,
    ENABLE_STAGE_D_EXPLAIN,
    QDRANT_COLLECTION,
    QDRANT_ENABLE_PREFILTER,
    QDRANT_LOCAL_PATH,
    RANKING_LOG_PATH,
    STRUCTURED_CONFLICT_LOG_PATH,
    STRUCTURED_POLICY,
    STRUCTURED_TRAINING_LOG_PATH,
)
from skills.search.engine import load_stage_a_resources, stage_a_search
from skills.search.extractors import (
    compact_constraints_view,
    merge_constraints,
    normalize_constraints,
    repair_extracted_constraints,
    summarize_constraint_changes,
)
from skills.search.pipeline import (
    build_stage_a_records,
    build_stage_c_records,
    summarize_stage_b_failures,
)
from skills.search.pipeline_service import (
    ExplainDeps,
    ExtractDeps,
    LoggingDeps,
    PipelineDeps,
    SearchDeps,
    run_normal_query,
)
from skills.search.state_ops import (
    init_runtime_state,
    parse_command as parse_command_v2,
    reset_runtime_state,
    set_k_value,
    set_recall_value,
    set_view_mode,
)

# Focused sub-modules
from skills.search.signals import (
    build_stage_a_query,
    candidate_snapshot,
    split_query_signals,
)
from skills.search.hard_filter import apply_hard_filters_with_audit
from skills.search.soft_rank import compute_stagec_weights, rank_stage_c
from skills.search.evidence import build_evidence_for_row
from skills.search.structured_policy import (
    apply_structured_policy,
    append_structured_conflict_log,
    append_structured_training_samples,
)

# Re-export formatting helpers for backward compatibility
from skills.search.formatter import (  # noqa: E402
    format_listing_row,
    format_listing_row_debug,
    format_listing_row_summary,
)


# ---------------------------------------------------------------------------
# CLI command parser (thin wrapper — full implementation in state_ops)
# ---------------------------------------------------------------------------

def parse_command(s: str) -> Tuple[Optional[str], str]:
    s = s.strip()
    if not s.startswith("/"):
        return None, ""
    parts = s.split(maxsplit=1)
    cmd = parts[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else ""
    return cmd, arg


# ---------------------------------------------------------------------------
# Pipeline dependency injection
# ---------------------------------------------------------------------------

def build_pipeline_deps(stage_note):
    return PipelineDeps(
        stage_note=stage_note,
        extract=ExtractDeps(
            llm_extract_all_signals=llm_extract_all_signals,
            llm_extract=llm_extract,
            repair_extracted_constraints=repair_extracted_constraints,
            apply_structured_policy=apply_structured_policy,
            append_structured_conflict_log=append_structured_conflict_log,
            append_structured_training_samples=append_structured_training_samples,
            merge_constraints=merge_constraints,
            normalize_constraints=normalize_constraints,
            summarize_constraint_changes=summarize_constraint_changes,
            compact_constraints_view=compact_constraints_view,
            split_query_signals=split_query_signals,
        ),
        search=SearchDeps(
            build_stage_a_query=build_stage_a_query,
            stage_a_search=stage_a_search,
            candidate_snapshot=candidate_snapshot,
            apply_hard_filters_with_audit=apply_hard_filters_with_audit,
            rank_stage_c=rank_stage_c,
            build_stage_a_records=build_stage_a_records,
            summarize_stage_b_failures=summarize_stage_b_failures,
            build_stage_c_records=build_stage_c_records,
        ),
        explain=ExplainDeps(
            build_evidence_for_row=build_evidence_for_row,
            llm_grounded_explain=llm_grounded_explain,
            render_stage_d_for_user=render_stage_d_for_user,
            format_grounded_evidence=format_grounded_evidence,
            format_listing_row=format_listing_row,
        ),
        logging=LoggingDeps(
            append_ranking_log_entry=append_ranking_log_entry,
            log_message=log_message,
        ),
    )


# ---------------------------------------------------------------------------
# Interactive CLI
# ---------------------------------------------------------------------------

def run_chat():
    qdrant_client = load_stage_a_resources()
    embedder = SentenceTransformer(EMBED_MODEL)

    state = init_runtime_state()

    def stage_note(stage: str, detail: str) -> None:
        print(f"\nBot> [{stage}] {detail}")

    print("RentBot (minimal retrieval)")
    print("Commands: /exit /reset /k N /show /recall N /constraints /model /view summary|debug")
    print(f"StageA backend: qdrant")
    print(f"Qdrant path   : {QDRANT_LOCAL_PATH}")
    print(f"Collection    : {QDRANT_COLLECTION}")
    print(f"Qdrant prefilter: {QDRANT_ENABLE_PREFILTER}")
    print(f"Embed: {EMBED_MODEL}")
    print(f"Log  : {RANKING_LOG_PATH}")
    print(f"Structured policy: {STRUCTURED_POLICY}")
    print(f"Stage D explain enabled: {ENABLE_STAGE_D_EXPLAIN}")
    print(f"Structured conflict log: {STRUCTURED_CONFLICT_LOG_PATH}")
    print(f"Structured training samples: {STRUCTURED_TRAINING_LOG_PATH}")
    print("----")

    while True:
        try:
            user_in = input("\nYou> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            break

        if not user_in:
            continue

        cmd, arg = parse_command_v2(user_in)

        if cmd == "/exit":
            print("Bye.")
            break

        if cmd == "/reset":
            reset_runtime_state(state)
            print("State reset.")
            continue

        if cmd == "/k":
            _, msg = set_k_value(state, arg)
            print(msg)
            continue

        if cmd == "/recall":
            _, msg = set_recall_value(state, arg)
            print(msg)
            continue

        if cmd == "/show":
            if state["last_df"] is None or len(state["last_df"]) == 0:
                print("No previous results.")
                continue
            df = state["last_df"]
            print(f"\nBot> Showing last results (k={state['k']}, recall={state['recall']})")
            for i, r in df.iterrows():
                print(format_listing_row(r.to_dict(), i + 1, view_mode=state.get("view_mode", "summary")))
            continue

        if cmd == "/view":
            _, msg = set_view_mode(state, arg)
            print(msg)
            continue

        if cmd == "/constraints":
            print(json.dumps(state.get("constraints") or {}, ensure_ascii=False, indent=2))
            continue

        if cmd == "/model":
            print(f"QWEN_BASE_URL={QWEN_BASE_URL}")
            print(f"QWEN_MODEL={QWEN_MODEL}")
            print(f"RENT_STRUCTURED_POLICY={STRUCTURED_POLICY}")
            print("RENT_STAGEA_BACKEND=qdrant (fixed)")
            print(f"RENT_QDRANT_ENABLE_PREFILTER={QDRANT_ENABLE_PREFILTER}")
            print(f"RENT_LOG_LEVEL={LOG_LEVEL}")
            print(f"RENT_RANKING_LOG_DETAIL={RANKING_LOG_DETAIL}")
            continue

        result = run_normal_query(
            user_in=user_in,
            state=state,
            qdrant_client=qdrant_client,
            embedder=embedder,
            deps=build_pipeline_deps(stage_note),
        )
        for msg in result.get("pre_reply_messages", []):
            print("\nBot> " + msg)
        out = result["out"]
        print("\nBot> " + out)
        state["history"].append((user_in, out))
        state["last_query"] = result["query"]
        state["last_df"] = result["df"]
        if result.get("stop_turn"):
            continue


if __name__ == "__main__":
    run_chat()
