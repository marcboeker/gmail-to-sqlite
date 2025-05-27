"""Tests for database functionality."""

import pytest
from gmail_to_sqlite.db import init, Message


class TestDatabase:
    """Test database operations."""

    def test_initialize_database(self, temp_dir):
        """Test database initialization."""
        db_path = str(temp_dir)
        db = init(db_path)
        assert db is not None

    def test_message_model(self):
        """Test Message model creation."""
        # Test that the model exists and has required fields
        assert Message is not None
        assert hasattr(Message, "message_id")
        assert hasattr(Message, "subject")
        assert hasattr(Message, "thread_id")
        assert hasattr(Message, "sender")
        assert hasattr(Message, "recipients")
