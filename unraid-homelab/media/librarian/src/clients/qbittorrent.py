import logging
import urllib.request
import urllib.parse
import urllib.error
import http.cookiejar
from typing import Optional

from config import Config
from core.http import DEFAULT_USER_AGENT


class QBittorrentClient:
    def __init__(self, config=Config):
        self.config = config
        self.cookie_jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cookie_jar),
            urllib.request.ProxyHandler()
        )
        self._is_logged_in = False

    def login(self) -> bool:
        """
        Authenticates with qBittorrent Web API (/api/v2/auth/login).
        """
        if not self.config.QBITTORRENT_URL:
            return False

        if not self.config.QBITTORRENT_USER:
            # If no auth configured, assume local bypass
            return True

        login_url = f"{self.config.QBITTORRENT_URL}/api/v2/auth/login"
        payload = urllib.parse.urlencode({
            "username": self.config.QBITTORRENT_USER,
            "password": self.config.QBITTORRENT_PASSWORD
        }).encode("utf-8")

        req = urllib.request.Request(
            login_url,
            data=payload,
            headers={
                "User-Agent": DEFAULT_USER_AGENT,
                "Content-Type": "application/x-www-form-urlencoded",
                "Referer": f"{self.config.QBITTORRENT_URL}/"
            }
        )

        try:
            with self.opener.open(req, timeout=10) as resp:
                raw = resp.read().decode("utf-8", errors="ignore").strip()
                if "Ok." in raw or resp.status == 200:
                    logging.info("qBittorrent WebUI login successful.")
                    self._is_logged_in = True
                    return True
                logging.warning(f"qBittorrent login response: {raw}")
                return False
        except Exception as e:
            logging.error(f"Failed to authenticate with qBittorrent: {e}")
            return False

    def add_torrent(
        self,
        torrent_url_or_magnet: str,
        save_path: Optional[str] = None,
        category: Optional[str] = None,
        tags: Optional[str] = None
    ) -> bool:
        """
        Adds a torrent to qBittorrent via /api/v2/torrents/add with specified save path, category, and tag.
        """
        if not self.config.QBITTORRENT_URL:
            logging.error("QBITTORRENT_URL is not configured.")
            return False

        if self.config.QBITTORRENT_USER and not self._is_logged_in:
            self.login()

        add_url = f"{self.config.QBITTORRENT_URL}/api/v2/torrents/add"
        effective_savepath = save_path or self.config.QBITTORRENT_SAVE_PATH
        effective_category = category or self.config.QBITTORRENT_CATEGORY
        effective_tags = tags or self.config.QBITTORRENT_TAG

        form_data = {
            "urls": torrent_url_or_magnet,
            "savepath": effective_savepath,
            "category": effective_category,
            "tags": effective_tags,
            "paused": "false"
        }

        payload = urllib.parse.urlencode(form_data).encode("utf-8")
        req = urllib.request.Request(
            add_url,
            data=payload,
            headers={
                "User-Agent": DEFAULT_USER_AGENT,
                "Content-Type": "application/x-www-form-urlencoded",
                "Referer": f"{self.config.QBITTORRENT_URL}/"
            }
        )

        try:
            with self.opener.open(req, timeout=15) as resp:
                res_text = resp.read().decode("utf-8", errors="ignore").strip()
                if resp.status == 200 and ("Ok." in res_text or not res_text):
                    logging.info(
                        f"Torrent added to qBittorrent successfully (SavePath: {effective_savepath}, Category: {effective_category}, Tag: {effective_tags})."
                    )
                    return True
                logging.warning(f"qBittorrent add torrent response: {res_text}")
                return False
        except urllib.error.HTTPError as e:
            if e.code == 403 and not self._is_logged_in:
                logging.info("qBittorrent returned 403. Attempting login and retry...")
                if self.login():
                    return self.add_torrent(torrent_url_or_magnet, save_path, category, tags)
            logging.error(f"qBittorrent HTTP Error {e.code} on add torrent: {e}")
            return False
        except Exception as e:
            logging.error(f"Failed to add torrent to qBittorrent: {e}")
            return False
