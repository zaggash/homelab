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
    Example: 'Télécharger : EBOOK Il faudrait leur dire – Carène Ponte.epub' -> 'Carène Ponte - Il faudrait leur dire'
    """
    text = html_lib.unescape(raw_text).strip()
    # Strip prefix 'Télécharger :'
    text = re.sub(r'^Télécharger\s*:\s*', '', text, flags=re.IGNORECASE).strip()
    # Strip leading category tag (EBOOK, BD, MANGA, etc.)
    text = re.sub(r'^(?:EBOOK|BD|MANGA|MAGAZINE|JOURNAL|AUDIO|AUTRES)\s+', '', text, flags=re.IGNORECASE).strip()
    # Strip trailing file extension
    text = re.sub(r'\.(?:epub|pdf|mobi|azw3|cbr|cbz)$', '', text, flags=re.IGNORECASE).strip()
    # Normalize dashes: '–' or '—' -> '-'
    text = re.sub(r'\s*[–—]\s*', ' - ', text).strip()
    return text


async def _async_search_fti(url: str, query: str, timeout_sec: int = 35) -> List[dict]:
    """
    Navigates to FourToutIci, searches the query, and extracts resulting download links.
    """
    async with stealth_browser_page() as (page, context):
        await page.goto(url, wait_until="domcontentloaded", timeout=timeout_sec * 1000)
        await asyncio.sleep(2)

        # Fill search input and submit
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
        return raw_items or []


def search_fourtoutici(query: str, domain: Optional[str] = None) -> List[BookCandidate]:
    """
    Searches FourToutIci for matching books.
    """
    active_domain = domain or resolve_active_fti_domain()
    base_url = f"https://{active_domain}"

    logging.info(f"Searching FourToutIci for '{query}' on {active_domain}...")
    try:
        raw_items = asyncio.run(_async_search_fti(base_url, query))
        candidates: List[BookCandidate] = []
        seen_urls = set()

        for item in raw_items:
            href = item.get("href", "")
            if not href or href in seen_urls:
                continue
            seen_urls.add(href)

            label = item.get("label", "") or item.get("text", "") or item.get("rowText", "")
            clean_title = _clean_fti_title(label)

            # Determine format from label
            fmt = "epub"
            if ".pdf" in label.lower() or " pdf" in label.lower():
                fmt = "pdf"
            elif ".mobi" in label.lower():
                fmt = "mobi"

            candidates.append(BookCandidate(
                title=clean_title,
                domain=active_domain,
                format=fmt,
                size="Unknown",
                lang="fr",
                download_url=href,
                meta=f"fourtoutici · {fmt.upper()}",
                source_type="direct"
            ))

        logging.info(f"FourToutIci returned {len(candidates)} candidates for '{query}'.")
        return candidates
    except Exception as e:
        logging.warning(f"FourToutIci search failed on {active_domain}: {e}")
        return []


async def _async_download_fti(download_url: str, timeout_sec: int = 40) -> Optional[Tuple[str, List[dict], str]]:
    """
    Resolves FourToutIci download session and extracts clearance cookies + User Agent.
    """
    parsed = urllib.parse.urlparse(download_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"

    async with stealth_browser_page() as (page, context):
        await page.goto(origin, wait_until="domcontentloaded", timeout=timeout_sec * 1000)
        await asyncio.sleep(1.5)
        cookies = await context.cookies()
        user_agent = await page.evaluate("navigator.userAgent")
        return download_url, cookies, user_agent


def download_fourtoutici_book(candidate: BookCandidate, dest_filename: str) -> bool:
    """
    Downloads book from FourToutIci using resolved session cookies and streams to disk.
    """
    if not candidate.download_url:
        logging.error("Candidate missing download_url for FourToutIci.")
        return False

    logging.info(f"Downloading from FourToutIci: '{candidate.title}' ({candidate.download_url})...")
    try:
        resolved = asyncio.run(_async_download_fti(candidate.download_url))
        if not resolved:
            logging.error("Failed to establish FourToutIci download session.")
            return False

        target_url, cookies, user_agent = resolved

        cookie_header = "; ".join(f"{c['name']}={c['value']}" for c in cookies if 'name' in c and 'value' in c)
        headers = {
            "User-Agent": user_agent or DEFAULT_USER_AGENT,
            "Referer": f"https://{candidate.domain}/"
        }
        if cookie_header:
            headers["Cookie"] = cookie_header

        success = download_stream(
            target_url,
            dest_filename,
            headers=headers,
            timeout=120,
            min_size_bytes=1024
        )

        if success:
            logging.info(f"Book saved successfully from FourToutIci: {dest_filename}")
            return True
        else:
            logging.warning("FourToutIci download failed or file too small.")
            return False
    except Exception as e:
        logging.error(f"FourToutIci download exception: {e}")
        return False
