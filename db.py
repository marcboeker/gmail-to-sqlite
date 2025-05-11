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
        last_indexed (DateTimeField): The timestamp when the message was last indexed.
        is_deleted (BooleanField): Indicates whether the message has been deleted.

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
    timestamp = DateTimeField(null=True)
    is_read = BooleanField()
    is_outgoing = BooleanField()
    last_indexed = DateTimeField()
    is_deleted = BooleanField(default=False)

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


def create_message(msg: Message):
    """
    Saves a message to the database.

    Args:
        msg (Message): The message to save.
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
        last_indexed=last_indexed,
        is_deleted=False,
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


def create_messages_batch(msg_objects: list):
    """
    Saves a batch of messages to the database using insert_many for performance.

    Args:
        msg_objects (list): A list of message.Message objects (from message.py).
    """
    if not msg_objects:
        return

    now = datetime.now()
    batch_data = []
    for msg in msg_objects:
        batch_data.append({
            Message.message_id: msg.id,
            Message.thread_id: msg.thread_id,
            Message.sender: msg.sender,
            Message.recipients: msg.recipients,
            Message.labels: msg.labels,
            Message.subject: msg.subject,
            Message.body: msg.body,
            Message.size: msg.size,
            Message.timestamp: msg.timestamp,
            Message.is_read: msg.is_read,
            Message.is_outgoing: msg.is_outgoing,
            Message.last_indexed: now, # Use a consistent timestamp for the batch
            Message.is_deleted: False,
        })

    # EXCLUDED refers to the values from the row that was proposed for insertion.
    # If a field is not in the update clause, its existing value is preserved for conflicting rows.
    Message.insert_many(batch_data).on_conflict(
        conflict_target=[Message.message_id],
        update={
            Message.is_read: EXCLUDED.is_read,
            Message.labels: EXCLUDED.labels,
            Message.last_indexed: EXCLUDED.last_indexed, # This will take 'now' from EXCLUDED
            Message.is_deleted: EXCLUDED.is_deleted, # This will take 'False' from EXCLUDED
        }
    ).execute()


def get_active_message_ids() -> set:
    """
    Returns a set of message_id's for all messages not marked as deleted.

    Returns:
        set: A set of message_id strings.
    """
    query = Message.select(Message.message_id).where(Message.is_deleted == False)
    return {m.message_id for m in query}


def mark_messages_as_deleted(message_ids: list):
    """
    Marks a list of messages as deleted in the database.

    Args:
        message_ids (list): A list of message_id strings to mark as deleted.
    """
    if not message_ids:
        return
    Message.update(is_deleted=True).where(Message.message_id.in_(message_ids)).execute()


def last_indexed() -> datetime:
    """
    Returns the timestamp of the last indexed message.

    Returns:
        datetime: The timestamp of the last indexed message.
    """

    msg = Message.select().where(Message.timestamp.is_null(False)).order_by(Message.timestamp.desc()).first()
    if msg:
        return datetime.fromisoformat(msg.timestamp)
    else:
        return None


def first_indexed() -> datetime:
    """
    Returns the timestamp of the first indexed message.

    Returns:
        datetime: The timestamp of the first indexed message.
    """

    msg = Message.select().where(Message.timestamp.is_null(False)).order_by(Message.timestamp.asc()).first()
    if msg:
        return datetime.fromisoformat(msg.timestamp)
    else:
        return None
