"""Tests for database migrations functionality."""

import pytest
import tempfile
import os
from gmail_to_sqlite.db import database_proxy, SchemaVersion, Message
from gmail_to_sqlite.migrations import (
    get_schema_version,
    set_schema_version,
    run_migrations,
    column_exists,
)
from gmail_to_sqlite.schema_migrations.v1_add_is_deleted_column import (
    run as migration_v1_run,
)
from peewee import SqliteDatabase


class TestMigrations:
    """Test migration operations."""

    def setup_method(self):
        """Set up test database for each test."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test.db")
        self.db = SqliteDatabase(self.db_path)
        database_proxy.initialize(self.db)

    def teardown_method(self):
        """Clean up after each test."""
        if hasattr(self, "db") and self.db:
            self.db.close()

    def test_schema_version_functions(self):
        """Test schema version tracking functions."""
        # Create schema version table
        self.db.create_tables([SchemaVersion])

        # Test initial version (should be 0)
        version = get_schema_version()
        assert version == 0

        # Test setting version
        success = set_schema_version(5)
        assert success is True

        # Test getting version again
        version = get_schema_version()
        assert version == 5

    def test_run_migrations_from_scratch(self):
        """Test running migrations from a fresh database."""
        # Also need to create Message table for the migration to work
        self.db.create_tables([Message])

        # Run migrations
        success = run_migrations()
        assert success is True

        # Check that schema version is set to 1
        version = get_schema_version()
        assert version == 1

        # Check that is_deleted column was added
        assert column_exists("messages", "is_deleted") is True

    def test_run_migrations_already_up_to_date(self):
        """Test running migrations when database is already up to date."""
        # Create tables and set version to 1
        self.db.create_tables([SchemaVersion, Message])
        set_schema_version(1)

        # Run migrations
        success = run_migrations()
        assert success is True

        # Version should still be 1
        version = get_schema_version()
        assert version == 1

    def test_migration_v1_add_is_deleted_column(self):
        """Test migration v1 directly."""
        # Create Message table
        self.db.create_tables([Message])

        # Run the migration
        success = migration_v1_run()
        assert success is True

        # Check that is_deleted column was added
        assert column_exists("messages", "is_deleted") is True

        # Running again should still succeed (idempotent)
        success = migration_v1_run()
        assert success is True
