from dataclasses import dataclass
from typing import Optional


@dataclass
class BookCandidate:
    title: str
    domain: str
    format: str = "epub"
    size: str = "Unknown"
    lang: str = "fr"
    year: str = "Unknown"
    meta: str = ""
    similarity: float = 0.0
    md5: Optional[str] = None
    download_url: Optional[str] = None
    source_type: str = "direct"  # "direct" (local download) or "torrent" (prowlarr/qbittorrent)
    indexer: Optional[str] = None


@dataclass
class IncomingEvent:
    sender: str
    reply_to: str
    text_query: Optional[str] = None
    photo_id: Optional[str] = None
    is_group: bool = False
    group_name: Optional[str] = None
