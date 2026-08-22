import os
import re
import socket
import asyncio
import logging
import urllib.parse
import html as html_lib
from typing import Optional, List, Tuple, Dict
from contextlib import asynccontextmanager

from config import Config
from core.models import BookCandidate
from core.http import DEFAULT_USER_AGENT, download_stream


def resolve_active_domain(
    primary_domain: Optional[str] = None,
    fallback_domains: Optional[List[str]] = None
) -> str:
    """
    Checks DNS resolution for the primary Anna's Archive mirror.
    Falls back to secondary mirrors ONLY if the primary fails at the DNS/network level.
    """
    primary = primary_domain or Config.ANNAS_PRIMARY_DOMAIN
    fallbacks = fallback_domains if fallback_domains is not None else Config.ANNAS_FALLBACK_DOMAINS

    try:
        socket.getaddrinfo(primary, 443, socket.AF_UNSPEC, socket.SOCK_STREAM)
        return primary
    except (socket.gaierror, socket.herror, OSError) as e:
        logging.warning(f"DNS resolution failed for primary mirror '{primary}': {e}. Testing fallback mirrors...")

    for fallback in fallbacks:
        try:
            socket.getaddrinfo(fallback, 443, socket.AF_UNSPEC, socket.SOCK_STREAM)
            logging.info(f"Fallback mirror '{fallback}' resolved successfully.")
            return fallback
        except (socket.gaierror, socket.herror, OSError):
            continue

    logging.error("No Anna's Archive mirrors could be resolved via DNS. Defaulting to primary.")
    return primary


@asynccontextmanager
async def stealth_browser_page(proxy_url: Optional[str] = None):
    """
    Async context manager providing a configured Camoufox/InvisiblePlaywright page.
    Ensures proper resource cleanup upon exit.
    """
    effective_proxy = proxy_url or os.getenv("HTTP_PROXY") or os.getenv("http_proxy")
    proxy_config = {"server": effective_proxy} if effective_proxy else None

    try:
        from camoufox.async_api import AsyncCamoufox as BrowserEngine
        engine_kwargs = {"headless": "virtual", "humanize": True, "geoip": True}
    except ImportError:
        try:
            from invisible_playwright.async_api import InvisiblePlaywright as BrowserEngine
            engine_kwargs = {"headless": "virtual", "humanize": True}
        except ImportError:
            raise ImportError("Camoufox or InvisiblePlaywright must be installed for Anna's Archive operations.")

    if proxy_config:
        engine_kwargs["proxy"] = proxy_config

    async with BrowserEngine(**engine_kwargs) as browser:
        context = await browser.new_context(proxy=proxy_config)
        page = await context.new_page()
        try:
            yield page, context
        finally:
            try:
                await page.close()
            except Exception:
                pass
            try:
                await context.close()
            except Exception:
                pass


def _parse_annas_html(html: str, connected_domain: str) -> List[BookCandidate]:
    """
    Extracts book candidates and metadata from Anna's Archive search HTML.
    """
    matches = list(re.finditer(r'/md5/([a-f0-9]{32})', html))
    unique_md5s: List[str] = []
    unique_positions: List[int] = []
    for m in matches:
        h = m.group(1)
        if h not in unique_md5s:
            unique_md5s.append(h)
            unique_positions.append(m.start())

    results: List[BookCandidate] = []
    for idx, (h, pos) in enumerate(zip(unique_md5s, unique_positions)):
        start_pos = max(0, pos - 300)
        next_pos = unique_positions[idx + 1] if idx + 1 < len(unique_positions) else pos + 5000

        # Title parsing from <a> tag
        title_snippet = html[start_pos:next_pos]
        title = "Unknown"
        a_matches = re.findall(
            r'<a[^>]*href=[\"\']/md5/' + h + r'[\"\'][^>]*>(.*?)</a>',
            title_snippet,
            re.DOTALL | re.IGNORECASE
        )
        for am in a_matches:
            clean = re.sub(r'<[^>]+>', ' ', am)
            clean_title = ' '.join(html_lib.unescape(clean).split())
            if clean_title:
                title = clean_title
                break

        # Metadata line parsing
        meta_snippet = html[pos:next_pos]
        clean_text = re.sub(r'<[^>]+>', ' | ', meta_snippet)
        clean_text = re.sub(r'\s*\|\s*', ' | ', clean_text)
        clean_text = re.sub(r'\s+', ' ', clean_text)

        meta_line = "Unknown"
        dot_match = re.search(r'([^|·<\n]+·\s*[^|·<\n]+\s*·\s*[^|·<\n]+\s*·\s*[^|·<\n]+)', clean_text)
        if dot_match:
            meta_line = html_lib.unescape(dot_match.group(1).strip())

        parts = [p.strip() for p in meta_line.split("·")] if meta_line != "Unknown" else []

        lang = parts[0] if len(parts) > 0 else "Unknown"
        fmt = parts[1] if len(parts) > 1 else "Unknown"
        size = parts[2] if len(parts) > 2 else "Unknown"
        year = parts[3] if len(parts) > 3 else "Unknown"

        results.append(BookCandidate(
            md5=h,
            title=title,
            meta=meta_line,
            lang=lang,
            format=fmt,
            size=size,
            year=year,
            domain=connected_domain
        ))

    return results


