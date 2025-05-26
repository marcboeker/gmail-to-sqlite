"""
Constants and configuration values for the Gmail to SQLite application.
"""

from typing import List

# API Configuration
GMAIL_API_VERSION: str = "v1"
GMAIL_SCOPES: List[str] = ["https://www.googleapis.com/auth/gmail.readonly"]
OAUTH2_CREDENTIALS_FILE: str = "credentials.json"
TOKEN_FILE_NAME: str = "token.json"
DATABASE_FILE_NAME: str = "messages.db"

# Sync Configuration
MAX_RESULTS_PER_PAGE: int = 500
DEFAULT_WORKERS: int = 4
MAX_RETRY_ATTEMPTS: int = 3
RETRY_DELAY_SECONDS: int = 5

# MIME Types for email body extraction
SUPPORTED_MIME_TYPES: List[str] = [
    "text/html",
    "text/plain",
    "multipart/related",
    "multipart/alternative",
]

# Logging Configuration
LOG_FORMAT: str = "%(asctime)s - %(levelname)s: %(message)s"
PROGRESS_LOG_INTERVAL: int = 50
COLLECTION_LOG_INTERVAL: int = 100
