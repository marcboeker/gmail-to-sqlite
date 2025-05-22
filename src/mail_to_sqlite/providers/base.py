from abc import ABC, abstractmethod
from typing import Dict, List, Optional
from datetime import datetime

from ..message import Message

class EmailProvider(ABC):
    """Abstract base class for email providers."""
    
    @abstractmethod
    def authenticate(self, data_dir: str):
        """Authenticate with the email provider."""
        pass
    
    @abstractmethod
    def get_labels(self) -> Dict[str, str]:
        """Get all labels/folders from the email provider."""
        pass
    
    @abstractmethod
    def get_message(self, message_id: str) -> Message:
        """Get a single message by ID."""
        pass
    
    @abstractmethod
    def list_messages(self, 
                      query: Optional[List[str]] = None, 
                      page_token: Optional[str] = None,
                      max_results: int = 500) -> Dict:
        """List messages, optionally filtered by query."""
        pass
    
    @abstractmethod
    def build_query(self, after: Optional[datetime] = None, 
                   before: Optional[datetime] = None) -> List[str]:
        """Build a query for the provider based on datetime filters."""
        pass