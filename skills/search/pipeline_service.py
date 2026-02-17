from datetime import datetime
from dataclasses import dataclass
from typing import Any, Callable, Dict

import copy
import json
import os

from core.chatbot_config import GROUNDED_EXPLAIN_SYSTEM
from core.settings import (
    DEFAULT_K,
    ENABLE_STAGE_D_EXPLAIN,
    RANKING_LOG_PATH,
    STRUCTURED_POLICY,
    VERBOSE_STATE_LOG,
)


@dataclass
class ExtractDeps:
    llm_extract_all_signals: Callable[..., Any]
    llm_extract: Callable[..., Any]
    repair_extracted_constraints: Callable[..., Any]
    apply_structured_policy: Callable[..., Any]
    append_structured_conflict_log: Callable[..., Any]
    append_structured_training_samples: Callable[..., Any]
    merge_constraints: Callable[..., Any]
    normalize_budget_to_pcm: Callable[..., Any]
    normalize_constraints: Callable[..., Any]
    summarize_constraint_changes: Callable[..., Any]
    compact_constraints_view: Callable[..., Any]
    split_query_signals: Callable[..., Any]


@dataclass
class SearchDeps:
    build_stage_a_query: Callable[..., Any]
    stage_a_search: Callable[..., Any]
    candidate_snapshot: Callable[..., Any]
    apply_hard_filters_with_audit: Callable[..., Any]
    rank_stage_c: Callable[..., Any]
    build_stage_a_records: Callable[..., Any]
    summarize_stage_b_failures: Callable[..., Any]
    build_stage_c_records: Callable[..., Any]


@dataclass
class ExplainDeps:
    build_evidence_for_row: Callable[..., Any]
    llm_grounded_explain: Callable[..., Any]
    render_stage_d_for_user: Callable[..., Any]
    format_grounded_evidence: Callable[..., Any]
    format_listing_row: Callable[..., Any]


@dataclass
class LoggingDeps:
    append_ranking_log_entry: Callable[..., Any]
    log_message: Callable[..., Any]


@dataclass
class PipelineDeps:
    stage_note: Callable[[str, str], None]
    extract: ExtractDeps
    search: SearchDeps
    explain: ExplainDeps
    logging: LoggingDeps

    @property
    def llm_extract_all_signals(self) -> Callable[..., Any]:
        return self.extract.llm_extract_all_signals

    @property
    def llm_extract(self) -> Callable[..., Any]:
        return self.extract.llm_extract

    @property
    def repair_extracted_constraints(self) -> Callable[..., Any]:
        return self.extract.repair_extracted_constraints

    @property
    def apply_structured_policy(self) -> Callable[..., Any]:
        return self.extract.apply_structured_policy

    @property
    def append_structured_conflict_log(self) -> Callable[..., Any]:
        return self.extract.append_structured_conflict_log

    @property
    def append_structured_training_samples(self) -> Callable[..., Any]:
        return self.extract.append_structured_training_samples

    @property
    def merge_constraints(self) -> Callable[..., Any]:
        return self.extract.merge_constraints

    @property
    def normalize_budget_to_pcm(self) -> Callable[..., Any]:
        return self.extract.normalize_budget_to_pcm

    @property
    def normalize_constraints(self) -> Callable[..., Any]:
        return self.extract.normalize_constraints

    @property
    def summarize_constraint_changes(self) -> Callable[..., Any]:
        return self.extract.summarize_constraint_changes

    @property
    def compact_constraints_view(self) -> Callable[..., Any]:
        return self.extract.compact_constraints_view

    @property
    def split_query_signals(self) -> Callable[..., Any]:
        return self.extract.split_query_signals

    @property
    def build_stage_a_query(self) -> Callable[..., Any]:
        return self.search.build_stage_a_query

    @property
    def stage_a_search(self) -> Callable[..., Any]:
        return self.search.stage_a_search

    @property
    def candidate_snapshot(self) -> Callable[..., Any]:
        return self.search.candidate_snapshot

    @property
    def apply_hard_filters_with_audit(self) -> Callable[..., Any]:
        return self.search.apply_hard_filters_with_audit

    @property
    def rank_stage_c(self) -> Callable[..., Any]:
        return self.search.rank_stage_c

    @property
    def build_stage_a_records(self) -> Callable[..., Any]:
        return self.search.build_stage_a_records

    @property
    def summarize_stage_b_failures(self) -> Callable[..., Any]:
        return self.search.summarize_stage_b_failures

    @property
    def build_stage_c_records(self) -> Callable[..., Any]:
        return self.search.build_stage_c_records

    @property
    def build_evidence_for_row(self) -> Callable[..., Any]:
        return self.explain.build_evidence_for_row

    @property
    def llm_grounded_explain(self) -> Callable[..., Any]:
        return self.explain.llm_grounded_explain

    @property
    def render_stage_d_for_user(self) -> Callable[..., Any]:
        return self.explain.render_stage_d_for_user

    @property
    def format_grounded_evidence(self) -> Callable[..., Any]:
        return self.explain.format_grounded_evidence

    @property
    def format_listing_row(self) -> Callable[..., Any]:
        return self.explain.format_listing_row

    @property
    def append_ranking_log_entry(self) -> Callable[..., Any]:
        return self.logging.append_ranking_log_entry

    @property
    def log_message(self) -> Callable[..., Any]:
        return self.logging.log_message


