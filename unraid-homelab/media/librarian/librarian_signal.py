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
import ssl

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
AUTHORIZED_NUMBERS_STR = os.getenv("AUTHORIZED_NUMBERS", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
IMPORT_DIR = os.getenv("IMPORT_DIR", "/books_import")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "10"))
AUTHORIZED_GROUP = os.getenv("AUTHORIZED_GROUP", "").strip()
GRIMMORY_URL = os.getenv("GRIMMORY_URL", "").rstrip("/")
GRIMMORY_USER = os.getenv("GRIMMORY_USER", "").strip()
GRIMMORY_PASSWORD = os.getenv("GRIMMORY_PASSWORD", "").strip()
GRIMMORY_AUTH_HEADER = os.getenv("GRIMMORY_AUTH_HEADER", "Remote-User").strip()
FLARESOLVERR_URL = os.getenv("FLARESOLVERR_URL", "").rstrip("/")

# Parse authorized numbers list
AUTHORIZED_NUMBERS = [num.strip() for num in AUTHORIZED_NUMBERS_STR.split(",") if num.strip()]

# Validate configuration
if not BOT_NUMBER:
    logging.error("BOT_NUMBER environment variable is missing!")
if not AUTHORIZED_NUMBERS:
    logging.error("No authorized numbers configured! Set AUTHORIZED_NUMBERS.")
if not GEMINI_API_KEY:
    logging.error("GEMINI_API_KEY environment variable is missing!")
if AUTHORIZED_GROUP:
    logging.info(f"Group restriction active: Only responding in group matching '{AUTHORIZED_GROUP}'")

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

# Global cache for resolving base64 group IDs to plain text names and API-compatible group IDs
GROUP_NAME_CACHE = {}
GROUP_ID_API_FORMAT_CACHE = {}

def resolve_group_name(group_id):
    """
    Resolves the plain-text name of a group from its base64 ID, using a local cache
    and falling back to the Signal REST API's groups list endpoint.
    Also caches the API-compatible double-base64 group ID format.
    """
    global GROUP_NAME_CACHE, GROUP_ID_API_FORMAT_CACHE
    
    if group_id in GROUP_NAME_CACHE:
        return GROUP_NAME_CACHE[group_id]
        
    logging.info(f"Group name cache miss for ID '{group_id}'. Querying Signal groups list...")
    endpoint = f"/v1/groups/{BOT_NUMBER}"
    groups_list = make_signal_request(endpoint, method="GET")
    
    logging.info(f"Signal API /v1/groups response: {groups_list}")
    
    if groups_list and isinstance(groups_list, list):
        for g in groups_list:
            g_id = g.get("id")
            g_internal = g.get("internal_id")
            g_name = g.get("name")
            
            # Cache using all possible representations to ensure robust matching
            if g_id:
                GROUP_NAME_CACHE[g_id] = g_name
                if g_id.startswith("group."):
                    raw_id = g_id[6:]
                    GROUP_NAME_CACHE[raw_id] = g_name
                    GROUP_ID_API_FORMAT_CACHE[raw_id] = g_id
            if g_internal:
                GROUP_NAME_CACHE[g_internal] = g_name
                if g_id:
                    GROUP_ID_API_FORMAT_CACHE[g_internal] = g_id
                
    # Fallback to direct group query if still not resolved
    if group_id not in GROUP_NAME_CACHE:
        logging.info(f"Attempting direct single group resolution for '{group_id}'...")
        # Ensure ID starts with "group." prefix for the API query
        api_group_id = group_id if group_id.startswith("group.") else f"group.{group_id}"
        single_endpoint = f"/v1/groups/{BOT_NUMBER}/{api_group_id}"
        g_details = make_signal_request(single_endpoint, method="GET")
        logging.info(f"Signal API single group response: {g_details}")
        if g_details and isinstance(g_details, dict):
            g_name = g_details.get("name")
            if g_name:
                GROUP_NAME_CACHE[group_id] = g_name
                # Cache the API group ID format too
                GROUP_NAME_CACHE[api_group_id] = g_name
                GROUP_ID_API_FORMAT_CACHE[group_id] = api_group_id
                
    return GROUP_NAME_CACHE.get(group_id)

