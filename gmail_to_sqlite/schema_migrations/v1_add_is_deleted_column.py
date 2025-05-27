"""
Migration v1: Add is_deleted column to messages table.

This migration adds a BooleanField with default value False to track
whether messages have been deleted from Gmail.
"""

import logging
from peewee import BooleanField
from playhouse.migrate import SqliteMigrator, migrate

from ..db import database_proxy
from ..migrations import column_exists


logger = logging.getLogger(__name__)


def run() -> bool:
    """
    Add the is_deleted column to the messages table if it doesn't exist.

    This migration adds a BooleanField with default value False to track
    whether messages have been deleted from Gmail.

    Returns:
        bool: True if the migration was successful or column already exists,
              False if the migration failed.
    """
    table_name = "messages"
    column_name = "is_deleted"

    try:
        if column_exists(table_name, column_name):
            logger.info(f"Column {column_name} already exists in {table_name} table")
            return True

        logger.info(f"Adding {column_name} column to {table_name} table")

        migrator = SqliteMigrator(database_proxy.obj)
        is_deleted_field = BooleanField(default=False)

        migrate(migrator.add_column(table_name, column_name, is_deleted_field))
        database_proxy.obj.execute_sql(
            f"UPDATE {table_name} SET {column_name} = ? WHERE {column_name} IS NULL",
            (False,),
        )

        logger.info(f"Successfully added {column_name} column to {table_name} table")
        return True

    except Exception as e:
        logger.error(f"Failed to add {column_name} column: {e}")
        return False
