import os
import json
import base64
import logging
import urllib.request
from config import Config


class SignalClient:
    def __init__(self, config=Config):
        self.config = config
        self.group_name_cache = {}
        self.group_id_api_format_cache = {}

    def make_request(self, endpoint, method="GET", payload=None, is_binary=False):
        """
        Sends an HTTP request directly to the Signal CLI REST API.
        """
        url = f"{self.config.SIGNAL_URL}{endpoint}"
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
                return json.loads(response.read().decode("utf-8"))
        except Exception as e:
            logging.error(f"Signal API error on {method} {endpoint}: {e}")
            return None

    def send_message(self, text, recipients, attachment_path=None, filename=None):
        """
        Sends a Signal message to recipients, optionally with a base64 attachment.
        """
        payload = {
            "message": text,
            "number": self.config.BOT_NUMBER,
            "recipients": recipients if isinstance(recipients, list) else [recipients]
        }
        
        if attachment_path and os.path.exists(attachment_path):
            try:
                with open(attachment_path, "rb") as f:
                    file_bytes = f.read()
                encoded_bytes = base64.b64encode(file_bytes).decode("utf-8")
                
                mime_type = "application/epub+zip" if attachment_path.endswith(".epub") else "application/octet-stream"
                disp_filename = filename or os.path.basename(attachment_path)
                attachment_str = f"data:{mime_type};filename={disp_filename};base64,{encoded_bytes}"
                
                payload["base64_attachments"] = [attachment_str]
                logging.info(f"Attached file: {attachment_path} ({len(file_bytes)} bytes)")
            except Exception as e:
                logging.error(f"Failed to encode attachment {attachment_path}: {e}")
                
        res = self.make_request("/v2/send", method="POST", payload=payload)
        if res:
            logging.info(f"Successfully sent message to {recipients}")
        return res

    def receive_messages(self):
        """
        Retrieves and clears unread messages from the Signal network.
        """
        endpoint = f"/v1/receive/{self.config.BOT_NUMBER}?timeout=5"
        return self.make_request(endpoint, method="GET")

    def download_attachment(self, attachment_id):
        """
        Fetches raw binary of a Signal attachment.
        """
        endpoint = f"/v1/attachments/{attachment_id}"
        return self.make_request(endpoint, method="GET", is_binary=True)

    def resolve_group_name(self, group_id):
        """
        Resolves plain-text name of a group from its base64 ID with caching.
        """
        if group_id in self.group_name_cache:
            return self.group_name_cache[group_id]
            
        logging.info(f"Group name cache miss for ID '{group_id}'. Querying Signal groups list...")
        endpoint = f"/v1/groups/{self.config.BOT_NUMBER}"
        groups_list = self.make_request(endpoint, method="GET")
        
        if groups_list and isinstance(groups_list, list):
            for g in groups_list:
                g_id = g.get("id")
                g_internal = g.get("internal_id")
                g_name = g.get("name")
                
                if g_id:
                    self.group_name_cache[g_id] = g_name
                    if g_id.startswith("group."):
                        raw_id = g_id[6:]
                        self.group_name_cache[raw_id] = g_name
                        self.group_id_api_format_cache[raw_id] = g_id
                if g_internal:
                    self.group_name_cache[g_internal] = g_name
                    if g_id:
                        self.group_id_api_format_cache[g_internal] = g_id
                    
        if group_id not in self.group_name_cache:
            logging.info(f"Attempting direct single group resolution for '{group_id}'...")
            api_group_id = group_id if group_id.startswith("group.") else f"group.{group_id}"
            single_endpoint = f"/v1/groups/{self.config.BOT_NUMBER}/{api_group_id}"
            g_details = self.make_request(single_endpoint, method="GET")
            if g_details and isinstance(g_details, dict):
                g_name = g_details.get("name")
                if g_name:
                    self.group_name_cache[group_id] = g_name
                    self.group_name_cache[api_group_id] = g_name
                    self.group_id_api_format_cache[group_id] = api_group_id
                    
        return self.group_name_cache.get(group_id)

    def get_api_group_id(self, group_id):
        return self.group_id_api_format_cache.get(group_id, group_id)