# -----------------------------------------------------------------------------
# GRIMMORY INTEGRATION (LIBRARY & BOOKDROP QUEUE VERIFICATION)
# -----------------------------------------------------------------------------
_GRIMMORY_JWT_CACHE = None

def get_grimmory_jwt():
    """
    Obtains a valid JWT token from Grimmory.
    Supports:
    1. Local Auth (if GRIMMORY_USER and GRIMMORY_PASSWORD are provided).
       Calls POST /api/v1/auth/login with username and password.
    2. Dynamic Remote Auth / SSO (if GRIMMORY_USER is provided and GRIMMORY_PASSWORD is not).
       Calls GET /api/v1/auth/remote with Remote-User header.
    """
    global _GRIMMORY_JWT_CACHE
    if not GRIMMORY_URL or not GRIMMORY_USER:
        return None
        
    # If we have a cached JWT, return it
    if _GRIMMORY_JWT_CACHE:
        return _GRIMMORY_JWT_CACHE
        
    # Case 1: Local Authentication (Username/Password)
    if GRIMMORY_USER and GRIMMORY_PASSWORD:
        logging.info(f"Authenticating with Grimmory Local Auth for user '{GRIMMORY_USER}'...")
        url = f"{GRIMMORY_URL}/api/v1/auth/login"
        payload = {
            "username": GRIMMORY_USER,
            "password": GRIMMORY_PASSWORD
        }
        headers = {
            "Content-Type": "application/json"
        }
        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data_bytes, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                res_data = json.loads(response.read().decode("utf-8"))
                _GRIMMORY_JWT_CACHE = res_data.get("accessToken")
                if _GRIMMORY_JWT_CACHE:
                    logging.info("Grimmory local JWT acquired and cached successfully.")
                    return _GRIMMORY_JWT_CACHE
        except Exception as e:
            logging.error(f"Failed to authenticate with Grimmory Local Auth: {e}")
        return None
        
    # Case 2: Remote Auth / SSO (Username only, no Password)
    if GRIMMORY_USER and not GRIMMORY_PASSWORD:
        logging.info(f"Authenticating dynamically with Grimmory Remote Auth for user '{GRIMMORY_USER}'...")
        url = f"{GRIMMORY_URL}/api/v1/auth/remote"
        
        # Pass standard Remote-User header
        headers = {
            "Remote-User": GRIMMORY_USER,
            "Remote-Name": GRIMMORY_USER,
            "Remote-Email": f"{GRIMMORY_USER}@local.internal"
        }
        
        # Also support custom header name if configured
        if GRIMMORY_AUTH_HEADER and GRIMMORY_AUTH_HEADER != "Authorization":
            headers[GRIMMORY_AUTH_HEADER] = GRIMMORY_USER
            
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                res_data = json.loads(response.read().decode("utf-8"))
                _GRIMMORY_JWT_CACHE = res_data.get("accessToken")
                if _GRIMMORY_JWT_CACHE:
                    logging.info("Grimmory dynamic JWT acquired and cached successfully.")
                    return _GRIMMORY_JWT_CACHE
        except Exception as e:
            logging.error(f"Failed to fetch dynamic JWT from Grimmory: {e}")
            
    return None

def make_grimmory_request(endpoint, retry_on_401=True):
    """
    Sends an HTTP GET request to the Grimmory API.
    """
    global _GRIMMORY_JWT_CACHE
    jwt = get_grimmory_jwt()
    if not jwt:
        return None
        
    url = f"{GRIMMORY_URL}{endpoint}"
    headers = {
        "Authorization": f"Bearer {jwt}"
    }
    
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 401 and retry_on_401:
            logging.warning("Grimmory token expired (401). Clearing cache and retrying...")
            _GRIMMORY_JWT_CACHE = None
            return make_grimmory_request(endpoint, retry_on_401=False)
        logging.error(f"Grimmory API HTTP error on GET {endpoint}: {e}")
        return None
    except Exception as e:
        logging.error(f"Grimmory API error on GET {endpoint}: {e}")
        return None

