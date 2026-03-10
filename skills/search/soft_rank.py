"""Stage C -- soft ranking: deposit, freshness, preference-vector, and unknown-field penalties."""

import json
import math
import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
try:
    from fastembed import TextEmbedding as SentenceTransformer  # type: ignore[assignment]
except ImportError:
    from sentence_transformers import SentenceTransformer  # type: ignore[no-redef]

from core.internal_helpers import _collect_value_candidates, _embed_texts_cached, _score_intent_group
from core.settings import (
    DEPOSIT_MISSING_POLICY,
    DEPOSIT_SCORE_CAP,
    DEPOSIT_SCORE_TAU,
    FRESHNESS_HALF_LIFE_DAYS,
    FRESHNESS_MISSING_POLICY,
    INTENT_HIT_THRESHOLD,
    PREF_VECTOR_DESCRIPTION_WEIGHT,
    PREF_VECTOR_ENABLED,
    PREF_VECTOR_FEATURE_WEIGHT,
    PREF_VECTOR_PATH,
    SEMANTIC_TOP_K,
    UNKNOWN_PENALTY_CAP,
    UNKNOWN_PENALTY_WEIGHTS,
    W_BUDGET_HEADROOM,
    W_DEPOSIT,
    W_FRESHNESS,
)
from skills.search.text_utils import _norm_furnish_value, _safe_text, _to_float, parse_jsonish_items
from skills.search.location_match import _normalize_location_keyword
from skills.search.hard_filter import _parse_available_from_date


# ---------------------------------------------------------------------------
# Weight computation
# ---------------------------------------------------------------------------

def compute_stagec_weights(signals: Dict[str, Any]) -> Dict[str, float]:
    has_transit = len(signals.get("topic_preferences", {}).get("transit_terms", [])) > 0
    has_school = len(signals.get("topic_preferences", {}).get("school_terms", [])) > 0

    if has_transit and has_school:
        base = {"transit": 0.45, "school": 0.35, "preference": 0.20}
        penalty = 0.35
    elif has_transit:
        base = {"transit": 0.65, "school": 0.00, "preference": 0.35}
        penalty = 0.30
    elif has_school:
        base = {"transit": 0.00, "school": 0.65, "preference": 0.35}
        penalty = 0.30
    else:
        # Default: No specific intents. Balance weights across metadata signals.
        base = {"transit": 0.00, "school": 0.00, "preference": 0.30}
        penalty = 0.20
    return {
        **base,
        "penalty": penalty,
        "deposit": float(W_DEPOSIT),
        "freshness": float(W_FRESHNESS),
        "budget_headroom": float(W_BUDGET_HEADROOM),
    }


# ---------------------------------------------------------------------------
# Deposit scoring
# ---------------------------------------------------------------------------

def _score_deposit(raw_deposit: Any, price_pcm: Any = None) -> Tuple[float, str]:
    raw = _safe_text(raw_deposit).strip()
    if not raw:
        if DEPOSIT_MISSING_POLICY == "neutral":
            return 0.50, "missing->neutral(0.50)"
        return 0.40, "missing->light_penalty(0.40)"
    lowered = raw.lower()
    if lowered in {"ask agent", "ask the agent", "unknown", "not provided", "not known", "n/a", "na"}:
        if DEPOSIT_MISSING_POLICY == "neutral":
            return 0.50, "ask_agent->neutral(0.50)"
        return 0.40, "ask_agent->light_penalty(0.40)"
    num_match = re.search(r"(\d+(?:\.\d+)?)", raw.replace(",", ""))
    if not num_match:
        if DEPOSIT_MISSING_POLICY == "neutral":
            return 0.50, "unparseable->neutral(0.50)"
        return 0.40, "unparseable->light_penalty(0.40)"
    try:
        v = max(0.0, float(num_match.group(1)))
        # Prefer ratio scoring (deposit / monthly_rent) — fairer across price points.
        # A 5-week deposit on £2,000/mo = £2,308 = 1.15× rent → score ≈ 0.56 (tau=2.0).
        # Falls back to absolute scoring when price_pcm is unavailable.
        price = _to_float(price_pcm)
        if price is not None and price > 0:
            ratio = v / price
            tau_ratio = 2.0
            score = math.exp(-ratio / tau_ratio)
            return float(score), f"parsed={v:.0f};price={price:.0f};ratio={ratio:.2f}x;tau={tau_ratio};score={score:.4f}"
        tau = max(1.0, float(DEPOSIT_SCORE_TAU))
        score = math.exp(-v / tau)
        cap = max(1.0, float(DEPOSIT_SCORE_CAP))
        return float(score), f"parsed={v:.0f};tau={tau:.0f};cap_ref={cap:.0f};score={score:.4f}"
    except Exception:
        if DEPOSIT_MISSING_POLICY == "neutral":
            return 0.50, "parse_error->neutral(0.50)"
        return 0.40, "parse_error->light_penalty(0.40)"


