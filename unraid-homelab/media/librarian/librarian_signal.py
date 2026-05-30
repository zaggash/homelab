#!/usr/bin/env python3
import os
import re
import sys
import time
import json
import base64
import logging
import urllib.request
import urllib.parse
import html as html_lib

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

# -----------------------------------------------------------------------------
# CONFIGURATION FROM ENVIRONMENT
# -----------------------------------------------------------------------------
SIGNAL_URL = os.getenv("SIGNAL_URL", "http://signal-api:8080").rstrip("/")
BOT_NUMBER = os.getenv("BOT_NUMBER", "")
WIFE_NUMBER = os.getenv("WIFE_NUMBER", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
IMPORT_DIR = os.getenv("IMPORT_DIR", "/books_import")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "10"))

# Validate configuration
if not BOT_NUMBER:
    logging.error("BOT_NUMBER environment variable is missing!")
if not WIFE_NUMBER:
    logging.error("WIFE_NUMBER environment variable is missing!")
if not GEMINI_API_KEY:
    logging.error("GEMINI_API_KEY environment variable is missing!")

os.makedirs(IMPORT_DIR, exist_ok=True)

# -----------------------------------------------------------------------------
# HELPER FOR DIRECT SIGNAL-API REQUESTS
# -----------------------------------------------------------------------------
def make_signal_request(endpoint, method="GET", payload=None, is_binary=False):
    """
    Sends an HTTP request directly to the Signal CLI REST API (internal network).
    """
    url = f"{SIGNAL_URL}{endpoint}"
    headers = {}
    
    data_bytes = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data_bytes = json.dumps(payload).encode("utf-8")
        
    req = urllib.request.Request(url, headers=headers, method=method, data=data_bytes)
    
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            if is_binary:
                return response.read()
            else:
                return json.loads(response.read().decode("utf-8"))
    except Exception as e:
        logging.error(f"Signal API error on {method} {endpoint}: {e}")
        return None

# -----------------------------------------------------------------------------
# SIGNAL API INTERACTION
# -----------------------------------------------------------------------------
def send_signal_message(text, recipients, attachment_path=None, filename=None):
    """
    Sends a Signal message to recipients, optionally with a base64 attachment.
    """
    payload = {
        "message": text,
        "number": BOT_NUMBER,
        "recipients": recipients if isinstance(recipients, list) else [recipients]
    }
    
    if attachment_path and os.path.exists(attachment_path):
        try:
            with open(attachment_path, "rb") as f:
                file_bytes = f.read()
            encoded_bytes = base64.b64encode(file_bytes).decode("utf-8")
            
            # Formulate the attachment string with metadata for proper display on receiver's end
            mime_type = "application/epub+zip" if attachment_path.endswith(".epub") else "application/octet-stream"
            disp_filename = filename or os.path.basename(attachment_path)
            attachment_str = f"data:{mime_type};filename={disp_filename};base64,{encoded_bytes}"
            
            payload["base64_attachments"] = [attachment_str]
            logging.info(f"Attached file: {attachment_path} ({len(file_bytes)} bytes)")
        except Exception as e:
            logging.error(f"Failed to encode attachment {attachment_path}: {e}")
            
    res = make_signal_request("/v2/send", method="POST", payload=payload)
    if res:
        logging.info(f"Successfully sent message to {recipients}")
    return res

def receive_signal_messages():
    """
    Retrieves and clears unread messages from the Signal network.
    """
    # Timeout is set to 5 seconds to prevent holding the thread indefinitely
    endpoint = f"/v1/receive/{BOT_NUMBER}?timeout=5"
    return make_signal_request(endpoint, method="GET")

def download_signal_attachment(attachment_id):
    """
    Fetches the raw binary of a Signal attachment.
    """
    endpoint = f"/v1/attachments/{attachment_id}"
    return make_signal_request(endpoint, method="GET", is_binary=True)

