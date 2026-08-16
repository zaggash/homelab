import re
import time
import json
import logging
import urllib.request
import urllib.error
from config import Config
from core.matching import calculate_title_similarity


class GrimmoryClient:
    def __init__(self, config=Config):
        self.config = config
        self._jwt_cache = None
        self._books_cache = {"data": None, "timestamp": 0}

    def get_jwt(self):
        if not self.config.GRIMMORY_URL or not self.config.GRIMMORY_USER:
            return None
            
        if self._jwt_cache:
            return self._jwt_cache
            
        # Case 1: Local Authentication (Username/Password)
        if self.config.GRIMMORY_USER and self.config.GRIMMORY_PASSWORD:
            logging.info(f"Authenticating with Grimmory Local Auth for user '{self.config.GRIMMORY_USER}'...")
            url = f"{self.config.GRIMMORY_URL}/api/v1/auth/login"
            payload = {
                "username": self.config.GRIMMORY_USER,
                "password": self.config.GRIMMORY_PASSWORD
            }
            headers = {"Content-Type": "application/json"}
            data_bytes = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(url, data=data_bytes, headers=headers, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=10) as response:
                    res_data = json.loads(response.read().decode("utf-8"))
                    self._jwt_cache = res_data.get("accessToken")
                    if self._jwt_cache:
                        logging.info("Grimmory local JWT acquired and cached successfully.")
                        return self._jwt_cache
            except Exception as e:
                logging.error(f"Failed to authenticate with Grimmory Local Auth: {e}")
            return None
            
        # Case 2: Remote Auth / SSO (Username only, no Password)
        if self.config.GRIMMORY_USER and not self.config.GRIMMORY_PASSWORD:
            logging.info(f"Authenticating dynamically with Grimmory Remote Auth for user '{self.config.GRIMMORY_USER}'...")
            url = f"{self.config.GRIMMORY_URL}/api/v1/auth/remote"
            headers = {
                "Remote-User": self.config.GRIMMORY_USER,
                "Remote-Name": self.config.GRIMMORY_USER,
                "Remote-Email": f"{self.config.GRIMMORY_USER}@local.internal"
            }
            if self.config.GRIMMORY_AUTH_HEADER and self.config.GRIMMORY_AUTH_HEADER != "Authorization":
                headers[self.config.GRIMMORY_AUTH_HEADER] = self.config.GRIMMORY_USER
                
            req = urllib.request.Request(url, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=10) as response:
                    res_data = json.loads(response.read().decode("utf-8"))
                    self._jwt_cache = res_data.get("accessToken")
                    if self._jwt_cache:
                        logging.info("Grimmory dynamic JWT acquired and cached successfully.")
                        return self._jwt_cache
            except Exception as e:
                logging.error(f"Failed to fetch dynamic JWT from Grimmory: {e}")
                
        return None

    def make_request(self, endpoint, retry_on_401=True):
        jwt = self.get_jwt()
        if not jwt:
            return None
            
        url = f"{self.config.GRIMMORY_URL}{endpoint}"
        headers = {
            "Authorization": f"Bearer {jwt}"
        }
        
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 401 and retry_on_401:
                logging.warning("Grimmory token expired (401). Clearing cache and retrying...")
                self._jwt_cache = None
                return self.make_request(endpoint, retry_on_401=False)
            logging.error(f"Grimmory API HTTP error on GET {endpoint}: {e}")
            return None
        except Exception as e:
            logging.error(f"Grimmory API error on GET {endpoint}: {e}")
            return None

    def is_book_already_present(self, query):
        """
        Checks if the book is already in Grimmory library or in the bookdrop queue.
        """
        if not self.config.GRIMMORY_URL or not self.config.GRIMMORY_USER:
            return False, None
            
        logging.info(f"Checking if '{query}' is already present in Grimmory (library or bookdrop)...")
        now = time.time()
        
        # 1. Check Library Books (GET /api/v1/books?size=1000)
        books = None
        if self._books_cache["data"] and (now - self._books_cache["timestamp"] < 60):
            books = self._books_cache["data"]
        else:
            raw_books = self.make_request("/api/v1/books?size=1000")
            if isinstance(raw_books, list):
                books = raw_books
            elif isinstance(raw_books, dict):
                books = raw_books.get("content", [])
            if books is not None:
                self._books_cache["data"] = books
                self._books_cache["timestamp"] = now

        if books and isinstance(books, list):
            for b in books:
                title = b.get("title")
                metadata = b.get("metadata") or {}
                meta_title = metadata.get("title")
                authors = metadata.get("authors") or []
                
                targets = []
                for t in [title, meta_title]:
                    if t:
                        targets.append(t)
                        for author in authors:
                            if author:
                                targets.append(f"{author} - {t}")
                                targets.append(f"{t} - {author}")
                
                for t in targets:
                    similarity = calculate_title_similarity(query, t)
                    if similarity >= 0.70:
                        return True, f"Déjà présent dans la bibliothèque : '{t}'"
                            
        # 2. Check Bookdrop Queue (GET /api/v1/bookdrop/files?size=1000)
        bookdrop_data = self.make_request("/api/v1/bookdrop/files?size=1000")
        if bookdrop_data and isinstance(bookdrop_data, dict):
            files = bookdrop_data.get("content", [])
            if isinstance(files, list):
                for f in files:
                    file_name = f.get("fileName")
                    original_metadata = f.get("originalMetadata") or {}
                    fetched_metadata = f.get("fetchedMetadata") or {}
                    
                    meta_title_orig = original_metadata.get("title")
                    meta_title_fetch = fetched_metadata.get("title")
                    
                    authors_orig = original_metadata.get("authors") or []
                    authors_fetch = fetched_metadata.get("authors") or []
                    
                    file_name_clean = re.sub(r'\.[a-zA-Z0-9]+$', '', file_name) if file_name else ""
                    
                    titles = [t for t in [file_name_clean, meta_title_orig, meta_title_fetch] if t]
                    authors = []
                    for a_list in [authors_orig, authors_fetch]:
                        for a in a_list:
                            if a and a not in authors:
                                authors.append(a)
                                
                    targets = []
                    for t in titles:
                        targets.append(t)
                        for author in authors:
                            if author:
                                targets.append(f"{author} - {t}")
                                targets.append(f"{t} - {author}")
                                
                    for t in targets:
                        similarity = calculate_title_similarity(query, t)
                        if similarity >= 0.70:
                            return True, f"Déjà dans la file d'attente bookdrop : '{t}'"
                                
        return False, None
