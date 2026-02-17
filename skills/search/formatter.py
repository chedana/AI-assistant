import json
import re
from typing import Any, Dict, List

from skills.search.extractors import _safe_text, _to_float


def format_listing_row_debug(r: Dict[str, Any], i: int) -> str:
    title = str(r.get("title", "") or "").strip()
    url = str(r.get("url", "") or "").strip()
    address = str(r.get("address", "") or "").strip()
    price_pcm = r.get("price_pcm", None)
    beds = r.get("bedrooms", None)
    baths = r.get("bathrooms", None)

    def norm_num(x):
        if x is None:
            return None
        try:
            if isinstance(x, str):
                x2 = re.sub(r"[^\d\.]", "", x)
                return float(x2) if x2 else None
            return float(x)
        except Exception:
            return None

    price = norm_num(price_pcm)
    beds_n = None
    try:
        beds_n = int(float(beds)) if beds is not None and str(beds).strip() != "" else None
    except Exception:
        beds_n = None

    baths_n = None
    try:
        baths_n = int(float(baths)) if baths is not None and str(baths).strip() != "" else None
    except Exception:
        baths_n = None

    bits = []
    bits.append(f"{i}. {title}" if title else f"{i}. (no title)")
    line2 = []
    if price is not None:
        line2.append(f"£{int(round(price))}/pcm")
    else:
        if price_pcm is not None and str(price_pcm).strip():
            line2.append(f"{price_pcm} pcm")
    if beds_n is not None:
        line2.append(f"{beds_n} bed")
    elif beds is not None and str(beds).strip():
        line2.append(f"{beds} bed")
    if baths_n is not None:
        line2.append(f"{baths_n} bath")
    elif baths is not None and str(baths).strip():
        line2.append(f"{baths} bath")

    if address:
        line2.append(address)
    if line2:
        bits.append("   " + " | ".join(line2))
    if url:
        bits.append("   " + url)

    if r.get("final_score", None) is not None:
        def f(x):
            try:
                return f"{float(x):.4f}"
            except Exception:
                return "0.0000"

        formula = str(r.get("score_formula", "") or "").strip()
        if formula:
            bits.append("   " + f"score: final={f(r.get('final_score'))} | {formula}")
        else:
            bits.append("   " + f"score: final={f(r.get('final_score'))}")

        if r.get("transit_score") is not None or r.get("school_score") is not None:
            bits.append(
                "   "
                + f"components: transit={f(r.get('transit_score'))}, "
                + f"school={f(r.get('school_score'))}, "
                + f"preference={f(r.get('preference_score'))}, "
                + f"deposit={f(r.get('deposit_score'))}, "
                + f"freshness={f(r.get('freshness_score'))}, "
                + f"penalty={f(r.get('penalty_score'))}"
            )
            try:
                wt = float(r.get("w_transit", 0.0))
                ws = float(r.get("w_school", 0.0))
                wp = float(r.get("w_preference", 0.0))
                wd = float(r.get("w_deposit", 0.0))
                wf = float(r.get("w_freshness", 0.0))
                wpen = float(r.get("w_penalty", 0.0))
                st = float(r.get("transit_score", 0.0))
                ss = float(r.get("school_score", 0.0))
                sp = float(r.get("preference_score", 0.0))
                sd = float(r.get("deposit_score", 0.0))
                sf = float(r.get("freshness_score", 0.0))
                spe = float(r.get("penalty_score", 0.0))
                c_t = wt * st
                c_s = ws * ss
                c_p = wp * sp
                c_d = wd * sd
                c_f = wf * sf
                c_pen = wpen * spe
                bits.append(
                    "   "
                    + "contrib: "
                    + f"transit={wt:.3f}*{st:.4f}={c_t:.4f}, "
                    + f"school={ws:.3f}*{ss:.4f}={c_s:.4f}, "
                    + f"preference={wp:.3f}*{sp:.4f}={c_p:.4f}, "
                    + f"deposit={wd:.3f}*{sd:.4f}={c_d:.4f}, "
                    + f"freshness={wf:.3f}*{sf:.4f}={c_f:.4f}, "
                    + f"penalty={wpen:.3f}*{spe:.4f}={c_pen:.4f}"
                )
                bits.append(
                    "   "
                    + "final_calc: "
                    + f"{c_t:.4f} + {c_s:.4f} + {c_p:.4f} + {c_d:.4f} + {c_f:.4f} - {c_pen:.4f} = "
                    + f"{(c_t + c_s + c_p + c_d + c_f - c_pen):.4f}"
                )
            except Exception:
                pass
        transit_hits = str(r.get("transit_hits", "") or "").strip()
        school_hits = str(r.get("school_hits", "") or "").strip()
        pref_hits = str(r.get("preference_hits", "") or "").strip()
        pref_source = str(r.get("preference_source", "") or "").strip()
        penalty_reasons = str(r.get("penalty_reasons", "") or "").strip()
        transit_detail = str(r.get("transit_detail", "") or "").strip()
        school_detail = str(r.get("school_detail", "") or "").strip()
        preference_detail = str(r.get("preference_detail", "") or "").strip()
        deposit_detail = str(r.get("deposit_detail", "") or "").strip()
        freshness_detail = str(r.get("freshness_detail", "") or "").strip()
        penalty_detail = str(r.get("penalty_detail", "") or "").strip()
        if transit_hits:
            bits.append("   " + f"transit_hits: {transit_hits}")
        if school_hits:
            bits.append("   " + f"school_hits: {school_hits}")
        if pref_hits:
            bits.append("   " + f"preference_hits: {pref_hits}")
        if pref_source:
            bits.append("   " + f"preference_source: {pref_source}")
        if penalty_reasons:
            bits.append("   " + f"penalty_reasons: {penalty_reasons}")
        if transit_detail:
            bits.append("   " + f"transit_calc: {transit_detail}")
        if school_detail:
            bits.append("   " + f"school_calc: {school_detail}")
        if preference_detail:
            bits.append("   " + f"preference_calc: {preference_detail}")
        if deposit_detail:
            bits.append("   " + f"deposit_calc: {deposit_detail}")
        if freshness_detail:
            bits.append("   " + f"freshness_calc: {freshness_detail}")
        if penalty_detail:
            bits.append("   " + f"penalty_calc: {penalty_detail}")
        pref_ev_raw = r.get("preference_evidence")
        pref_ev: List[Dict[str, Any]] = []
        if isinstance(pref_ev_raw, list):
            pref_ev = [x for x in pref_ev_raw if isinstance(x, dict)]
        elif isinstance(pref_ev_raw, str):
            s = pref_ev_raw.strip()
            if s:
                try:
                    obj = json.loads(s)
                    if isinstance(obj, list):
                        pref_ev = [x for x in obj if isinstance(x, dict)]
                except Exception:
                    pref_ev = []
        if pref_ev:
            bits.append("   preference_top_matches:")
            grouped: Dict[str, List[Dict[str, Any]]] = {}
            intent_order: List[str] = []
            for item in pref_ev:
                it = _safe_text(item.get("intent"))
                if it not in grouped:
                    grouped[it] = []
                    intent_order.append(it)
                grouped[it].append(item)
            for it in intent_order:
                rows = grouped.get(it, [])
                top_rows = sorted(
                    rows,
                    key=lambda x: (_to_float(x.get("sim")) if _to_float(x.get("sim")) is not None else -1.0),
                    reverse=True,
                )[:2]
                for item in top_rows:
                    field = _safe_text(item.get("field"))
                    text = _safe_text(item.get("text"))
                    sim = _to_float(item.get("sim"))
                    if sim is None:
                        bits.append(f"   - pref='{it}' | field={field} | text={text[:120]}")
                    else:
                        bits.append(f"   - pref='{it}' | field={field} | sim={sim:.4f} | text={text[:120]}")

    evidence = r.get("evidence")
    if isinstance(evidence, dict) and evidence:
        bits.append("   evidence: " + json.dumps(evidence, ensure_ascii=False))
    return "\n".join(bits)


