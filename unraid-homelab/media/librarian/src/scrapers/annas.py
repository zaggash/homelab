import re
import time
import os
import asyncio
import logging
import urllib.parse
import html as html_lib
from typing import Optional, List, Dict, Tuple
import requests

from core.models import BookCandidate
from core.http import DEFAULT_USER_AGENT

ANNAS_DOMAINS = ["annas-archive.gl", "annas-archive.pk", "annas-archive.gd"]


def _parse_annas_html(html: str, connected_domain: str) -> List[BookCandidate]:
    matches = list(re.finditer(r'/md5/([a-f0-9]{32})', html))
    unique_md5s = []
    unique_positions = []
    for m in matches:
        h = m.group(1)
        if h not in unique_md5s:
            unique_md5s.append(h)
            unique_positions.append(m.start())

    results: List[BookCandidate] = []
    for idx, (h, pos) in enumerate(zip(unique_md5s, unique_positions)):
        start_pos = max(0, pos - 300)
        next_pos = unique_positions[idx + 1] if idx + 1 < len(unique_positions) else pos + 5000

        # 1. Title is in the <a> tag surrounding /md5/{h} with non-empty text
        title_snippet = html[start_pos:next_pos]
        title = "Unknown"
        a_matches = re.findall(r'<a[^>]*href=[\"\']/md5/' + h + r'[\"\'][^>]*>(.*?)</a>', title_snippet, re.DOTALL | re.IGNORECASE)
        for am in a_matches:
            clean = re.sub(r'<[^>]+>', ' ', am)
            clean_title = ' '.join(html_lib.unescape(clean).split())
            if clean_title:
                title = clean_title
                break

        # 2. Metadata line is after pos
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


async def _async_fetch_annas_html(url: str, timeout_sec: int = 35) -> str:
    """
    Spins up stealth Camoufox browser to pass DDoS-Guard challenge and retrieve search HTML.
    """
    try:
        from invisible_playwright.async_api import InvisiblePlaywright
    except ImportError:
        try:
            from camoufox.async_api import AsyncCamoufox as InvisiblePlaywright
        except ImportError:
            raise ImportError("InvisiblePlaywright or Camoufox must be installed for Anna's Archive scraping.")

    proxy_url = os.getenv("HTTP_PROXY") or os.getenv("http_proxy")
    proxy_config = {"server": proxy_url} if proxy_url else None

    async with InvisiblePlaywright(headless="virtual", humanize=True, geoip=True, proxy=proxy_config) as browser:
        context = await browser.new_context(proxy=proxy_config)
        page = await context.new_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=timeout_sec * 1000)

        # Poll for DDoS-Guard clearance
        for _ in range(18):
            await asyncio.sleep(2)
            for f in page.frames:
                try:
                    fc = await f.content()
                    if "/md5/" in fc and "<title>DDoS-Guard</title>" not in fc:
                        return fc
                except Exception:
                    pass

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


def search_annas_archive(query: str) -> List[BookCandidate]:
    """
    Direct, fast search on Anna's Archive with minimal overhead.
    """
    encoded_query = urllib.parse.quote_plus(query)

    for domain in ANNAS_DOMAINS:
        url = f"https://{domain}/search?q={encoded_query}&lang=fr&ext=epub"
        logging.info(f"Searching Anna's Archive for '{query}' on {domain}...")
        try:
            raw_html = asyncio.run(_async_fetch_annas_html(url))
            is_challenge = ("<title>DDoS-Guard</title>" in raw_html) or ("<title>Just a moment...</title>" in raw_html)
            if raw_html and not is_challenge and "/md5/" in raw_html:
                results = _parse_annas_html(raw_html, domain)
                if results:
                    logging.info(f"Anna's Archive returned {len(results)} results from {domain}.")
                    return results
        except Exception as e:
            logging.warning(f"Search attempt failed on {domain}: {e}")

    logging.warning("Search failed across all Anna's Archive domains.")
    return []


async def _async_resolve_slow_link(target_url: str, md5_hash: str, timeout_sec: int = 40) -> Optional[Tuple[str, List[Dict], str]]:
    """
    Uses Camoufox to bypass countdown / DDoS-Guard on slow download partner pages.
    """
    try:
        from invisible_playwright.async_api import InvisiblePlaywright
    except ImportError:
        try:
            from camoufox.async_api import AsyncCamoufox as InvisiblePlaywright
        except ImportError:
            raise ImportError("InvisiblePlaywright or Camoufox must be installed for Anna's Archive scraping.")

    proxy_url = os.getenv("HTTP_PROXY") or os.getenv("http_proxy")
    proxy_config = {"server": proxy_url} if proxy_url else None

    async with InvisiblePlaywright(headless="virtual", humanize=True, geoip=True, proxy=proxy_config) as browser:
        context = await browser.new_context(proxy=proxy_config)
        page = await context.new_page()
        await page.goto(target_url, wait_until="domcontentloaded", timeout=timeout_sec * 1000)

        # Wait for partner timer countdown to resolve and expose download link
        for _ in range(20):
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
    active_domain = domain or "annas-archive.gl"
    options = ["0/4", "0/5"]

    for idx, opt in enumerate(options):
        target_url = f"https://{active_domain}/slow_download/{md5_hash}/{opt}"
        logging.info(f"Downloading from Anna's Archive Partner #{idx + 1} ({opt}) on {active_domain}...")

        try:
            resolved = asyncio.run(_async_resolve_slow_link(target_url, md5_hash))
            if not resolved:
                logging.warning(f"Partner #{idx + 1} ({opt}) - Could not resolve download URL.")
                continue

            captured_url, cookies, user_agent = resolved

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

            logging.info(f"Streaming book from resolved partner link...")
            s = requests.Session()
            for c in cookies:
                s.cookies.set(c['name'], c['value'])
            s.headers.update({
                "User-Agent": user_agent or DEFAULT_USER_AGENT,
                "Referer": target_url
            })

            resp = s.get(resolved_url, stream=True, timeout=120)
            if resp.status_code == 200:
                with open(dest_filename, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=65536):
                        if chunk:
                            f.write(chunk)

                if os.path.exists(dest_filename) and os.path.getsize(dest_filename) > 1024:
                    logging.info(f"Book saved successfully ({os.path.getsize(dest_filename)} bytes): {dest_filename}")
                    return True
                else:
                    logging.warning(f"Downloaded file was too small. Removing {dest_filename}...")
                    if os.path.exists(dest_filename):
                        os.remove(dest_filename)
            else:
                logging.warning(f"Download returned HTTP {resp.status_code}")
        except Exception as e:
            logging.warning(f"Partner #{idx + 1} ({opt}) download error: {e}")

    logging.error(f"All slow download partners failed for MD5: {md5_hash}.")
    return False
