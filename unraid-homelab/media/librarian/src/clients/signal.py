import os
import re
import base64
import logging
import urllib.request
from typing import Optional, List, Any
from config import Config
from core.models import IncomingEvent
from core.http import json_request
from core.matching import mask_identifier


class SignalClient:
    def __init__(self, config=Config):
        self.config = config
        self.group_name_cache = {}
        self.group_id_api_format_cache = {}

    def make_request(self, endpoint: str, method: str = "GET", payload: Optional[dict] = None, is_binary: bool = False) -> Optional[Any]:
        """
        Sends an HTTP request directly to the Signal CLI REST API.
        """
        url = f"{self.config.SIGNAL_URL}{endpoint}"
        if is_binary:
            req = urllib.request.Request(url, method=method)
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    return resp.read()
            except Exception as e:
                logging.error(f"Signal binary API error on {method} {endpoint}: {e}")
                return None

        data, _ = json_request(url, method=method, payload=payload, timeout=30)
        return data

    def send_message(self, text: str, recipients: Any, attachment_path: Optional[str] = None, filename: Optional[str] = None) -> Optional[dict]:
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

    def receive_messages(self) -> Optional[List[dict]]:
        """
        Retrieves unread messages from the Signal network.
        """
        endpoint = f"/v1/receive/{self.config.BOT_NUMBER}?timeout=5"
        res = self.make_request(endpoint, method="GET")
        return res if isinstance(res, list) else None

    def download_attachment(self, attachment_id: str) -> Optional[bytes]:
        """
        Fetches raw binary of a Signal attachment.
        """
        endpoint = f"/v1/attachments/{attachment_id}"
        return self.make_request(endpoint, method="GET", is_binary=True)

    def resolve_group_name(self, group_id: str) -> Optional[str]:
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

    def get_api_group_id(self, group_id: str) -> str:
        return self.group_id_api_format_cache.get(group_id, group_id)

    def parse_message_item(self, msg_item: dict) -> Optional[IncomingEvent]:
        """
        Extracts, filters and validates an incoming Signal envelope into an IncomingEvent.
        """
        envelope = msg_item.get("envelope", {})
        sender = envelope.get("sourceNumber")
        data_msg = envelope.get("dataMessage")

        sync_msg = envelope.get("syncMessage", {})
        sent_msg = sync_msg.get("sentMessage") if sync_msg else None
        if sent_msg and sender == self.config.BOT_NUMBER:
            data_msg = sent_msg

        if not sender or not data_msg:
            return None

        if sender not in self.config.AUTHORIZED_NUMBERS and sender != self.config.BOT_NUMBER:
            logging.warning(f"Blocked unauthorized message from {mask_identifier(sender)}.")
            return None

        logging.info(f"Received message from authorized sender ({mask_identifier(sender)}).")

        attachments = data_msg.get("attachments", [])
        raw_message = data_msg.get("message")
        text_content = raw_message.strip() if raw_message else ""

        group_info = data_msg.get("groupInfo") or data_msg.get("groupV2Info") or {}
        group_id = group_info.get("groupId")
        group_name = group_info.get("name")
        if group_id:
            resolved_name = self.resolve_group_name(group_id)
            if resolved_name:
                group_name = resolved_name
            elif group_name:
                self.group_name_cache[group_id] = group_name

        is_group = bool(group_id)
        if sent_msg:
            destination = sent_msg.get("destinationNumber") or sent_msg.get("destination")
            is_note_to_self = (destination == self.config.BOT_NUMBER) or (not destination)
        else:
            is_note_to_self = (sender == self.config.BOT_NUMBER)

        if not (is_group or is_note_to_self):
            logging.info(f"Ignored message from {mask_identifier(sender)} (not in a group and not Note to Self).")
            return None

        if is_group and self.config.AUTHORIZED_GROUP:
            matches_id = (group_id == self.config.AUTHORIZED_GROUP)
            matches_name = bool(group_name and group_name.strip().lower() == self.config.AUTHORIZED_GROUP.lower())
            if not (matches_id or matches_name):
                logging.warning(f"Blocked group message from unauthorized group: '{group_name}' (ID: {group_id}).")
                return None

        api_group_id = self.get_api_group_id(group_id or "")
        if is_group and not api_group_id.startswith("group."):
            api_group_id = f"group.{api_group_id}"

        reply_to = api_group_id if is_group else sender

        prefix_pattern = r"^(!book|!livre)\b"
        has_prefix = bool(re.match(prefix_pattern, text_content, re.IGNORECASE))
        image_att = next((att for att in attachments if "image" in att.get("contentType", "")), None)

        if not (has_prefix or image_att):
            return None

        photo_id = image_att.get("id") if image_att else None
        query = re.sub(prefix_pattern, "", text_content, flags=re.IGNORECASE).strip() if (text_content and has_prefix) else None

        return IncomingEvent(
            sender=sender,
            reply_to=reply_to,
            text_query=query,
            photo_id=photo_id,
            is_group=is_group,
            group_name=group_name
        )