def format_listing_row_summary(r: Dict[str, Any], i: int) -> str:
    title = _safe_text(r.get("title")) or "(no title)"
    url = _safe_text(r.get("url"))
    address = _safe_text(r.get("address"))
    price = _to_float(r.get("price_pcm"))
    beds = _to_float(r.get("bedrooms"))
    baths = _to_float(r.get("bathrooms"))
    final_score = _to_float(r.get("final_score"))
    deposit_score = _to_float(r.get("deposit_score"))
    freshness_score = _to_float(r.get("freshness_score"))
    w_deposit = _to_float(r.get("w_deposit")) or 0.0
    w_freshness = _to_float(r.get("w_freshness")) or 0.0

    transit_hits = [x.strip() for x in _safe_text(r.get("transit_hits")).split(",") if x.strip()]
    school_hits = [x.strip() for x in _safe_text(r.get("school_hits")).split(",") if x.strip()]
    pref_hits = [x.strip() for x in _safe_text(r.get("preference_hits")).split(",") if x.strip()]
    hit_terms = (pref_hits + transit_hits + school_hits)[:2]
    penalty_reasons = [x.strip() for x in _safe_text(r.get("penalty_reasons")).split(",") if x.strip()]

    parts: List[str] = []
    parts.append(f"{i}. {title}")
    line2: List[str] = []
    if price is not None:
        line2.append(f"£{int(round(price))}/pcm")
    if beds is not None:
        line2.append(f"{int(round(beds))} bed")
    if baths is not None:
        line2.append(f"{int(round(baths))} bath")
    if address:
        line2.append(address)
    if line2:
        parts.append("   " + " | ".join(line2))
    if final_score is not None:
        parts.append(f"   Final score: {final_score:.4f}")
    if hit_terms:
        parts.append("   Because matched: " + ", ".join(hit_terms))
    boost_bits: List[str] = []
    if deposit_score is not None and deposit_score > 0.5 and w_deposit > 0:
        boost_bits.append(f"deposit ({deposit_score:.2f})")
    if freshness_score is not None and freshness_score > 0.5 and w_freshness > 0:
        boost_bits.append(f"freshness ({freshness_score:.2f})")
    if boost_bits:
        parts.append("   Because boosted by " + " and ".join(boost_bits))
    if penalty_reasons:
        parts.append("   Because penalized: " + penalty_reasons[0])
    if url:
        parts.append("   " + url)
    return "\n".join(parts)


def format_listing_row(r: Dict[str, Any], i: int, view_mode: str = "summary") -> str:
    if str(view_mode).strip().lower() == "debug":
        return format_listing_row_debug(r, i)
    return format_listing_row_summary(r, i)
