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

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-GB,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

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
    """Fetch raw HTML of an OpenRent listing page."""
    own_client = client is None
    if own_client:
        client = httpx.Client(headers=HEADERS, follow_redirects=True, timeout=20)
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

    # --- Key details table: available from, min tenancy, deposit ---
    available_from = min_tenancy = deposit_str = council_tax = None
    deposit_amount = None

    # OpenRent uses a definition list or table for key facts
    # Look for labeled rows
    label_map = {
        "available from":   "available_from",
        "available":        "available_from",
        "minimum tenancy":  "min_tenancy",
        "min. tenancy":     "min_tenancy",
        "min tenancy":      "min_tenancy",
        "deposit":          "deposit",
        "council tax":      "council_tax",
        "council tax band": "council_tax",
    }

    results: dict[str, str] = {}

    # Strategy 1: dt/dd pairs
    for dt in soup.find_all("dt"):
        key = dt.get_text(strip=True).lower()
        dd = dt.find_next_sibling("dd")
        if dd:
            for k, field in label_map.items():
                if k in key:
                    results[field] = dd.get_text(strip=True)

    # Strategy 2: table rows with label|value
    for row in soup.find_all("tr"):
        cells = row.find_all(["th", "td"])
        if len(cells) >= 2:
            key = cells[0].get_text(strip=True).lower()
            val = cells[1].get_text(strip=True)
            for k, field in label_map.items():
                if k in key:
                    results[field] = val

    # Strategy 3: text search for labeled values
    for label, field in label_map.items():
        if field in results:
            continue
        pattern = re.compile(
            rf"{re.escape(label)}\s*[:\-]?\s*([^\n<]+)", re.I
        )
        m = pattern.search(soup.get_text(" "))
        if m:
            results[field] = m.group(1).strip()

    available_from = _parse_available(results.get("available_from", ""))
    min_tenancy    = _ask(results.get("min_tenancy"))
    council_tax    = _ask(results.get("council_tax"))

    dep_raw = results.get("deposit", "")
    deposit_str, deposit_amount = _parse_deposit(dep_raw)

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
    )

    # Attach image_urls list as extra attribute (picked up by sync_qdrant if present)
    rec.__dict__["image_urls"] = image_urls

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
