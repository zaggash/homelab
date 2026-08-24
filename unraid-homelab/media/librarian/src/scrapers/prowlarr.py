import logging
import urllib.parse
from typing import List, Optional

from config import Config
from core.models import BookCandidate
from core.http import json_request


# Torznab / Newznab standard categories for Books / EBooks and Audiobooks
EBOOK_CATEGORIES = [7000, 7020]
AUDIOBOOK_CATEGORIES = [3030]


def search_prowlarr(
    query: str,
    categories: Optional[List[int]] = None
) -> List[BookCandidate]:
    """
    Searches indexers configured in Prowlarr, filtered by category.
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

    is_audio_search = bool(categories and 3030 in categories)
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
        if size_kb >= 1024 * 1024:
            size_str = f"{size_kb / (1024.0 * 1024.0):.1f}GB"
        elif size_kb >= 1024:
            size_str = f"{size_kb / 1024.0:.1f}MB"
        else:
            size_str = f"{size_kb:.0f}KB"

        # Determine format from title
        title_lower = title.lower()
        if ".m4b" in title_lower or "m4b" in title_lower:
            fmt = "m4b"
        elif ".mp3" in title_lower or "mp3" in title_lower:
            fmt = "mp3"
        elif ".flac" in title_lower or "flac" in title_lower:
            fmt = "flac"
        elif ".pdf" in title_lower or " pdf" in title_lower:
            fmt = "pdf"
        elif ".mobi" in title_lower or " mobi" in title_lower:
            fmt = "mobi"
        elif ".epub" in title_lower or " epub" in title_lower:
            fmt = "epub"
        else:
            fmt = "audiobook" if is_audio_search else "epub"

        # Check language markers
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


def search_prowlarr_audiobooks(query: str) -> List[BookCandidate]:
    """
    Searches indexers configured in Prowlarr for audiobooks (Category 3030).
    """
    return search_prowlarr(query, categories=AUDIOBOOK_CATEGORIES)
