import json
import math
import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

try:
    from qdrant_client import QdrantClient, models
except Exception:
    QdrantClient = None
    models = None

try:
    from crawler.london_regions import LONDON_REGIONS as _LONDON_REGIONS
except Exception:
    _LONDON_REGIONS = {}


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _geocode_location_keywords(keywords: List[str]) -> Optional[Tuple[float, float, str]]:
    """Match location keywords to a known London region. Returns (lat, lon, area_name) or None."""
    if not _LONDON_REGIONS or not keywords:
        return None
    for kw in keywords:
        kw_norm = kw.strip().lower()
        # Exact match first
        for region_name, data in _LONDON_REGIONS.items():
            if kw_norm == region_name.lower():
                return data["lat"], data["lng"], region_name
        # Substring match
        for region_name, data in _LONDON_REGIONS.items():
            rn = region_name.lower()
            if kw_norm in rn or rn in kw_norm:
                return data["lat"], data["lng"], region_name
    return None

from skills.search.extractors import _safe_text, expand_location_keyword_candidates, _to_float
from core.logger import log_message
from core.settings import (
    QDRANT_COLLECTION,
    QDRANT_ENABLE_PREFILTER,
    QDRANT_LOCAL_PATH,
    QDRANT_URL,
    QDRANT_API_KEY,
    STAGEA_TRACE,
)


def load_qdrant_client() -> QdrantClient:
    if QdrantClient is None or models is None:
        raise ImportError("qdrant-client is not installed. Please run: pip install qdrant-client")

    if QDRANT_URL:
        client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY or None)
        log_message("INFO", f"boot qdrant mode=cloud url={QDRANT_URL}")
    else:
        client = QdrantClient(path=QDRANT_LOCAL_PATH)
        log_message("INFO", f"boot qdrant mode=local path={QDRANT_LOCAL_PATH}")

    if not client.collection_exists(QDRANT_COLLECTION):
        raise FileNotFoundError(
            f"Missing Qdrant collection: {QDRANT_COLLECTION}"
        )
    info = client.get_collection(QDRANT_COLLECTION)
    log_message("INFO", f"boot qdrant collection={QDRANT_COLLECTION}, points={info.points_count}")
    return client


def load_stage_a_resources():
    return load_qdrant_client()


def embed_query(embedder, q: str) -> np.ndarray:
    # Supports both fastembed.TextEmbedding (embed()) and sentence-transformers (encode())
    if hasattr(embedder, "embed"):
        x = np.array(list(embedder.embed([q])), dtype="float32")
    else:
        x = embedder.encode(
            [q], batch_size=1, show_progress_bar=False,
            convert_to_numpy=True, normalize_embeddings=False,
        ).astype("float32")
    norms = np.linalg.norm(x, axis=1, keepdims=True)
    norms = np.maximum(norms, 1e-12)
    x = x / norms
    return x


