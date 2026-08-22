import os
import re
import logging
from typing import Tuple, Optional, List
from config import Config
from core.models import BookCandidate
from core.matching import calculate_title_similarity, parse_size_to_kb
from clients.grimmory import GrimmoryClient
from scrapers.annas import search_annas_archive, download_annas_slow_link, resolve_active_domain
from core.vpn import rotate_vpn_ip


class BookPipeline:
    def __init__(
        self,
        config=Config,
        grimmory_client: Optional[GrimmoryClient] = None
    ):
        self.config = config
        self.grimmory = grimmory_client or GrimmoryClient(config)

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
                f"Max similarity found ({max_similarity:.2f}) is below confidence threshold ({min_confidence:.2f})."
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
        Processes an incoming book query:
        1. Checks for duplicates in Grimmory.
        2. Searches Anna's Archive via Camoufox on the active mirror.
        3. Rotates VPN IP if no candidates are returned due to potential challenge block.
        4. Filters and ranks matching French EPUBs.
        5. Downloads the best candidate via Anna's Archive slow download partners.
        """
        logging.info(f"Starting book search for query: '{query}'")

        # 0. Check if already present in Grimmory (library or bookdrop queue)
        present, reason = self.grimmory.is_book_already_present(query)
        if present:
            return None, f"📚 {reason}\nLa recherche a été annulée."

        active_domain = resolve_active_domain()
        logging.info(f"Using Anna's Archive active domain: {active_domain}")

        # 1. Primary search: Anna's Archive via Camoufox
        annas_results = search_annas_archive(query, domain=active_domain)
        candidates = self._filter_and_rank_candidates(query, annas_results)

        # 2. If Anna's Archive returned no results, rotate VPN IP and retry search once
        if not candidates:
            logging.warning("Anna's Archive search yielded no valid candidates. Rotating VPN IP to bypass potential anti-bot blocks...")
            rotated = rotate_vpn_ip(self.config.GLUETUN_URL)
            if rotated:
                logging.info("Retrying Anna's Archive search with new VPN IP...")
                annas_results = search_annas_archive(query, domain=active_domain)
                candidates = self._filter_and_rank_candidates(query, annas_results)

        if not candidates:
            return None, "Désolé, je n'ai trouvé aucun livre correspondant de manière fiable en EPUB français."

        # 3. Try downloading top matching candidates (limit to top 2 to avoid excessive delays)
        for idx, best_match in enumerate(candidates[:2]):
            title = best_match.title
            size = best_match.size
            md5 = best_match.md5
            sim_score = best_match.similarity

            logging.info(f"Trying Candidate {idx + 1}/{len(candidates)}: '{title}' | Similarity: {sim_score:.2f} | Size: {size} | MD5: {md5}")

            safe_title = re.sub(r'[/\\?%*:|"<>]', '_', title)
            dest_filename = os.path.join(self.config.IMPORT_DIR, f"{safe_title}.epub")

            success = download_annas_slow_link(md5, dest_filename, domain=best_match.domain)

            if success:
                return dest_filename, f"Livre trouvé ! '{title}' (EPUB, {size}). Téléchargement terminé."
            else:
                logging.warning(f"Failed to download candidate {idx + 1} ({md5}). Trying next available candidate...")
                if os.path.exists(dest_filename):
                    try:
                        os.remove(dest_filename)
                    except Exception as rm_err:
                        logging.error(f"Failed to remove partial download file {dest_filename}: {rm_err}")

        return None, "Le téléchargement du livre a échoué (tous les candidats ont échoué)."
