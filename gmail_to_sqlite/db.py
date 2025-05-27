import logging
from datetime import datetime
from typing import Any, List, Optional

from peewee import (
    BooleanField,
    DateTimeField,
    IntegerField,
    Model,
    Proxy,
    TextField,
    SQL,
)
from playhouse.sqlite_ext import JSONField, SqliteDatabase

from .constants import DATABASE_FILE_NAME

database_proxy = Proxy()


class DatabaseError(Exception):
    """Custom exception for database-related errors."""

    pass


class SchemaVersion(Model):
    """
    Represents the database schema version.

    Attributes:
        version (IntegerField): The current schema version number.

    Meta:
        database (Database): The database connection to use.
        db_table (str): The name of the database table for storing schema version.
    """

    version = IntegerField()

    class Meta:
        database = database_proxy
        db_table = "schema_version"


class Message(Model):
    """
    Represents an email message.

    Attributes:
        message_id (TextField): The unique identifier of the message.
        thread_id (TextField): The unique identifier of the thread.
        sender (JSONField): The sender of the message.
        recipients (JSONField): The recipients of the message.
        labels (JSONField): The labels of the message.
        subject (TextField): The subject of the message.
        body (TextField): The last messages sent or received without all other replies to the thread.
        size (IntegerField): The size of the message.
        timestamp (DateTimeField): The timestamp of the message.
        is_read (BooleanField): Indicates whether the message has been read.
        is_outgoing BooleanField(): Indicates whether the message was sent by the user.
        is_deleted (BooleanField): Indicates whether the message has been deleted from Gmail.
        last_indexed (DateTimeField): The timestamp when the message was last indexed.

    Meta:
        database (Database): The database connection to use.
        db_table (str): The name of the database table for storing messages.
    """

    message_id = TextField(unique=True)
    thread_id = TextField()
    sender = JSONField()
    recipients = JSONField()
    labels = JSONField()
    subject = TextField(null=True)
    body = TextField(null=True)
    size = IntegerField()
    timestamp = DateTimeField()
    is_read = BooleanField()
    is_outgoing = BooleanField()
    is_deleted = BooleanField(default=False)
    last_indexed = DateTimeField()

    class Meta:
        database = database_proxy
        db_table = "messages"


def init(data_dir: str, enable_logging: bool = False) -> SqliteDatabase:
    """
    Initialize the database for the given data_dir.

    Args:
        data_dir (str): The path where to store the data.
        enable_logging (bool, optional): Whether to enable logging. Defaults to False.

    Returns:
        SqliteDatabase: The initialized database object.

    Raises:
        DatabaseError: If database initialization fails.
    """
    try:
        db_path = f"{data_dir}/{DATABASE_FILE_NAME}"
        db = SqliteDatabase(db_path)
        database_proxy.initialize(db)
        db.create_tables([Message, SchemaVersion])

        if enable_logging:
            logger = logging.getLogger("peewee")
            logger.setLevel(logging.DEBUG)
            logger.addHandler(logging.StreamHandler())

        from .migrations import run_migrations

        if not run_migrations():
            raise DatabaseError("Failed to run database migrations")

        return db
    except Exception as e:
        raise DatabaseError(f"Failed to initialize database: {e}")


def create_message(msg: Any) -> None:
    """
    Saves a message to the database with conflict resolution.

    Args:
        msg: The message object to save (from message.Message class).

    Raises:
        DatabaseError: If the message cannot be saved to the database.
    """
    try:
        last_indexed = datetime.now()
        Message.insert(
            message_id=msg.id,
            thread_id=msg.thread_id,
            sender=msg.sender,
            recipients=msg.recipients,
            labels=msg.labels,
            subject=msg.subject,
            body=msg.body,
            size=msg.size,
            timestamp=msg.timestamp,
            is_read=msg.is_read,
            is_outgoing=msg.is_outgoing,
            is_deleted=False,
            last_indexed=last_indexed,
        ).on_conflict(
            conflict_target=[Message.message_id],
            update={
                Message.is_read: msg.is_read,
                Message.last_indexed: last_indexed,
                Message.labels: msg.labels,
                Message.is_deleted: False,
            },
        ).execute()
    except Exception as e:
        raise DatabaseError(f"Failed to save message {msg.id}: {e}")


def last_indexed() -> Optional[datetime]:
    """
    Returns the timestamp of the last indexed message.

    Returns:
        Optional[datetime]: The timestamp of the last indexed message, or None if no messages exist.
    """

    msg = Message.select().order_by(Message.timestamp.desc()).first()
    if msg:
        timestamp: Optional[datetime] = msg.timestamp
        return timestamp
    else:
        return None


def first_indexed() -> Optional[datetime]:
    """
    Returns the timestamp of the first indexed message.

    Returns:
        Optional[datetime]: The timestamp of the first indexed message, or None if no messages exist.
    """

    msg = Message.select().order_by(Message.timestamp.asc()).first()
    if msg:
        timestamp: Optional[datetime] = msg.timestamp
        return timestamp
    else:
        return None


def mark_messages_as_deleted(message_ids: List[str]) -> None:
    """
    Mark messages as deleted in the database.

    Args:
        message_ids (List[str]): List of message IDs to mark as deleted.

    Raises:
        DatabaseError: If the operation fails.
    """
    if not message_ids:
        return

    try:
        if not message_ids:
            return

        # Use the SQL IN clause with proper parameter binding
        batch_size = 100
        for i in range(0, len(message_ids), batch_size):
            batch = message_ids[i : i + batch_size]
            placeholders = ",".join(["?" for _ in batch])
            query = Message.update(is_deleted=True, last_indexed=datetime.now())
            query = query.where(SQL(f"message_id IN ({placeholders})", batch))
            query.execute()
    except Exception as e:
        raise DatabaseError(f"Failed to mark messages as deleted: {e}")


def get_all_message_ids() -> List[str]:
    """
    Returns all message IDs stored in the database.

    Returns:
        List[str]: List of message IDs.

    Raises:
        DatabaseError: If the query fails.
    """
    try:
        return [message.message_id for message in Message.select(Message.message_id)]
    except Exception as e:
        raise DatabaseError(f"Failed to retrieve message IDs: {e}")


def get_deleted_message_ids() -> List[str]:
    """
    Returns all message IDs that are already marked as deleted.

    Returns:
        List[str]: List of deleted message IDs.

    Raises:
        DatabaseError: If the query fails.
    """
    try:
        return [
            message.message_id
            for message in Message.select(Message.message_id).where(
                Message.is_deleted == True
            )
        ]
    except Exception as e:
        raise DatabaseError(f"Failed to retrieve deleted message IDs: {e}")
