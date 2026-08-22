import logging
import urllib.parse
from typing import List, Optional

from config import Config
from core.models import BookCandidate
from core.http import json_request


# Torznab / Newznab standard categories for Books / EBooks
EBOOK_CATEGORIES = [7000, 7020]


def search_prowlarr(
    query: str,
    categories: Optional[List[int]] = None
) -> List[BookCandidate]:
    """
    Searches indexers configured in Prowlarr, filtered by EBook categories.
    """
    if not Config.PROWLARR_URL or not Config.PROWLARR_API_KEY:
        return []

    cats = categories or EBOOK_CATEGORIES
    cat_param = ",".join(str(c) for c in cats)
    encoded_query = urllib.parse.quote_plus(query)

    url = f"{Config.PROWLARR_URL}/api/v1/search?query={encoded_query}&categories={cat_param}&type=search"
    headers = {
        "X-Api-Key": Config.PROWLARR_API_KEY
    }

    logging.info(f"Searching Prowlarr for '{query}' (Categories: {cat_param})...")
    data, status = json_request(url, method="GET", headers=headers, timeout=20)

    if not data or not isinstance(data, list):
        logging.warning(f"Prowlarr search returned status {status} or invalid payload.")
        return []

    candidates: List[BookCandidate] = []
    for item in data:
        if not isinstance(item, dict):
            continue

        title = item.get("title", "").strip()
        download_url = item.get("downloadUrl") or item.get("magnetUrl")
        indexer = item.get("indexer", "Prowlarr")
        size_bytes = item.get("size", 0)

        if not title or not download_url:
            continue

        # Format file size
        size_kb = float(size_bytes) / 1024.0 if size_bytes else 0
        size_str = f"{size_kb / 1024.0:.1f}MB" if size_kb > 1024 else f"{size_kb:.0f}KB"

        # Determine format from title
        fmt = "epub"
        if ".pdf" in title.lower() or " pdf" in title.lower():
            fmt = "pdf"
        elif ".mobi" in title.lower():
            fmt = "mobi"

        # Check language markers
        title_lower = title.lower()
        is_fr = "french" in title_lower or "fr" in title_lower or "vff" in title_lower or "truefrench" in title_lower

        candidates.append(BookCandidate(
            title=title,
            domain="prowlarr",
            format=fmt,
            size=size_str,
            lang="fr" if is_fr else "unknown",
            download_url=download_url,
            meta=f"{indexer} · Torrent · {fmt.upper()} · {size_str}",
            source_type="torrent",
            indexer=indexer
        ))

    logging.info(f"Prowlarr returned {len(candidates)} candidates for '{query}'.")
    return candidates
