import imaplib
import email
from email.utils import parsedate_to_datetime
from typing import Dict, List, Optional
from datetime import datetime
import re

from .base import EmailProvider
from ..message import Message

class IMAPProvider(EmailProvider):
    """IMAP implementation of the EmailProvider interface."""
    
    def __init__(self):
        self.conn = None
        self.username = None
        
    def authenticate(self, data_dir: str):
        """Authenticate with IMAP server."""
        from .. import auth
        credentials = auth.get_imap_credentials(data_dir)
        
        self.username = credentials['username']
        self.conn = imaplib.IMAP4_SSL(credentials['server'])
        self.conn.login(credentials['username'], credentials['password'])
    
    def get_labels(self) -> Dict[str, str]:
        """Get all folders from IMAP server."""
        labels = {}
        typ, data = self.conn.list()
        if typ == 'OK':
            for folder in data:
                folder_str = folder.decode('utf-8')
                match = re.search(r'"([^"]+)"$|([^ ]+)$', folder_str)
                if match:
                    folder_name = match.group(1) or match.group(2)
                    labels[folder_name] = folder_name
        return labels
    
    def _parse_imap_message(self, raw_msg, labels) -> Message:
        """Parse an IMAP message into our Message format."""
        msg_obj = Message()
        
        # Parse email using the built-in email module
        email_message = email.message_from_bytes(raw_msg)
        
        # Extract headers
        msg_obj.id = email_message.get('Message-ID', '')
        if not msg_obj.id:
            # Create a synthetic ID if none exists
            msg_obj.id = f"imap-{hash(email_message.get('Date', '') + email_message.get('From', ''))}"
        
        msg_obj.thread_id = None
        
        # Parse From
        from_header = email_message.get('From', '')
        from_name, from_email = email.utils.parseaddr(from_header)
        msg_obj.sender = {"name": from_name, "email": from_email}
        
        # Parse To, CC, BCC
        msg_obj.recipients = {}
        if 'To' in email_message:
            msg_obj.recipients['to'] = msg_obj.parse_addresses(email_message['To'])
        if 'Cc' in email_message:
            msg_obj.recipients['cc'] = msg_obj.parse_addresses(email_message['Cc'])
        if 'Bcc' in email_message:
            msg_obj.recipients['bcc'] = msg_obj.parse_addresses(email_message['Bcc'])
        
        # Subject
        msg_obj.subject = email_message.get('Subject', '')
        
        # Date
        date_str = email_message.get('Date')
        if date_str:
            try:
                msg_obj.timestamp = parsedate_to_datetime(date_str)
            except:
                msg_obj.timestamp = datetime.now()
        
        # Body
        msg_obj.body = ""
        if email_message.is_multipart():
            for part in email_message.walk():
                if part.get_content_type() == "text/plain":
                    msg_obj.body = part.get_payload(decode=True).decode('utf-8', errors='replace')
                    break
                elif part.get_content_type() == "text/html" and not msg_obj.body:
                    html = part.get_payload(decode=True).decode('utf-8', errors='replace')
                    msg_obj.body = msg_obj.html2text(html)
        else:
            payload = email_message.get_payload(decode=True)
            if payload:
                msg_obj.body = payload.decode('utf-8', errors='replace')
        
        # Size
        msg_obj.size = len(raw_msg)
        
        # Labels - use the current folder name
        msg_obj.labels = list(labels.values())
        
        # Read status and outgoing
        msg_obj.is_read = True  # Default to true unless we can determine otherwise
        msg_obj.is_outgoing = from_email == self.username
        
        return msg_obj
    
    def get_message(self, message_id: str) -> Message:
        """Get a single message by ID from IMAP."""
        # In IMAP we need to search for message_id
        labels = self.get_labels()
        
        for folder_name in labels.keys():
            self.conn.select('"' + folder_name + '"')
            # Search for the message by Message-ID header
            typ, data = self.conn.search(None, f'HEADER Message-ID "{message_id}"')
            if typ == 'OK' and data[0]:
                # Get the first matching message
                msg_nums = data[0].split()
                if msg_nums:
                    typ, msg_data = self.conn.fetch(msg_nums[0], '(RFC822)')
                    if typ == 'OK':
                        raw_msg = msg_data[0][1]
                        return self._parse_imap_message(raw_msg, {folder_name: folder_name})
        
        raise ValueError(f"Message with ID {message_id} not found")
    
    def list_messages(self, 
                     query: Optional[List[str]] = None, 
                     page_token: Optional[str] = None,
                     max_results: int = 500) -> Dict:
        """List messages, optionally filtered by query."""
        if query is None:
            query = ["ALL"]
        
        # page_token in IMAP is just the starting message number
        start_idx = 1
        if page_token:
            start_idx = int(page_token)
        
        result = {"messages": [], "nextPageToken": None}
        
        # We need to search each folder
        labels = self.get_labels()
        for folder_name in labels.keys():
            self.conn.select('"' + folder_name + '"')
            
            # Combine query conditions for IMAP
            search_criteria = " OR ".join(query)
            search_criteria = "OR " + search_criteria + " NOT ALL"
            typ, data = self.conn.search(None, search_criteria)
            
            if typ == 'OK':
                message_nums = data[0].split()
                # Apply pagination
                end_idx = min(start_idx + max_results, len(message_nums))
                batch = message_nums[start_idx-1:end_idx]
                
                # Check if there are more messages
                if end_idx < len(message_nums):
                    result["nextPageToken"] = str(end_idx + 1)
                
                for num in batch:
                    # Just get the headers and UID for listing
                    typ, msg_data = self.conn.fetch(num, '(UID BODY.PEEK[HEADER])')
                    if typ == 'OK':
                        msg_id = None
                        for response_part in msg_data:
                            if isinstance(response_part, tuple):
                                msg_id_match = re.search(r'Message-ID: (\S+)', response_part[1].decode('utf-8'), re.IGNORECASE)
                                if msg_id_match:
                                    msg_id = msg_id_match.group(1)
                                else:
                                    print(response_part[1].decode('utf-8'))
                        
                        if msg_id:
                            result["messages"].append({"id": msg_id})
        
        return result
    
    # XXX: IMAP search granularity is one-day, so we can't do any better for
    # getting non-indexed email without a lot of complication.
    def build_query(self, after: Optional[datetime] = None, 
                   before: Optional[datetime] = None) -> List[str]:
        """Build an IMAP query based on datetime filters."""
        query = []
        if after:
            # Format date for IMAP: DD-MMM-YYYY
            date_str = after.strftime("%d-%b-%Y")
            query.append(f'SINCE "{date_str}"')
        if before:
            date_str = before.strftime("%d-%b-%Y")
            query.append(f'BEFORE "{date_str}"')
        
        if not query:
            query = ["ALL"]
            
        return query
