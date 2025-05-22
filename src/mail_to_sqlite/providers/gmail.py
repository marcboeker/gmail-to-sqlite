from typing import Dict, List, Optional
from datetime import datetime

from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

from .base import EmailProvider
from ..message import Message
from .. import auth

class GmailProvider(EmailProvider):
    """Gmail implementation of the EmailProvider interface."""
    
    def __init__(self):
        self.service = None
        self.credentials = None
    
    def authenticate(self, data_dir: str):
        """Authenticate with Gmail."""
        self.credentials = auth.get_gmail_credentials(data_dir)
        self.service = build("gmail", "v1", credentials=self.credentials)
    
    def get_labels(self) -> Dict[str, str]:
        """Get all labels from Gmail."""
        labels = {}
        for label in self.service.users().labels().list(userId="me").execute()["labels"]:
            labels[label["id"]] = label["name"]
        return labels
    
    def get_message(self, message_id: str) -> Message:
        """Get a single message by ID."""
        labels = self.get_labels()
        raw_msg = self.service.users().messages().get(userId="me", id=message_id).execute()
        return Message.from_raw(raw_msg, labels, provider="gmail")
    
    def list_messages(self, 
                     query: Optional[List[str]] = None, 
                     page_token: Optional[str] = None,
                     max_results: int = 500) -> Dict:
        """List messages, optionally filtered by query."""
        if query is None:
            query = []
            
        results = (
            self.service.users()
            .messages()
            .list(
                userId="me",
                maxResults=max_results,
                pageToken=page_token,
                q=" | ".join(query),
            )
            .execute()
        )
        return results
    
    def build_query(self, after: Optional[datetime] = None, 
                   before: Optional[datetime] = None) -> List[str]:
        """Build a Gmail query based on datetime filters."""
        query = []
        if after:
            query.append(f"after:{int(after.timestamp())}")
        if before:
            query.append(f"before:{int(before.timestamp())}")
        return query