def is_book_already_present(query):
    """
    Checks if the book is already in Grimmory library or in the bookdrop queue.
    Supports robust comparisons by checking both title-only and combined 'Author - Title' strings.
    """
    if not GRIMMORY_URL or not GRIMMORY_USER:
        return False, None
        
    logging.info(f"Checking if '{query}' is already present in Grimmory (library or bookdrop)...")
    
    # 1. Check Library Books (GET /api/v1/books)
    books = make_grimmory_request("/api/v1/books")
    if books and isinstance(books, list):
        for b in books:
            title = b.get("title")
            metadata = b.get("metadata") or {}
            meta_title = metadata.get("title")
            authors = metadata.get("authors") or []
            
            # Gather all comparison targets (both title-only and combined "Author - Title")
            targets = []
            for t in [title, meta_title]:
                if t:
                    targets.append(t)
                    for author in authors:
                        if author:
                            targets.append(f"{author} - {t}")
                            targets.append(f"{t} - {author}")
            
            for t in targets:
                similarity = calculate_title_similarity(query, t)
                if similarity >= 0.70:
                    return True, f"Déjà présent dans la bibliothèque : '{t}'"
                        
    # 2. Check Bookdrop Queue (GET /api/v1/bookdrop/files)
    bookdrop_data = make_grimmory_request("/api/v1/bookdrop/files")
    if bookdrop_data and isinstance(bookdrop_data, dict):
        files = bookdrop_data.get("content", [])
        if isinstance(files, list):
            for f in files:
                file_name = f.get("fileName")
                original_metadata = f.get("originalMetadata") or {}
                fetched_metadata = f.get("fetchedMetadata") or {}
                
                # Try getting titles and authors from both original and fetched metadata
                meta_title_orig = original_metadata.get("title")
                meta_title_fetch = fetched_metadata.get("title")
                
                authors_orig = original_metadata.get("authors") or []
                authors_fetch = fetched_metadata.get("authors") or []
                
                # Clean extension for name match
                file_name_clean = re.sub(r'\.[a-zA-Z0-9]+$', '', file_name) if file_name else ""
                
                # Build unique comparison list
                titles = [t for t in [file_name_clean, meta_title_orig, meta_title_fetch] if t]
                authors = []
                for a_list in [authors_orig, authors_fetch]:
                    for a in a_list:
                        if a and a not in authors:
                            authors.append(a)
                            
                targets = []
                for t in titles:
                    targets.append(t)
                    for author in authors:
                        if author:
                            targets.append(f"{author} - {t}")
                            targets.append(f"{t} - {author}")
                            
                for t in targets:
                    similarity = calculate_title_similarity(query, t)
                    if similarity >= 0.70:
                        return True, f"Déjà dans la file d'attente bookdrop : '{t}'"
                            
    return False, None

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
    domains = ["annas-archive.gl", "annas-archive.pk", "annas-archive.gd"]
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
    }
    
    html = ""
    connected_domain = ""
    
    for domain in domains:
        url = f"https://{domain}/search?q={encoded_query}&lang=fr&ext=epub"
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
        
        with opener.open(get_url, timeout=180) as download_response:
            with open(dest_filename, "wb") as f_out:
                f_out.write(download_response.read())
                
        actual_size = os.path.getsize(dest_filename)
        logging.info(f"Book saved successfully: {dest_filename} ({actual_size} bytes)")
        return True
    except Exception as e:
        logging.error(f"Libgen.li session download failed: {e}")
        return False

