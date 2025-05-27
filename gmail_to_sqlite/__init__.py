"""Gmail to SQLite package.

A robust Python application that syncs Gmail messages to a local SQLite database
for analysis and archival purposes.
"""

__version__ = "0.2.0"

from .auth import get_credentials
from .db import init, Message, create_message, get_all_message_ids
from .sync import all_messages, single_message, get_labels

__all__ = [
    "get_credentials",
    "init",
    "Message",
    "create_message",
    "get_all_message_ids",
    "all_messages",
    "single_message",
    "get_labels",
]
