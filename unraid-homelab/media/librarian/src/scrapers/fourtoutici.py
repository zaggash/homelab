import os
import re
import socket
import asyncio
import logging
import urllib.parse
import html as html_lib
from typing import Optional, List, Tuple

from config import Config
from core.models import BookCandidate
from core.matching import calculate_title_similarity
from core.http import DEFAULT_USER_AGENT, download_stream
from scrapers.annas import stealth_browser_page


def resolve_active_fti_domain(
    primary_domain: Optional[str] = None,
    fallback_domains: Optional[List[str]] = None
) -> str:
    """
    Checks DNS resolution for the primary FourToutIci domain.
    Falls back to secondary domains ONLY if the primary fails at the DNS/network level.
    """
    primary = primary_domain or Config.FOURTOUTICI_PRIMARY_DOMAIN
    fallbacks = fallback_domains if fallback_domains is not None else Config.FOURTOUTICI_FALLBACK_DOMAINS

    try:
        socket.getaddrinfo(primary, 443, socket.AF_UNSPEC, socket.SOCK_STREAM)
        return primary
    except (socket.gaierror, socket.herror, OSError) as e:
        logging.warning(f"DNS resolution failed for FourToutIci mirror '{primary}': {e}. Testing fallback mirrors...")

    for fallback in fallbacks:
        try:
            socket.getaddrinfo(fallback, 443, socket.AF_UNSPEC, socket.SOCK_STREAM)
            logging.info(f"FourToutIci fallback mirror '{fallback}' resolved successfully.")
            return fallback
        except (socket.gaierror, socket.herror, OSError):
            continue

    logging.error("No FourToutIci mirror could be resolved via DNS. Defaulting to primary.")
    return primary


def _clean_fti_title(raw_text: str) -> str:
    """
    Cleans raw FourToutIci download label or link text into a clean 'Author - Title' or 'Title'.
    Example: 'Télécharger : EBOOK Il faudrait leur dire – Carène Ponte.epub' -> 'Il faudrait leur dire - Carène Ponte'
    """
    text = html_lib.unescape(raw_text).strip()
    text = re.sub(r'^Télécharger\s*:\s*', '', text, flags=re.IGNORECASE).strip()
    text = re.sub(r'^(?:EBOOK|BD|MANGA|MAGAZINE|JOURNAL|AUDIO|AUTRES)\s+', '', text, flags=re.IGNORECASE).strip()
    text = re.sub(r'\.(?:epub|pdf|mobi|azw3|cbr|cbz)$', '', text, flags=re.IGNORECASE).strip()
    text = re.sub(r'\s*[–—]\s*', ' - ', text).strip()
    return text


async def _async_search_and_download_fti(
    query: str,
    dest_dir: str,
    domain: str,
    min_confidence: float = 0.55,
    timeout_sec: int = 35
) -> Tuple[Optional[str], Optional[str]]:
    """
    Single-pass search and direct download on FourToutIci:
    1. Opens FourToutIci with Camoufox stealth browser.
    2. Searches for the query.
    3. Ranks matching French EPUB candidates.
    4. Downloads the best candidate directly using active session cookies.
    """
    url = f"https://{domain}"
    async with stealth_browser_page() as (page, context):
        logging.info(f"Navigating to FourToutIci ({domain})...")
        await page.goto(url, wait_until="domcontentloaded", timeout=timeout_sec * 1000)
        await asyncio.sleep(1.5)

        # Type search query and click search
        logging.info(f"Searching FourToutIci for '{query}'...")
        await page.fill("#fileSearch", query)
        await page.click("#searchBtn")
        await asyncio.sleep(2.5)

        raw_items = await page.evaluate("""() => {
            const links = Array.from(document.querySelectorAll('a.download-link'));
            return links.map(a => {
                const row = a.closest('tr') || a.closest('.file-item') || a.parentElement;
                return {
                    href: a.href,
                    label: a.getAttribute('aria-label') || '',
                    text: a.innerText || '',
                    rowText: row ? row.innerText : ''
                };
            });
        }""")

        if not raw_items:
            logging.info("FourToutIci returned 0 search results.")
            return None, None

        candidates = []
        for item in raw_items:
            href = item.get("href")
            if not href:
                continue
            label = item.get("label") or item.get("text") or item.get("rowText", "")
            clean_title = _clean_fti_title(label)

            fmt = "epub"
            if ".pdf" in label.lower() or " pdf" in label.lower():
                fmt = "pdf"
            elif ".mobi" in label.lower():
                fmt = "mobi"

            sim = calculate_title_similarity(query, clean_title)
            if fmt == "epub" and sim >= min_confidence:
                candidates.append({
                    "title": clean_title,
                    "download_url": href,
                    "similarity": sim
                })

        if not candidates:
            logging.info(f"No candidate passed confidence threshold ({min_confidence}) on FourToutIci.")
            return None, None

        candidates.sort(key=lambda x: x["similarity"], reverse=True)
        best = candidates[0]
        title = best["title"]
        dl_url = best["download_url"]

        logging.info(f"Found match on FourToutIci: '{title}' (Similarity: {best['similarity']:.2f}). Streaming file...")

        safe_title = re.sub(r'[/\\?%*:|"<>]', '_', title)
        dest_filename = os.path.join(dest_dir, f"{safe_title}.epub")

        cookies = await context.cookies()
        user_agent = await page.evaluate("navigator.userAgent")
        cookie_header = "; ".join(f"{c['name']}={c['value']}" for c in cookies if 'name' in c and 'value' in c)

        headers = {
            "User-Agent": user_agent or DEFAULT_USER_AGENT,
            "Referer": url
        }
        if cookie_header:
            headers["Cookie"] = cookie_header

        success = download_stream(
            dl_url,
            dest_filename,
            headers=headers,
            timeout=90,
            min_size_bytes=1024
        )

        if success:
            logging.info(f"Book saved successfully from FourToutIci: {dest_filename}")
            return dest_filename, title

        return None, None


def fetch_from_fourtoutici(query: str, dest_dir: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Entry point for FourToutIci single-pass search & download.
    """
    domain = resolve_active_fti_domain()
    try:
        return asyncio.run(_async_search_and_download_fti(query, dest_dir, domain))
    except Exception as e:
        logging.error(f"FourToutIci error on {domain}: {e}")
        return None, None