async def _async_fetch_search_html(url: str, timeout_sec: int = 40) -> str:
    """
    Fetches search results page with Camoufox, polling for DDoS-Guard clearance.
    """
    async with stealth_browser_page() as (page, _):
        await page.goto(url, wait_until="domcontentloaded", timeout=timeout_sec * 1000)

        # Poll for challenge resolution (up to 36 seconds)
        for _ in range(18):
            await asyncio.sleep(2)
            try:
                content = await page.content()
                if "/md5/" in content and "<title>DDoS-Guard</title>" not in content:
                    return content
            except Exception:
                pass

        try:
            return await page.content()
        except Exception:
            return ""


def search_annas_archive(query: str, domain: Optional[str] = None) -> List[BookCandidate]:
    """
    Executes search on the active Anna's Archive domain.
    """
    active_domain = domain or resolve_active_domain()
    encoded_query = urllib.parse.quote_plus(query)
    url = f"https://{active_domain}/search?q={encoded_query}&lang=fr&ext=epub"

    logging.info(f"Searching Anna's Archive for '{query}' on {active_domain}...")
    try:
        raw_html = asyncio.run(_async_fetch_search_html(url))
        is_challenge = ("<title>DDoS-Guard</title>" in raw_html) or ("<title>Just a moment...</title>" in raw_html)
        if raw_html and not is_challenge and "/md5/" in raw_html:
            results = _parse_annas_html(raw_html, active_domain)
            if results:
                logging.info(f"Anna's Archive returned {len(results)} results from {active_domain}.")
                return results
    except Exception as e:
        logging.warning(f"Search attempt failed on {active_domain}: {e}")

    return []


async def _async_resolve_slow_link(
    target_url: str,
    md5_hash: str,
    timeout_sec: int = 45
) -> Optional[Tuple[str, List[Dict], str]]:
    """
    Resolves slow download partner countdown page to extract the direct file download URL and session cookies.
    """
    async with stealth_browser_page() as (page, context):
        await page.goto(target_url, wait_until="domcontentloaded", timeout=timeout_sec * 1000)

        # Wait for partner timer countdown to resolve and reveal direct download link
        for _ in range(22):
            await asyncio.sleep(2)
            for f in page.frames:
                try:
                    fc = await f.content()
                    urls = re.findall(r'(https?://[^\s\"\'\)\(<>&]+)', fc)
                    for u in urls:
                        u_clean = html_lib.unescape(u)
                        if (md5_hash in u_clean or md5_hash[:12] in u_clean) and "slow_download" not in u_clean:
                            cookies = await context.cookies()
                            user_agent = await page.evaluate("navigator.userAgent")
                            return u_clean, cookies, user_agent
                except Exception:
                    pass

            try:
                content = await page.content()
                urls = re.findall(r'(https?://[^\s\"\'\)\(<>&]+)', content)
                for u in urls:
                    u_clean = html_lib.unescape(u)
                    if (md5_hash in u_clean or md5_hash[:12] in u_clean) and "slow_download" not in u_clean:
                        cookies = await context.cookies()
                        user_agent = await page.evaluate("navigator.userAgent")
                        return u_clean, cookies, user_agent
            except Exception:
                pass

    return None


def download_annas_slow_link(
    md5_hash: str,
    dest_filename: str,
    domain: Optional[str] = None
) -> bool:
    """
    Downloads book from Anna's Archive slow download partners using session cookies.
    Tries primary partner (0/4) first, then fallback partner (0/5).
    """
    active_domain = domain or resolve_active_domain()
    options = ["0/4", "0/5"]

    for idx, opt in enumerate(options):
        target_url = f"https://{active_domain}/slow_download/{md5_hash}/{opt}"
        logging.info(f"Attempting download via Partner #{idx + 1} ({opt}) on {active_domain}...")

        try:
            resolved = asyncio.run(_async_resolve_slow_link(target_url, md5_hash))
            if not resolved:
                logging.warning(f"Partner #{idx + 1} ({opt}) - Could not resolve download URL.")
                continue

            captured_url, cookies, user_agent = resolved

            # Sanitize URL path for safe downloading
            parsed_url = urllib.parse.urlparse(captured_url)
            encoded_path = urllib.parse.quote(parsed_url.path, safe="/")
            resolved_url = urllib.parse.urlunparse((
                parsed_url.scheme,
                parsed_url.netloc,
                encoded_path,
                parsed_url.params,
                parsed_url.query,
                parsed_url.fragment
            ))

            logging.info("Streaming book from resolved partner link...")
            cookie_header = "; ".join(f"{c['name']}={c['value']}" for c in cookies if 'name' in c and 'value' in c)
            headers = {
                "User-Agent": user_agent or DEFAULT_USER_AGENT,
                "Referer": target_url
            }
            if cookie_header:
                headers["Cookie"] = cookie_header

            success = download_stream(
                resolved_url,
                dest_filename,
                headers=headers,
                timeout=120,
                min_size_bytes=1024
            )

            if success:
                logging.info(f"Book saved successfully via Partner #{idx + 1}: {dest_filename}")
                return True
            else:
                logging.warning(f"Download stream failed or file too small for Partner #{idx + 1}.")
        except Exception as e:
            logging.warning(f"Partner #{idx + 1} ({opt}) download error: {e}")

    logging.error(f"All slow download partners failed for MD5: {md5_hash}.")
    return False
