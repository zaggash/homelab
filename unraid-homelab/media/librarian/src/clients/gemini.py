import re
import json
import base64
import logging
from typing import Optional
from config import Config
from core.http import json_request


class GeminiClient:
    def __init__(self, config=Config):
        self.config = config

    def extract_book_details_from_cover(self, image_bytes: bytes) -> Optional[str]:
        """
        Sends cover photo to Gemini to extract Title and Author using Structured JSON.
        Uses x-goog-api-key header authentication.
        """
        if not self.config.GEMINI_API_KEY:
            logging.error("GEMINI_API_KEY is not configured!")
            return None

        logging.info(f"Sending cover photo to Gemini ({self.config.GEMINI_MODEL}) for structured OCR analysis...")
        image_b64 = base64.b64encode(image_bytes).decode("utf-8")

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.config.GEMINI_MODEL}:generateContent"
        headers = {
            "x-goog-api-key": self.config.GEMINI_API_KEY
        }

        prompt_text = (
            "Tu es un bibliothécaire expert. Analyse avec précision la couverture de ce livre "
            "pour identifier l'auteur principal et le titre exact. Remplis le schéma JSON fourni."
        )

        payload = {
            "contents": [{
                "parts": [
                    {
                        "inlineData": {
                            "mimeType": "image/jpeg",
                            "data": image_b64
                        }
                    },
                    {
                        "text": prompt_text
                    }
                ]
            }],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseSchema": {
                    "type": "OBJECT",
                    "properties": {
                        "author": {"type": "STRING"},
                        "title": {"type": "STRING"}
                    },
                    "required": ["title"]
                }
            }
        }

        res, _ = json_request(url, method="POST", payload=payload, headers=headers, timeout=30)
        try:
            if res and isinstance(res, dict):
                raw_text = res["candidates"][0]["content"]["parts"][0]["text"].strip()
                parsed = json.loads(raw_text)
                author = parsed.get("author", "").strip()
                title = parsed.get("title", "").strip()

                result = f"{author} - {title}" if author and title else (title or author)
                logging.info(f"Gemini Structured OCR result: '{result}' (Author: '{author}', Title: '{title}')")
                return result
        except Exception as e:
            logging.error(f"Gemini structured response parsing failed: {e}")

        # Fallback to plain prompt if structured output isn't supported on custom model endpoint
        try:
            logging.info("Attempting fallback non-schema prompt to Gemini...")
            fallback_payload = {
                "contents": [{
                    "parts": [
                        {
                            "inlineData": {
                                "mimeType": "image/jpeg",
                                "data": image_b64
                            }
                        },
                        {
                            "text": "Analyse la couverture de ce livre et renvoie UNIQUEMENT 'Auteur - Titre' sans markdown."
                        }
                    ]
                }]
            }
            res_fb, _ = json_request(url, method="POST", payload=fallback_payload, headers=headers, timeout=30)
            if res_fb and isinstance(res_fb, dict):
                text = res_fb["candidates"][0]["content"]["parts"][0]["text"].strip()
                text = re.sub(r'[*`"]', '', text).strip()
                logging.info(f"Gemini fallback OCR result: '{text}'")
                return text
        except Exception as fb_err:
            logging.error(f"Gemini fallback OCR failed: {fb_err}")

        return None
