"""
extract_one_page.py
-------------------
Fetch and parse a single Rightmove listing page.

Exports:
  fetch_rendered_html_and_nearby(url) -> tuple[str, list[dict], list[dict]]
  build_record_from_html(html, url, source, stations, schools) -> ListingRecord

Requirements applied:
  - Unknown / null string fields  → "ask agent"
  - Prices: always resolve to price_pcm; price_pw kept when listed weekly;
    price_display shows both e.g. "£350 pw (£1,517 pcm)"
  - Room sizes extracted from key-features + description text
"""

import argparse
import json
import re
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright


# ══════════════════════════════════════════════════════════════════════════════
# Utils
# ══════════════════════════════════════════════════════════════════════════════

def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def clean_text(s: str) -> str:
    s = (s or "").replace("\u00a0", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s

def norm_key(s: str) -> str:
    return clean_text(s).replace(":", "").lower()

def parse_money(s: str) -> Optional[int]:
    if not s:
        return None
    m = re.search(r"£\s*([\d,]+)", s)
    return int(m.group(1).replace(",", "")) if m else None

def parse_date_ddmmyyyy(s: str) -> Optional[str]:
    s = (s or "").strip()
    m = re.match(r"^(\d{2})/(\d{2})/(\d{4})$", s)
    if not m:
        return None
    dd, mm, yyyy = m.group(1), m.group(2), m.group(3)
    return f"{yyyy}-{mm}-{dd}"


_NOW_TOKENS = {"now", "immediately", "available now", "available immediately", "asap"}

def parse_available_from(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    clean = clean_text(s).lower()
    if clean in _NOW_TOKENS:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")
    parsed = parse_date_ddmmyyyy(s)
    return parsed if parsed else s


_POSTCODE_RE = re.compile(
    r'\b([A-Z]{1,2}\d[0-9A-Z]?\s*\d[A-Z]{2})\b',
    re.IGNORECASE,
)

def extract_postcode(address: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """Return (postcode, postcode_district) from a raw address string."""
    if not address:
        return None, None
    m = _POSTCODE_RE.search(address)
    if not m:
        return None, None
    postcode = re.sub(r'\s+', ' ', m.group(1).upper()).strip()
    district = postcode.split()[0] if ' ' in postcode else postcode[:-3].strip()
    return postcode, district


def normalise_council_tax(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    m = re.search(r'\bband\s+([A-H])\b', s, re.IGNORECASE)
    return f"Band {m.group(1).upper()}" if m else s


def extract_deposit_amount(deposit_str: Optional[str]) -> Optional[int]:
    return parse_money(deposit_str) if deposit_str else None


# strict unknown mapping: only exact tokens become "ask agent"; empty stays None
UNKNOWN_TOKENS = {
    "ask agent", "ask the agent",
    "not provided", "not known", "unknown",
    "n/a", "na", "-", "—", "tbc"
}

def normalize_maybe_unknown(v: Optional[str]) -> Optional[str]:
    if v is None:
        return None
    s = clean_text(v)
    if not s:
        return None
    # Remove Rightmove deposit boilerplate that leaks into field values
    s = re.split(r"A deposit provides security", s, maxsplit=1, flags=re.IGNORECASE)[0].strip()
    if not s:
        return None
    if s.lower() in UNKNOWN_TOKENS:
        return "ask agent"
    return s

def _ask(val) -> str:
    """Return 'ask agent' if val is None/empty, else the string value."""
    if val is None:
        return "ask agent"
    s = str(val).strip()
    return s if s else "ask agent"


# ══════════════════════════════════════════════════════════════════════════════
# Size parsing  (handles commas like 6,028)
# ══════════════════════════════════════════════════════════════════════════════

def parse_int_with_commas(s: str) -> Optional[int]:
    if not s:
        return None
    s2 = s.replace(",", "").strip()
    return int(s2) if s2.isdigit() else None

def extract_sizes_from_text(text: str) -> Tuple[Optional[int], Optional[int]]:
    sqft_candidates = re.findall(
        r"(\d{1,3}(?:,\d{3})+|\d+)\s*sq\s*ft", text, flags=re.IGNORECASE
    )
    sqm_candidates = re.findall(
        r"(\d{1,3}(?:,\d{3})+|\d+)\s*sq\s*m", text, flags=re.IGNORECASE
    )
    sqft_vals = [parse_int_with_commas(x) for x in sqft_candidates]
    sqm_vals  = [parse_int_with_commas(x) for x in sqm_candidates]
    # pick largest to avoid accidental small matches like "28"
    sqft = max([v for v in sqft_vals if v is not None], default=None)
    sqm  = max([v for v in sqm_vals  if v is not None], default=None)
    return sqft, sqm


# ══════════════════════════════════════════════════════════════════════════════
# Price combining  (pw → pcm, always store both)
# ══════════════════════════════════════════════════════════════════════════════

PW_TO_PCM = 52 / 12

def _build_price(price_pcm: Optional[int], price_pw: Optional[int]) -> Tuple[Optional[int], Optional[int], str]:
    """
    Given raw pcm and pw values from the page, return (pcm, pw, display).
    - If only pw given: derive pcm = round(pw * 52/12)
    - If both given: use both as-is
    - display shows both when pw is present
    """
    if price_pcm is None and price_pw is None:
        return None, None, "ask agent"

    if price_pw is not None and price_pcm is None:
        pcm = round(price_pw * PW_TO_PCM)
        return pcm, price_pw, f"£{price_pw:,} pw (£{pcm:,} pcm)"

    if price_pcm is not None and price_pw is not None:
        return price_pcm, price_pw, f"£{price_pcm:,} pcm (£{price_pw:,} pw)"

    # pcm only
    return price_pcm, None, f"£{price_pcm:,} pcm"



# ══════════════════════════════════════════════════════════════════════════════
# Data model
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class ListingRecord:
    source:         str
    url:            str
    listing_id:     str
    scraped_at:     str

    address:          Optional[str] = None
    postcode:         Optional[str] = None   # "E8 1JU"
    postcode_district:Optional[str] = None   # "E8"
    title:            Optional[str] = None
    added_date:       Optional[str] = None

    # Price — always pcm; pw kept when listed weekly; display shows both
    price_pcm:        Optional[int] = None
    price_pw:         Optional[int] = None
    price_display:    str           = "ask agent"

    deposit:          Optional[str] = None   # "£2,808 (6 weeks)" / "ask agent"
    deposit_amount:   Optional[int] = None   # 2808

    available_from:   Optional[str] = None   # ISO date or "ask agent"
    min_tenancy:      Optional[str] = None
    let_type:         Optional[str] = None
    furnish_type:     Optional[str] = None
    council_tax:      Optional[str] = None   # "Band C"

    property_type:    Optional[str] = None
    bedrooms:         Optional[Any] = None   # int or "ask agent"
    bathrooms:        Optional[Any] = None   # int or "ask agent"
    size_sqft:        Optional[Any] = None
    size_sqm:         Optional[Any] = None

    description:      Optional[str] = None
    features:         Optional[str] = None   # newline-joined key-feature bullets

    latitude:         Optional[float] = None
    longitude:        Optional[float] = None
    image_url:        Optional[str] = None

    # JSON strings (Qdrant payload must be str)
    stations:         Optional[str] = None   # json.dumps([{"name": ..., "miles": ...}])
    schools:          Optional[str] = None

    # OpenRent-specific fields (None for Rightmove records unless merged)
    bills_included:   Optional[bool] = None
    student_friendly: Optional[bool] = None
    families_allowed: Optional[bool] = None
    pets_allowed:     Optional[bool] = None
    smokers_allowed:  Optional[bool] = None
    dss_covers_rent:  Optional[bool] = None
    garden:           Optional[bool] = None
    parking:          Optional[bool] = None
    fireplace:        Optional[bool] = None
    epc_rating:       Optional[str]  = None  # "A"–"G"


DTDD_MAP = {
    "let available date": "available_from",
    "deposit":            "deposit",
    "min. tenancy":       "min_tenancy",
    "min tenancy":        "min_tenancy",
    "let type":           "let_type",
    "furnish type":       "furnish_type",
    "council tax":        "council_tax",
}


# ══════════════════════════════════════════════════════════════════════════════
# Playwright helpers
# ══════════════════════════════════════════════════════════════════════════════

def _click_first_available(page, selectors: List[str], timeout_ms: int = 2500) -> bool:
    for sel in selectors:
        try:
            page.locator(sel).first.click(timeout=timeout_ms)
            page.wait_for_timeout(400)
            return True
        except Exception:
            continue
    return False


def click_tab(page, name: str, timeout_ms: int = 5000) -> None:
    selectors = [
        f'role=tab[name="{name}"]',
        f'button:has-text("{name}")',
        f'a:has-text("{name}")',
        f'[role="button"]:has-text("{name}")',
    ]
    last = None
    deadline = time.time() + max(timeout_ms, 500) / 1000.0
    for sel in selectors:
        while time.time() < deadline:
            try:
                loc = page.locator(sel)
                cnt = loc.count()
                if cnt == 0:
                    page.wait_for_timeout(150)
                    continue
                for i in range(min(cnt, 12)):
                    item = loc.nth(i)
                    try:
                        if item.is_visible():
                            item.click(timeout=1500)
                            page.wait_for_timeout(300)
                            return
                    except Exception as e:
                        last = e
                        continue
                page.wait_for_timeout(150)
            except Exception as e:
                last = e
                page.wait_for_timeout(150)
                continue
    if last:
        raise last
    raise RuntimeError(f"Tab not clickable: {name}")


def wait_tab_active(page, name: str, timeout_ms: int = 7000) -> None:
    page.wait_for_function(
        """
        (tabName) => {
          const norm = (s) => (s || '').replace(/\\s+/g, ' ').trim().toLowerCase();
          const want = norm(tabName);
          const tabs = Array.from(document.querySelectorAll('[role="tab"], button, a'));
          for (const el of tabs) {
            const txt = norm(el.innerText || el.textContent || '');
            if (!txt) continue;
            if (txt !== want && !txt.includes(want)) continue;
            const rect = el.getBoundingClientRect();
            if (!(rect.width > 0 && rect.height > 0)) continue;
            const aria = (el.getAttribute('aria-selected') || '').toLowerCase();
            const cls = (el.className || '').toString().toLowerCase();
            if (aria === 'true' || cls.includes('active') || cls.includes('selected')) {
              return true;
            }
          }
          return false;
        }
        """,
        arg=name,
        timeout=timeout_ms,
    )


def wait_nearest_header(page, header_text: str, timeout_ms: int = 9000) -> None:
    page.wait_for_function(
        """
        (hdr) => {
          const t = (document.body.innerText || '').toLowerCase();
          return t.includes((hdr || '').toLowerCase());
        }
        """,
        arg=header_text,
        timeout=timeout_ms,
    )


def click_tab_js_fallback(page, name: str) -> bool:
    try:
        ok = page.evaluate(
            """
            (tabName) => {
              const norm = (s) => (s || '').replace(/\\s+/g, ' ').trim().toLowerCase();
              const want = norm(tabName);
              const candidates = Array.from(document.querySelectorAll('[role="tab"], button, a, [role="button"]'));
              for (const el of candidates) {
                const txt = norm(el.innerText || el.textContent || '');
                if (!txt) continue;
                if (txt !== want && !txt.includes(want)) continue;
                const rect = el.getBoundingClientRect();
                if (!(rect.width > 0 && rect.height > 0)) continue;
                try { el.scrollIntoView({block: 'center', inline: 'center'}); } catch (e) {}
                el.click();
                return true;
              }
              return false;
            }
            """,
            name,
        )
        return bool(ok)
    except Exception:
        return False


def activate_tab(page, name: str, timeout_ms: int = 7000) -> None:
    last = None
    try:
        click_tab(page, name, timeout_ms=timeout_ms)
        wait_tab_active(page, name, timeout_ms=timeout_ms)
        return
    except Exception as e:
        last = e
    try:
        if click_tab_js_fallback(page, name):
            page.wait_for_timeout(300)
            wait_tab_active(page, name, timeout_ms=timeout_ms)
            return
    except Exception as e:
        last = e
    if last:
        raise last
    raise RuntimeError(f"Failed to activate tab: {name}")


def extract_nearby_by_header(page, header_text: str) -> List[Dict[str, Any]]:
    data = page.evaluate(
        """
        (hdr) => {
          const norm = (s) => (s || '').replace(/\\u00a0/g,' ').replace(/\\s+/g,' ').trim();
          const hdrLower = (hdr || '').toLowerCase();
          const mileRe = /^(\\d+(?:\\.\\d+)?)\\s*miles?$/i;

          const els = Array.from(document.querySelectorAll('*'));
          let headerEl = null;
          for (const el of els) {
            const t = norm(el.innerText);
            if (!t) continue;
            if (t.toLowerCase() === hdrLower || t.toLowerCase().includes(hdrLower)) {
              headerEl = el;
              break;
            }
          }
          if (!headerEl) return [];

          let container = headerEl;
          for (let i = 0; i < 12; i++) {
            if (!container.parentElement) break;
            const cand = container.parentElement;
            const lines = norm(cand.innerText).split(/\\n+/).map(norm).filter(Boolean);
            const mileCount = lines.filter(x => mileRe.test(x)).length;
            if (mileCount >= 1) container = cand;
            else break;
          }

          const out = [];
          const seen = new Set();

          const invalidLine = (line) => {
            const low = norm(line).toLowerCase();
            if (!low) return true;
            if (mileRe.test(low)) return true;
            if (low.includes('nearest stations') || low.includes('nearest schools')) return true;
            if (low === 'stations' || low === 'schools' || low === 'my places') return true;
            if (low.startsWith('type:') || low.startsWith('rating:') || low.startsWith('ofsted:')) return true;
            if (low === 'state school' || low === 'independent school') return true;
            if (low.includes(' | ')) return true;
            return false;
          };

          const parseRow = (rowEl) => {
            const rowLines = norm(rowEl.innerText).split(/\\n+/).map(norm).filter(Boolean);
            if (!rowLines.length) return null;
            let miles = null, mileIdx = -1;
            for (let i = 0; i < rowLines.length; i++) {
              const mm = rowLines[i].match(mileRe);
              if (mm) { miles = parseFloat(mm[1]); mileIdx = i; break; }
            }
            if (miles === null || Number.isNaN(miles)) return null;
            let name = null;
            const anchors = Array.from(rowEl.querySelectorAll('a, h3, h2, [role="link"]'));
            for (const a of anchors) {
              const t = norm(a.innerText || a.textContent || '');
              if (!invalidLine(t)) { name = t; break; }
            }
            if (!name && mileIdx > 0) {
              for (let i = mileIdx - 1; i >= 0; i--) {
                if (!invalidLine(rowLines[i])) { name = rowLines[i]; break; }
              }
            }
            if (!name || invalidLine(name)) return null;
            return { name, miles };
          };

          const iconSelectors = ['svg', 'img', '[data-testid*="icon"]', '[class*="icon"]'];
          const iconNodes = [];
          for (const sel of iconSelectors) {
            for (const n of Array.from(container.querySelectorAll(sel))) iconNodes.push(n);
          }
          for (const icon of iconNodes) {
            let row = icon, found = false;
            for (let i = 0; i < 8; i++) {
              if (!row) break;
              const txt = norm(row.innerText);
              if (txt && txt.split(/\\n+/).some(line => mileRe.test(norm(line)))) { found = true; break; }
              row = row.parentElement;
            }
            if (!found || !row) continue;
            const parsed = parseRow(row);
            if (!parsed) continue;
            const key = parsed.name + '|' + parsed.miles;
            if (seen.has(key)) continue;
            seen.add(key);
            out.push(parsed);
          }
          if (out.length > 0) { out.sort((a, b) => a.miles - b.miles); return out; }

          const all = Array.from(container.querySelectorAll('*'));
          const mileNodes = all.filter(el => mileRe.test(norm(el.innerText)));
          for (const node of mileNodes) {
            const milesText = norm(node.innerText);
            const mm = milesText.match(mileRe);
            if (!mm) continue;
            let row = node;
            for (let i = 0; i < 6; i++) {
              if (!row.parentElement) break;
              row = row.parentElement;
              const txt = norm(row.innerText);
              if (!txt) continue;
              if (txt.split(/\\n+/).map(norm).filter(Boolean).length >= 2) break;
            }
            const parsed = parseRow(row);
            if (!parsed) continue;
            const key = parsed.name + '|' + parsed.miles;
            if (seen.has(key)) continue;
            seen.add(key);
            out.push(parsed);
          }
          out.sort((a, b) => a.miles - b.miles);
          return out;
        }
        """,
        header_text,
    )
    return data if isinstance(data, list) else []


def extract_nearby_from_text_fallback(page, header_text: str) -> List[Dict[str, Any]]:
    body_text = page.inner_text("body")
    lines = [clean_text(x) for x in body_text.splitlines()]
    lines = [x for x in lines if x]
    hdr = header_text.lower()

    start = -1
    for i, line in enumerate(lines):
        if hdr in line.lower():
            start = i
            break
    if start < 0:
        return []

    out: List[Dict[str, Any]] = []
    miles_only_re = re.compile(r"^(\d+(?:\.\d+)?)\s*miles?$", re.IGNORECASE)
    full_re = re.compile(r"^(.+?)\s+(\d+(?:\.\d+)?)\s*miles?$", re.IGNORECASE)
    stop_tokens = {"show more on map", "my places", "stations", "schools", "nearest stations", "nearest schools"}
    meta_prefixes = ("type:", "rating:", "ofsted:", "state school", "independent school")

    for line in lines[start + 1 : start + 200]:
        low = line.lower()
        if low in stop_tokens:
            continue
        if "ofsted information displayed" in low or "show more on map" in low:
            break
        if low.startswith("to check broadband") or low.startswith("council tax"):
            break
        if low.startswith(meta_prefixes):
            continue
        if " | " in line and ("ofsted" in low or "state school" in low):
            continue
        m_full = full_re.match(line)
        if m_full:
            out.append({"name": clean_text(m_full.group(1)), "miles": float(m_full.group(2))})
            continue
        m_miles = miles_only_re.match(line)
        if m_miles and out and out[-1].get("miles") is None:
            out[-1]["miles"] = float(m_miles.group(1))
            continue
        if (not low.startswith(meta_prefixes) and " miles" not in low
                and " | " not in line and ":" not in line
                and 2 < len(line) < 120 and not low.startswith("nearest ")):
            out.append({"name": line, "miles": None})

    cleaned: List[Dict[str, Any]] = []
    seen: set = set()
    for row in out:
        name = clean_text(str(row.get("name") or ""))
        miles = row.get("miles")
        low_name = name.lower()
        if (not name or miles is None or low_name.startswith(meta_prefixes)
                or low_name in {"state school", "independent school"} | stop_tokens):
            continue
        key = f"{name}|{miles}"
        if key in seen:
            continue
        seen.add(key)
        cleaned.append({"name": name, "miles": float(miles)})

    cleaned.sort(key=lambda x: x["miles"])
    return cleaned


def _extract_nearby_with_retry(page, header_text: str, timeout_ms: int = 10_000) -> List[Dict[str, Any]]:
    deadline = time.time() + max(timeout_ms, 500) / 1000.0
    last_rows: List[Dict[str, Any]] = []
    while time.time() < deadline:
        try:
            rows = extract_nearby_by_header(page, header_text)
            if rows:
                return rows
            last_rows = rows
        except Exception:
            pass
        try:
            rows2 = extract_nearby_from_text_fallback(page, header_text)
            if rows2:
                return rows2
        except Exception:
            pass
        page.wait_for_timeout(250)
    return last_rows


def dismiss_onetrust(page) -> None:
    for sel in [
        "#onetrust-accept-btn-handler", "#onetrust-reject-all-handler",
        "button:has-text('Accept')", "button:has-text('Accept all')",
        "button:has-text('Reject')", "button:has-text('Reject all')",
        "button:has-text('Continue')",
    ]:
        try:
            loc = page.locator(sel).first
            if loc.count() and loc.is_visible():
                loc.click(timeout=1500)
                page.wait_for_timeout(300)
                break
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════════════════════
# Fetch page + click tabs to get stations / schools
# ══════════════════════════════════════════════════════════════════════════════

def fetch_rendered_html_and_nearby(
    url: str, timeout_ms: int = 45_000
) -> Tuple[str, List[Dict[str, Any]], List[Dict[str, Any]]]:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        page.wait_for_timeout(2000)

        dismiss_onetrust(page)

        _click_first_available(page, selectors=[
            'text=Read full description', 'text=Read Full Description',
            'text=Read more', 'text=Read More',
            'text=Show more', 'text=Show More',
            'role=button[name="Read full description"]',
            'role=link[name="Read full description"]',
            'role=button[name="Read more"]',
            'role=link[name="Read more"]',
        ], timeout_ms=3000)
        page.wait_for_timeout(500)

        stations: List[Dict[str, Any]] = []
        schools:  List[Dict[str, Any]] = []

        try:
            activate_tab(page, "Stations", timeout_ms=7000)
            wait_nearest_header(page, "NEAREST STATIONS", timeout_ms=12000)
            stations = _extract_nearby_with_retry(page, "NEAREST STATIONS", timeout_ms=8000)
        except Exception as e:
            print(f"Warn: station extraction skipped for {url}: {e}")

        try:
            activate_tab(page, "Schools", timeout_ms=7000)
            try:
                wait_nearest_header(page, "NEAREST SCHOOLS", timeout_ms=12000)
            except Exception:
                page.wait_for_function(
                    "() => { const t = (document.body.innerText||'').toLowerCase(); "
                    "return t.includes('type:') || t.includes('rating:') || t.includes('nearest schools'); }",
                    timeout=10000,
                )
            schools = _extract_nearby_with_retry(page, "NEAREST SCHOOLS", timeout_ms=10000)
        except Exception as e:
            print(f"Warn: school extraction skipped for {url}: {e}")

        html = page.content()
        browser.close()
        return html, stations, schools


# ══════════════════════════════════════════════════════════════════════════════
# BeautifulSoup extractors
# ══════════════════════════════════════════════════════════════════════════════

def extract_title_and_added_date(soup: BeautifulSoup) -> Tuple[Optional[str], Optional[str]]:
    h1 = soup.find("h1") or soup.find("h2")
    title = clean_text(h1.get_text(" ", strip=True)) if h1 else None
    text = soup.get_text(" ", strip=True)
    m = re.search(r"Added on\s+(\d{2})/(\d{2})/(\d{4})", text)
    added = f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else None
    return title, added


def extract_price(soup: BeautifulSoup) -> Tuple[Optional[int], Optional[int]]:
    text = soup.get_text(" ", strip=True)
    m_pcm = re.search(r"£\s*[\d,]+\s*pcm", text, re.IGNORECASE)
    m_pw  = re.search(r"£\s*[\d,]+\s*pw",  text, re.IGNORECASE)
    return (
        parse_money(m_pcm.group(0)) if m_pcm else None,
        parse_money(m_pw.group(0))  if m_pw  else None,
    )


def extract_address(soup: BeautifulSoup) -> Optional[str]:
    price_node = (
        soup.find(string=re.compile(r"\bpcm\b", re.IGNORECASE))
        or soup.find(string=re.compile(r"\bpw\b", re.IGNORECASE))
    )
    if not price_node:
        return None
    price_el = getattr(price_node, "parent", None)
    if not price_el:
        return None
    container = price_el
    for _ in range(4):
        if getattr(container, "parent", None):
            container = container.parent
    prev = container
    for _ in range(350):
        prev = prev.find_previous()
        if not prev:
            break
        if getattr(prev, "name", None) not in ["div", "span", "p", "h1", "h2", "h3"]:
            continue
        txt = clean_text(prev.get_text(" ", strip=True))
        if not txt:
            continue
        if re.search(r"£\s*[\d,]+\s*(pcm|pw)", txt, re.IGNORECASE):
            continue
        if "tenancy info" in txt.lower():
            continue
        if "," in txt or re.search(r"\b[A-Z]{1,2}\d{1,2}[A-Z]?\b", txt):
            return txt
    return None


def extract_dt_dd_pairs(soup: BeautifulSoup) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for dt in soup.find_all("dt"):
        label = dt.get_text(" ", strip=True)
        if not label:
            continue
        dd = dt.find_next_sibling("dd") or dt.find_next("dd")
        if not dd:
            continue
        value = dd.get_text(" ", strip=True)
        if value:
            out[label] = value
    return out


def extract_core_specs(soup: BeautifulSoup) -> Tuple[Optional[str], Optional[int], Optional[int], Optional[int], Optional[int]]:
    text_nl = soup.get_text("\n", strip=True)
    prop_type = bedrooms = bathrooms = None
    m = re.search(r"PROPERTY TYPE\s*\n([^\n]+)", text_nl, re.IGNORECASE)
    if m:
        prop_type = clean_text(m.group(1))
    m = re.search(r"BEDROOMS\s*\n(\d+)", text_nl, re.IGNORECASE)
    if m:
        bedrooms = int(m.group(1))
    m = re.search(r"BATHROOMS\s*\n(\d+)", text_nl, re.IGNORECASE)
    if m:
        bathrooms = int(m.group(1))
    text_sp = soup.get_text(" ", strip=True)
    size_sqft, size_sqm = extract_sizes_from_text(text_sp)
    return prop_type, bedrooms, bathrooms, size_sqft, size_sqm


DESCRIPTION_UI_NOISE = {"read full description", "read more", "show more", "show less", "read less", "collapse", "expand"}
PARA_SEP = " <PARA> "

def extract_description(soup: BeautifulSoup) -> Optional[str]:
    header = None
    for tag in soup.find_all(["h2", "h3", "h4"]):
        if "description" in tag.get_text(" ", strip=True).lower():
            header = tag
            break
    if not header:
        return None
    parts: List[str] = []
    cur = header.find_next_sibling()
    while cur:
        if cur.name in ["h2", "h3", "h4"]:
            break
        txt = cur.get_text("\n", strip=True).replace("\u00a0", " ")
        if txt:
            lines = [clean_text(x) for x in txt.split("\n")]
            cleaned = []
            for line in lines:
                if line.lower() in DESCRIPTION_UI_NOISE:
                    continue
                for noise in DESCRIPTION_UI_NOISE:
                    line = re.sub(rf"\b{re.escape(noise)}\b", "", line, flags=re.IGNORECASE).strip()
                if line:
                    cleaned.append(line)
            if cleaned:
                parts.append(PARA_SEP.join(cleaned))
        cur = cur.find_next_sibling()
    desc = PARA_SEP.join([p for p in parts if p]).strip()
    desc = re.split(r"\bBrochures?\b", desc, maxsplit=1, flags=re.IGNORECASE)[0].strip()
    return desc or None


def extract_features(soup: BeautifulSoup) -> Optional[List[str]]:
    heading = None
    for tag in soup.find_all(["h2", "h3", "h4"]):
        if "key features" in tag.get_text(" ", strip=True).lower():
            heading = tag
            break
    if not heading:
        return None
    container = heading.find_next()
    lis = container.find_all("li") if container else []
    feats = [clean_text(li.get_text(" ", strip=True)) for li in lis if li.get_text(strip=True)]
    feats = [f for f in feats if f and len(f) <= 200]
    out, seen = [], set()
    for f in feats:
        if f not in seen:
            seen.add(f)
            out.append(f)
    return out or None


def extract_lat_lon(html: str) -> Tuple[Optional[float], Optional[float]]:
    """Extract latitude/longitude from Rightmove's embedded JSON blob."""
    patterns = [
        r'"latitude"\s*:\s*(-?\d+\.\d+)',
        r'"lat"\s*:\s*(-?\d+\.\d+)',
        r'latitude["\s:]+(-?\d+\.\d+)',
    ]
    lon_patterns = [
        r'"longitude"\s*:\s*(-?\d+\.\d+)',
        r'"lng"\s*:\s*(-?\d+\.\d+)',
        r'"lon"\s*:\s*(-?\d+\.\d+)',
        r'longitude["\s:]+(-?\d+\.\d+)',
    ]
    lat = lon = None
    for pat in patterns:
        m = re.search(pat, html)
        if m:
            lat = float(m.group(1))
            # sanity check: UK latitude range
            if not (49.0 <= lat <= 61.0):
                lat = None
                continue
            break
    for pat in lon_patterns:
        m = re.search(pat, html)
        if m:
            lon = float(m.group(1))
            # sanity check: UK longitude range
            if not (-8.0 <= lon <= 2.0):
                lon = None
                continue
            break
    return lat, lon


def extract_image_url(soup: BeautifulSoup) -> Optional[str]:
    """Extract og:image meta tag — Rightmove's property cover photo."""
    tag = soup.find("meta", property="og:image")
    if tag and tag.get("content"):
        return tag["content"]
    return None


def _listing_id(url: str) -> str:
    m = re.search(r'/properties/(\d+)', url or "")
    return f"rightmove:{m.group(1)}" if m else ""


# ══════════════════════════════════════════════════════════════════════════════
# Build record
# ══════════════════════════════════════════════════════════════════════════════

def build_record_from_html(
    html:     str,
    url:      str,
    source:   str = "rightmove",
    stations: Optional[List[Dict[str, Any]]] = None,
    schools:  Optional[List[Dict[str, Any]]] = None,
) -> ListingRecord:
    soup = BeautifulSoup(html, "lxml")
    lat, lon = extract_lat_lon(html)

    title, added_date = extract_title_and_added_date(soup)
    raw_pcm, raw_pw   = extract_price(soup)
    price_pcm, price_pw, price_display = _build_price(raw_pcm, raw_pw)

    rec = ListingRecord(
        source=source,
        url=url,
        listing_id=_listing_id(url),
        scraped_at=now_utc_iso(),
        title=title,
        added_date=added_date,
        price_pcm=price_pcm,
        price_pw=price_pw,
        price_display=price_display,
    )

    rec.address = extract_address(soup)
    rec.postcode, rec.postcode_district = extract_postcode(rec.address)

    # letting details from dt/dd pairs
    pairs = extract_dt_dd_pairs(soup)
    for raw_k, raw_v in pairs.items():
        k     = norm_key(raw_k)
        field = DTDD_MAP.get(k)
        if not field:
            continue
        v = normalize_maybe_unknown(raw_v)
        if field == "available_from":
            rec.available_from = parse_available_from(v)
        elif field == "deposit":
            rec.deposit        = v
            rec.deposit_amount = extract_deposit_amount(v)
        elif field == "council_tax":
            rec.council_tax = normalise_council_tax(v)
        else:
            setattr(rec, field, v)

    # core specs
    prop_type, bedrooms, bathrooms, size_sqft, size_sqm = extract_core_specs(soup)
    rec.property_type = _ask(prop_type)
    rec.bathrooms     = _ask(bathrooms)
    rec.size_sqft     = _ask(size_sqft)
    rec.size_sqm      = _ask(size_sqm)
    rec.let_type      = _ask(rec.let_type)
    rec.furnish_type  = _ask(rec.furnish_type)
    rec.min_tenancy   = _ask(rec.min_tenancy)

    # studio / bedsit → 0 bedrooms
    if bedrooms is None:
        text_lower = (title or "").lower() + " " + soup.get_text(" ", strip=True).lower()
        if "studio" in text_lower or "bedsit" in text_lower:
            rec.bedrooms = 0
        else:
            rec.bedrooms = "ask agent"
    else:
        rec.bedrooms = bedrooms

    # text
    desc_text  = extract_description(soup) or "ask agent"
    feats_list = extract_features(soup)
    feats_text = "\n".join(feats_list) if feats_list else "ask agent"

    rec.description = desc_text
    rec.features    = feats_text

    # stations & schools → always JSON strings
    rec.stations = json.dumps(stations, ensure_ascii=False) if stations else "ask agent"
    rec.schools  = json.dumps(schools,  ensure_ascii=False) if schools  else "ask agent"

    rec.latitude  = lat
    rec.longitude = lon
    rec.image_url = extract_image_url(soup)

    return rec


# ══════════════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url",    required=True,          help="Rightmove property URL")
    parser.add_argument("--source", default="rightmove",    help="Source label stored in output")
    args = parser.parse_args()

    html, stations, schools = fetch_rendered_html_and_nearby(args.url)
    rec = build_record_from_html(html, url=args.url, source=args.source, stations=stations, schools=schools)
    print(json.dumps(asdict(rec), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
