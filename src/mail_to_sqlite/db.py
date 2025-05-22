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

    Meta:
        database (Database): The database connection to use.
        db_table (str): The name of the database table for storing messages.
    """

    message_id = TextField(unique=True)
    thread_id = TextField(null=True)
    sender = JSONField()
    recipients = JSONField()
    labels = JSONField()
    subject = TextField(null=True)
    body = TextField(null=True)
    size = IntegerField()
    timestamp = DateTimeField()
    is_read = BooleanField()
    is_outgoing = BooleanField()
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


def create_message(msg: Message, clobber=[]):
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
    ).on_conflict(
        conflict_target=[Message.message_id],
        # weirdly, "preserve" means almost the opposite of what you'd expect.
        # It preserves the value from the *INSERTED* row, not the original row.
        # So our "clobber" is the same as playhouse "preserve".
        preserve=[] +
        ([Message.thread_id] if "thread_id" in clobber else []) + 
        ([Message.sender] if "sender" in clobber else []) + 
        ([Message.recipients] if "recipients" in clobber else []) + 
        ([Message.subject] if "subject" in clobber else []) +
        ([Message.body] if "body" in clobber else []) +
        ([Message.size] if "size" in clobber else []) +
        ([Message.timestamp] if "timestamp" in clobber else []) +
        ([Message.is_outgoing] if "is_outgoing" in clobber else []) +
        ([Message.is_read] if "is_read" in clobber else []) +
        ([Message.labels] if "labels" in clobber else []) ,
        update={
            Message.last_indexed: last_indexed,
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
        return datetime.fromisoformat(msg.timestamp)
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
        return datetime.fromisoformat(msg.timestamp)
    else:
        return None
