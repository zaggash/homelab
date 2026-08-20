import os
import re
import logging
from typing import Tuple, Optional, List
from config import Config
from core.models import BookCandidate
from core.matching import calculate_title_similarity, parse_size_to_kb
from clients.grimmory import GrimmoryClient
from clients.flaresolverr import FlareSolverrClient
from scrapers.libgen import search_libgen_li, download_libgen_book
from scrapers.annas import search_annas_archive, download_annas_slow_link


class BookPipeline:
    def __init__(
        self,
        config=Config,
        grimmory_client: Optional[GrimmoryClient] = None,
        flaresolverr_client: Optional[FlareSolverrClient] = None
    ):
        self.config = config
        self.grimmory = grimmory_client or GrimmoryClient(config)
        self.flaresolverr = flaresolverr_client or FlareSolverrClient(config.FLARESOLVERR_URL)

    def _filter_and_rank_candidates(
        self,
        query: str,
        results: List[BookCandidate],
        min_confidence: float = 0.55
    ) -> List[BookCandidate]:
        """
        Filters raw candidates for French EPUBs, calculates similarity scores,
        and returns matching candidates sorted primarily by similarity score (descending),
        using file size as a secondary tie-breaker.
        """
        french_epubs: List[BookCandidate] = []
        for r in results:
            lang_lower = r.lang.lower()
            format_lower = r.format.lower()

            is_french = "french" in lang_lower or "fr" in lang_lower or "[fr]" in lang_lower or lang_lower == "unknown"
            is_epub = "epub" in format_lower or format_lower == "unknown"

            if is_french and is_epub:
                r.similarity = calculate_title_similarity(query, r.title)
                french_epubs.append(r)

        if not french_epubs:
            return []

        max_similarity = max(r.similarity for r in french_epubs)
        if max_similarity < min_confidence:
            logging.warning(
                f"Max similarity found ({max_similarity:.2f}) is below absolute confidence threshold ({min_confidence:.2f})."
            )
            return []

        # Keep candidates within a tight margin of best match, never going below min_confidence
        relevance_threshold = max(max_similarity - 0.10, min_confidence)
        candidates = [r for r in french_epubs if r.similarity >= relevance_threshold]
        
        # Sort primarily by similarity score (highest first), with size (smallest first) as tie-breaker
        candidates.sort(key=lambda x: (-round(x.similarity, 2), parse_size_to_kb(x.size)))
        return candidates

    def process_book_request(self, query: str) -> Tuple[Optional[str], str]:
        """
        Takes a query, searches Anna's Archive first (via Byparr), falls back to Libgen,
        filters French EPUBs, ranks them by title relevance, and downloads the best match.
        """
        logging.info(f"Starting book search for query: '{query}'")

        # 0. Check if already present in Grimmory (library or bookdrop queue)
        present, reason = self.grimmory.is_book_already_present(query)
        if present:
            return None, f"📚 {reason}\nLa recherche a été annulée."

        candidates: List[BookCandidate] = []

        # 1. Primary search: Anna's Archive via Byparr / FlareSolverr (comprehensive shadow library index)
        if self.flaresolverr.is_available:
            logging.info("Searching Anna's Archive (Primary Engine via Byparr)...")
            annas_results = search_annas_archive(query, flaresolverr=self.flaresolverr)
            candidates = self._filter_and_rank_candidates(query, annas_results)

        # 2. Secondary fallback search: Libgen.li direct JSON API (fast fallback)
        if not candidates:
            logging.info("Anna's Archive produced no valid French EPUB candidates. Trying Libgen.li fallback...")
            libgen_results = search_libgen_li(query)
            candidates = self._filter_and_rank_candidates(query, libgen_results)

        if not candidates:
            return None, "Désolé, je n'ai trouvé aucun livre correspondant de manière fiable en EPUB français."

        # 3. Try downloading candidates sequentially until one succeeds
        for idx, best_match in enumerate(candidates):
            title = best_match.title
            size = best_match.size
            md5 = best_match.md5
            sim_score = best_match.similarity

            logging.info(f"Trying Candidate {idx + 1}/{len(candidates)}: '{title}' | Similarity: {sim_score:.2f} | Size: {size} | MD5: {md5}")

            safe_title = re.sub(r'[/\\?%*:|"<>]', '_', title)
            dest_filename = os.path.join(self.config.IMPORT_DIR, f"{safe_title}.epub")

            # Try Libgen direct download key first (instant, no slow wait timer)
            success = download_libgen_book(md5, dest_filename)
            # If not in Libgen, fall back to Anna's Archive slow download link via Byparr
            if not success and self.flaresolverr.is_available:
                success = download_annas_slow_link(md5, dest_filename, flaresolverr=self.flaresolverr)

            if success:
                return dest_filename, f"Livre trouvé ! '{title}' (EPUB, {size}). Téléchargement terminé."
            else:
                logging.warning(f"Failed to download candidate {idx + 1} ({md5}). Trying next available candidate...")
                if os.path.exists(dest_filename):
                    try:
                        os.remove(dest_filename)
                    except Exception as rm_err:
                        logging.error(f"Failed to remove partial/failed download file {dest_filename}: {rm_err}")

        return None, "Le téléchargement du livre a échoué (tous les candidats ont échoué)."
