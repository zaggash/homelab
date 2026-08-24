import os
import re
import logging
from typing import Tuple, Optional, List

from config import Config
from core.models import BookCandidate
from core.matching import calculate_title_similarity, parse_size_to_kb
from clients.grimmory import GrimmoryClient
from clients.qbittorrent import QBittorrentClient
from scrapers.fourtoutici import fetch_from_fourtoutici
from scrapers.prowlarr import search_prowlarr, search_prowlarr_audiobooks
from scrapers.annas import search_annas_archive, download_annas_slow_link, resolve_active_domain
from core.vpn import rotate_vpn_ip


class BookPipeline:
    def __init__(
        self,
        config=Config,
        grimmory_client: Optional[GrimmoryClient] = None,
        qbittorrent_client: Optional[QBittorrentClient] = None
    ):
        self.config = config
        self.grimmory = grimmory_client or GrimmoryClient(config)
        self.qbittorrent = qbittorrent_client or QBittorrentClient(config)

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

    def check_audiobook_availability(self, query: str) -> Optional[BookCandidate]:
        """
        Checks Prowlarr for an audiobook version matching the query.
        Returns the top matching BookCandidate if similarity is >= 0.55, else None.
        """
        if not self.config.PROWLARR_API_KEY:
            return None

        try:
            audio_results = search_prowlarr_audiobooks(query)
            if not audio_results:
                return None

            valid_candidates: List[BookCandidate] = []
            for r in audio_results:
                lang_lower = r.lang.lower()
                is_french = "french" in lang_lower or "fr" in lang_lower or "[fr]" in lang_lower or lang_lower == "unknown"
                if is_french:
                    r.similarity = calculate_title_similarity(query, r.title)
                    if r.similarity >= 0.55:
                        valid_candidates.append(r)

            if not valid_candidates:
                return None

            valid_candidates.sort(key=lambda x: -round(x.similarity, 2))
            best = valid_candidates[0]
            logging.info(f"Audiobook candidate found: '{best.title}' on {best.indexer} (score: {best.similarity:.2f})")
            return best
        except Exception as e:
            logging.error(f"Error checking audiobook availability: {e}")
            return None

    def _format_audiobook_note(self, audio_match: Optional[BookCandidate]) -> Optional[str]:
        if not audio_match:
            return None
        indexer_name = audio_match.indexer or "Prowlarr"
        fmt_str = audio_match.format.upper()
        return f"🎧 *Note : La version livre audio est disponible sur {indexer_name} ({fmt_str} – {audio_match.size}).*"

    def process_book_request(self, query: str) -> Tuple[Optional[str], str, Optional[str]]:
        """
        Multi-provider search cascade:
        0. Check Grimmory for duplicates.
        1. Single-pass Search & Download via FourToutIci.
        2. Search Prowlarr (EBook categories) & send to qBittorrent (#ebook tag, /books_import savepath).
        3. Search Anna's Archive (dedicated mirror + VPN rotation fallback) & slow download.
        Additionally checks Prowlarr for audiobook availability in parallel.
        Returns: (file_path_if_downloaded, status_message, optional_audiobook_note)
        """
        logging.info(f"Starting book retrieval cascade for query: '{query}'")

        # Check for audiobook availability
        audio_match = self.check_audiobook_availability(query)
        audio_note = self._format_audiobook_note(audio_match)

        # 0. Check if already present in Grimmory (library or bookdrop queue)
        present, reason = self.grimmory.is_book_already_present(query)
        if present:
            return None, f"📚 {reason}\nLa recherche a été annulée.", audio_note

        # ---------------------------------------------------------------------
        # 1. Provider: FourToutIci (Single-pass search & stream download)
        # ---------------------------------------------------------------------
        logging.info("Cascade Step 1: Checking FourToutIci...")
        dest_file, fti_title = fetch_from_fourtoutici(query, self.config.IMPORT_DIR)
        if dest_file:
            return dest_file, f"Livre trouvé sur FourToutIci ! '{fti_title}' (EPUB). Téléchargement terminé.", audio_note

        # ---------------------------------------------------------------------
        # 2. Provider: Prowlarr + qBittorrent
        # ---------------------------------------------------------------------
        if self.config.PROWLARR_API_KEY:
            logging.info("Cascade Step 2: Checking Prowlarr EBook indexers...")
            prowlarr_results = search_prowlarr(query)
            prowlarr_candidates = self._filter_and_rank_candidates(query, prowlarr_results)

            for best_torrent in prowlarr_candidates[:2]:
                if best_torrent.download_url:
                    indexer_name = best_torrent.indexer or "Prowlarr"
                    logging.info(f"Queueing torrent to qBittorrent from {indexer_name}: '{best_torrent.title}'...")
                    queued = self.qbittorrent.add_torrent(
                        torrent_url_or_magnet=best_torrent.download_url,
                        save_path=self.config.QBITTORRENT_SAVE_PATH,
                        category=self.config.QBITTORRENT_CATEGORY,
                        tags=self.config.QBITTORRENT_TAG
                    )
                    if queued:
                        return None, (
                            f"Livre trouvé sur {indexer_name} ! '{best_torrent.title}'.\n"
                            f"📥 Téléchargement ajouté à qBittorrent avec le tag #{self.config.QBITTORRENT_TAG} "
                            f"(dossier dédié NAS). Il sera importé automatiquement dans Grimmory dès réception."
                        ), audio_note

        # ---------------------------------------------------------------------
        # 3. Provider: Anna's Archive (dedicated mirror + VPN failover)
        # ---------------------------------------------------------------------
        logging.info("Cascade Step 3: Checking Anna's Archive...")
        active_domain = resolve_active_domain()
        annas_results = search_annas_archive(query, domain=active_domain)
        annas_candidates = self._filter_and_rank_candidates(query, annas_results)

        if not annas_candidates:
            logging.warning("Anna's Archive yielded no valid candidates. Rotating VPN IP...")
            rotated = rotate_vpn_ip(self.config.GLUETUN_URL)
            if rotated:
                logging.info("Retrying Anna's Archive search with new VPN IP...")
                annas_results = search_annas_archive(query, domain=active_domain)
                annas_candidates = self._filter_and_rank_candidates(query, annas_results)

        for best_match in annas_candidates[:2]:
            title = best_match.title
            size = best_match.size
            md5 = best_match.md5

            safe_title = re.sub(r'[/\\?%*:|"<>]', '_', title)
            dest_filename = os.path.join(self.config.IMPORT_DIR, f"{safe_title}.epub")

            logging.info(f"Attempting Anna's Archive slow download for '{title}' ({md5})...")
            success = download_annas_slow_link(md5, dest_filename, domain=best_match.domain)
            if success:
                return dest_filename, f"Livre trouvé sur Anna's Archive ! '{title}' (EPUB, {size}). Téléchargement terminé.", audio_note
            else:
                if os.path.exists(dest_filename):
                    try:
                        os.remove(dest_filename)
                    except Exception as rm_err:
                        logging.error(f"Failed to remove partial download file {dest_filename}: {rm_err}")

        return None, "Désolé, aucun livre correspondant n'a pu être trouvé ou téléchargé parmi les fournisseurs disponibles.", audio_note