# ---------------------------------------------------------------------------
# Freshness scoring
# ---------------------------------------------------------------------------

def _score_freshness(raw_added_date: Any) -> Tuple[float, str]:
    raw = _safe_text(raw_added_date).strip()
    if not raw:
        if FRESHNESS_MISSING_POLICY == "neutral":
            return 0.50, "missing->neutral(0.50)"
        return 0.40, "missing->light_penalty(0.40)"
    lowered = raw.lower()
    today = datetime.utcnow().date()
    if lowered in {"today", "added today"}:
        age_days = 0
    elif lowered in {"yesterday", "added yesterday"}:
        age_days = 1
    else:
        cleaned = re.sub(r"\b(added|on|reduced)\b", " ", raw, flags=re.I)
        dt = pd.to_datetime(cleaned, errors="coerce", dayfirst=True)
        if pd.isna(dt):
            if FRESHNESS_MISSING_POLICY == "neutral":
                return 0.50, "unparseable->neutral(0.50)"
            return 0.40, "unparseable->light_penalty(0.40)"
        age_days = max(0, int((today - dt.date()).days))
    half_life = max(1.0, float(FRESHNESS_HALF_LIFE_DAYS))
    score = math.exp(-math.log(2.0) * (float(age_days) / half_life))
    return float(score), f"age_days={age_days};half_life={half_life:.1f};score={score:.4f}"


# ---------------------------------------------------------------------------
# Budget headroom scoring
# ---------------------------------------------------------------------------

def _score_budget_headroom(price_pcm: Any, max_rent_pcm: Any) -> Tuple[float, str]:
    """Reward listings that are under budget — (budget - price) / budget.

    Returns 0.0 when budget or price is unknown; score ∈ [0, 1].
    A listing at 85% of budget scores 0.15; one at 99% scores 0.01.
    Stage B already filters out listings over budget, so scores are always ≥ 0.
    """
    price = _to_float(price_pcm)
    budget = _to_float(max_rent_pcm)
    if price is None or budget is None or budget <= 0:
        return 0.0, "missing->no_signal(0.0)"
    headroom = max(0.0, (budget - price) / budget)
    return float(headroom), f"price={price:.0f};budget={budget:.0f};headroom={headroom:.4f}"


# ---------------------------------------------------------------------------
# Preference-vector sidecar store
# ---------------------------------------------------------------------------

_PREF_VECTOR_STORE: Optional[Dict[str, Dict[str, Any]]] = None
_PREF_VECTOR_STORE_META: str = ""


def _json_list(v: Any) -> List[Any]:
    if isinstance(v, list):
        return v
    s = _safe_text(v).strip()
    if not s:
        return []
    try:
        obj = json.loads(s)
        return obj if isinstance(obj, list) else []
    except Exception:
        return []


def _load_pref_vector_store() -> Dict[str, Dict[str, Any]]:
    global _PREF_VECTOR_STORE, _PREF_VECTOR_STORE_META
    if _PREF_VECTOR_STORE is not None:
        return _PREF_VECTOR_STORE
    store: Dict[str, Dict[str, Any]] = {}
    if not PREF_VECTOR_ENABLED:
        _PREF_VECTOR_STORE = store
        _PREF_VECTOR_STORE_META = "disabled"
        return store
    if not PREF_VECTOR_PATH or not os.path.exists(PREF_VECTOR_PATH):
        _PREF_VECTOR_STORE = store
        _PREF_VECTOR_STORE_META = "missing_file"
        return store
    try:
        df = pd.read_parquet(PREF_VECTOR_PATH)
        for _, row in df.iterrows():
            url_key = _safe_text(row.get("url"))
            listing_key = _safe_text(row.get("listing_id"))
            rec = {
                "features_segments": _json_list(row.get("features_segments")),
                "description_segments": _json_list(row.get("description_segments")),
                "features_vecs": _json_list(row.get("features_vecs")),
                "description_vecs": _json_list(row.get("description_vecs")),
            }
            if url_key:
                store[f"url::{url_key}"] = rec
            if listing_key:
                store[f"listing_id::{listing_key}"] = rec
        _PREF_VECTOR_STORE_META = f"loaded:{len(store)}"
    except Exception as e:
        _PREF_VECTOR_STORE_META = f"load_error:{e}"
    _PREF_VECTOR_STORE = store
    return store


