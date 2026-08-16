from dataclasses import dataclass
from typing import Optional


@dataclass
class BookCandidate:
    md5: str
    title: str
    format: str
    size: str
    lang: str
    domain: str
    year: str = "Unknown"
    meta: str = ""
    similarity: float = 0.0


@dataclass
class IncomingEvent:
    sender: str
    reply_to: str
    text_query: Optional[str] = None
    photo_id: Optional[str] = None
    is_group: bool = False
    group_name: Optional[str] = None