def qdrant_search(
    client: QdrantClient,
    embedder,
    query: str,
    recall: int,
    c: Optional[Dict[str, Any]] = None,
) -> pd.DataFrame:
    if models is None:
        raise ImportError("qdrant-client models are unavailable. Please run: pip install qdrant-client")

    trace_info: Dict[str, Any] = {
        "location_keywords": [],
        "location_keyword_expansions": {},
        "location_station_added": {},
        "location_tokens": [],
        "prefilter_count": None,
    }

    def _count_prefilter_candidates(qfilter: Optional["models.Filter"]) -> Optional[int]:
        if qfilter is None:
            return None
        try:
            # Fast path: qdrant count API.
            resp = client.count(
                collection_name=QDRANT_COLLECTION,
                count_filter=qfilter,
                exact=True,
            )
            n = getattr(resp, "count", None)
            return int(n) if n is not None else None
        except Exception:
            # Fallback for older qdrant-client versions: scroll and count.
            try:
                total = 0
                offset = None
                while True:
                    points, offset = client.scroll(
                        collection_name=QDRANT_COLLECTION,
                        scroll_filter=qfilter,
                        limit=512,
                        offset=offset,
                        with_payload=False,
                        with_vectors=False,
                    )
                    total += len(points or [])
                    if offset is None:
                        break
                return int(total)
            except Exception:
                # Still unavailable on this backend/version.
                return None

    def _build_qdrant_filter(c: Optional[Dict[str, Any]]) -> Optional["models.Filter"]:
        c = c or {}
        must: List[Any] = []

        # Geo-bound: add bounding box pre-filter on latitude/longitude payload fields.
        # Prefer exact viewport bounds (min/max lat/lng) sent by frontend; fall back to
        # approximate bbox derived from center+radius for backward compat.
        import math as _math
        geo = c.get("geo_bound")
        if isinstance(geo, dict):
            min_lat = _to_float(geo.get("min_lat"))
            max_lat = _to_float(geo.get("max_lat"))
            min_lng = _to_float(geo.get("min_lng"))
            max_lng = _to_float(geo.get("max_lng"))
            if min_lat is not None and max_lat is not None and min_lng is not None and max_lng is not None:
                # Exact viewport bounds — use directly
                must.append(models.FieldCondition(
                    key="latitude",
                    range=models.Range(gte=min_lat, lte=max_lat),
                ))
                must.append(models.FieldCondition(
                    key="longitude",
                    range=models.Range(gte=min_lng, lte=max_lng),
                ))
            else:
                glat = _to_float(geo.get("lat"))
                glon = _to_float(geo.get("lng") or geo.get("lon"))
                grad = _to_float(geo.get("radius_km"))
                if glat is not None and glon is not None and grad is not None:
                    # Fallback: approximate bounding box from center + radius
                    lat_delta = grad / 111.32
                    lon_delta = grad / (111.32 * _math.cos(_math.radians(glat)))
                    must.append(models.FieldCondition(
                        key="latitude",
                        range=models.Range(gte=glat - lat_delta, lte=glat + lat_delta),
                    ))
                    must.append(models.FieldCondition(
                        key="longitude",
                        range=models.Range(gte=glon - lon_delta, lte=glon + lon_delta),
                    ))

        # 2. Token-based Location Prefilter
        loc_values: List[str] = []
        station_values: List[str] = []
        region_values: List[str] = []
        postcode_values: List[str] = []
        loc_keywords = [str(x).strip() for x in (c.get("location_keywords") or []) if str(x).strip()]
        trace_info["location_keywords"] = loc_keywords
        for term in loc_keywords:
            expanded = expand_location_keyword_candidates(term, limit=20, min_score=0.80)
            expanded_terms = [term] + [x for x in expanded if _safe_text(x)]
            # Preserve order while removing duplicates.
            seen_local = set()
            uniq_terms: List[str] = []
            for x in expanded_terms:
                k = _safe_text(x).lower().strip()
                if not k or k in seen_local:
                    continue
                seen_local.add(k)
                uniq_terms.append(k)
            trace_info["location_keyword_expansions"][_safe_text(term)] = uniq_terms
            station_added_for_term: List[str] = []

            for raw in uniq_terms:
                raw = re.sub(r"\s+", " ", raw).strip()
                slug = re.sub(r"[^a-z0-9]+", "_", raw)
                slug = re.sub(r"_+", "_", slug).strip("_")
                for m in re.findall(r"\b[a-z]{1,2}\d[a-z0-9]?\s?\d[a-z]{2}\b", raw):
                    postcode_values.append(m.replace(" ", ""))
                if raw:
                    loc_values.append(raw)
                    if " " in raw:
                        loc_values.append(raw.replace(" ", ""))
                    station_values.append(raw)
                if slug:
                    loc_values.append(slug)
                    loc_values.append(f"{slug}_london")
                    if not slug.endswith("_station"):
                        loc_values.append(f"{slug}_station")
                    station_values.append(slug)
                    if not slug.endswith("_station"):
                        station_token = f"{slug}_station"
                        station_values.append(station_token)
                        station_added_for_term.append(station_token)
                    region_values.append(slug)
                    region_values.append(f"{slug}_london")
            trace_info["location_station_added"][_safe_text(term)] = list(dict.fromkeys(station_added_for_term))
            if _safe_text(os.environ.get("RENT_LOCATION_DEBUG_PRINT")).strip().lower() in {"1", "true", "yes", "on"}:
                preview_station = trace_info["location_station_added"][_safe_text(term)]
                station_preview = preview_station[:6]
                flow = f"location_flow_stageA {term} -> {uniq_terms[:6]}"
                if station_preview:
                    flow += f" -> {station_preview}"
                log_message("INFO", flow)

        loc_values = list(dict.fromkeys([x for x in loc_values if x]))
        station_values = list(dict.fromkeys([x for x in station_values if x]))
        region_values = list(dict.fromkeys([x for x in region_values if x]))
        postcode_values = list(dict.fromkeys([x for x in postcode_values if x]))
        trace_info["location_tokens"] = loc_values
        trace_info["location_station_tokens"] = station_values
        trace_info["location_region_tokens"] = region_values
        trace_info["location_postcode_tokens"] = postcode_values
        should_conditions: List[Any] = []
        if postcode_values:
            should_conditions.append(
                models.FieldCondition(
                    key="location_postcode_tokens",
                    match=models.MatchAny(any=postcode_values),
                )
            )
        if station_values:
            should_conditions.append(
                models.FieldCondition(
                    key="location_station_tokens",
                    match=models.MatchAny(any=station_values),
                )
            )
        if region_values:
            should_conditions.append(
                models.FieldCondition(
                    key="location_region_tokens",
                    match=models.MatchAny(any=region_values),
                )
            )
        # Backward-compatible fallback for older indexes.
        if loc_values:
            should_conditions.append(
                models.FieldCondition(
                    key="location_tokens",
                    match=models.MatchAny(any=loc_values),
                )
            )
        if should_conditions:
            must.append(models.Filter(should=should_conditions))

        if not must:
            return None
        return models.Filter(must=must)

    qx = embed_query(embedder, query)[0].tolist()
    qfilter = _build_qdrant_filter(c) if QDRANT_ENABLE_PREFILTER else None
    prefilter_count = _count_prefilter_candidates(qfilter)
    trace_info["prefilter_count"] = prefilter_count
    if STAGEA_TRACE:
        log_message("DEBUG", f"stageA backend=qdrant recall={recall} prefilter={QDRANT_ENABLE_PREFILTER}")
        log_message("DEBUG", f"stageA query={query}")
        if prefilter_count is not None:
            log_message("DEBUG", f"stageA prefilter_count={prefilter_count}")
        if trace_info.get("location_keywords"):
            log_message(
                "DEBUG",
                "stageA location keywords="
                + json.dumps(trace_info.get("location_keywords", []), ensure_ascii=False)
                + " expanded="
                + json.dumps(trace_info.get("location_keyword_expansions", {}), ensure_ascii=False)
                + " station_added="
                + json.dumps(trace_info.get("location_station_added", {}), ensure_ascii=False)
                + " any_tokens="
                + json.dumps(trace_info.get("location_tokens", []), ensure_ascii=False),
            )
            log_message(
                "DEBUG",
                "stageA grouped location tokens="
                + json.dumps(
                    {
                        "postcode": trace_info.get("location_postcode_tokens", []),
                        "station": trace_info.get("location_station_tokens", []),
                        "region": trace_info.get("location_region_tokens", []),
                    },
                    ensure_ascii=False,
                ),
            )
        else:
            log_message("DEBUG", "stageA location keywords=[]")

    # Detect pure geo-bound mode: geo_bound present, no location keywords.
    # In this mode, use scroll to fetch ALL listings in the bounding box (no recall cap).
    geo = (c or {}).get("geo_bound")
    loc_kws = [str(x).strip() for x in (c or {}).get("location_keywords") or [] if str(x).strip()]
    is_pure_geo = isinstance(geo, dict) and not loc_kws

    if is_pure_geo and qfilter is not None:
        glat = _to_float(geo.get("lat"))
        glon = _to_float(geo.get("lng") or geo.get("lon"))
        grad = _to_float(geo.get("radius_km"))
        _t_scroll = time.perf_counter()
        all_points = []
        offset = None
        GEO_SCROLL_MAX = 15000
        while True:
            points, offset = client.scroll(
                collection_name=QDRANT_COLLECTION,
                scroll_filter=qfilter,
                limit=512,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            all_points.extend(points or [])
            if offset is None or len(all_points) >= GEO_SCROLL_MAX:
                break
        hit_cap = len(all_points) >= GEO_SCROLL_MAX
        print(f"[TIMING] qdrant_geo_scroll={time.perf_counter()-_t_scroll:.2f}s total={len(all_points)} hit_cap={hit_cap}")

        rows = []
        # Skip haversine when: exact viewport bounds were used (min/max lat/lng) — no circle needed;
        # or when cap was hit (sampling); or for very large radius (zoomed out).
        has_exact_bounds = all(geo.get(k) is not None for k in ("min_lat", "max_lat", "min_lng", "max_lng"))
        skip_haversine = has_exact_bounds or hit_cap or (grad is not None and grad > 20.0)
        for pt in all_points:
            payload = dict(pt.payload or {})
            plat = _to_float(payload.get("latitude"))
            plon = _to_float(payload.get("longitude"))
            if not skip_haversine and plat is not None and plon is not None and glat is not None and glon is not None and grad is not None:
                dist = _haversine_km(glat, glon, plat, plon)
                if dist > grad:
                    continue
            payload["retrieval_score"] = 1.0
            payload["qdrant_score"] = 1.0
            payload["_qdrant_id"] = pt.id
            rows.append(payload)
        log_message("INFO", f"stageA geo_scroll: {len(rows)} listings within {grad}km (scrolled {len(all_points)} from bbox)")
    else:
        # Standard vector search path
        _t_qdrant = time.perf_counter()
        if hasattr(client, "search"):
            hits = client.search(
                collection_name=QDRANT_COLLECTION,
                query_vector=qx,
                query_filter=qfilter,
                limit=recall,
                with_payload=True,
                with_vectors=False,
            )
        else:
            qp = client.query_points(
                collection_name=QDRANT_COLLECTION,
                query=qx,
                query_filter=qfilter,
                limit=recall,
                with_payload=True,
                with_vectors=False,
            )
            hits = list(getattr(qp, "points", []) or [])
        print(f"[TIMING] qdrant_search={time.perf_counter()-_t_qdrant:.2f}s recall={recall} hits={len(hits)}")

        rows = []
        # Post-filter for geometric radius if geo_bound + location_keywords combo
        if isinstance(geo, dict):
            glat = _to_float(geo.get("lat"))
            glon = _to_float(geo.get("lng") or geo.get("lon"))
            grad = _to_float(geo.get("radius_km"))
            if glat is not None and glon is not None and grad is not None:
                for h in hits:
                    payload = dict(h.payload or {})
                    plat = _to_float(payload.get("latitude"))
                    plon = _to_float(payload.get("longitude"))
                    if plat is not None and plon is not None:
                        dist = _haversine_km(glat, glon, plat, plon)
                        if dist <= grad:
                            score = float(h.score)
                            payload["retrieval_score"] = score
                            payload["qdrant_score"] = score
                            payload["_qdrant_id"] = h.id
                            rows.append(payload)
                log_message("INFO", f"stageA geo_postfilter: {len(rows)} listings within {grad}km of center")
        else:
            # Standard processing — no geo filtering
            for h in hits:
                payload = dict(h.payload or {})
                score = float(h.score)
                payload["retrieval_score"] = score
                payload["qdrant_score"] = score
                payload["_qdrant_id"] = h.id
                rows.append(payload)

    # Geo-radius fallback: search returned nothing but user specified a location keyword.
    # Triggers when token index misses. Skip if we already used an explicit geometric bound.
    loc_keywords = [str(x).strip() for x in (c or {}).get("location_keywords") or [] if str(x).strip()]
    has_geo_bound = isinstance((c or {}).get("geo_bound"), dict)
    
    if not rows and loc_keywords and not has_geo_bound:
        geo_result = _geocode_location_keywords(loc_keywords)
        if geo_result:
            center_lat, center_lon, area_name = geo_result
            GEO_RADIUS_KM = 3.0
            log_message("INFO", f"stageA geo_fallback: token miss → radius {GEO_RADIUS_KM}km around '{area_name}' ({center_lat},{center_lon})")
            _t_geo = time.perf_counter()
            try:
                if hasattr(client, "search"):
                    geo_hits = client.search(
                        collection_name=QDRANT_COLLECTION,
                        query_vector=qx,
                        query_filter=None,
                        limit=recall,
                        with_payload=True,
                        with_vectors=False,
                    )
                else:
                    gqp = client.query_points(
                        collection_name=QDRANT_COLLECTION,
                        query=qx,
                        query_filter=None,
                        limit=recall,
                        with_payload=True,
                        with_vectors=False,
                    )
                    geo_hits = list(getattr(gqp, "points", []) or [])
                print(f"[TIMING] geo_fallback_search={time.perf_counter()-_t_geo:.2f}s hits={len(geo_hits)}")
                for h in geo_hits:
                    payload = dict(h.payload or {})
                    lat = payload.get("latitude")
                    lon = payload.get("longitude")
                    if lat is None or lon is None:
                        continue
                    try:
                        dist = _haversine_km(center_lat, center_lon, float(lat), float(lon))
                    except (TypeError, ValueError):
                        continue
                    if dist <= GEO_RADIUS_KM:
                        score = float(h.score)
                        payload["retrieval_score"] = score
                        payload["qdrant_score"] = score
                        payload["_qdrant_id"] = h.id
                        rows.append(payload)
                log_message("INFO", f"stageA geo_fallback: {len(rows)} listings within {GEO_RADIUS_KM}km of '{area_name}'")
            except Exception as exc:
                log_message("WARN", f"stageA geo_fallback error: {exc}")

            if rows:
                df = pd.DataFrame(rows).reset_index(drop=True)
                df.attrs["prefilter_count"] = prefilter_count
                df.attrs["geo_fallback_area"] = area_name
                return df

    if not rows:
        df = pd.DataFrame()
        df.attrs["prefilter_count"] = prefilter_count
        return df
    df = pd.DataFrame(rows).reset_index(drop=True)
    df.attrs["prefilter_count"] = prefilter_count
    return df


def stage_a_search(
    client,
    embedder,
    query: str,
    recall: int,
    c: Optional[Dict[str, Any]] = None,
) -> pd.DataFrame:
    return qdrant_search(client, embedder, query=query, recall=recall, c=c)
