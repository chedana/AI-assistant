"""Location fuzzy matching and vocabulary index for UK rental locations."""

import io
import json
import os
import pickle
import re
import sqlite3
from typing import Any, Dict, List, Optional, Tuple

from core.settings import ROOT_DIR
from skills.search.text_utils import _safe_text, _truthy_env, parse_jsonish_items

_LOCATION_MATCH_INDEX_CACHE: Optional[Dict[str, Any]] = None


def _normalize_location_keyword(v: Any) -> str:
    s = _safe_text(v).lower()
    if not s:
        return ""
    s = (
        s.replace("’", "'")
        .replace("‘", "'")
        .replace("`", "'")
        .replace("-", " ")
        .replace("_", " ")
    )
    # king's -> kings
    s = s.replace("'", "")
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _iter_location_vocab_sources() -> List[str]:
    explicit = _safe_text(os.environ.get("RENT_QDRANT_STORAGE_SQLITE")).strip()
    if explicit:
        return [explicit]
    return [
        os.path.join(
            ROOT_DIR,
            "artifacts",
            "skills",
            "search",
            "data",
            "qdrant_local",
            "collection",
            "rent_listings",
            "storage.sqlite",
        ),
    ]


def _strip_station_suffix(s: str) -> str:
    t = _safe_text(s)
    if not t:
        return ""
    # e.g. "King's Cross St. Pancras (0.3 mi)" -> "King's Cross St. Pancras"
    t = re.sub(r"\s*\([^)]*\)\s*$", "", t).strip()
    return t


def _slug_key(v: Any) -> str:
    s = _normalize_location_keyword(v)
    if not s:
        return ""
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s


def _compact_key(v: Any) -> str:
    s = _slug_key(v)
    return s.replace("_", "")


def _parse_jsonlike(v: Any) -> Any:
    if isinstance(v, (list, dict)):
        return v
    s = _safe_text(v).strip()
    if not s:
        return []
    if not (s.startswith("[") or s.startswith("{")):
        return []
    try:
        return json.loads(s)
    except Exception:
        return []


def _source_signature(paths: List[str]) -> Tuple[Tuple[str, int, int], ...]:
    sig: List[Tuple[str, int, int]] = []
    for p in paths:
        if not os.path.exists(p):
            sig.append((p, -1, -1))
            continue
        try:
            st = os.stat(p)
            sig.append((p, int(st.st_mtime), int(st.st_size)))
        except Exception:
            sig.append((p, -2, -2))
    return tuple(sig)


def _add_location_alias(entry: Dict[str, Any], alias: str) -> None:
    plain = _normalize_location_keyword(alias)
    if not plain or len(plain) < 3:
        return
    slug = _slug_key(plain)
    compact = _compact_key(plain)
    if not slug or not compact:
        return
    aliases = entry.setdefault("aliases", set())
    aliases.add((plain, slug, compact))


