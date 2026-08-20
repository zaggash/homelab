import re
import time
import logging
import urllib.parse
import html as html_lib
from typing import Optional, List
from core.matching import generate_query_candidates
from core.models import BookCandidate
from core.http import json_request, download_stream, get_ssl_context, DEFAULT_USER_AGENT
from clients.flaresolverr import FlareSolverrClient

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

        # 1. Title is in the <a> tag surrounding /md5/{h}
        title_snippet = html[start_pos:next_pos]
        title = "Unknown"
        m = re.search(r'<a[^>]*href=[\"\']/md5/' + h + r'[\"\'][^>]*>(.*?)</a>', title_snippet, re.DOTALL | re.IGNORECASE)
        if m:
            clean = re.sub(r'<[^>]+>', ' ', m.group(1))
            title = ' '.join(html_lib.unescape(clean).split())
        else:
            m2 = re.search(r'/md5/' + h + r'[^>]*>(.*?)</a>', title_snippet, re.DOTALL | re.IGNORECASE)
            if m2:
                clean = re.sub(r'<[^>]+>', ' ', m2.group(1))
                title = ' '.join(html_lib.unescape(clean).split())

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


def search_annas_archive(
    query: str,
    flaresolverr: Optional[FlareSolverrClient] = None,
    max_retries: int = 1,
    retry_delay: int = 2
) -> List[BookCandidate]:
    """
    Searches Anna's Archive across active domains using query candidates.
    Falls back to FlareSolverr / Byparr when challenge is detected.
    """
    fs_client = flaresolverr or FlareSolverrClient()
    query_candidates = generate_query_candidates(query)

    for target_q in query_candidates:
        encoded_query = urllib.parse.quote_plus(target_q)
        html = ""
        connected_domain = ""

        for domain in ANNAS_DOMAINS:
            url = f"https://{domain}/search?q={encoded_query}&lang=fr&ext=epub"
            logging.info(f"Searching Anna's Archive for '{target_q}' on {domain}...")

            for attempt in range(max_retries):
                # 1. Direct Attempt
                raw_html, status = json_request(url, timeout=10, ssl_context=get_ssl_context())
                if raw_html and isinstance(raw_html, str):
                    is_direct_challenge = ("<title>DDoS-Guard</title>" in raw_html) or ("<title>Just a moment...</title>" in raw_html) or ("id=\"ddg-l10n-title\"" in raw_html)
                    if not is_direct_challenge and "/md5/" in raw_html:
                        html = raw_html
                        connected_domain = domain
                        logging.info(f"Successfully fetched results directly from {domain}")
                        break

                # 2. Byparr / FlareSolverr Fallback Attempt
                if fs_client.is_available:
                    solution = fs_client.solve(url, timeout_ms=60000)
                    if solution:
                        byparr_html = solution.get("response", "")
                        is_byparr_challenge = ("<title>DDoS-Guard</title>" in byparr_html) or ("<title>Just a moment...</title>" in byparr_html) or ("id=\"ddg-l10n-title\"" in byparr_html)
                        if byparr_html and not is_byparr_challenge:
                            html = byparr_html
                            connected_domain = domain
                            logging.info(f"Successfully fetched results via Byparr from {domain}")
                            break

                if attempt < max_retries - 1 and not html:
                    time.sleep(retry_delay)

            if html:
                break

        if html:
            results = _parse_annas_html(html, connected_domain)
            if results:
                logging.info(f"Anna's Archive returned {len(results)} results for query '{target_q}'.")
                return results

    logging.warning("All search attempts on Anna's Archive failed.")
    return []


def download_annas_slow_link(
    md5_hash: str,
    dest_filename: str,
    flaresolverr: Optional[FlareSolverrClient] = None
) -> bool:
    """
    Uses Byparr / FlareSolverr to bypass challenge on Anna's Archive slow download page.
    """
    fs_client = flaresolverr or FlareSolverrClient()
    if not fs_client.is_available:
        return False

    options = ["0/4", "0/5", "0/6", "0/0", "0/1", "0/2"]

    for idx, opt in enumerate(options):
        logging.info(f"Attempting FlareSolverr bypass Option #{idx + 1} ({opt}) for MD5: {md5_hash}...")
        target_url = f"https://annas-archive.gl/slow_download/{md5_hash}/{opt}"

        solution = fs_client.solve(target_url, timeout_ms=60000)
        if not solution:
            continue

        html_content = solution.get("response", "")
        cookies = solution.get("cookies", [])
        user_agent = solution.get("userAgent", DEFAULT_USER_AGENT)

        urls = re.findall(r'(https?://[^\s\"\'\)\(<>&]+)', html_content)
        valid_urls = []
        for u in urls:
            u_clean = html_lib.unescape(u)
            if (md5_hash in u_clean or md5_hash[:12] in u_clean) and u_clean not in valid_urls:
                valid_urls.append(u_clean)

        if not valid_urls:
            logging.warning(f"Option #{idx + 1} ({opt}) - Could not find resolved download URL in FlareSolverr response.")
            continue

        captured_url = valid_urls[0]
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

        logging.info(f"Option #{idx + 1} ({opt}) resolved download URL: {resolved_url}")

        cookie_header = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
        dl_headers = {
            "User-Agent": user_agent,
            "Referer": target_url
        }
        if cookie_header:
            dl_headers["Cookie"] = cookie_header

        success = download_stream(
            resolved_url,
            dest_filename,
            headers=dl_headers,
            timeout=90,
            min_size_bytes=1024,
            ssl_context=get_ssl_context()
        )
        if success:
            logging.info(f"Book saved successfully via FlareSolverr Option #{idx + 1} ({opt}): {dest_filename}")
            return True

    logging.error(f"All slow download options failed for MD5: {md5_hash}.")
    return False
