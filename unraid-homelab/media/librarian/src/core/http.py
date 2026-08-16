import os
import ssl
import json
import logging
import urllib.request
import urllib.error
from typing import Optional, Dict, Any, Tuple

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)


def get_ssl_context() -> ssl.SSLContext:
    return ssl._create_unverified_context()


def json_request(
    url: str,
    method: str = "GET",
    payload: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: int = 15,
    ssl_context: Optional[ssl.SSLContext] = None
) -> Tuple[Optional[Any], Optional[int]]:
    """
    Standardized JSON HTTP request helper returning (data, status_code).
    """
    req_headers = {"User-Agent": DEFAULT_USER_AGENT}
    if headers:
        req_headers.update(headers)

    data_bytes = None
    if payload is not None:
        req_headers["Content-Type"] = "application/json"
        data_bytes = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(url, data=data_bytes, headers=req_headers, method=method)
    try:
        if ssl_context:
            resp_ctx = urllib.request.urlopen(req, timeout=timeout, context=ssl_context)
        else:
            resp_ctx = urllib.request.urlopen(req, timeout=timeout)

        with resp_ctx as resp:
            raw = resp.read().decode("utf-8", errors="ignore")
            status = getattr(resp, "status", 200)
            try:
                return json.loads(raw), status
            except json.JSONDecodeError:
                return raw, status
    except urllib.error.HTTPError as e:
        logging.error(f"HTTP error {e.code} on {method} {url}: {e}")
        return None, e.code
    except Exception as e:
        logging.error(f"Network error on {method} {url}: {e}")
        return None, None


def download_stream(
    req_or_url: Any,
    dest_path: str,
    opener: Optional[urllib.request.OpenerDirector] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: int = 120,
    min_size_bytes: int = 1024,
    ssl_context: Optional[ssl.SSLContext] = None
) -> bool:
    """
    Streams download directly to disk with chunked buffering (64KB) and size validation.
    Removes partial/corrupt files on failure.
    """
    if isinstance(req_or_url, str):
        req_headers = {"User-Agent": DEFAULT_USER_AGENT}
        if headers:
            req_headers.update(headers)
        req = urllib.request.Request(req_or_url, headers=req_headers)
    else:
        req = req_or_url

    try:
        if opener:
            open_resp = opener.open(req, timeout=timeout)
        elif ssl_context:
            open_resp = urllib.request.urlopen(req, timeout=timeout, context=ssl_context)
        else:
            open_resp = urllib.request.urlopen(req, timeout=timeout)

        with open_resp as resp:
            with open(dest_path, "wb") as f_out:
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    f_out.write(chunk)

        actual_size = os.path.getsize(dest_path)
        if actual_size < min_size_bytes:
            logging.warning(f"File too small ({actual_size} bytes < {min_size_bytes}). Removing {dest_path}...")
            if os.path.exists(dest_path):
                os.remove(dest_path)
            return False

        logging.info(f"File successfully downloaded: {dest_path} ({actual_size} bytes)")
        return True
    except Exception as e:
        logging.warning(f"Download stream failed for {dest_path}: {e}")
        if os.path.exists(dest_path):
            try:
                os.remove(dest_path)
            except Exception:
                pass
        return False