def _pref_vec_row_key(r: Dict[str, Any]) -> str:
    url = _safe_text(r.get("url"))
    if url:
        return f"url::{url}"
    listing_id = _safe_text(r.get("listing_id"))
    if listing_id:
        return f"listing_id::{listing_id}"
    return ""


def _score_preference_with_sidecar(
    pref_terms: List[str],
    row: Dict[str, Any],
    embedder: SentenceTransformer,
    sim_cache: Dict[str, np.ndarray],
) -> Optional[Tuple[float, List[str], str, List[Dict[str, Any]]]]:
    if not pref_terms:
        return 0.0, [], "no_intents", []
    store = _load_pref_vector_store()
    key = _pref_vec_row_key(row)
    rec = store.get(key)
    if not rec:
        return None

    feat_vecs_raw = rec.get("features_vecs") or []
    desc_vecs_raw = rec.get("description_vecs") or []
    feat_seg = rec.get("features_segments") or []
    desc_seg = rec.get("description_segments") or []

    try:
        feat_vecs = np.array(feat_vecs_raw, dtype="float32") if feat_vecs_raw else np.zeros((0, 0), dtype="float32")
        desc_vecs = np.array(desc_vecs_raw, dtype="float32") if desc_vecs_raw else np.zeros((0, 0), dtype="float32")
    except Exception:
        return None

    if feat_vecs.size == 0 and desc_vecs.size == 0:
        return None

    w_feat = max(0.0, float(PREF_VECTOR_FEATURE_WEIGHT))
    w_desc = max(0.0, float(PREF_VECTOR_DESCRIPTION_WEIGHT))
    top1_w = 0.7
    top2_w = 0.3
    if w_feat <= 0.0 and w_desc <= 0.0:
        return None

    cleaned = []
    seen = set()
    for i in pref_terms:
        s = _safe_text(i).lower()
        if not s or s in seen:
            continue
        seen.add(s)
        cleaned.append(s)
    if not cleaned:
        return 0.0, [], "no_intents", []

    q_vecs = _embed_texts_cached(embedder, cleaned, sim_cache)
    intent_scores: List[float] = []
    hit_terms: List[str] = []
    details: List[str] = []
    evidence: List[Dict[str, Any]] = []

    for intent, qv in zip(cleaned, q_vecs):
        feat_sc = 0.0
        desc_sc = 0.0
        feat_top: List[Tuple[float, int]] = []
        desc_top: List[Tuple[float, int]] = []
        k_top = 2

        if feat_vecs.size > 0:
            sims = np.dot(feat_vecs, qv)
            sims = np.clip((sims + 1.0) / 2.0, 0.0, 1.0)
            feat_top = sorted([(float(v), int(i)) for i, v in enumerate(sims)], key=lambda x: x[0], reverse=True)[:2]
            if feat_top:
                top1 = float(feat_top[0][0])
                top2 = float(feat_top[1][0]) if len(feat_top) > 1 else top1
                feat_sc = float(top1_w * top1 + top2_w * top2)
        if desc_vecs.size > 0:
            sims = np.dot(desc_vecs, qv)
            sims = np.clip((sims + 1.0) / 2.0, 0.0, 1.0)
            desc_top = sorted([(float(v), int(i)) for i, v in enumerate(sims)], key=lambda x: x[0], reverse=True)[:2]
            if desc_top:
                top1 = float(desc_top[0][0])
                top2 = float(desc_top[1][0]) if len(desc_top) > 1 else top1
                desc_sc = float(top1_w * top1 + top2_w * top2)

        den = (w_feat if feat_vecs.size > 0 else 0.0) + (w_desc if desc_vecs.size > 0 else 0.0)
        if den <= 0:
            score = 0.0
        else:
            score = ((w_feat * feat_sc) + (w_desc * desc_sc)) / den
        intent_scores.append(float(score))
        if score >= INTENT_HIT_THRESHOLD:
            hit_terms.append(intent)

        feat_top_show = ", ".join(
            f"features[{idx}]={sim:.4f}:\"{_safe_text(feat_seg[idx])[:120]}\""
            for sim, idx in feat_top
            if idx < len(feat_seg)
        ) or "none"
        desc_top_show = ", ".join(
            f"description[{idx}]={sim:.4f}:\"{_safe_text(desc_seg[idx])[:120]}\""
            for sim, idx in desc_top
            if idx < len(desc_seg)
        ) or "none"
        detail_bits = [
            f"intent='{intent}'",
            f"score={score:.4f}",
            f"features_field_score={feat_sc:.4f}",
            f"description_field_score={desc_sc:.4f}",
            f"field_agg=0.7*top1+0.3*top2",
            f"features_top2_fields=[{feat_top_show}]",
            f"description_top2_fields=[{desc_top_show}]",
        ]
        details.append("; ".join(detail_bits))

        for sim, idx in feat_top:
            text = _safe_text(feat_seg[idx]) if idx < len(feat_seg) else ""
            evidence.append(
                {
                    "intent": intent,
                    "intent_score": float(score),
                    "field": "features",
                    "text": text,
                    "sim": float(sim),
                    "weight": float(w_feat),
                    "weighted": float(w_feat * sim),
                }
            )
        for sim, idx in desc_top:
            text = _safe_text(desc_seg[idx]) if idx < len(desc_seg) else ""
            evidence.append(
                {
                    "intent": intent,
                    "intent_score": float(score),
                    "field": "description",
                    "text": text,
                    "sim": float(sim),
                    "weight": float(w_desc),
                    "weighted": float(w_desc * sim),
                }
            )

    group_score = float(sum(intent_scores) / max(1, len(intent_scores)))
    details.append("group_agg=mean(intent_scores)")
    return group_score, hit_terms, " | ".join(details), evidence


