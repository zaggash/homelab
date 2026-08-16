import os
import re
import ssl
import time
import json
import logging
import urllib.request
import urllib.parse
import html as html_lib
from typing import Optional, List
from config import Config
from core.matching import generate_query_candidates


def search_annas_archive(query: str, flaresolverr_url: Optional[str] = None, max_retries: int = 1, retry_delay: int = 2) -> List[dict]:
    """
    Searches Anna's Archive across active domains using query candidates.
    """
    if flaresolverr_url is None:
        flaresolverr_url = Config.FLARESOLVERR_URL

    query_candidates = generate_query_candidates(query)
    domains = ["annas-archive.gl", "annas-archive.pk", "annas-archive.gd", "annas-archive.li", "annas-archive.se"]
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
    }
    ctx = ssl._create_unverified_context()

    for target_q in query_candidates:
        encoded_query = urllib.parse.quote_plus(target_q)
        html = ""
        connected_domain = ""

        for domain in domains:
            url = f"https://{domain}/search?q={encoded_query}&lang=fr&ext=epub"
            logging.info(f"Searching Anna's Archive for '{target_q}' on {domain}...")

            for attempt in range(max_retries):
                # 1. Direct Attempt
                try:
                    req = urllib.request.Request(url, headers=headers)
                    with urllib.request.urlopen(req, timeout=10) as response:
                        raw_html = response.read().decode("utf-8", errors="ignore")
                        if "DDoS-Guard" not in raw_html and "Just a moment..." not in raw_html:
                            html = raw_html
                            connected_domain = domain
                            logging.info(f"Successfully fetched results directly from {domain}")
                            break
                except Exception:
                    pass

                # 2. Byparr Fallback Attempt
                if flaresolverr_url:
                    payload = {"cmd": "request.get", "url": url, "maxTimeout": 60000}
                    req_proxy = urllib.request.Request(
                        f"{flaresolverr_url}/v1",
                        data=json.dumps(payload).encode("utf-8"),
                        headers={"Content-Type": "application/json"}
                    )
                    try:
                        with urllib.request.urlopen(req_proxy, timeout=75, context=ctx) as response:
                            res_data = json.loads(response.read().decode("utf-8"))
                            if res_data.get("status") == "ok":
                                byparr_html = res_data.get("solution", {}).get("response", "")
                                if byparr_html and "DDoS-Guard" not in byparr_html:
                                    html = byparr_html
                                    connected_domain = domain
                                    logging.info(f"Successfully fetched results via Byparr from {domain}")
                                    break
                    except Exception as e:
                        logging.error(f"Error calling Byparr endpoint for {domain}: {e}")

                if attempt < max_retries - 1 and not html:
                    time.sleep(retry_delay)

            if html:
                break

        if html:
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
                next_pos = unique_positions[idx+1] if idx + 1 < len(unique_positions) else pos + 5000
                snippet = html[pos:next_pos]

                title = "Unknown"
                title_match = re.search(r'href="/md5/[a-f0-9]{32}"[^>]*class="[^"]*font-semibold[^"]*">([^<]+)</a>', snippet)
                if title_match:
                    title = html_lib.unescape(title_match.group(1))
                else:
                    a_match = re.search(r'<a href="/md5/[a-f0-9]{32}"[^>]*>([^<]+)</a>', snippet)
                    if a_match:
                        title = html_lib.unescape(a_match.group(1))
                title = re.sub(r'<[^>]+>', '', title).strip()

                clean_text = re.sub(r'<[^>]+>', ' | ', snippet)
                clean_text = re.sub(r'\s*\|\s*', ' | ', clean_text)
                clean_text = re.sub(r'\s+', ' ', clean_text)

                meta_line = "Unknown"
                dot_match = re.search(r'([^|·]+·\s*[^|·]+\s*·\s*[^|·]+\s*·\s*[^|·]+)', clean_text)
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

            if results:
                logging.info(f"Anna's Archive returned {len(results)} results for candidate query '{target_q}'.")
                return results

    logging.warning("All search attempts on Anna's Archive failed.")
    return []


def download_annas_slow_link(md5_hash: str, dest_filename: str, flaresolverr_url: Optional[str] = None) -> bool:
    """
    Uses Byparr / FlareSolverr to bypass challenge on Anna's Archive slow download page.
    """
    if flaresolverr_url is None:
        flaresolverr_url = Config.FLARESOLVERR_URL

    if not flaresolverr_url:
        return False
        
    options = ["0/4", "0/5", "0/6", "0/0", "0/1", "0/2"]
    ctx = ssl._create_unverified_context()
    
    for idx, opt in enumerate(options):
        logging.info(f"Attempting FlareSolverr bypass Option #{idx+1} ({opt}) for MD5: {md5_hash}...")
        target_url = f"https://annas-archive.gl/slow_download/{md5_hash}/{opt}"
        
        payload = {
            "cmd": "request.get",
            "url": target_url,
            "maxTimeout": 30000
        }
        
        headers = {"Content-Type": "application/json"}
        req = urllib.request.Request(
            f"{flaresolverr_url}/v1", 
            data=json.dumps(payload).encode("utf-8"), 
            headers=headers
        )
        
        try:
            with urllib.request.urlopen(req, timeout=35, context=ctx) as response:
                res_data = json.loads(response.read().decode("utf-8"))
                
            if res_data.get("status") != "ok":
                logging.warning(f"Option #{idx+1} ({opt}) challenge resolution failed: {res_data.get('message')}")
                continue
                
            solution = res_data.get("solution", {})
            html_content = solution.get("response", "")
            cookies = solution.get("cookies", [])
            user_agent = solution.get("userAgent", "")
            
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
            
            if captured_url.startswith("/"):
                parsed_origin = urllib.parse.urlparse(target_url)
                resolved_url = f"{parsed_origin.scheme}://{parsed_origin.netloc}{captured_url}"
            else:
                resolved_url = captured_url
                
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
            
            cookie_header = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
            dl_headers = {
                "User-Agent": user_agent,
                "Referer": target_url
            }
            if cookie_header:
                dl_headers["Cookie"] = cookie_header
                
            dl_req = urllib.request.Request(resolved_url, headers=dl_headers)
            with urllib.request.urlopen(dl_req, timeout=90, context=ctx) as dl_response:
                with open(dest_filename, "wb") as f_out:
                    while True:
                        chunk = dl_response.read(65536)
                        if not chunk:
                            break
                        f_out.write(chunk)
                    
            actual_size = os.path.getsize(dest_filename)
            if actual_size < 1024:
                logging.warning(f"File too small ({actual_size} bytes). Removing...")
                if os.path.exists(dest_filename):
                    os.remove(dest_filename)
                continue

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
            
    logging.error(f"All slow download options failed for MD5: {md5_hash}.")
    return False
