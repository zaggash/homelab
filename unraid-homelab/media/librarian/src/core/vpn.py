import time
import logging
from typing import Optional
import requests
from config import Config


def rotate_vpn_ip(gluetun_url: Optional[str] = None) -> bool:
    """
    Triggers WireGuard VPN reconnection via Gluetun control API to obtain a new public IP.
    """
    url = (gluetun_url or Config.GLUETUN_URL).rstrip("/")
    if not url:
        return False

    try:
        ip0 = ""
        try:
            r0 = requests.get(f"{url}/v1/publicip/ip", timeout=5)
            if r0.status_code == 200:
                ip0 = r0.json().get("public_ip", "")
        except Exception:
            pass

        logging.info(f"Triggering Gluetun IP rotation (current IP: {ip0 or 'unknown'})...")
        requests.put(f"{url}/v1/vpn/status", json={"status": "stopped"}, timeout=10)
        time.sleep(2)
        requests.put(f"{url}/v1/vpn/status", json={"status": "running"}, timeout=10)

        for _ in range(15):
            time.sleep(1)
            try:
                r1 = requests.get(f"{url}/v1/publicip/ip", timeout=5)
                if r1.status_code == 200:
                    new_ip = r1.json().get("public_ip")
                    if new_ip:
                        logging.info(f"Gluetun VPN reconnected with IP: {new_ip} (previous: {ip0})")
                        return True
            except Exception:
                pass

        logging.warning("VPN status command sent, but timed out waiting for new public IP verification.")
        return True
    except Exception as e:
        logging.error(f"Failed to rotate Gluetun VPN IP via API: {e}")
        return False
