import os
import re
import logging
from typing import Tuple, Optional
from config import Config
from core.matching import calculate_title_similarity, parse_size_to_kb
from clients.grimmory import GrimmoryClient
from scrapers.libgen import search_libgen_li, download_libgen_book
from scrapers.annas import search_annas_archive, download_annas_slow_link


class BookPipeline:
    def __init__(self, config=Config, grimmory_client: Optional[GrimmoryClient] = None):
        self.config = config
        self.grimmory = grimmory_client or GrimmoryClient(config)

    def process_book_request(self, query: str) -> Tuple[Optional[str], str]:
        """
        Takes a query, searches Libgen & Anna's Archive, filters French EPUBs,
        ranks them by title relevance, and downloads the best match.
        """
        logging.info(f"Starting book search for query: '{query}'")
        
        # 0. Check if already present in Grimmory (library or bookdrop queue)
        present, reason = self.grimmory.is_book_already_present(query)
        if present:
            return None, f"📚 {reason}\nLa recherche a été annulée."
        
        # 1. Primary search: Libgen.li direct JSON API (fast, no DDoS-Guard)
        results = search_libgen_li(query)
        
        # 2. Secondary fallback search: Anna's Archive (if Libgen.li returns no results)
        if not results:
            logging.info("Libgen.li returned no results. Trying Anna's Archive secondary fallback...")
            results = search_annas_archive(query, flaresolverr_url=self.config.FLARESOLVERR_URL)
            
        if not results:
            return None, "Désolé, je n'ai trouvé aucun résultat pour cette recherche."
            
        # 3. Filter for French and EPUB format, and compute similarity scores
        french_epubs = []
        for r in results:
            lang_lower = r["lang"].lower()
            format_lower = r["format"].lower()
            
            is_french = "french" in lang_lower or "fr" in lang_lower or "[fr]" in lang_lower or lang_lower == "unknown"
            is_epub = "epub" in format_lower or format_lower == "unknown"
            
            if is_french and is_epub:
                similarity = calculate_title_similarity(query, r["title"])
                r["similarity"] = similarity
                french_epubs.append(r)
                
        if not french_epubs:
            return None, "J'ai trouvé des résultats mais aucun n'est au format EPUB en français."
            
        # 4. Multi-pass selection
        max_similarity = max(r["similarity"] for r in french_epubs)
        min_confidence = 0.35
        if max_similarity < min_confidence:
            logging.warning(f"Max similarity found ({max_similarity:.2f}) is below absolute confidence threshold ({min_confidence:.2f}). Aborting search.")
            return None, f"Désolé, je n'ai trouvé aucun livre correspondant de manière fiable à ta recherche (similarité max : {max_similarity:.2f})."
            
        relevance_threshold = max(max_similarity - 0.15, 0.20)
        candidates = [r for r in french_epubs if r["similarity"] >= relevance_threshold]
        
        if not candidates:
            return None, "Désolé, je n'ai trouvé aucun livre correspondant de manière fiable à ta recherche."
            
        # Sort candidates by size (ascending) to prefer standard compact EPUBs
        candidates.sort(key=lambda x: parse_size_to_kb(x["size"]))
        
        # 5. Try downloading candidates sequentially until one succeeds
        for idx, best_match in enumerate(candidates):
            title = best_match["title"]
            size = best_match["size"]
            md5 = best_match["md5"]
            sim_score = best_match.get("similarity", 0.0)
            
            logging.info(f"Trying Candidate {idx+1}/{len(candidates)}: '{title}' | Similarity: {sim_score:.2f} | Size: {size} | MD5: {md5}")
            
            safe_title = re.sub(r'[/\\?%*:|"<>]', '_', title)
            dest_filename = os.path.join(self.config.IMPORT_DIR, f"{safe_title}.epub")
            
            success = download_libgen_book(md5, dest_filename)
            if not success and self.config.FLARESOLVERR_URL:
                success = download_annas_slow_link(md5, dest_filename, flaresolverr_url=self.config.FLARESOLVERR_URL)
                
            if success:
                return dest_filename, f"Livre trouvé ! '{title}' (EPUB, {size}). Téléchargement terminé."
            else:
                logging.warning(f"Failed to download candidate {idx+1} ({md5}). Trying next available candidate...")
                if os.path.exists(dest_filename):
                    try:
                        os.remove(dest_filename)
                    except Exception as rm_err:
                        logging.error(f"Failed to remove partial/failed download file {dest_filename}: {rm_err}")
                
        return None, "Le téléchargement du livre a échoué (tous les candidats ont échoué)."
