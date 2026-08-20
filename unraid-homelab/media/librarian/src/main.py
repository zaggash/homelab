#!/usr/bin/env python3
import os
import sys
import time
import logging
from concurrent.futures import ThreadPoolExecutor

# Ensure src root is on sys.path for direct execution
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import Config
from core.models import IncomingEvent
from clients.signal import SignalClient
from clients.gemini import GeminiClient
from clients.grimmory import GrimmoryClient
from core.pipeline import BookPipeline


def handle_event(
    event: IncomingEvent,
    signal_client: SignalClient,
    gemini_client: GeminiClient,
    pipeline: BookPipeline
):
    """
    Worker task handling OCR and book retrieval in background threads.
    """
    try:
        query = event.text_query

        if event.photo_id:
            signal_client.send_message("📸 J'ai bien reçu la photo de la couverture. Analyse de l'image en cours...", event.reply_to)
            photo_bytes = signal_client.download_attachment(event.photo_id)
            if not photo_bytes:
                signal_client.send_message("⚠️ Erreur lors du téléchargement de la photo depuis l'API Signal.", event.reply_to)
                return

            ocr_text = gemini_client.extract_book_details_from_cover(photo_bytes)
            if ocr_text:
                query = ocr_text
                signal_client.send_message(f"🔍 Titre détecté : '{ocr_text}'. Recherche en cours...", event.reply_to)
            else:
                signal_client.send_message("⚠️ Désolé, je n'ai pas réussi à lire le titre sur la photo. Peux-tu m'écrire le titre et l'auteur par texte ?", event.reply_to)
                return

        if query:
            if not event.photo_id:
                signal_client.send_message(f"🔍 Recherche de '{query}' en cours...", event.reply_to)

            epub_path, status_msg = pipeline.process_book_request(query)
            if epub_path:
                signal_client.send_message(f"📥 {status_msg}\nEnvoi du livre en cours...", event.reply_to)
                signal_client.send_message("✨ Voilà ton livre ! Bonne lecture 📖", event.reply_to, attachment_path=epub_path)
                logging.info(f"Process complete. Book sent to {event.reply_to} and saved in {Config.IMPORT_DIR}")
            else:
                signal_client.send_message(f"⚠️ {status_msg}", event.reply_to)

    except Exception as e:
        logging.error(f"Unhandled error in worker task: {e}")
        signal_client.send_message("⚠️ Une erreur inattendue est survenue lors du traitement de ta demande.", event.reply_to)


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
            # Touch heartbeat for container health checking
            try:
                with open(Config.HEARTBEAT_FILE, "w") as f:
                    f.write(str(int(time.time())))
            except Exception:
                pass

            messages = signal_client.receive_messages()
            if messages:
                for msg_item in messages:
                    event = signal_client.parse_message_item(msg_item)
                    if event:
                        task_executor.submit(handle_event, event, signal_client, gemini_client, pipeline)

        except Exception as e:
            logging.error(f"Error in bot polling loop: {e}")

        time.sleep(Config.POLL_INTERVAL)


if __name__ == "__main__":
    run_bot()