# ---------------------------------------------------------------------------
# Main Stage C entry point
# ---------------------------------------------------------------------------

def rank_stage_c(
    filtered: pd.DataFrame,
    signals: Dict[str, Any],
    embedder: SentenceTransformer,
) -> Tuple[pd.DataFrame, Dict[str, float]]:
    if filtered is None or len(filtered) == 0:
        return pd.DataFrame(), compute_stagec_weights(signals)

    out = filtered.copy()
    weights = compute_stagec_weights(signals)
    hard = signals.get("hard_constraints", {}) or {}
    transit_terms = signals.get("topic_preferences", {}).get("transit_terms", [])
    school_terms = signals.get("topic_preferences", {}).get("school_terms", [])
    pref_terms = signals.get("general_semantic", [])
    location_terms = []
    for x in signals.get("location_intent", []):
        t = _normalize_location_keyword(x)
        if t:
            location_terms.append(t)

    out["transit_score"] = 0.0
    out["school_score"] = 0.0
    out["preference_score"] = 0.0
    out["deposit_score"] = 0.0
    out["freshness_score"] = 0.0
    out["budget_headroom_score"] = 0.0
    out["penalty_score"] = 0.0
    out["location_hit_count"] = 0
    out["transit_hits"] = ""
    out["school_hits"] = ""
    out["preference_hits"] = ""
    out["preference_source"] = ""
    out["penalty_reasons"] = ""
    out["transit_detail"] = ""
    out["school_detail"] = ""
    out["preference_detail"] = ""
    out["deposit_detail"] = ""
    out["freshness_detail"] = ""
    out["budget_headroom_detail"] = ""
    out["penalty_detail"] = ""
    out["transit_evidence"] = ""
    out["school_evidence"] = ""
    out["preference_evidence"] = ""
    sim_cache: Dict[str, np.ndarray] = {}

    for idx, row in out.iterrows():
        r = row.to_dict()
        stations_items = parse_jsonish_items(r.get("stations"))
        schools_items = parse_jsonish_items(r.get("schools"))

        title = _safe_text(r.get("title"))
        address = _safe_text(r.get("address"))
        desc = _safe_text(r.get("description"))
        feats = _safe_text(r.get("features"))
        stations_text = " ; ".join(stations_items)
        schools_text = " ; ".join(schools_items)

        pref_text = " ".join([desc, feats]).strip()
        loc_text = _normalize_location_keyword(
            " ".join([title, address, desc, feats, stations_text, schools_text])
        )

        candidates = _collect_value_candidates(r)
        transit_score, transit_hits, transit_group_detail, transit_evidence = _score_intent_group(
            transit_terms,
            candidates,
            top_k=SEMANTIC_TOP_K,
            embedder=embedder,
            sim_cache=sim_cache,
        )
        school_score, school_hits, school_group_detail, school_evidence = _score_intent_group(
            school_terms,
            candidates,
            top_k=SEMANTIC_TOP_K,
            embedder=embedder,
            sim_cache=sim_cache,
        )
        if not pref_terms:
            pref_score, pref_hits, pref_group_detail, pref_evidence = (0.50, [], "no_intents", [])
            pref_source = "no_intents"
        else:
            pref_source = "sidecar_vectors"
            sidecar_pref = _score_preference_with_sidecar(
                pref_terms=pref_terms,
                row=r,
                embedder=embedder,
                sim_cache=sim_cache,
            )
            if sidecar_pref is not None:
                pref_score, pref_hits, pref_group_detail, pref_evidence = sidecar_pref
            else:
                pref_score, pref_hits, pref_group_detail, pref_evidence = (0.0, [], "fallback_disabled", [])
                pref_source = "sidecar_missing_no_fallback"
        deposit_score, deposit_detail = _score_deposit(r.get("deposit"), r.get("price_pcm"))
        freshness_score, freshness_detail = _score_freshness(r.get("added_date"))
        budget_headroom_score, budget_headroom_detail = _score_budget_headroom(
            r.get("price_pcm"), hard.get("max_rent_pcm")
        )
        loc_hits = sum(1 for loc in location_terms if loc and loc in loc_text)

        penalties = []
        penalty_score = 0.0
        unknown_penalty_raw = 0.0
        unknown_items: List[str] = []
        unknown_item_set = set()

        def _add_unknown(field_key: str) -> None:
            nonlocal unknown_penalty_raw
            if field_key in unknown_item_set:
                return
            w = float(UNKNOWN_PENALTY_WEIGHTS.get(field_key, 0.0))
            if w <= 0.0:
                return
            unknown_item_set.add(field_key)
            unknown_items.append(field_key)
            unknown_penalty_raw += w

        # Penalize unknown values (e.g. "Ask agent") on active hard constraints.
        if hard.get("max_rent_pcm") is not None and _to_float(r.get("price_pcm")) is None:
            _add_unknown("price")
        layout_opts = hard.get("layout_options") or []
        requires_price = any(isinstance(x, dict) and x.get("max_rent_pcm") is not None for x in layout_opts)
        requires_bed = any(isinstance(x, dict) and x.get("bedrooms") is not None for x in layout_opts)
        requires_bath = any(isinstance(x, dict) and x.get("bathrooms") is not None for x in layout_opts)
        requires_prop = any(
            isinstance(x, dict) and _safe_text(x.get("property_type")).strip()
            for x in layout_opts
        )
        if requires_price and _to_float(r.get("price_pcm")) is None:
            _add_unknown("price")
        if requires_bed and _to_float(r.get("bedrooms")) is None:
            _add_unknown("bedrooms")
        if requires_bath and _to_float(r.get("bathrooms")) is None:
            _add_unknown("bathrooms")
        if requires_prop and not _safe_text(r.get("property_type")).strip():
            _add_unknown("property_type")
        if hard.get("available_from") is not None and pd.isna(_parse_available_from_date(r.get("available_from"))):
            _add_unknown("available_from")

        furnish_req = _norm_furnish_value(hard.get("furnish_type"))
        if furnish_req:
            furn_val = _norm_furnish_value(r.get("furnish_type"))
            if not furn_val or furn_val == "ask agent":
                _add_unknown("furnish_type")

        if _safe_text(hard.get("let_type")).strip() and not _safe_text(r.get("let_type")).strip():
            _add_unknown("let_type")

        if hard.get("min_tenancy_months") is not None:
            tenancy_txt = _safe_text(r.get("min_tenancy")).lower()
            if not re.search(r"(\d+(?:\.\d+)?)", tenancy_txt):
                _add_unknown("min_tenancy_months")

        if hard.get("min_size_sqm") is not None:
            if _to_float(r.get("size_sqm")) is None and _to_float(r.get("size_sqft")) is None:
                _add_unknown("min_size_sqm")

        if unknown_penalty_raw > 0.0:
            unknown_penalty = min(float(UNKNOWN_PENALTY_CAP), float(unknown_penalty_raw))
            penalty_score += unknown_penalty
            penalties.append(
                f"unknown_hard({','.join(unknown_items)};+{unknown_penalty:.2f})"
            )

        if transit_terms and not stations_items:
            penalty_score += 0.12
            penalties.append("missing_stations(+0.12)")
        if school_terms and not schools_items:
            penalty_score += 0.12
            penalties.append("missing_schools(+0.12)")
        if pref_terms and not pref_text:
            penalty_score += 0.08
            penalties.append("missing_text(+0.08)")

        out.at[idx, "transit_score"] = float(transit_score)
        out.at[idx, "school_score"] = float(school_score)
        out.at[idx, "preference_score"] = float(pref_score)
        out.at[idx, "deposit_score"] = float(deposit_score)
        out.at[idx, "freshness_score"] = float(freshness_score)
        out.at[idx, "penalty_score"] = float(penalty_score)
        out.at[idx, "location_hit_count"] = int(loc_hits)
        out.at[idx, "transit_hits"] = ", ".join(transit_hits)
        out.at[idx, "school_hits"] = ", ".join(school_hits)
        out.at[idx, "preference_hits"] = ", ".join(pref_hits)
        out.at[idx, "preference_source"] = pref_source
        out.at[idx, "penalty_reasons"] = ", ".join(penalties)
        out.at[idx, "transit_detail"] = (
            f"group_score={transit_score:.4f}; "
            f"hits=[{', '.join(transit_hits)}]; "
            + transit_group_detail
        )
        out.at[idx, "school_detail"] = (
            f"group_score={school_score:.4f}; "
            f"hits=[{', '.join(school_hits)}]; "
            + school_group_detail
        )
        out.at[idx, "preference_detail"] = (
            f"group_score={pref_score:.4f}; "
            f"hits=[{', '.join(pref_hits)}]; "
            + f"source={pref_source}; "
            + pref_group_detail
        )
        out.at[idx, "budget_headroom_score"] = float(budget_headroom_score)
        out.at[idx, "deposit_detail"] = str(deposit_detail)
        out.at[idx, "freshness_detail"] = str(freshness_detail)
        out.at[idx, "budget_headroom_detail"] = str(budget_headroom_detail)
        out.at[idx, "penalty_detail"] = (
            f"sum(active_penalties)={penalty_score:.4f}; "
            f"triggers=[{', '.join(penalties)}]"
        )
        out.at[idx, "transit_evidence"] = json.dumps(transit_evidence, ensure_ascii=False)
        out.at[idx, "school_evidence"] = json.dumps(school_evidence, ensure_ascii=False)
        out.at[idx, "preference_evidence"] = json.dumps(pref_evidence, ensure_ascii=False)

    out["final_score"] = (
        weights["transit"] * out["transit_score"]
        + weights["school"] * out["school_score"]
        + weights["preference"] * out["preference_score"]
        + weights["deposit"] * out["deposit_score"]
        + weights["freshness"] * out["freshness_score"]
        + weights["budget_headroom"] * out["budget_headroom_score"]
        - weights["penalty"] * out["penalty_score"]
    )
    out["score_formula"] = (
        f"final = {weights['transit']:.3f}*transit + "
        f"{weights['school']:.3f}*school + "
        f"{weights['preference']:.3f}*preference + "
        f"{weights['deposit']:.3f}*deposit + "
        f"{weights['freshness']:.3f}*freshness + "
        f"{weights['budget_headroom']:.3f}*budget_headroom - "
        f"{weights['penalty']:.3f}*penalty"
    )
    out["w_transit"] = weights["transit"]
    out["w_school"] = weights["school"]
    out["w_preference"] = weights["preference"]
    out["w_penalty"] = weights["penalty"]
    out["w_deposit"] = weights["deposit"]
    out["w_freshness"] = weights["freshness"]
    out["w_budget_headroom"] = weights["budget_headroom"]

    out = out.sort_values(
        ["final_score", "location_hit_count", "qdrant_score"],
        ascending=[False, False, False],
    ).reset_index(drop=True)
    return out, weights
