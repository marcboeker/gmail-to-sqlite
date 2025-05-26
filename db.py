import logging
from datetime import datetime

from peewee import *
from playhouse.sqlite_ext import *

database_proxy = Proxy()


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


def init(data_dir: str, enable_logging=False) -> SqliteDatabase:
    """
    Initialize the database for the given data_dir. The database is stored in <data_dir>/messages.db.

    Args:
        data_dir (str): The path where to store the data.
        enable_logging (bool, optional): Whether to enable logging. Defaults to False.

    Returns:
        SqliteDatabase: The initialized database object.
    """
    db = SqliteDatabase(f"{data_dir}/messages.db")
    database_proxy.initialize(db)
    db.create_tables([Message])

    if enable_logging:
        logger = logging.getLogger("peewee")
        logger.setLevel(logging.DEBUG)
        logger.addHandler(logging.StreamHandler())

    return db


def create_message(msg):
    """
    Saves a message to the database.

    Args:
        msg: The message object to save (from message.Message class).
    """

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
        preserve=[
            Message.thread_id,
            Message.sender,
            Message.recipients,
            Message.subject,
            Message.body,
            Message.size,
            Message.timestamp,
            Message.is_outgoing,
        ],
        update={
            Message.is_read: msg.is_read,
            Message.last_indexed: last_indexed,
            Message.labels: msg.labels,
            Message.is_deleted: False,
        },
    ).execute()


def last_indexed() -> datetime:
    """
    Returns the timestamp of the last indexed message.

    Returns:
        datetime: The timestamp of the last indexed message.
    """

    msg = Message.select().order_by(Message.timestamp.desc()).first()
    if msg:
        return msg.timestamp
    else:
        return None


def first_indexed() -> datetime:
    """
    Returns the timestamp of the first indexed message.

    Returns:
        datetime: The timestamp of the first indexed message.
    """

    msg = Message.select().order_by(Message.timestamp.asc()).first()
    if msg:
        return msg.timestamp
    else:
        return None


def mark_messages_as_deleted(message_ids: list):
    """
    Mark messages as deleted in the database.

    Args:
        message_ids (list): List of message IDs to mark as deleted.
    """
    if not message_ids:
        return

    Message.update(is_deleted=True, last_indexed=datetime.now()).where(
        Message.message_id.in_(message_ids)
    ).execute()


def get_all_message_ids() -> list:
    """
    Returns all message IDs stored in the database.

    Returns:
        list: List of message IDs.
    """
    return [message.message_id for message in Message.select(Message.message_id)]


def get_deleted_message_ids() -> list:
    """
    Returns all message IDs that are already marked as deleted.

    Returns:
        list: List of deleted message IDs.
    """
    return [
        message.message_id
        for message in Message.select(Message.message_id).where(
            Message.is_deleted == True
        )
    ]
