from typing import Any, Dict, List


def build_stage_a_records(stage_a_df, candidate_snapshot) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if stage_a_df is None or len(stage_a_df) == 0:
        return out
    for i, row in stage_a_df.reset_index(drop=True).iterrows():
        rec = candidate_snapshot(row.to_dict())
        rec["rank"] = i + 1
        rec["score"] = rec.get("qdrant_score")
        rec["score_formula"] = "score = qdrant_cosine_similarity(query_A, listing_embedding)"
        out.append(rec)
    return out


def summarize_stage_b_failures(hard_audits: List[Dict[str, Any]]) -> str:
    fail_counter: Dict[str, int] = {}
    for rec in hard_audits:
        if rec.get("hard_pass"):
            continue
        reasons = rec.get("hard_fail_reasons") or []
        if not reasons:
            continue
        key = str(reasons[0]).split(" ", 1)[0]
        fail_counter[key] = fail_counter.get(key, 0) + 1
    return ", ".join(
        [f"{k}:{v}" for k, v in sorted(fail_counter.items(), key=lambda x: x[1], reverse=True)[:3]]
    )


def build_stage_c_records(ranked, candidate_snapshot, stage_c_weights: Dict[str, float]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if ranked is None or len(ranked) == 0:
        return out
    for i, row in ranked.iterrows():
        rec = candidate_snapshot(row.to_dict())
        rec["rank"] = i + 1
        rec["score"] = float(row.get("final_score", 0.0))
        rec["score_formula"] = str(row.get("score_formula", ""))
        rec["components"] = {
            "transit_score": float(row.get("transit_score", 0.0)),
            "school_score": float(row.get("school_score", 0.0)),
            "preference_score": float(row.get("preference_score", 0.0)),
            "penalty_score": float(row.get("penalty_score", 0.0)),
            "weights": stage_c_weights,
        }
        rec["hits"] = {
            "transit_hits": str(row.get("transit_hits", "") or ""),
            "school_hits": str(row.get("school_hits", "") or ""),
            "preference_hits": str(row.get("preference_hits", "") or ""),
            "penalty_reasons": str(row.get("penalty_reasons", "") or ""),
        }
        out.append(rec)
    return out
