import re
import difflib
import unicodedata
from typing import List, Set

STOP_WORDS = {
    'le', 'la', 'les', 'un', 'une', 'des', 'du', 'de', 'et', 'en', 'au', 'aux',
    'pour', 'dans', 'sur', 'par', 'avec', 'sans', 'sous', 'the', 'of', 'and', 'in', 'on', 'with', 'for',
    'fr', 'french', 'epub', 'edition', 'tome', 'vol', 'volume', 'ebook', 'livre',
    'pdf', 'complet', 'gratuit', 'gratuits', 'version', 'integrale'
}


def mask_identifier(val: str) -> str:
    """
    Masks sensitive identifiers like phone numbers for privacy-safe logging.
    """
    if not val or len(val) < 8:
        return "****"
    return f"{val[:4]}****{val[-4:]}"


def normalize_text(text: str) -> str:
    """
    Normalizes string by lowering case, converting ligatures, removing accents.
    """
    if not text:
        return ""
    text = text.lower().replace('œ', 'oe').replace('æ', 'ae')
    text = unicodedata.normalize('NFD', text)
    return ''.join(c for c in text if unicodedata.category(c) != 'Mn')


def parse_size_to_kb(size_str: str) -> float:
    """
    Converts size strings (e.g. '2.4MB', '320KB') into float values in KB.
    """
    if not size_str:
        return 999999.0
    size_str = size_str.upper().strip()
    match = re.search(r'([0-9.]+)\s*([KM]B)', size_str)
    if not match:
        return 999999.0
    val = float(match.group(1))
    unit = match.group(2)
    if unit == "MB":
        return val * 1024.0
    return val


def tokenize(text: str) -> Set[str]:
    norm = normalize_text(text)
    text_norm = re.sub(r'[^\w\s]', ' ', norm)
    return set(w for w in text_norm.split() if len(w) > 1 and w not in STOP_WORDS)


def calculate_title_similarity(query: str, title: str) -> float:
    """
    Calculates a hybrid similarity score (0.0 to 1.0) combining token containment,
    Jaccard token overlap, and Levenshtein/difflib ratio.
    Prevents false negatives on short single-word queries against rich metadata titles,
    and queries containing 'Author - Title' against standalone book titles.
    """
    query_tokens = tokenize(query)
    title_tokens = tokenize(title)

    if not query_tokens or not title_tokens:
        return 0.0

    intersection = query_tokens.intersection(title_tokens)
    union = query_tokens.union(title_tokens)

    containment_q = len(intersection) / len(query_tokens)
    containment_t = len(intersection) / len(title_tokens)
    containment = max(containment_q, containment_t)
    jaccard = len(intersection) / len(union) if union else 0.0

    norm_q = " ".join(sorted(query_tokens))
    norm_t = " ".join(sorted(title_tokens))
    seq_ratio = difflib.SequenceMatcher(None, norm_q, norm_t).ratio()

    # Case 1: 100% of query tokens found in candidate title (e.g. 'Dune' in 'Cycle de Dune')
    # Case 2: 100% of title tokens found in multi-token query with substantial overlap (e.g. 'Author - Title')
    is_exact_query_match = (containment_q == 1.0)
    is_exact_title_in_query = (containment_t == 1.0 and (containment_q >= 0.5 or len(intersection) >= 2))

    if is_exact_query_match or is_exact_title_in_query:
        return max(0.85, 0.5 * containment + 0.3 * jaccard + 0.2 * seq_ratio)

    return 0.5 * containment_q + 0.35 * jaccard + 0.15 * (jaccard * seq_ratio)


def generate_query_candidates(raw_q: str) -> List[str]:
    """
    Generates variations of a search query (full, split on hyphen, top keywords).
    """
    candidates = [raw_q]
    if '-' in raw_q:
        parts = [p.strip() for p in raw_q.split('-') if p.strip()]
        for p in parts:
            if len(p) > 2 and p not in candidates:
                candidates.append(p)

    norm = normalize_text(raw_q)
    words = [w for w in re.sub(r'[^\w\s]', ' ', norm).split() if len(w) > 1 and w not in STOP_WORDS]
    if len(words) >= 2:
        two_words = f"{words[0]} {words[1]}"
        if two_words not in candidates:
            candidates.append(two_words)
    return candidates