# -----------------------------------------------------------------------------
# GEMINI OCR (RE-IMPLEMENTED USING RAW HTTP TO MINIMIZE DEPENDENCIES)
# -----------------------------------------------------------------------------
def extract_book_details_from_cover(image_bytes):
    """
    Sends the cover photo to Gemini to extract Title and Author.
    """
    logging.info("Sending cover photo to Gemini for OCR analysis...")
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    headers = {"Content-Type": "application/json"}
    
    prompt_text = (
        "Tu es un bibliothécaire expert. Analyse la couverture de ce livre et renvoie UNIQUEMENT "
        "l'auteur et le titre sous le format 'Auteur - Titre' (par exemple: 'Clara Dupont-Monod - S'adapter'). "
        "Ne rajoute aucune autre phrase, ni salutation, ni markdown, ni explication."
    )
    
    payload = {
        "contents": [{
            "parts": [
                {
                    "inlineData": {
                        "mimeType": "image/jpeg",
                        "data": image_b64
                    }
                },
                {
                    "text": prompt_text
                }
            ]
        }]
    }
    
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            res = json.loads(response.read().decode("utf-8"))
            
        text = res["candidates"][0]["content"]["parts"][0]["text"].strip()
        # Strip common formatting leaks
        text = re.sub(r'[*`"]', '', text).strip()
        logging.info(f"Gemini OCR result: '{text}'")
        return text
    except Exception as e:
        logging.error(f"Gemini API request failed: {e}")
        return None

