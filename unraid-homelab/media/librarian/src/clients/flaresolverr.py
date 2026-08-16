import logging
from typing import Optional, Dict
from config import Config
from core.http import json_request, get_ssl_context


class FlareSolverrClient:
    def __init__(self, endpoint_url: Optional[str] = None):
        self.endpoint_url = (endpoint_url or Config.FLARESOLVERR_URL).rstrip("/")

    @property
    def is_available(self) -> bool:
        return bool(self.endpoint_url)

    def solve(self, target_url: str, timeout_ms: int = 60000) -> Optional[Dict]:
        """
        Submits request to FlareSolverr / Byparr to bypass DDoS-Guard / Cloudflare challenges.
        Returns the solved solution dict with 'response', 'cookies', 'userAgent', etc.
        """
        if not self.is_available:
            return None

        url = f"{self.endpoint_url}/v1"
        payload = {
            "cmd": "request.get",
            "url": target_url,
            "maxTimeout": timeout_ms
        }
        
        timeout_sec = int(timeout_ms / 1000) + 15
        data, status = json_request(
            url=url,
            method="POST",
            payload=payload,
            timeout=timeout_sec,
            ssl_context=get_ssl_context()
        )
        
        if data and isinstance(data, dict) and data.get("status") == "ok":
            return data.get("solution", {})
            
        logging.warning(f"FlareSolverr challenge solve failed for {target_url} (status: {status})")
        return None