# -----------------------------------------------------------------------------
# FLARESOLVERR BYPASS FOR ANNA'S ARCHIVE DIRECT SLOW LINK
# -----------------------------------------------------------------------------
# -----------------------------------------------------------------------------
# WELIB BYPASS FOR CLOUDFLARE AND SLOW LINK DOWNLOAD
# -----------------------------------------------------------------------------
def download_annas_slow_link(md5_hash, dest_filename):
    """
    Uses FlareSolverr to bypass DDoS-Guard on Anna's Archive, resolve
    the 'no waitlist' (Option #5/6/7/8) slow download link, and download the book.
    Attempts up to 3 options (0/4, 0/5, 0/6) sequentially.
    """
    if not FLARESOLVERR_URL:
        return False
        
    options = ["0/4", "0/5", "0/6"]
    ctx = ssl._create_unverified_context()
    
    for idx, opt in enumerate(options):
        logging.info(f"Attempting FlareSolverr bypass Option #{idx+1} ({opt}) for MD5: {md5_hash}...")
        target_url = f"https://annas-archive.gl/slow_download/{md5_hash}/{opt}"
        
        payload = {
            "cmd": "request.get",
            "url": target_url,
            "maxTimeout": 30000  # 30 seconds for fast fallback
        }
        
        headers = {"Content-Type": "application/json"}
        req = urllib.request.Request(
            f"{FLARESOLVERR_URL}/v1", 
            data=json.dumps(payload).encode("utf-8"), 
            headers=headers
        )
        
        try:
            # urlopen timeout set to 35 to allow 30s FlareSolverr maxTimeout + network overhead
            with urllib.request.urlopen(req, timeout=35, context=ctx) as response:
                res_data = json.loads(response.read().decode("utf-8"))
                
            if res_data.get("status") != "ok":
                logging.warning(f"Option #{idx+1} ({opt}) challenge resolution failed: {res_data.get('message')}")
                continue
                
            solution = res_data.get("solution", {})
            html_content = solution.get("response", "")
            cookies = solution.get("cookies", [])
            user_agent = solution.get("userAgent", "")
            
            # Search for any URL on the page that contains the MD5 hash (or its first 12 characters)
            # This is 100% robust against any HTML/JS changes (handles href, plain text, clipboard JS, etc.)
            urls = re.findall(r'(https?://[^\s\"\'\)\(<>&]+)', html_content)
            valid_urls = []
            for u in urls:
                u_clean = html_lib.unescape(u)
                if (md5_hash in u_clean or md5_hash[:12] in u_clean) and u_clean not in valid_urls:
                    valid_urls.append(u_clean)
                    
            if not valid_urls:
                logging.warning(f"Option #{idx+1} ({opt}) - Could not find resolved download URL in FlareSolverr response.")
                continue
                
            captured_url = valid_urls[0]
            
            # If the URL is relative, construct the absolute URL using the target_url origin
            if captured_url.startswith("/"):
                parsed_origin = urllib.parse.urlparse(target_url)
                resolved_url = f"{parsed_origin.scheme}://{parsed_origin.netloc}{captured_url}"
            else:
                resolved_url = captured_url
                
            # URL encode spaces/special characters in the URL path (preserving slashes)
            parsed_url = urllib.parse.urlparse(resolved_url)
            encoded_path = urllib.parse.quote(parsed_url.path, safe="/")
            resolved_url = urllib.parse.urlunparse((
                parsed_url.scheme,
                parsed_url.netloc,
                encoded_path,
                parsed_url.params,
                parsed_url.query,
                parsed_url.fragment
            ))
                
            logging.info(f"Option #{idx+1} ({opt}) resolved download URL: {resolved_url}")
            
            # Prepare request using solved cookies and user-agent
            cookie_header = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
            dl_headers = {
                "User-Agent": user_agent,
                "Referer": target_url
            }
            if cookie_header:
                dl_headers["Cookie"] = cookie_header
                
            dl_req = urllib.request.Request(resolved_url, headers=dl_headers)
            with urllib.request.urlopen(dl_req, timeout=60, context=ctx) as dl_response:
                with open(dest_filename, "wb") as f_out:
                    f_out.write(dl_response.read())
                    
            actual_size = os.path.getsize(dest_filename)
            logging.info(f"Book saved successfully via FlareSolverr Option #{idx+1} ({opt}): {dest_filename} ({actual_size} bytes)")
            return True
            
        except Exception as e:
            logging.warning(f"Option #{idx+1} ({opt}) download flow failed: {e}. Trying next option...")
            if os.path.exists(dest_filename):
                try:
                    os.remove(dest_filename)
                except Exception:
                    pass
            continue
            
    logging.error(f"All {len(options)} FlareSolverr slow download options failed for MD5: {md5_hash}.")
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
# JACCARD STRING SIMILARITY FOR ROBUST TITLE RELEVANCE FILTERING
# -----------------------------------------------------------------------------
def calculate_title_similarity(query, title):
    """
    Calculates a similarity score (0.0 to 1.0) between query and title
    based on word overlap, ignoring case, punctuation, and common short stop words.
    """
    def tokenize(text):
        # Convert to lowercase and replace non-alphanumeric with spaces
        text_norm = re.sub(r'[^\w\s]', ' ', text.lower())
        # Filter out short or common noise words in French and English
        stop_words = {
            'le', 'la', 'les', 'un', 'une', 'des', 'du', 'de', 'et', 'en', 'au', 'aux', 
            'pour', 'dans', 'sur', 'par', 'avec', 'sans', 'sous', 'the', 'of', 'and', 'in', 'on', 'with', 'for',
            'fr', 'french', 'epub', 'edition', 'tome', 'vol', 'volume', 'ebook', 'livre', 
            'pdf', 'complet', 'gratuit', 'gratuits', 'version', 'intégrale', 'integrale'
        }
        words = [w for w in text_norm.split() if len(w) > 1 and w not in stop_words]
        return set(words)
        
    query_tokens = tokenize(query)
    title_tokens = tokenize(title)
    
    if not query_tokens:
        return 0.0
        
    intersection = query_tokens.intersection(title_tokens)
    union = query_tokens.union(title_tokens)
    
    # Standard Jaccard similarity
    return len(intersection) / len(union) if union else 0.0