def _build_location_match_index() -> Dict[str, Any]:
    entries_by_canon: Dict[str, Dict[str, Any]] = {}

    def _ensure_entry(canonical: str) -> Dict[str, Any]:
        c = _safe_text(canonical).strip()
        if not c:
            c = canonical
        key = _normalize_location_keyword(c)
        if key in entries_by_canon:
            return entries_by_canon[key]
        ent = {"canonical": c, "aliases": set()}
        entries_by_canon[key] = ent
        return ent

    def _add_phrase(canonical: str, phrase: Any) -> None:
        raw = _safe_text(phrase).strip()
        if not raw:
            return
        ent = _ensure_entry(canonical if canonical else raw)
        _add_location_alias(ent, raw)
        base = _normalize_location_keyword(raw)
        toks = base.split()
        if len(toks) >= 3:
            for n in (2, 3):
                for i in range(0, len(toks) - n + 1):
                    sub = " ".join(toks[i:i + n])
                    if len(sub) >= 6:
                        _add_location_alias(ent, sub)

    def _extract_payload_obj(obj: Any) -> Optional[Dict[str, Any]]:
        # qdrant local pickle shape can vary; recursively find payload-like dict.
        seen = set()

        def _walk(x: Any, depth: int = 0) -> Optional[Dict[str, Any]]:
            if depth > 6:
                return None
            xid = id(x)
            if xid in seen:
                return None
            seen.add(xid)

            if isinstance(x, dict):
                if isinstance(x.get("payload"), dict):
                    return x.get("payload")
                if any(
                    k in x
                    for k in (
                        "location_tokens",
                        "location_station_tokens",
                        "location_region_tokens",
                        "location_postcode_tokens",
                        "station_names_norm",
                        "address",
                        "stations",
                    )
                ):
                    return x
                for v in x.values():
                    hit = _walk(v, depth + 1)
                    if hit is not None:
                        return hit
                return None

            dd = getattr(x, "__dict__", None)
            if isinstance(dd, dict):
                hit = _walk(dd, depth + 1)
                if hit is not None:
                    return hit

            if isinstance(x, (list, tuple, set)):
                for v in x:
                    hit = _walk(v, depth + 1)
                    if hit is not None:
                        return hit
            return None

        return _walk(obj, 0)

    class _GenericPoint:
        pass

    class _CompatUnpickler(pickle.Unpickler):
        def find_class(self, module, name):
            # Allow loading pickles even when qdrant_client classes are missing.
            return _GenericPoint

    def _add_from_payload(rec: Dict[str, Any]) -> None:
        if not isinstance(rec, dict):
            return
        for key in ("location_region_tokens", "location_region_slugs"):
            for x in (rec.get(key) or []):
                sx = _safe_text(x).strip()
                if sx:
                    _add_phrase(sx, sx)
        for key in ("location_station_tokens", "location_station_slugs", "station_names_norm"):
            for x in (rec.get(key) or []):
                sx = _safe_text(x).strip()
                if sx:
                    _add_phrase(sx, sx)

        dqm = _parse_jsonlike(rec.get("discovery_queries_by_method"))
        if isinstance(dqm, dict):
            for x in dqm.get("region") or []:
                sx = _safe_text(x).strip()
                if sx:
                    _add_phrase(sx, sx)
            for x in dqm.get("station") or []:
                sx = _safe_text(x).strip()
                if sx:
                    _add_phrase(sx, sx)

        stations = _parse_jsonlike(rec.get("stations"))
        if isinstance(stations, list):
            for item in stations:
                if isinstance(item, dict):
                    name = _safe_text(item.get("name")).strip()
                else:
                    name = _safe_text(item).strip()
                name = _strip_station_suffix(name)
                if name:
                    _add_phrase(name, name)
        else:
            for s_item in parse_jsonish_items(rec.get("stations")):
                name = _strip_station_suffix(s_item)
                if name:
                    _add_phrase(name, name)

    # ── Qdrant Cloud path (when RENT_QDRANT_URL is set) ──────────────
    from core.settings import QDRANT_URL, QDRANT_API_KEY, QDRANT_COLLECTION
    if QDRANT_URL:
        try:
            from qdrant_client import QdrantClient as _QC
            _client = _QC(url=QDRANT_URL, api_key=QDRANT_API_KEY or None)
            _offset = None
            while True:
                _points, _offset = _client.scroll(
                    QDRANT_COLLECTION,
                    limit=500,
                    offset=_offset,
                    with_payload=[
                        "location_region_tokens", "location_region_slugs",
                        "location_station_tokens", "location_station_slugs",
                        "station_names_norm", "stations",
                        "discovery_queries_by_method",
                    ],
                    with_vectors=False,
                )
                for _pt in _points:
                    if _pt.payload:
                        _add_from_payload(_pt.payload)
                if _offset is None:
                    break
        except Exception:
            pass

    # ── Local SQLite path (when running with local Qdrant) ───────────
    for path in _iter_location_vocab_sources():
        if not os.path.exists(path):
            continue
        try:
            con = sqlite3.connect(path)
            cur = con.cursor()
            cur.execute("SELECT point FROM points")
            for (blob,) in cur.fetchall():
                if not isinstance(blob, (bytes, bytearray)):
                    continue
                try:
                    obj = pickle.loads(blob)
                except Exception:
                    try:
                        obj = _CompatUnpickler(io.BytesIO(blob)).load()
                    except Exception:
                        continue
                rec = _extract_payload_obj(obj)
                if rec:
                    _add_from_payload(rec)
            con.close()
        except Exception:
            continue

    entries: List[Dict[str, Any]] = []
    lookup_plain: Dict[str, str] = {}
    lookup_slug: Dict[str, str] = {}
    lookup_compact: Dict[str, str] = {}
    for ent in entries_by_canon.values():
        aliases = sorted(list(ent.get("aliases") or []), key=lambda x: (len(x[0]), x[0]))
        if not aliases:
            continue
        canonical = ent["canonical"]
        clean_aliases = []
        for plain, slug, compact in aliases:
            clean_aliases.append((plain, slug, compact))
            # Exact-key lookups should return an alias token directly.
            lookup_plain.setdefault(plain, plain)
            lookup_slug.setdefault(slug, plain)
            lookup_compact.setdefault(compact, plain)
        entries.append({"canonical": canonical, "aliases": clean_aliases})
    return {
        "entries": entries,
        "lookup_plain": lookup_plain,
        "lookup_slug": lookup_slug,
        "lookup_compact": lookup_compact,
        "signature": _source_signature(_iter_location_vocab_sources()),
    }