# -----------------------------------------------------------------------------
# ANNA'S ARCHIVE SEARCH Scraper (BeautifulSoup-independent)
# -----------------------------------------------------------------------------
def search_annas_archive(query, max_retries=5, retry_delay=2):
    """
    Searches Anna's Archive across active domains and parses metadata using regex.
    """
    encoded_query = urllib.parse.quote_plus(query)
    domains = ["annas-archive.gl", "annas-archive.li", "annas-archive.gs"]
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
    }
    
    html = ""
    connected_domain = ""
    
    for domain in domains:
        url = f"https://{domain}/search?q={encoded_query}"
        logging.info(f"Searching Anna's Archive on {domain}...")
        
        for attempt in range(max_retries):
            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=15) as response:
                    html = response.read().decode("utf-8", errors="ignore")
                    connected_domain = domain
                    logging.info(f"Successfully fetched results from {domain} (attempt {attempt+1})")
                    break
            except Exception as e:
                logging.warning(f"Attempt {attempt+1} on {domain} failed: {e}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
        if html:
            break
            
    if not html:
        logging.error("All search attempts on all domains failed.")
        return []

    # Regex search for unique MD5 hashes
    matches = list(re.finditer(r'/md5/([a-f0-9]{32})', html))
    unique_md5s = []
    unique_positions = []
    for m in matches:
        h = m.group(1)
        if h not in unique_md5s:
            unique_md5s.append(h)
            unique_positions.append(m.start())
            
    results = []
    for idx, (h, pos) in enumerate(zip(unique_md5s, unique_positions)):
        if idx + 1 < len(unique_positions):
            next_pos = unique_positions[idx+1]
        else:
            next_pos = pos + 5000
        snippet = html[pos:next_pos]
        
        # Parse title
        title = "Unknown"
        title_match = re.search(r'href="/md5/[a-f0-9]{32}"[^>]*class="[^"]*font-semibold[^"]*">([^<]+)</a>', snippet)
        if title_match:
            title = html_lib.unescape(title_match.group(1))
        else:
            a_match = re.search(r'<a href="/md5/[a-f0-9]{32}"[^>]*>([^<]+)</a>', snippet)
            if a_match:
                title = html_lib.unescape(a_match.group(1))
        title = re.sub(r'<[^>]+>', '', title).strip()
            
        # Clean up tags inside snippet to parse metadata
        clean_text = re.sub(r'<[^>]+>', ' | ', snippet)
        clean_text = re.sub(r'\s*\|\s*', ' | ', clean_text)
        clean_text = re.sub(r'\s+', ' ', clean_text)
        
        meta_line = "Unknown"
        dot_match = re.search(r'([^|·]+·\s*[^|·]+\s*·\s*[^|·]+\s*·\s*[^|·]+)', clean_text)
        if dot_match:
            meta_line = dot_match.group(1).strip()
        else:
            dot_match = re.search(r'([^|·]+·\s*[^|·]+\s*·\s*[^|·]+)', clean_text)
            if dot_match:
                meta_line = dot_match.group(1).strip()
                
        meta_line = html_lib.unescape(meta_line)
        parts = [p.strip() for p in meta_line.split("·")] if meta_line != "Unknown" else []
        
        lang = parts[0] if len(parts) > 0 else "Unknown"
        fmt = parts[1] if len(parts) > 1 else "Unknown"
        size = parts[2] if len(parts) > 2 else "Unknown"
        year = parts[3] if len(parts) > 3 else "Unknown"
        
        results.append({
            "md5": h,
            "title": title,
            "meta": meta_line,
            "lang": lang,
            "format": fmt,
            "size": size,
            "year": year,
            "domain": connected_domain
        })
        
    return results

# -----------------------------------------------------------------------------
# LIBGEN.LI SESSION-PRESERVING DOWNLOADER
# -----------------------------------------------------------------------------
def download_libgen_book(md5_hash, dest_filename):
    """
    Downloads a book directly from Libgen.li using a session cookie jar.
    """
    ads_url = f"https://libgen.li/ads.php?md5={md5_hash}"
    
    # Establish cookie processor for session binding
    cookie_jar = urllib.request.HTTPCookieProcessor()
    opener = urllib.request.build_opener(cookie_jar)
    opener.addheaders = [
        ("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"),
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
        
        with opener.open(get_url, timeout=60) as download_response:
            with open(dest_filename, "wb") as f_out:
                f_out.write(download_response.read())
                
        actual_size = os.path.getsize(dest_filename)
        logging.info(f"Book saved successfully: {dest_filename} ({actual_size} bytes)")
        return True
    except Exception as e:
        logging.error(f"Libgen.li session download failed: {e}")
        return False

# -----------------------------------------------------------------------------
# HELPER TO PARSE FILE SIZE FOR SORTING (e.g. "2.4MB" -> float(2400.0) KB)
# -----------------------------------------------------------------------------
def parse_size_to_kb(size_str):
    """
    Converts sizing strings (e.g., '2.4MB', '320KB') into float values in KB.
    """
    size_str = size_str.upper().strip()
    match = re.search(r'([0-9.]+)\s*([KM]B)', size_str)
    if not match:
        return 999999.0
    val = float(match.group(1))
    unit = match.group(2)
    if unit == "MB":
        return val * 1024.0
    return val

# -----------------------------------------------------------------------------
# MAIN BOOK RETRIEVAL PIPELINE
# -----------------------------------------------------------------------------
def process_book_request(query):
    """
    Takes a query, searches Anna's Archive, filters French EPUBs,
    downloads the smallest file, and returns the path.
    """
    logging.info(f"Starting book search for query: '{query}'")
    
    # 1. Search Anna's Archive
    results = search_annas_archive(query)
    if not results:
        return None, "Désolé, je n'ai trouvé aucun résultat pour cette recherche sur Anna's Archive."
        
    # 2. Filter for French and EPUB format
    french_epubs = []
    for r in results:
        lang_lower = r["lang"].lower()
        format_lower = r["format"].lower()
        
        # Check language matches French / fr
        is_french = "french" in lang_lower or "fr" in lang_lower or "[fr]" in lang_lower
        is_epub = "epub" in format_lower
        
        if is_french and is_epub:
            french_epubs.append(r)
            
    if not french_epubs:
        return None, "J'ai trouvé des résultats mais aucun n'est au format EPUB en français."
        
    # 3. Sort by size (ascending) to get the smallest EPUB for the e-reader
    # Alex prefers smallest EPUB files to save space
    french_epubs.sort(key=lambda x: parse_size_to_kb(x["size"]))
    
    best_match = french_epubs[0]
    title = best_match["title"]
    size = best_match["size"]
    md5 = best_match["md5"]
    
    logging.info(f"Selected Best Match: '{title}' | Size: {size} | MD5: {md5}")
    
    # 4. Standardize safe filename
    safe_title = re.sub(r'[/\\?%*:|"<>]', '_', title)
    dest_filename = os.path.join(IMPORT_DIR, f"{safe_title}.epub")
    
    # 5. Download book
    success = download_libgen_book(md5, dest_filename)
    if success:
        return dest_filename, f"Livre trouvé ! '{title}' (EPUB, {size}). Téléchargement terminé."
    else:
        return None, "Le téléchargement du livre a échoué depuis les serveurs Libgen."

# -----------------------------------------------------------------------------
# BOT WORKER LOOP
# -----------------------------------------------------------------------------
def run_bot():
    logging.info(f"Librarian Signal Bot is active. Polling {SIGNAL_URL} every {POLL_INTERVAL}s...")
    
    while True:
        try:
            messages = receive_signal_messages()
            if not messages:
                time.sleep(POLL_INTERVAL)
                continue
                
            for msg_item in messages:
                envelope = msg_item.get("envelope", {})
                sender = envelope.get("sourceNumber")
                data_msg = envelope.get("dataMessage")
                
                if not sender or not data_msg:
                    continue
                    
                # Strict Whitelist Validation for Security
                if sender != WIFE_NUMBER:
                    logging.warning(f"Blocked unauthorized message from {sender}.")
                    continue
                    
                logging.info(f"Received message from authorized sender ({WIFE_NUMBER}).")
                
                # Check for cover photo attachments
                attachments = data_msg.get("attachments", [])
                text_content = data_msg.get("message", "").strip()
                
                query = None
                
                # Handling Cover Photo OCR
                if attachments:
                    photo = attachments[0]
                    content_type = photo.get("contentType", "")
                    if "image" in content_type:
                        photo_id = photo.get("id")
                        send_signal_message(
                            "📸 J'ai bien reçu la photo de la couverture. Analyse de l'image en cours...", 
                            WIFE_NUMBER
                        )
                        
                        image_bytes = download_signal_attachment(photo_id)
                        if image_bytes:
                            ocr_text = extract_book_details_from_cover(image_bytes)
                            if ocr_text:
                                query = ocr_text
                                send_signal_message(
                                    f"🔍 Titre détecté : '{ocr_text}'. Recherche en cours sur Anna's Archive...", 
                                    WIFE_NUMBER
                                )
                            else:
                                send_signal_message(
                                    "⚠️ Désolé, je n'ai pas réussi à lire le titre sur la photo. Peux-tu m'écrire le titre et l'auteur par texte ?", 
                                    WIFE_NUMBER
                                )
                        else:
                            send_signal_message(
                                "⚠️ Erreur lors du téléchargement de la photo depuis l'API Signal.", 
                                WIFE_NUMBER
                            )
                
                # Handling Text Search Query
                elif text_content:
                    query = text_content
                    send_signal_message(
                        f"🔍 Recherche de '{query}' en cours sur Anna's Archive...", 
                        WIFE_NUMBER
                    )
                    
                # Run the search & download pipeline
                if query:
                    epub_path, status_msg = process_book_request(query)
                    
                    if epub_path:
                        send_signal_message(
                            f"📥 {status_msg}\nEnvoi du livre en cours...", 
                            WIFE_NUMBER
                        )
                        # Send the file back natively to the wife via Signal
                        send_signal_message(
                            "✨ Voilà ton livre ! Bonne lecture 📖", 
                            WIFE_NUMBER, 
                            attachment_path=epub_path
                        )
                        logging.info(f"Process complete. Book sent and saved in {IMPORT_DIR}")
                    else:
                        send_signal_message(
                            f"⚠️ {status_msg}", 
                            WIFE_NUMBER
                        )
                        
        except Exception as e:
            logging.error(f"Error in bot loop: {e}")
            
        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    run_bot()
