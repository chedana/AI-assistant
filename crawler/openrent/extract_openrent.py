"""
OpenRent detail-page extractor.

Usage (standalone test):
    python -m crawler.openrent.extract_openrent --url https://www.openrent.co.uk/property-to-rent/london/...

Produces the same ListingRecord dataclass as extract_one_page.py so that
sync_qdrant.py can ingest OpenRent data without modification.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import date, datetime
from typing import Any, Optional

import httpx
from bs4 import BeautifulSoup

# Reuse the shared ListingRecord dataclass from the Rightmove extractor
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[2]))
from crawler.extract_one_page import ListingRecord

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

OPENRENT_BASE = "https://www.openrent.co.uk"
SOURCE = "openrent"

import random

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-GB,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
]

UNKNOWN_TOKENS = {
    "ask agent", "ask the agent", "not provided", "not known",
    "unknown", "n/a", "na", "-", "—", "tbc", "tba", "", "none",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ask(v: Optional[str]) -> Optional[str]:
    """Return 'ask agent' for empty / unknown values."""
    if v is None:
        return "ask agent"
    s = v.strip()
    return "ask agent" if s.lower() in UNKNOWN_TOKENS else s


def _listing_id(url: str) -> str:
    """Extract numeric ID from OpenRent URL and prefix with 'openrent:'."""
    m = re.search(r"/(\d+)\s*$", url.rstrip("/"))
    if m:
        return f"openrent:{m.group(1)}"
    # fallback: use full URL path
    return f"openrent:{url.split('/')[-1]}"


def _parse_price(text: str) -> tuple[Optional[int], Optional[int], str]:
    """
    Parse price string → (price_pcm, price_pw, price_display).
    OpenRent shows: "£2,100.00" (pcm) and separately "£484.62 pw"
    """
    text = text.replace(",", "").strip()
    pcm_m = re.search(r"£([\d.]+)\s*(?:pcm|per\s*month|/\s*month)?", text, re.I)
    pw_m  = re.search(r"£([\d.]+)\s*(?:pw|per\s*week|/\s*week)", text, re.I)

    price_pcm = int(float(pcm_m.group(1))) if pcm_m else None
    price_pw  = int(float(pw_m.group(1)))  if pw_m  else None

    # If only weekly given, convert to pcm
    if price_pcm is None and price_pw is not None:
        price_pcm = round(price_pw * 52 / 12)

    display_parts = []
    if price_pw:
        display_parts.append(f"£{price_pw} pw")
    if price_pcm:
        display_parts.append(f"£{price_pcm:,} pcm")
    price_display = " ".join(display_parts) if display_parts else "ask agent"

    return price_pcm, price_pw, price_display


def _parse_deposit(text: str) -> tuple[Optional[str], Optional[int]]:
    """Parse deposit → (human string, numeric amount)."""
    text = text.strip()
    if not text or text.lower() in UNKNOWN_TOKENS:
        return "ask agent", None
    m = re.search(r"£([\d,]+(?:\.\d+)?)", text)
    amount = None
    if m:
        amount = int(float(m.group(1).replace(",", "")))
    return text, amount


def _parse_available(text: str) -> Optional[str]:
    """Normalise available-from date → ISO string or 'ask agent'."""
    text = text.strip()
    if not text or text.lower() in UNKNOWN_TOKENS:
        return "ask agent"
    low = text.lower()
    if "today" in low or "now" in low or "immediately" in low:
        return date.today().isoformat()
    # Try common date formats
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d %B %Y", "%d %b %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            pass
    return text  # return as-is if we can't parse


def _extract_postcode(text: str) -> Optional[str]:
    """Extract UK postcode from an address string."""
    m = re.search(
        r"\b([A-Z]{1,2}\d{1,2}[A-Z]?\s?\d[A-Z]{2})\b",
        text.upper(),
    )
    return m.group(1) if m else None


def _postcode_district(postcode: Optional[str]) -> Optional[str]:
    if not postcode:
        return None
    return postcode.strip().split()[0] if " " in postcode else postcode[:3]


def _extract_lat_lon(html: str) -> tuple[Optional[float], Optional[float]]:
    """
    Extract lat/lon from OpenRent page.
    Primary: data-lat / data-lng attributes on the map widget.
    Fallback: JSON-like patterns.
    """
    lat = lon = None

    # Primary: data-lat / data-lng on map element (most reliable)
    m_lat = re.search(r'data-lat="(-?\d{1,3}\.\d+)"', html)
    m_lng = re.search(r'data-lng="(-?\d{1,3}\.\d+)"', html)
    if m_lat and m_lng:
        lat_val = float(m_lat.group(1))
        lng_val = float(m_lng.group(1))
        if 49.0 < lat_val < 62.0 and -8.0 < lng_val < 2.0:
            return lat_val, lng_val

    return lat, lon


def _extract_images(soup: BeautifulSoup, listing_id_num: str) -> tuple[Optional[str], list[str]]:
    """
    Extract image URLs from OpenRent listing page.
    Images are served from imagescdn.openrent.co.uk/listings/{id}/...
    """
    images: list[str] = []
    seen: set[str] = set()

    def add(url: str) -> None:
        if url and url not in seen:
            # Normalise protocol-relative URLs
            if url.startswith("//"):
                url = "https:" + url
            seen.add(url)
            images.append(url)

    # Strategy 1: og:image meta — only if it's a real listing image (not logo)
    og = soup.find("meta", property="og:image")
    if og and og.get("content") and "imagescdn.openrent" in og.get("content", ""):
        add(og["content"])

    # Strategy 2: img tags pointing at imagescdn
    for img in soup.find_all("img", src=re.compile(r"imagescdn\.openrent", re.I)):
        add(img["src"])

    # Strategy 3: data-src / data-lazy-src (lazy-loaded images)
    for img in soup.find_all("img", attrs={"data-src": re.compile(r"imagescdn\.openrent", re.I)}):
        add(img["data-src"])

    # Strategy 4: anchor hrefs for full-size images
    for a in soup.find_all("a", href=re.compile(r"imagescdn\.openrent", re.I)):
        add(a["href"])

    # Strategy 5: inline JS — look for array of image filenames for this listing
    for script in soup.find_all("script"):
        text = script.get_text()
        if listing_id_num in text and "imagescdn" in text:
            urls = re.findall(
                r'(?:https:)?//imagescdn\.openrent\.co\.uk/listings/[^\s\'"]+',
                text,
            )
            for u in urls:
                add(u)

    # Remove thumbnail variants, prefer full-size
    def prefer_full(urls: list[str]) -> list[str]:
        full = [u for u in urls if "_homepage" not in u and "_thumb" not in u]
        return full if full else urls

    images = prefer_full(images)[:10]  # cap at 10
    cover = images[0] if images else None
    return cover, images


# ---------------------------------------------------------------------------
# Main extractor
# ---------------------------------------------------------------------------

def fetch_listing(url: str, client: Optional[httpx.Client] = None) -> str:
    """Fetch raw HTML of an OpenRent listing page with retry logic."""
    own_client = client is None
    if own_client:
        headers = {**HEADERS, "User-Agent": random.choice(USER_AGENTS)}
        client = httpx.Client(headers=headers, follow_redirects=True, timeout=30)
    try:
        resp = client.get(url)
        resp.raise_for_status()
        return resp.text
    finally:
        if own_client:
            client.close()


def extract_listing(html: str, url: str) -> ListingRecord:
    """
    Parse OpenRent listing HTML → ListingRecord.

    All fields use the same schema as the Rightmove extractor so that
    sync_qdrant.py works unchanged.
    """
    soup = BeautifulSoup(html, "html.parser")
    lid_num = _listing_id(url).replace("openrent:", "")
    listing_id = f"openrent:{lid_num}"

    # --- Title ---
    title_el = soup.find("h1") or soup.find("title")
    title = title_el.get_text(strip=True) if title_el else None

    # --- Address ---
    address = title  # h1 contains the address/title
    postcode = None

    # Best source: postCode= URL param in the broadband comparison link
    m_pc = re.search(r"postCode=([A-Z0-9%+]+)", html, re.I)
    if m_pc:
        postcode = m_pc.group(1).replace("%20", " ").replace("+", " ").upper().strip()
    else:
        postcode = _extract_postcode(address or "")

    postcode_district = _postcode_district(postcode)

    # --- Price ---
    price_pcm = price_pw = None
    price_display = "ask agent"

    # Look for "Rent PCM: £X" pattern
    rent_el = soup.find(string=re.compile(r"Rent\s*PCM", re.I))
    if rent_el:
        parent = rent_el.parent
        price_text = parent.get_text(" ", strip=True) if parent else ""
        price_pcm, price_pw, price_display = _parse_price(price_text)

    if price_pcm is None:
        # Fallback: find a prominent £ amount
        for el in soup.find_all(string=re.compile(r"£[\d,.]+")):
            m = re.search(r"£([\d,.]+)", el)
            if m:
                price_pcm = int(float(m.group(1).replace(",", "")))
                price_display = f"£{price_pcm:,} pcm"
                break

    # --- Bedrooms / Bathrooms ---
    # OpenRent renders them in a <ul> right after <h1>, e.g. "1bedrooms", "1bathrooms"
    bedrooms = bathrooms = None
    h1 = soup.find("h1")
    if h1:
        ul = h1.find_next("ul")
        if ul:
            for li in ul.find_all("li"):
                text = li.get_text(strip=True)
                mb = re.match(r"(\d+)\s*bedroom", text, re.I)
                mt = re.match(r"(\d+)\s*bathroom", text, re.I)
                if mb:
                    bedrooms = int(mb.group(1))
                if mt:
                    bathrooms = int(mt.group(1))
    # Fallback: full-text search
    if bedrooms is None:
        for el in soup.find_all(string=re.compile(r"\d+\s*bedroom", re.I)):
            m = re.search(r"(\d+)\s*bedroom", el, re.I)
            if m:
                bedrooms = int(m.group(1))
                break
    if bathrooms is None:
        for el in soup.find_all(string=re.compile(r"\d+\s*bathroom", re.I)):
            m = re.search(r"(\d+)\s*bathroom", el, re.I)
            if m:
                bathrooms = int(m.group(1))
                break

    # --- Property type ---
    property_type = None
    for el in soup.find_all(string=re.compile(
        r"\b(flat|house|studio|apartment|maisonette|bungalow|terraced|detached|semi-detached|room|bedsit)\b",
        re.I,
    )):
        m = re.search(
            r"\b(flat|house|studio|apartment|maisonette|bungalow|terraced|detached|semi-detached|room|bedsit)\b",
            el, re.I,
        )
        if m:
            property_type = m.group(1).capitalize()
            break

    # --- Furnishing ---
    furnish_type = let_type = None
    for el in soup.find_all(string=re.compile(r"(furnished|unfurnished|part.?furnished)", re.I)):
        m = re.search(r"(unfurnished|part.?furnished|furnished)", el, re.I)
        if m:
            furnish_type = let_type = m.group(1).capitalize()
            break

    # -----------------------------------------------------------------------
    # Dynamic section extraction
    # -----------------------------------------------------------------------
    # OpenRent structures each listing as named sections (Price & Bills,
    # Tenant Preference, Availability, Features) each with a heading followed
    # by label/value rows.  The specific rows vary per listing — we extract
    # ALL of them dynamically rather than hardcoding labels.
    #
    # Output:
    #   section_rows: dict[section_slug, dict[label_slug, raw_value]]
    #   where raw_value is True/False (bool checkbox) or str (text cell).
    # -----------------------------------------------------------------------

    TICK_CLASSES   = {"fa-check-circle", "fa-check", "glyphicon-ok", "icon-check"}
    CROSS_CLASSES  = {"fa-times-circle", "fa-times", "glyphicon-remove", "icon-times"}
    TICK_CHARS     = {"✓", "✔", "☑"}
    CROSS_CHARS    = {"✗", "✘", "☒"}

    def _cell_bool(cell) -> Optional[bool]:
        """Read True/False/None from a value cell containing a tick or cross icon."""
        if cell is None:
            return None
        for icon in cell.find_all(["i", "span"]):
            classes = set(icon.get("class") or [])
            if classes & TICK_CLASSES:
                return True
            if classes & CROSS_CLASSES:
                return False
        for img in cell.find_all("img"):
            src = (img.get("src") or img.get("data-src") or "").lower()
            alt = (img.get("alt") or "").lower()
            if any(k in src or k in alt for k in ("tick", "check", "yes", "true")):
                return True
            if any(k in src or k in alt for k in ("cross", "times", "no", "false")):
                return False
        text = cell.get_text(strip=True)
        if any(c in text for c in TICK_CHARS):
            return True
        if any(c in text for c in CROSS_CHARS):
            return False
        low = text.lower()
        if low in ("yes", "true", "included", "allowed"):
            return True
        if low in ("no", "false", "not included", "not allowed"):
            return False
        return False if low == "" else None

    def _slug(s: str) -> str:
        """Normalise label to a consistent slug key."""
        return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")

    def _extract_rows_from_container(container) -> dict:
        """
        Given a BeautifulSoup container (table, dl, div, section),
        extract all label/value pairs as {slug: bool_or_str}.
        """
        rows: dict = {}

        # Table rows: <tr><td>Label</td><td>value</td></tr>
        for tr in container.find_all("tr"):
            cells = tr.find_all(["th", "td"])
            if len(cells) < 2:
                continue
            label_text = cells[0].get_text(strip=True)
            if not label_text:
                continue
            val_cell = cells[1]
            bool_val = _cell_bool(val_cell)
            if bool_val is not None:
                rows[_slug(label_text)] = bool_val
            else:
                text_val = val_cell.get_text(strip=True)
                if text_val:
                    rows[_slug(label_text)] = text_val

        # Definition list: <dt>Label</dt><dd>value</dd>
        for dt in container.find_all("dt"):
            label_text = dt.get_text(strip=True)
            if not label_text:
                continue
            dd = dt.find_next_sibling("dd")
            if dd is None:
                continue
            bool_val = _cell_bool(dd)
            if bool_val is not None:
                rows[_slug(label_text)] = bool_val
            else:
                text_val = dd.get_text(strip=True)
                if text_val:
                    rows[_slug(label_text)] = text_val

        return rows

    # OpenRent section headings we care about
    SECTION_SLUGS = {
        "price_bills":         {"price & bills", "price and bills", "price"},
        "availability":        {"availability"},
        "tenant_preference":   {"tenant preference", "tenant preferences"},
        "features":            {"features", "property features"},
    }

    def _section_slug(heading_text: str) -> Optional[str]:
        low = heading_text.lower().strip()
        for slug, aliases in SECTION_SLUGS.items():
            if low in aliases:
                return slug
        return None

    section_rows: dict[str, dict] = {}

    # Walk all heading-like elements and collect rows that follow
    for heading in soup.find_all(["h2", "h3", "h4", "b", "strong"]):
        sec = _section_slug(heading.get_text(strip=True))
        if sec is None:
            continue
        # Collect rows from the next sibling container (table, dl, div, section)
        container = heading.find_next_sibling(["table", "dl", "div", "section", "ul"])
        if container:
            rows = _extract_rows_from_container(container)
            if rows:
                section_rows.setdefault(sec, {}).update(rows)

    # Fallback: scan all tables and dl globally if sections not found
    if not section_rows:
        global_rows = _extract_rows_from_container(soup)
        # Bin them into sections based on known label slugs
        PRICE_LABELS    = {"deposit", "rent_pcm", "bills_included", "broadband"}
        AVAIL_LABELS    = {"available_from", "available", "minimum_tenancy", "min_tenancy"}
        TENANT_LABELS   = {"student_friendly", "families_allowed", "pets_allowed",
                           "smokers_allowed", "dss_lha_covers_rent", "dss_covers_rent"}
        FEATURE_LABELS  = {"garden", "parking", "fireplace", "furnishing", "epc_rating"}
        for slug, val in global_rows.items():
            if slug in PRICE_LABELS:
                section_rows.setdefault("price_bills", {})[slug] = val
            elif slug in AVAIL_LABELS:
                section_rows.setdefault("availability", {})[slug] = val
            elif slug in TENANT_LABELS:
                section_rows.setdefault("tenant_preference", {})[slug] = val
            elif slug in FEATURE_LABELS:
                section_rows.setdefault("features", {})[slug] = val

    pb   = section_rows.get("price_bills", {})
    av   = section_rows.get("availability", {})
    tp   = section_rows.get("tenant_preference", {})
    feat = section_rows.get("features", {})

    # --- Map known labels → structured fields ---

    # Price & Bills
    dep_raw = str(pb.get("deposit") or "")
    deposit_str, deposit_amount = _parse_deposit(dep_raw)
    # rent_pcm already extracted from the main price block above; don't override

    bills_included = pb.get("bills_included")  # bool or None

    # Availability
    av_raw = str(av.get("available_from") or av.get("available") or "")
    available_from = _parse_available(av_raw)
    min_tenancy_raw = str(av.get("minimum_tenancy") or av.get("min_tenancy") or av.get("min__tenancy") or "")
    min_tenancy = _ask(min_tenancy_raw) if min_tenancy_raw else "ask agent"

    council_tax = _ask(str(feat.get("council_tax") or feat.get("council_tax_band") or ""))

    # Tenant preferences
    student_friendly = tp.get("student_friendly")
    families_allowed = tp.get("families_allowed")
    pets_allowed     = tp.get("pets_allowed")
    smokers_allowed  = tp.get("smokers_allowed")
    dss_covers_rent  = tp.get("dss_lha_covers_rent") or tp.get("dss_covers_rent")

    # Features
    garden    = feat.get("garden")
    parking   = feat.get("parking")
    fireplace = feat.get("fireplace")

    furnish_raw = feat.get("furnishing")
    if furnish_raw and isinstance(furnish_raw, str):
        furnish_type = furnish_raw.capitalize()
        let_type     = furnish_type
    # (already extracted from text above if not found here)

    epc_raw = feat.get("epc_rating")
    epc_rating: Optional[str] = None
    if epc_raw and isinstance(epc_raw, str):
        m_epc = re.match(r"([A-G])\b", epc_raw.strip(), re.I)
        if m_epc:
            epc_rating = m_epc.group(1).upper()
    if not epc_rating:
        m_epc = re.search(r"EPC\s*Rating\s*[:\-]?\s*([A-G])\b", html, re.I)
        if m_epc:
            epc_rating = m_epc.group(1).upper()

    # --- Collect unknown rows as openrent_extras ---
    # Any label we haven't explicitly mapped goes here for future use
    KNOWN_SLUGS = {
        "deposit", "rent_pcm", "bills_included", "broadband",
        "available_from", "available", "minimum_tenancy", "min_tenancy", "min__tenancy",
        "student_friendly", "families_allowed", "pets_allowed", "smokers_allowed",
        "dss_lha_covers_rent", "dss_covers_rent",
        "garden", "parking", "fireplace", "furnishing", "epc_rating",
        "council_tax", "council_tax_band",
    }
    openrent_extras: dict = {}
    for sec_rows in section_rows.values():
        for slug, val in sec_rows.items():
            if slug not in KNOWN_SLUGS:
                openrent_extras[slug] = val

    # --- Size ---
    size_sqft = size_sqm = None
    size_text = soup.get_text(" ")
    sqft_m = re.search(r"([\d,]+)\s*sq\.?\s*ft", size_text, re.I)
    sqm_m  = re.search(r"([\d,]+\.?\d*)\s*(?:sq\.?\s*m|m²|m2)", size_text, re.I)
    if sqft_m:
        size_sqft = int(sqft_m.group(1).replace(",", ""))
    if sqm_m:
        size_sqm = float(sqm_m.group(1).replace(",", ""))

    # --- Description ---
    description = None
    for sel in [".description-text", "#description", "[itemprop='description']",
                ".property-description", ".desc"]:
        el = soup.select_one(sel)
        if el:
            description = el.get_text("\n", strip=True)
            break

    if not description:
        # Fallback: find a long text block
        for el in soup.find_all("p"):
            text = el.get_text(strip=True)
            if len(text) > 150:
                description = text
                break

    # --- Features & Stations ---
    # OpenRent uses headings like <b>Property Details</b> → <ul> for features
    # and <b>Features</b> → <ul> for transport (stations with "~N min. walk")
    features_list: list[str] = []
    stations_list: list[dict] = []

    for heading in soup.find_all(["b", "strong", "h2", "h3", "h4"]):
        heading_text = heading.get_text(strip=True).lower()
        ul = heading.find_next("ul")
        if not ul:
            continue
        items = [li.get_text(strip=True) for li in ul.find_all("li") if li.get_text(strip=True)]

        if "property detail" in heading_text or "key feature" in heading_text:
            features_list = items

        elif heading_text in ("features", "transport", "nearby transport", "nearby stations"):
            # Items like "Charing Cross~2 min. walk" or "Hackney Central~0.4 miles"
            for item in items:
                m_st = re.match(r"^(.+?)\s*[~|]\s*([\d.]+)\s*(min|mile|km)", item, re.I)
                if m_st:
                    name = m_st.group(1).strip()
                    dist_val = float(m_st.group(2))
                    dist_unit = m_st.group(3).lower()
                    # Convert minutes to approximate miles (avg walking 0.05 miles/min)
                    miles = round(dist_val * 0.05, 2) if "min" in dist_unit else round(dist_val, 2)
                    stations_list.append({"name": name, "miles": miles})
                else:
                    # Not a transport item; add to features if features empty
                    if not features_list:
                        features_list.append(item)

    features = "\n".join(features_list) if features_list else None
    stations_json = json.dumps(stations_list, ensure_ascii=False) if stations_list else "ask agent"

    # --- OpenRent-specific: Tenant Preference + Property Features + EPC ---
    # OpenRent renders checkboxes as Font Awesome icons:
    #   Ticked:   <i class="fa fa-check-circle ...">  or  <i class="fa fa-check ...">
    #   Unticked: <i class="fa fa-times-circle ...">  or  no icon / empty cell
    #
    # soup.get_text() strips all icons so plain-text detection cannot distinguish
    # ticked from unticked. We must inspect the HTML element near each label.

    TICK_CLASSES   = {"fa-check-circle", "fa-check", "glyphicon-ok", "icon-check"}
    CROSS_CLASSES  = {"fa-times-circle", "fa-times", "glyphicon-remove", "icon-times"}
    TICK_CHARS     = {"✓", "✔", "☑"}
    CROSS_CHARS    = {"✗", "✘", "☒"}

    def _cell_bool(cell) -> Optional[bool]:
        """
        Determine True/False/None from a BeautifulSoup element (td/dd/span)
        that represents the value side of a label/value pair.

        OpenRent renders as green tick (✓) or red cross (✗) — either as:
          - <i class="fa fa-check ..."> / <i class="fa fa-times ...">
          - <img src="...tick..." / "...check..." / "...cross..." / "...times...">
          - Unicode characters ✓ / ✗
          - Plain text "Yes" / "No"
        An empty cell = False (unticked checkbox).
        """
        if cell is None:
            return None

        # Check <i> and <span> icon classes (Font Awesome etc.)
        for icon in cell.find_all(["i", "span"]):
            classes = set(icon.get("class") or [])
            if classes & TICK_CLASSES:
                return True
            if classes & CROSS_CLASSES:
                return False

        # Check <img> src for tick/check/cross/times keywords
        for img in cell.find_all("img"):
            src = (img.get("src") or img.get("data-src") or "").lower()
            alt = (img.get("alt") or "").lower()
            if any(k in src or k in alt for k in ("tick", "check", "yes", "true")):
                return True
            if any(k in src or k in alt for k in ("cross", "times", "no", "false")):
                return False

        # Check unicode tick/cross in text
        text = cell.get_text(strip=True)
        if any(c in text for c in TICK_CHARS):
            return True
        if any(c in text for c in CROSS_CHARS):
            return False

        # Explicit yes/no text
        low = text.lower()
        if low in ("yes", "true", "included", "allowed"):
            return True
        if low in ("no", "false", "not included", "not allowed"):
            return False

        # Empty cell = unticked (False), non-empty unknown text = None
        return False if low == "" else None


    # (boolean fields extracted dynamically above via section_rows)

    # --- Coordinates ---
    lat, lon = _extract_lat_lon(html)

    # --- Images ---
    image_url, image_urls = _extract_images(soup, lid_num)

    # --- Added date ---
    added_date = None
    for el in soup.find_all(string=re.compile(r"listed|added|posted", re.I)):
        m = re.search(r"(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4})", el)
        if m:
            added_date = m.group(1)
            break

    # --- Build record ---
    rec = ListingRecord(
        source=SOURCE,
        url=url,
        listing_id=listing_id,
        scraped_at=datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        title=_ask(title),
        address=_ask(address),
        postcode=postcode,
        postcode_district=postcode_district,
        price_pcm=price_pcm,
        price_pw=price_pw,
        price_display=price_display,
        deposit=deposit_str,
        deposit_amount=deposit_amount,
        available_from=available_from,
        min_tenancy=min_tenancy,
        let_type=let_type,
        furnish_type=furnish_type,
        council_tax=council_tax,
        property_type=_ask(property_type),
        bedrooms=bedrooms if bedrooms is not None else "ask agent",
        bathrooms=bathrooms if bathrooms is not None else "ask agent",
        size_sqft=size_sqft,
        size_sqm=size_sqm,
        description=description,
        features=features,
        latitude=lat,
        longitude=lon,
        image_url=image_url,
        stations=stations_json,
        schools="ask agent",
        added_date=added_date,
        bills_included=bills_included,
        student_friendly=student_friendly,
        families_allowed=families_allowed,
        pets_allowed=pets_allowed,
        smokers_allowed=smokers_allowed,
        dss_covers_rent=dss_covers_rent,
        garden=garden,
        parking=parking,
        fireplace=fireplace,
        epc_rating=epc_rating,
    )

    # Attach extra attributes (picked up by crawl_openrent when building the dict)
    rec.__dict__["image_urls"] = image_urls
    rec.__dict__["openrent_extras"] = openrent_extras  # unknown labels captured dynamically

    return rec


# ---------------------------------------------------------------------------
# CLI entry point (for testing a single URL)
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Extract a single OpenRent listing")
    parser.add_argument("--url", required=True, help="OpenRent listing URL")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    print(f"Fetching: {args.url}", file=sys.stderr)
    html = fetch_listing(args.url)
    rec = extract_listing(html, args.url)

    if args.json:
        print(json.dumps(rec.__dict__, default=str, indent=2))
    else:
        for k, v in rec.__dict__.items():
            print(f"  {k:20s}: {v!r}")


if __name__ == "__main__":
    main()