def _get_location_match_index() -> Dict[str, Any]:
    global _LOCATION_MATCH_INDEX_CACHE
    sig = _source_signature(_iter_location_vocab_sources())
    if (
        _LOCATION_MATCH_INDEX_CACHE is None
        or _LOCATION_MATCH_INDEX_CACHE.get("signature") != sig
    ):
        _LOCATION_MATCH_INDEX_CACHE = _build_location_match_index()
    return _LOCATION_MATCH_INDEX_CACHE


def _edit_distance(a: str, b: str) -> int:
    # Damerau-Levenshtein distance (optimal string alignment):
    # supports insertion/deletion/substitution and adjacent transposition.
    if a == b:
        return 0
    la, lb = len(a), len(b)
    if la == 0:
        return lb
    if lb == 0:
        return la

    d = [[0] * (lb + 1) for _ in range(la + 1)]
    for i in range(la + 1):
        d[i][0] = i
    for j in range(lb + 1):
        d[0][j] = j

    for i in range(1, la + 1):
        for j in range(1, lb + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            d[i][j] = min(
                d[i - 1][j] + 1,      # deletion
                d[i][j - 1] + 1,      # insertion
                d[i - 1][j - 1] + cost,  # substitution
            )
            if (
                i > 1 and j > 1
                and a[i - 1] == b[j - 2]
                and a[i - 2] == b[j - 1]
            ):
                d[i][j] = min(d[i][j], d[i - 2][j - 2] + 1)  # transposition
    return d[la][lb]


def _adaptive_max_ed(n: int) -> int:
    if n <= 6:
        return 1
    if n <= 12:
        return 2
    return max(2, int(round(n * 0.2)))


def _window_best_similarity(q: str, cand: str) -> float:
    if not q or not cand:
        return 0.0
    if q == cand:
        return 1.0
    if len(cand) <= len(q) + 2:
        d = _edit_distance(q, cand)
        denom = max(len(q), len(cand), 1)
        return 1.0 - (float(d) / float(denom))
    best = 0.0
    qlen = len(q)
    lens = [max(3, qlen - 1), qlen, qlen + 1]
    edge_k = 3  # only evaluate a few prefix/suffix windows
    for ln in lens:
        if ln > len(cand):
            continue
        max_start = len(cand) - ln
        starts = list(range(0, min(edge_k, max_start + 1)))
        suffix_starts = list(range(max(0, max_start - edge_k + 1), max_start + 1))
        seen = set(starts)
        for si in suffix_starts:
            if si not in seen:
                starts.append(si)
                seen.add(si)
        for i in starts:
            w = cand[i:i + ln]
            d = _edit_distance(q, w)
            denom = max(len(q), len(w), 1)
            score = 1.0 - (float(d) / float(denom))
            if score > best:
                best = score
    return best


def _subsequence_similarity(q: str, cand: str) -> float:
    # Abbreviation-friendly similarity: reward ordered character coverage.
    # Example: "bdg" ~= "bridge".
    if not q or not cand:
        return 0.0
    if len(q) > len(cand):
        return 0.0
    qi = 0
    first = -1
    last = -1
    for i, ch in enumerate(cand):
        if qi < len(q) and ch == q[qi]:
            if first < 0:
                first = i
            last = i
            qi += 1
            if qi == len(q):
                break
    if qi != len(q):
        return 0.0
    span = max(1, last - first + 1)
    density = float(len(q)) / float(span)
    coverage = float(len(q)) / float(max(len(cand), 1))
    return 0.70 + 0.20 * density + 0.10 * coverage


def _location_abbrev_override(q_plain: str) -> str:
    s = _normalize_location_keyword(q_plain)
    if not s:
        return ""
    s_compact = _compact_key(s)

    # High-risk King's Cross abbreviations frequently collapse to "king s"
    # and drift retrieval. Force them to the full station family anchor.
    kings_cross_compacts = {
        "kx",
        "kingx",
        "kingsx",
        "kingscross",
        "kingcross",
        "kingscrossstpancras",
        "kingcrossstpancras",
        "kingsxstpancras",
        "kingsxstp",
        "kingscrossstn",
        "kingscrossstation",
    }
    if s_compact in kings_cross_compacts:
        return "kings cross st pancras"

    if s in {"king s", "kings x", "king x", "k x"}:
        return "kings cross st pancras"

    if re.search(r"\b(kings?|king)\s*x\b", s):
        return "kings cross st pancras"
    if re.search(r"\bkx\b", s):
        return "kings cross st pancras"
    if re.search(r"\bkings?\s+cross\b", s):
        return "kings cross st pancras"
    if "pancras" in s and re.search(r"\bkings?|king\b", s):
        return "kings cross st pancras"
    return ""


def _normalize_location_query_term(raw: str) -> Tuple[str, str, str]:
    q_plain = _normalize_location_keyword(raw)
    if not q_plain:
        return "", "", ""
    override = _location_abbrev_override(q_plain)
    if override:
        q_plain = override
    # Drop accidental trailing digits in long non-postcode tokens, e.g.:
    # "wtaerloo0" -> "wtaerloo".
    if (
        not re.fullmatch(r"[a-z]{1,2}\d[a-z0-9]?\s?\d[a-z]{2}", q_plain)
        and len(q_plain.replace(" ", "")) >= 6
    ):
        q_plain = re.sub(r"\d+$", "", q_plain).strip()
        if not q_plain:
            return "", "", ""
    return q_plain, _slug_key(q_plain), _compact_key(q_plain)


def expand_location_keyword_candidates(raw: str, limit: int = 8, min_score: float = 0.80) -> List[str]:
    q_plain, q_slug, q_compact = _normalize_location_query_term(raw)
    if not q_plain:
        return []
    idx = _get_location_match_index()
    entries = idx.get("entries") or []
    if len(entries) < 20:
        return []

    lookup_plain = idx.get("lookup_plain") or {}
    lookup_slug = idx.get("lookup_slug") or {}
    lookup_compact = idx.get("lookup_compact") or {}
    scored: Dict[str, float] = {}

    # exact
    exact_hits: List[str] = []
    if q_plain in lookup_plain:
        hit = _safe_text(lookup_plain[q_plain]).strip()
        if hit:
            exact_hits.append(hit)
    if q_slug in lookup_slug:
        hit = _safe_text(lookup_slug[q_slug]).strip()
        if hit:
            exact_hits.append(hit)
    if q_compact in lookup_compact:
        hit = _safe_text(lookup_compact[q_compact]).strip()
        if hit:
            exact_hits.append(hit)

    # Short-circuit: if exact match exists, skip fuzzy expansion to avoid drift
    # like "waterloo" -> "bakerloo".
    exact_hits = list(dict.fromkeys([x for x in exact_hits if x]))
    if exact_hits and 1.0 >= float(min_score):
        ranked = [(alias, 1.0) for alias in exact_hits]
        if _truthy_env("RENT_LOCATION_DEBUG_PRINT"):
            debug_top = [
                {"alias": alias, "score": 1.0}
                for alias in ranked[: max(1, limit)]
            ]
            payload = {
                "query": str(raw or ""),
                "min_score": float(min_score),
                "limit": int(limit),
                "top": debug_top,
                "mode": "exact_short_circuit",
            }
            msg = "location_candidate_dict " + json.dumps(payload, ensure_ascii=False)
            try:
                from core.logger import log_message

                log_message("INFO", msg)
            except Exception:
                print("[INFO] " + msg)
        out = [alias for alias, _ in ranked if alias]
        if limit > 0:
            out = out[:limit]
        return out

    # contains + distance score
    for ent in entries:
        aliases = ent.get("aliases") or []
        for plain, slug, compact in aliases:
            local_score = 0.0
            # contains on compact form
            if q_compact and compact:
                if q_compact in compact or compact in q_compact:
                    shorter = float(min(len(q_compact), len(compact)))
                    longer = float(max(len(q_compact), len(compact)))
                    ratio = shorter / max(1.0, longer)
                    score = 0.88 + 0.10 * ratio
                    if score > local_score:
                        local_score = score
            # adaptive distance on compact/window
            if q_compact and compact:
                sim = _window_best_similarity(q_compact, compact)
                need = _adaptive_max_ed(max(len(q_compact), min(len(compact), len(q_compact) + 1)))
                # Convert threshold to similarity lower-bound.
                if len(q_compact) > 0:
                    min_sim = 1.0 - (float(need) / float(max(len(q_compact), 1)))
                    if sim >= min_sim:
                        # Distance score with length proximity bonus:
                        # prefer candidates with similar compact length.
                        len_ratio = float(min(len(q_compact), len(compact))) / float(max(len(q_compact), len(compact), 1))
                        score = 0.68 + 0.20 * sim + 0.12 * len_ratio
                        if score > local_score:
                            local_score = score
            # subsequence score for abbreviation-like queries
            if q_compact and compact and 3 <= len(q_compact) <= 8:
                score = _subsequence_similarity(q_compact, compact)
                if score > local_score:
                    local_score = score
            if local_score >= min_score:
                prev = scored.get(plain, 0.0)
                if local_score > prev:
                    scored[plain] = local_score

    ranked = sorted(scored.items(), key=lambda x: (-x[1], len(x[0]), x[0]))
    if _truthy_env("RENT_LOCATION_DEBUG_PRINT"):
        debug_top = [
            {"alias": alias, "score": round(float(score), 4)}
            for alias, score in ranked[: max(1, limit)]
        ]
        payload = {
            "query": str(raw or ""),
            "min_score": float(min_score),
            "limit": int(limit),
            "top": debug_top,
        }
        msg = "location_candidate_dict " + json.dumps(payload, ensure_ascii=False)
        try:
            from core.logger import log_message

            log_message("INFO", msg)
        except Exception:
            print("[INFO] " + msg)
    out = [alias for alias, _ in ranked if alias]
    if limit > 0:
        out = out[:limit]
    return out


def _correct_location_keyword(raw: str) -> str:
    cands = expand_location_keyword_candidates(raw, limit=1, min_score=0.80)
    if cands:
        return cands[0]
    return _safe_text(raw).strip()
