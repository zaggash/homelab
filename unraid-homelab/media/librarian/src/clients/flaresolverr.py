import logging
from typing import Optional, Dict, List
from config import Config
from core.http import json_request, get_ssl_context


class FlareSolverrClient:
    def __init__(self, endpoint_url: Optional[str] = None):
        self.endpoint_url = (endpoint_url or Config.FLARESOLVERR_URL).rstrip("/")
        self.session_id: Optional[str] = None
        self._cached_cookies: List[Dict] = []
        self._cached_user_agent: Optional[str] = None

    @property
    def is_available(self) -> bool:
        return bool(self.endpoint_url)

    def create_session(self) -> Optional[str]:
        """
        Creates a persistent browser session in FlareSolverr/Byparr to retain cookies and bypass repeated challenges.
        """
        if not self.is_available:
            return None

        url = f"{self.endpoint_url}/v1"
        payload = {"cmd": "sessions.create"}
        data, status = json_request(url=url, method="POST", payload=payload, timeout=30, ssl_context=get_ssl_context())

        if data and isinstance(data, dict) and data.get("status") == "ok":
            self.session_id = data.get("session")
            logging.info(f"FlareSolverr session created: {self.session_id}")
            return self.session_id

        logging.warning(f"Could not create FlareSolverr session (status: {status}). Continuing in stateless mode.")
        return None

    def destroy_session(self):
        """
        Destroys the active persistent session if any.
        """
        if not self.is_available or not self.session_id:
            return

        url = f"{self.endpoint_url}/v1"
        payload = {"cmd": "sessions.destroy", "session": self.session_id}
        json_request(url=url, method="POST", payload=payload, timeout=15, ssl_context=get_ssl_context())
        self.session_id = None

    def solve(self, target_url: str, timeout_ms: int = 60000) -> Optional[Dict]:
        """
        Submits request to FlareSolverr / Byparr to bypass DDoS-Guard / Cloudflare challenges.
        Reuses session context if available to skip repeated JS challenges.
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
        if self.session_id:
            payload["session"] = self.session_id

        timeout_sec = int(timeout_ms / 1000) + 15
        data, status = json_request(
            url=url,
            method="POST",
            payload=payload,
            timeout=timeout_sec,
            ssl_context=get_ssl_context()
        )

        # If failed with session error, reset session and retry once
        if (not data or (isinstance(data, dict) and data.get("status") != "ok")) and self.session_id:
            logging.warning(f"FlareSolverr request with session '{self.session_id}' failed. Retrying without session...")
            self.session_id = None
            payload.pop("session", None)
            data, status = json_request(
                url=url,
                method="POST",
                payload=payload,
                timeout=timeout_sec,
                ssl_context=get_ssl_context()
            )

        if data and isinstance(data, dict) and data.get("status") == "ok":
            solution = data.get("solution", {})
            if solution.get("cookies"):
                self._cached_cookies = solution["cookies"]
            if solution.get("userAgent"):
                self._cached_user_agent = solution["userAgent"]
            return solution

        logging.warning(f"FlareSolverr challenge solve failed for {target_url} (status: {status})")
        return None
