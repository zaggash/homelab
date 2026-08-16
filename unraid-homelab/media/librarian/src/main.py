#!/usr/bin/env python3
import os
import sys
import time
import re
import logging
from typing import Optional
from concurrent.futures import ThreadPoolExecutor

# Ensure src root is on sys.path for direct execution
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import Config
from clients.signal import SignalClient
from clients.gemini import GeminiClient
from clients.grimmory import GrimmoryClient
from core.pipeline import BookPipeline


def handle_incoming_request(
    signal_client: SignalClient,
    gemini_client: GeminiClient,
    pipeline: BookPipeline,
    reply_to: str,
    photo_bytes: Optional[bytes],
    text_query: Optional[str]
):
    """
    Executes OCR and book search/download in a background worker thread.
    """
    try:
        query = None
        if photo_bytes:
            ocr_text = gemini_client.extract_book_details_from_cover(photo_bytes)
            if ocr_text:
                query = ocr_text
                signal_client.send_message(f"🔍 Titre détecté : '{ocr_text}'. Recherche en cours...", reply_to)
            else:
                signal_client.send_message("⚠️ Désolé, je n'ai pas réussi à lire le titre sur la photo. Peux-tu m'écrire le titre et l'auteur par texte ?", reply_to)
                return
        elif text_query:
            query = text_query

        if query:
            epub_path, status_msg = pipeline.process_book_request(query)
            if epub_path:
                signal_client.send_message(f"📥 {status_msg}\nEnvoi du livre en cours...", reply_to)
                signal_client.send_message("✨ Voilà ton livre ! Bonne lecture 📖", reply_to, attachment_path=epub_path)
                logging.info(f"Process complete. Book sent to {reply_to} and saved in {Config.IMPORT_DIR}")
            else:
                signal_client.send_message(f"⚠️ {status_msg}", reply_to)
    except Exception as e:
        logging.error(f"Unhandled error in worker task: {e}")
        signal_client.send_message("⚠️ Une erreur inattendue est survenue lors du traitement de ta demande.", reply_to)


def run_bot():
    Config.validate()
    os.makedirs(Config.IMPORT_DIR, exist_ok=True)
    
    signal_client = SignalClient(Config)
    gemini_client = GeminiClient(Config)
    grimmory_client = GrimmoryClient(Config)
    pipeline = BookPipeline(Config, grimmory_client)
    
    task_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="librarian_worker")
    
    logging.info(f"Librarian Signal Bot is active (Model: {Config.GEMINI_MODEL}). Polling {Config.SIGNAL_URL} every {Config.POLL_INTERVAL}s...")
    
    while True:
        try:
            # Update heartbeat for container health checks
            try:
                with open(Config.HEARTBEAT_FILE, "w") as f:
                    f.write(str(int(time.time())))
            except Exception:
                pass

            messages = signal_client.receive_messages()
            if not messages:
                time.sleep(Config.POLL_INTERVAL)
                continue
                
            for msg_item in messages:
                envelope = msg_item.get("envelope", {})
                sender = envelope.get("sourceNumber")
                data_msg = envelope.get("dataMessage")
                
                sync_msg = envelope.get("syncMessage", {})
                sent_msg = sync_msg.get("sentMessage") if sync_msg else None
                if sent_msg and sender == Config.BOT_NUMBER:
                    data_msg = sent_msg
                
                if not sender or not data_msg:
                    continue
                    
                if sender not in Config.AUTHORIZED_NUMBERS and sender != Config.BOT_NUMBER:
                    logging.warning(f"Blocked unauthorized message from {sender}.")
                    continue
                    
                logging.info(f"Received message from authorized sender ({sender}).")
                
                attachments = data_msg.get("attachments", [])
                raw_message = data_msg.get("message")
                text_content = raw_message.strip() if raw_message else ""
                
                group_info = data_msg.get("groupInfo") or data_msg.get("groupV2Info") or {}
                group_id = group_info.get("groupId")
                group_name = group_info.get("name")
                if group_id:
                    resolved_name = signal_client.resolve_group_name(group_id)
                    if resolved_name:
                        group_name = resolved_name
                    elif group_name:
                        signal_client.group_name_cache[group_id] = group_name
                
                is_group = bool(group_id)
                if sent_msg:
                    destination = sent_msg.get("destinationNumber") or sent_msg.get("destination")
                    is_note_to_self = (destination == Config.BOT_NUMBER) or (not destination)
                else:
                    is_note_to_self = (sender == Config.BOT_NUMBER)
                
                if not (is_group or is_note_to_self):
                    logging.info(f"Ignored message from {sender} (not in a group and not Note to Self).")
                    continue
                
                if is_group and Config.AUTHORIZED_GROUP:
                    matches_id = (group_id == Config.AUTHORIZED_GROUP)
                    matches_name = (group_name and group_name.strip().lower() == Config.AUTHORIZED_GROUP.lower())
                    if not (matches_id or matches_name):
                        logging.warning(f"Blocked group message from unauthorized group: '{group_name}' (ID: {group_id}).")
                        continue
                
                api_group_id = signal_client.get_api_group_id(group_id)
                if is_group and not api_group_id.startswith("group."):
                    api_group_id = f"group.{api_group_id}"
                
                reply_to = api_group_id if is_group else sender
                
                prefix_pattern = r"^(!book|!livre)\b"
                has_prefix = bool(re.match(prefix_pattern, text_content, re.IGNORECASE))
                has_image_attachment = any("image" in att.get("contentType", "") for att in attachments)
                
                if not (has_prefix or has_image_attachment):
                    continue
                
                # Fast path: dispatch tasks to thread pool so receive loop never blocks
                if attachments and has_image_attachment:
                    photo = next(att for att in attachments if "image" in att.get("contentType", ""))
                    photo_id = photo.get("id")
                    signal_client.send_message("📸 J'ai bien reçu la photo de la couverture. Analyse de l'image en cours...", reply_to)
                    
                    image_bytes = signal_client.download_attachment(photo_id)
                    if image_bytes:
                        task_executor.submit(handle_incoming_request, signal_client, gemini_client, pipeline, reply_to, image_bytes, None)
                    else:
                        signal_client.send_message("⚠️ Erreur lors du téléchargement de la photo depuis l'API Signal.", reply_to)
                
                elif text_content and has_prefix:
                    query = re.sub(prefix_pattern, "", text_content, flags=re.IGNORECASE).strip()
                    signal_client.send_message(f"🔍 Recherche de '{query}' en cours...", reply_to)
                    task_executor.submit(handle_incoming_request, signal_client, gemini_client, pipeline, reply_to, None, query)
                        
        except Exception as e:
            logging.error(f"Error in bot loop: {e}")
            
        time.sleep(Config.POLL_INTERVAL)


if __name__ == "__main__":
    run_bot()
