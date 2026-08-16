import os
import re
import json
import logging
import urllib.request
import urllib.parse
import html as html_lib
from core.matching import generate_query_candidates


def search_libgen_li(query: str) -> list:
    """
    Searches Libgen.li directly using its index and JSON API endpoint.
    Tries the full query first, then candidate decompositions.
    """
    query_list = generate_query_candidates(query)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
    }

    for target_q in query_list:
        encoded = urllib.parse.quote_plus(target_q)
        url = f"https://libgen.li/index.php?req={encoded}"
        logging.info(f"Searching Libgen.li for candidate query: '{target_q}'...")
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as resp:
                html = resp.read().decode("utf-8", errors="ignore")
                
            m = re.search(r'href=["\'](?:/)?(json\.php\?object=f&ids=[0-9,]+)["\']', html)
            if not m:
                logging.warning(f"No JSON API payload link found on Libgen.li index page for query '{target_q}'.")
                continue
                
            json_url = f"https://libgen.li/{m.group(1)}"
            req_json = urllib.request.Request(json_url, headers=headers)
            with urllib.request.urlopen(req_json, timeout=15) as resp_json:
                data = json.loads(resp_json.read().decode("utf-8"))
                
            results = []
            for item in data.values():
                md5 = item.get("md5", "").lower()
                extension = item.get("extension", "").lower()
                locator = item.get("locator", "")
                filesize = item.get("filesize", 0)
                
                title = item.get("title", "")
                authors = item.get("authors", "")
                
                if not title and locator:
                    filename = locator.split("\\")[-1].split("/")[-1]
                    title = re.sub(r'\.[a-zA-Z0-9]+$', '', filename)
                    
                full_title = f"{authors} - {title}" if authors and title else (title or authors)
                size_kb = float(filesize) / 1024.0 if filesize else 0
                size_str = f"{size_kb / 1024.0:.1f}MB" if size_kb > 1024 else f"{size_kb:.0f}KB"
                
                is_french_locator = "[fr]" in locator.lower() or "french" in locator.lower() or " romance)" in locator.lower()
                lang = "fr" if is_french_locator else "unknown"
                
                results.append({
                    "md5": md5,
                    "title": html_lib.unescape(full_title),
                    "meta": f"{lang} · {extension} · {size_str}",
                    "lang": lang,
                    "format": extension,
                    "size": size_str,
                    "year": item.get("year", "Unknown"),
                    "domain": "libgen.li"
                })
                
            if results:
                logging.info(f"Libgen.li search returned {len(results)} results for query '{target_q}'.")
                return results
        except Exception as e:
            logging.error(f"Libgen.li search attempt failed for '{target_q}': {e}")
            
    return []


def download_libgen_book(md5_hash: str, dest_filename: str) -> bool:
    """
    Downloads a book directly from Libgen.li using a session cookie jar and chunked stream.
    """
    ads_url = f"https://libgen.li/ads.php?md5={md5_hash}"
    
    cookie_jar = urllib.request.HTTPCookieProcessor()
    opener = urllib.request.build_opener(cookie_jar)
    opener.addheaders = [
        ("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"),
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
                while True:
                    chunk = download_response.read(65536)
                    if not chunk:
                        break
                    f_out.write(chunk)
                
        actual_size = os.path.getsize(dest_filename)
        if actual_size < 1024:
            logging.error(f"Downloaded file is too small ({actual_size} bytes). Likely an error page.")
            if os.path.exists(dest_filename):
                os.remove(dest_filename)
            return False

        logging.info(f"Book saved successfully: {dest_filename} ({actual_size} bytes)")
        return True
    except Exception as e:
        logging.error(f"Libgen.li session download failed: {e}")
        if os.path.exists(dest_filename):
            try:
                os.remove(dest_filename)
            except Exception:
                pass
        return False