def run_normal_query(
    *,
    user_in: str,
    state: Dict[str, Any],
    qdrant_client: Any,
    embedder: Any,
    deps: PipelineDeps,
) -> Dict[str, Any]:
    stage_note = deps.stage_note

    prev_constraints = dict(state["constraints"] or {})
    stage_note("Pre Stage A", "Parsing input and extracting/repairing constraints and preference signals")
    semantic_parse_source = "llm_combined"
    combined = {"constraints": {}, "semantic_terms": {}}
    llm_extracted: Dict[str, Any] = {}
    rule_extracted: Dict[str, Any] = {}
    structured_audit: Dict[str, Any] = {}
    try:
        combined = deps.llm_extract_all_signals(user_in, state["constraints"])
        llm_extracted = combined.get("constraints") or {}
        semantic_terms = combined.get("semantic_terms") or {}
    except Exception:
        semantic_parse_source = "fallback_split_calls"
        llm_extracted = deps.llm_extract(user_in, state["constraints"])
        semantic_terms = {}
    llm_extracted_raw = copy.deepcopy(llm_extracted or {})
    rule_extracted = deps.repair_extracted_constraints(llm_extracted, user_in)
    extracted, structured_audit = deps.apply_structured_policy(
        user_text=user_in,
        llm_constraints=llm_extracted,
        rule_constraints=rule_extracted,
        policy=STRUCTURED_POLICY,
    )
    if str(os.environ.get("RENT_STRUCTURED_DEBUG_PRINT", "0")).strip().lower() in {"1", "true", "yes", "on"}:
        llm_loc = (llm_extracted_raw or {}).get("location_keywords") or []
        rule_loc = (rule_extracted or {}).get("location_keywords") or []
        final_loc = (extracted or {}).get("location_keywords") or []
        deps.log_message(
            "INFO",
            "structured_debug location_keywords "
            + json.dumps(
                {
                    "llm": llm_loc,
                    "rule": rule_loc,
                    "final": final_loc,
                    "policy": STRUCTURED_POLICY,
                },
                ensure_ascii=False,
            ),
        )
    deps.append_structured_conflict_log(
        user_text=user_in,
        semantic_parse_source=semantic_parse_source,
        audit=structured_audit,
    )
    deps.append_structured_training_samples(
        user_text=user_in,
        semantic_parse_source=semantic_parse_source,
        audit=structured_audit,
    )
    state["constraints"] = deps.merge_constraints(state["constraints"], extracted)
    state["constraints"] = deps.normalize_budget_to_pcm(state["constraints"])
    state["constraints"] = deps.normalize_constraints(state["constraints"])

    changes_line = deps.summarize_constraint_changes(prev_constraints, state["constraints"])
    active_line = deps.compact_constraints_view(state["constraints"])
    stage_note("Pre Stage A", f"Because the input changed constraints, state was updated to: {changes_line}")
    stage_note(
        "Pre Stage A",
        f"Because retrieval/filtering depends on active constraints, current constraints: {json.dumps(active_line, ensure_ascii=False)}",
    )
    c = state["constraints"] or {}
    signals = deps.split_query_signals(
        user_in,
        c,
        precomputed_semantic_terms=semantic_terms,
        semantic_parse_source=semantic_parse_source,
    )

    deps.log_message("INFO", f"state changes: {changes_line}")
    deps.log_message("INFO", f"state active_constraints: {json.dumps(active_line, ensure_ascii=False)}")
    conflict_count = int(structured_audit.get("conflict_count", 0))
    if conflict_count > 0:
        deps.log_message(
            "INFO",
            f"state structured_conflicts: policy={STRUCTURED_POLICY}, "
            f"count={conflict_count}, agreement_rate={float(structured_audit.get('agreement_rate', 1.0)):.3f}",
        )
    if VERBOSE_STATE_LOG:
        deps.log_message("DEBUG", f"state verbose llm_constraints: {json.dumps(llm_extracted, ensure_ascii=False)}")
        deps.log_message("DEBUG", f"state verbose rule_constraints: {json.dumps(rule_extracted, ensure_ascii=False)}")
        deps.log_message("DEBUG", f"state verbose selected_constraints: {json.dumps(extracted, ensure_ascii=False)}")
        deps.log_message("DEBUG", f"state verbose llm_semantic_terms: {json.dumps(semantic_terms, ensure_ascii=False)}")
        deps.log_message("DEBUG", f"state verbose signals: {json.dumps(signals, ensure_ascii=False)}")

    k = int(c.get("k", DEFAULT_K) or DEFAULT_K)
    recall = int(state["recall"])
    query = deps.build_stage_a_query(signals, user_in)

    stage_note("Stage A", f"Because we need a broad candidate pool first, running vector recall (recall={recall})")
    stage_a_df = deps.stage_a_search(qdrant_client, embedder, query=query, recall=recall, c=c)
    prefilter_count = stage_a_df.attrs.get("prefilter_count") if hasattr(stage_a_df, "attrs") else None
    if prefilter_count is not None:
        stage_note(
            "Stage A",
            f"Because prefilter finished first, candidate pool={prefilter_count}; after vector recall limit, got {len(stage_a_df)} candidates",
        )
    else:
        stage_note("Stage A", f"Because recall finished, got {len(stage_a_df)} candidates")
    stage_a_records = deps.build_stage_a_records(stage_a_df, deps.candidate_snapshot)

    stage_note("Stage B", "Because these are hard constraints, applying hard filters (budget/layout/move-in, etc.)")
    filtered, hard_audits = deps.apply_hard_filters_with_audit(stage_a_df, c)
    stage_b_pass_records = [x for x in hard_audits if x.get("hard_pass")]
    fail_brief = deps.summarize_stage_b_failures(hard_audits)
    if fail_brief:
        stage_note("Stage B", f"Because of hard filtering, result is pass={len(filtered)}/{len(stage_a_df)}; top eliminations: {fail_brief}")
    else:
        stage_note("Stage B", f"Because of hard filtering, result is pass={len(filtered)}/{len(stage_a_df)}")

    pref_terms_all = (
        list(signals.get("topic_preferences", {}).get("transit_terms", []) or [])
        + list(signals.get("topic_preferences", {}).get("school_terms", []) or [])
        + list(signals.get("general_semantic", []) or [])
    )
    pref_preview = ", ".join([str(x) for x in pref_terms_all[:3]]) if pref_terms_all else "no explicit preference"
    stage_note("Stage C", f"Because preference signals are [{pref_preview}], running soft rerank and unknown-pass penalties")
    ranked, stage_c_weights = deps.rank_stage_c(filtered, signals, embedder=embedder)
    stage_note("Stage C", f"Because reranking finished, ranked={len(ranked)}; weights={json.dumps(stage_c_weights, ensure_ascii=False)}")
    stage_c_records = deps.build_stage_c_records(ranked, deps.candidate_snapshot, stage_c_weights)

    deps.log_message(
        "INFO",
        f"pipeline counts: stageA={len(stage_a_df)} stageB={len(filtered)} "
        f"stageC={len(ranked)} k={k} recall={recall}",
    )
    stage_d_payload: Dict[str, Any] = None
    stage_d_output: str = ""
    stage_d_raw_output: str = ""
    stage_d_error: str = ""

    pre_reply_messages = []
    if len(filtered) < k:
        pre_reply_messages.append(
            "Not enough listings pass current hard constraints (price/bedrooms/bathrooms/move-in/furnishing/tenancy/size). You can relax budget or update constraints."
        )
        df = ranked.reset_index(drop=True)
    else:
        df = ranked.head(k).reset_index(drop=True)

    if ENABLE_STAGE_D_EXPLAIN and df is not None and len(df) > 0:
        stage_note("Stage D", "Because explainability is required, building evidence and generating grounded explanation")
        df = df.copy()
        df["evidence"] = df.apply(lambda row: deps.build_evidence_for_row(row.to_dict(), c, user_in), axis=1)

    if df is None or len(df) == 0:
        deps.append_ranking_log_entry(
            RANKING_LOG_PATH,
            {
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "log_path": RANKING_LOG_PATH,
                "user_query": user_in,
                "stage_a_query": query,
                "constraints": c,
                "structured_audit": structured_audit,
                "signals": signals,
                "counts": {"stage_a": len(stage_a_df), "stage_b": len(filtered), "stage_c": len(ranked), "k": k, "recall": recall},
                "stage_a_candidates": stage_a_records,
                "stage_b_hard_audit": hard_audits,
                "stage_b_pass_candidates": stage_b_pass_records,
                "stage_c_candidates": stage_c_records,
                "stage_d": {
                    "enabled": True,
                    "system_prompt": GROUNDED_EXPLAIN_SYSTEM,
                    "payload": None,
                    "output": "",
                    "raw_output": "",
                    "error": "no_candidates",
                },
            },
        )
        out = "I couldn't find any matching listings. Try different keywords (area, budget, bedrooms, bathrooms, available date)."
        return {
            "out": out,
            "query": query,
            "df": df,
            "stop_turn": True,
            "pre_reply_messages": pre_reply_messages,
        }

    top_lines = [f"Top {min(k, len(df))} results:"]
    for i, r in df.iterrows():
        top_lines.append(deps.format_listing_row(r.to_dict(), i + 1, view_mode=state.get("view_mode", "summary")))
    lines = []
    if state.get("view_mode", "summary") == "debug":
        lines.extend(top_lines)
    if ENABLE_STAGE_D_EXPLAIN:
        try:
            grounded_out, stage_d_payload, stage_d_raw_output = deps.llm_grounded_explain(
                user_query=user_in,
                c=c,
                signals=signals,
                df=df,
            )
            stage_d_output = grounded_out
            if grounded_out:
                lines.append("")
                lines.append("Recommendation summary:")
                if state.get("view_mode", "summary") == "debug":
                    lines.append(grounded_out)
                else:
                    lines.append(deps.render_stage_d_for_user(grounded_out, df=df, max_items=min(8, len(df))))
            elif state.get("view_mode", "summary") != "debug":
                lines.extend(top_lines)
            if state.get("view_mode", "summary") == "debug":
                ev_txt = deps.format_grounded_evidence(df=df, max_items=min(8, len(df)))
                if ev_txt:
                    lines.append("")
                    lines.append("Grounded evidence:")
                    lines.append(ev_txt)
        except Exception as e:
            stage_d_error = str(e)
            if state.get("view_mode", "summary") == "debug":
                lines.append("")
                lines.append(f"[warn] grounded explanation unavailable: {e}")
            lines.extend(top_lines)
    else:
        stage_d_error = "disabled_by_config"
        lines.extend(top_lines)
    deps.append_ranking_log_entry(
        RANKING_LOG_PATH,
        {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "log_path": RANKING_LOG_PATH,
            "user_query": user_in,
            "stage_a_query": query,
            "constraints": c,
            "structured_audit": structured_audit,
            "signals": signals,
            "counts": {"stage_a": len(stage_a_df), "stage_b": len(filtered), "stage_c": len(ranked), "k": k, "recall": recall},
            "stage_a_candidates": stage_a_records,
            "stage_b_hard_audit": hard_audits,
            "stage_b_pass_candidates": stage_b_pass_records,
            "stage_c_candidates": stage_c_records,
            "stage_d": {
                "enabled": True,
                "system_prompt": GROUNDED_EXPLAIN_SYSTEM,
                "payload": stage_d_payload,
                "output": stage_d_output,
                "raw_output": stage_d_raw_output,
                "error": stage_d_error,
            },
        },
    )
    out = "\n".join(lines)
    return {
        "out": out,
        "query": query,
        "df": df,
        "stop_turn": False,
        "pre_reply_messages": pre_reply_messages,
    }
