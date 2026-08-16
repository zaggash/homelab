import re
import logging
import urllib.parse
import html as html_lib
import urllib.request
from typing import List
from core.matching import generate_query_candidates
from core.models import BookCandidate
from core.http import json_request, download_stream, DEFAULT_USER_AGENT


def search_libgen_li(query: str) -> List[BookCandidate]:
    """
    Searches Libgen.li directly using its index and JSON API endpoint.
    Tries candidate query decompositions sequentially.
    """
    query_list = generate_query_candidates(query)

    for target_q in query_list:
        encoded = urllib.parse.quote_plus(target_q)
        url = f"https://libgen.li/index.php?req={encoded}"
        logging.info(f"Searching Libgen.li for candidate query: '{target_q}'...")
        
        raw_html, status = json_request(url, timeout=15)
        if not raw_html or not isinstance(raw_html, str):
            continue

        m = re.search(r'href=["\'](?:/)?(json\.php\?object=f&ids=[0-9,]+)["\']', raw_html)
        if not m:
            logging.warning(f"No JSON API payload link found on Libgen.li index page for '{target_q}'.")
            continue

        json_url = f"https://libgen.li/{m.group(1)}"
        data, _ = json_request(json_url, timeout=15)
        if not data or not isinstance(data, dict):
            continue

        results: List[BookCandidate] = []
        for item in data.values():
            md5 = item.get("md5", "").lower()
            extension = item.get("extension", "").lower()
            locator = item.get("locator", "")
            filesize = item.get("filesize", 0)

            title = item.get("title", "")
            authors = item.get("authors", "")

            if not title and locator:
                filename = locator.split("\\")[-1].split("/")[-1]
                title = re.sub(r'\.[a-zA-Z0-9]+$', '', filename)

            full_title = f"{authors} - {title}" if authors and title else (title or authors)
            size_kb = float(filesize) / 1024.0 if filesize else 0
            size_str = f"{size_kb / 1024.0:.1f}MB" if size_kb > 1024 else f"{size_kb:.0f}KB"

            is_french_locator = "[fr]" in locator.lower() or "french" in locator.lower() or " romance)" in locator.lower()
            lang = "fr" if is_french_locator else "unknown"

            results.append(BookCandidate(
                md5=md5,
                title=html_lib.unescape(full_title),
                meta=f"{lang} · {extension} · {size_str}",
                lang=lang,
                format=extension,
                size=size_str,
                year=item.get("year", "Unknown"),
                domain="libgen.li"
            ))

        if results:
            logging.info(f"Libgen.li search returned {len(results)} results for query '{target_q}'.")
            return results

    return []


def download_libgen_book(md5_hash: str, dest_filename: str) -> bool:
    """
    Downloads a book directly from Libgen.li using a session cookie jar and stream writer.
    """
    ads_url = f"https://libgen.li/ads.php?md5={md5_hash}"
    cookie_jar = urllib.request.HTTPCookieProcessor()
    opener = urllib.request.build_opener(cookie_jar)
    opener.addheaders = [
        ("User-Agent", DEFAULT_USER_AGENT),
        ("Referer", ads_url)
    ]

    try:
        logging.info("Retrieving dynamic download key from Libgen.li...")
        with opener.open(ads_url, timeout=15) as response:
            html = response.read().decode("utf-8")

        match = re.search(r'href=["\'](get\.php\?md5=[a-f0-9]{32}&key=([A-Z0-9]+))["\']', html)
        if not match:
            logging.error("Could not parse dynamic download key from ads.php.")
            return False

        get_relative_path = match.group(1)
        parsed_key = match.group(2)
        get_url = f"https://libgen.li/{get_relative_path}"
        logging.info(f"Session key verified: {parsed_key}. Streaming direct file download...")

        return download_stream(get_url, dest_filename, opener=opener, timeout=180, min_size_bytes=1024)
    except Exception as e:
        logging.error(f"Libgen.li download preparation failed: {e}")
        return False
