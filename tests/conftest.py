"""Test configuration and fixtures."""

import pytest
import tempfile
import os
from pathlib import Path


@pytest.fixture
def temp_dir():
    """Create a temporary directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def mock_credentials_file(temp_dir):
    """Create a mock credentials file for testing."""
    creds_file = temp_dir / "credentials.json"
    creds_file.write_text('{"test": "credentials"}')
    return creds_file
