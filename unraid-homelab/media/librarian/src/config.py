import os
import sys
import logging

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)


class Config:
    SIGNAL_URL = os.getenv("SIGNAL_URL", "http://signal-api:8080").rstrip("/")
    BOT_NUMBER = os.getenv("BOT_NUMBER", "").strip()
    AUTHORIZED_NUMBERS_STR = os.getenv("AUTHORIZED_NUMBERS", "").strip()
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()
    IMPORT_DIR = os.getenv("IMPORT_DIR", "/books_import").strip()
    POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "10"))
    AUTHORIZED_GROUP = os.getenv("AUTHORIZED_GROUP", "").strip()
    GRIMMORY_URL = os.getenv("GRIMMORY_URL", "").rstrip("/")
    GRIMMORY_USER = os.getenv("GRIMMORY_USER", "").strip()
    GRIMMORY_PASSWORD = os.getenv("GRIMMORY_PASSWORD", "").strip()
    GRIMMORY_AUTH_HEADER = os.getenv("GRIMMORY_AUTH_HEADER", "Remote-User").strip()
    HEARTBEAT_FILE = os.getenv("HEARTBEAT_FILE", "/tmp/librarian_heartbeat")
    GLUETUN_URL = os.getenv("GLUETUN_URL", "http://gluetun:8000").rstrip("/")

    # Anna's Archive Mirrors
    ANNAS_PRIMARY_DOMAIN = os.getenv("ANNAS_PRIMARY_DOMAIN", "annas-archive.gl").strip()
    ANNAS_FALLBACK_DOMAINS = [
        d.strip()
        for d in os.getenv("ANNAS_FALLBACK_DOMAINS", "annas-archive.pk,annas-archive.gd").split(",")
        if d.strip()
    ]

    AUTHORIZED_NUMBERS = [num.strip() for num in AUTHORIZED_NUMBERS_STR.split(",") if num.strip()]

    @classmethod
    def validate(cls):
        if not cls.BOT_NUMBER:
            logging.error("BOT_NUMBER environment variable is missing!")
        if not cls.AUTHORIZED_NUMBERS:
            logging.error("No authorized numbers configured! Set AUTHORIZED_NUMBERS.")
        if not cls.GEMINI_API_KEY:
            logging.error("GEMINI_API_KEY environment variable is missing!")
        if cls.AUTHORIZED_GROUP:
            logging.info(f"Group restriction active: Only responding in group matching '{cls.AUTHORIZED_GROUP}'")