# -----------------------------------------------------------------------------
# MAIN BOOK RETRIEVAL PIPELINE
# -----------------------------------------------------------------------------
def process_book_request(query):
    """
    Takes a query, searches Anna's Archive, filters French EPUBs,
    ranks them by title relevance, and downloads the smallest highly relevant file.
    """
    logging.info(f"Starting book search for query: '{query}'")
    
    # 0. Check if already present in Grimmory (library or bookdrop queue)
    present, reason = is_book_already_present(query)
    if present:
        return None, f"📚 {reason}\nLa recherche a été annulée."
    
    # 1. Search Anna's Archive (with lang=fr and ext=epub pre-filtering)
    results = search_annas_archive(query)
    if not results:
        return None, "Désolé, je n'ai trouvé aucun résultat pour cette recherche sur Anna's Archive."
        
    # 2. Filter for French and EPUB format, and compute title similarity scores
    french_epubs = []
    for r in results:
        lang_lower = r["lang"].lower()
        format_lower = r["format"].lower()
        
        # Check language matches French / fr
        is_french = "french" in lang_lower or "fr" in lang_lower or "[fr]" in lang_lower
        is_epub = "epub" in format_lower
        
        if is_french and is_epub:
            # Calculate title similarity score between the query and this result's title
            similarity = calculate_title_similarity(query, r["title"])
            r["similarity"] = similarity
            french_epubs.append(r)
            
    if not french_epubs:
        return None, "J'ai trouvé des résultats mais aucun n'est au format EPUB en français."
        
    # 3. Two-pass selection to balance relevance and file size:
    # Pass 1: Find the highest title similarity score in our results
    max_similarity = max(r["similarity"] for r in french_epubs)
    
    # Require at least a minimum absolute confidence score (e.g. 0.35) for the best match to avoid downloading random books
    min_confidence = 0.35
    if max_similarity < min_confidence:
        logging.warning(f"Max similarity found ({max_similarity:.2f}) is below absolute confidence threshold ({min_confidence:.2f}). Aborting search.")
        return None, f"Désolé, je n'ai trouvé aucun livre correspondant de manière fiable à ta recherche (la similarité maximale avec les titres trouvés est de {max_similarity:.2f})."
        
    # Pass 2: Filter results to keep only those within a close margin (e.g. within 0.15) of the highest score,
    # and require at least a minimum similarity score (e.g. 0.20) to avoid completely irrelevant matches.
    relevance_threshold = max(max_similarity - 0.15, 0.20)
    candidates = [r for r in french_epubs if r["similarity"] >= relevance_threshold]
    
    # If no results passed the relevance threshold, cancel the search to avoid downloading completely irrelevant books
    if not candidates:
        logging.warning(f"No results passed the similarity threshold of {relevance_threshold:.2f} (max similarity found was {max_similarity:.2f}).")
        return None, f"Désolé, je n'ai trouvé aucun livre correspondant de manière fiable à ta recherche (la similarité maximale avec les titres trouvés est de {max_similarity:.2f})."
        
    # 4. Sort candidates by size (ascending) to get the smallest file of the highly-relevant set
    candidates.sort(key=lambda x: parse_size_to_kb(x["size"]))
    
    # 5. Try downloading candidates sequentially until one succeeds
    for idx, best_match in enumerate(candidates):
        title = best_match["title"]
        size = best_match["size"]
        md5 = best_match["md5"]
        sim_score = best_match.get("similarity", 0.0)
        
        logging.info(f"Trying Candidate {idx+1}/{len(candidates)}: '{title}' | Similarity: {sim_score:.2f} | Size: {size} | MD5: {md5}")
        
        # Standardize safe filename
        safe_title = re.sub(r'[/\\?%*:|"<>]', '_', title)
        dest_filename = os.path.join(IMPORT_DIR, f"{safe_title}.epub")
        
        # Download book
        success = download_libgen_book(md5, dest_filename)
        if not success and FLARESOLVERR_URL:
            success = download_annas_slow_link(md5, dest_filename)
            
        if success:
            return dest_filename, f"Livre trouvé ! '{title}' (EPUB, {size}). Téléchargement terminé."
        else:
            logging.warning(f"Failed to download candidate {idx+1} ({md5}). Trying next available candidate...")
            if os.path.exists(dest_filename):
                try:
                    os.remove(dest_filename)
                except Exception as rm_err:
                    logging.error(f"Failed to remove partial/failed download file {dest_filename}: {rm_err}")
            
    return None, "Le téléchargement du livre a échoué (tous les candidats ont échoué sur Libgen et Anna's Archive)."

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
                
                # Handle sync messages (e.g., "Note to Self" sent from primary mobile device)
                sync_msg = envelope.get("syncMessage", {})
                sent_msg = sync_msg.get("sentMessage") if sync_msg else None
                if sent_msg and sender == BOT_NUMBER:
                    data_msg = sent_msg
                
                if not sender or not data_msg:
                    continue
                    
                # Strict Whitelist Validation for Security
                # Automatically allow BOT_NUMBER (Note to Self)
                if sender not in AUTHORIZED_NUMBERS and sender != BOT_NUMBER:
                    logging.warning(f"Blocked unauthorized message from {sender}.")
                    continue
                    
                logging.info(f"Received message from authorized sender ({sender}).")
                
                # Check for cover photo attachments
                attachments = data_msg.get("attachments", [])
                
                # Handle cases where message is explicitly None (e.g. photo sent with no caption)
                raw_message = data_msg.get("message")
                text_content = raw_message.strip() if raw_message else ""
                
                # Determine if the message comes from a group chat (v1 or v2 format)
                group_info = data_msg.get("groupInfo") or data_msg.get("groupV2Info") or {}
                group_id = group_info.get("groupId")
                
                # Fetch group name from message, caching it, or resolving dynamically on cache miss
                group_name = group_info.get("name")
                if group_id:
                    # Always resolve to ensure BOTH name cache and API-compatible ID format cache are populated
                    resolved_name = resolve_group_name(group_id)
                    if resolved_name:
                        group_name = resolved_name
                    elif group_name:
                        GROUP_NAME_CACHE[group_id] = group_name
                
                is_group = bool(group_id)
                is_note_to_self = (sender == BOT_NUMBER)
                
                # Enforce context isolation: Only respond in group chats OR in Note to Self.
                # Standard one-on-one DMs from other users are completely ignored to avoid spam.
                if not (is_group or is_note_to_self):
                    logging.info(f"Ignored message from {sender} (not in a group and not Note to Self).")
                    continue
                
                # If a specific authorized group is configured, restrict group messages to that group
                if is_group and AUTHORIZED_GROUP:
                    # Match by group ID or group name (case-insensitive)
                    matches_id = (group_id == AUTHORIZED_GROUP)
                    matches_name = (group_name and group_name.strip().lower() == AUTHORIZED_GROUP.lower())
                    
                    if not (matches_id or matches_name):
                        logging.warning(f"Blocked group message from unauthorized group: '{group_name}' (ID: {group_id}).")
                        continue
                
                # Resolve the API-compatible group ID format (starting with "group.") if it exists in cache
                api_group_id = GROUP_ID_API_FORMAT_CACHE.get(group_id, group_id)
                # Ensure the prefix "group." is present for sending back to a group ID
                if is_group and not api_group_id.startswith("group."):
                    api_group_id = f"group.{api_group_id}"
                
                # Reply destination: send back to the group if it's a group message, otherwise to DM (Note to Self)
                reply_to = api_group_id if is_group else sender
                
                # Verify trigger prefixes (e.g., !book or !livre) to prevent normal chat/note/group spam.
                # Prefix is strictly mandatory for normal messages, but optional if there is an image attachment.
                prefix_pattern = r"^(!book|!livre)\b"
                has_prefix = bool(re.match(prefix_pattern, text_content, re.IGNORECASE))
                has_image_attachment = any("image" in att.get("contentType", "") for att in attachments)
                
                if not (has_prefix or has_image_attachment):
                    # Silently ignore normal non-book related messages in chats/groups
                    continue
                
                query = None
                
                # Handling Cover Photo OCR
                if attachments:
                    photo = attachments[0]
                    content_type = photo.get("contentType", "")
                    if "image" in content_type:
                        photo_id = photo.get("id")
                        send_signal_message(
                            "📸 J'ai bien reçu la photo de la couverture. Analyse de l'image en cours...", 
                            reply_to
                        )
                        
                        image_bytes = download_signal_attachment(photo_id)
                        if image_bytes:
                            ocr_text = extract_book_details_from_cover(image_bytes)
                            if ocr_text:
                                query = ocr_text
                                send_signal_message(
                                    f"🔍 Titre détecté : '{ocr_text}'. Recherche en cours sur Anna's Archive...", 
                                    reply_to
                                )
                            else:
                                send_signal_message(
                                    "⚠️ Désolé, je n'ai pas réussi à lire le titre sur la photo. Peux-tu m'écrire le titre et l'auteur par texte ?", 
                                    reply_to
                                )
                        else:
                            send_signal_message(
                                "⚠️ Erreur lors du téléchargement de la photo depuis l'API Signal.", 
                                reply_to
                            )
                
                # Handling Text Search Query (only processed if has_prefix is True)
                elif text_content:
                    # Extract query by stripping the prefix
                    query = re.sub(prefix_pattern, "", text_content, flags=re.IGNORECASE).strip()
                    
                    send_signal_message(
                        f"🔍 Recherche de '{query}' en cours sur Anna's Archive...", 
                        reply_to
                    )
                    
                # Run the search & download pipeline
                if query:
                    epub_path, status_msg = process_book_request(query)
                    
                    if epub_path:
                        send_signal_message(
                            f"📥 {status_msg}\nEnvoi du livre en cours...", 
                            reply_to
                        )
                        # Send the file back natively to the user via Signal
                        send_signal_message(
                            "✨ Voilà ton livre ! Bonne lecture 📖", 
                            reply_to, 
                            attachment_path=epub_path
                        )
                        logging.info(f"Process complete. Book sent and saved in {IMPORT_DIR}")
                    else:
                        send_signal_message(
                            f"⚠️ {status_msg}", 
                            reply_to
                        )
                        
        except Exception as e:
            logging.error(f"Error in bot loop: {e}")
            
        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    run_bot()
