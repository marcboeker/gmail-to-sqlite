import logging

from peewee import *
from playhouse.sqlite_ext import *

database_proxy = Proxy()


class Message(Model):
    """
    Represents an email message.

    Attributes:
        message_id (TextField): The unique identifier of the message.
        thread_id (TextField): The unique identifier of the thread.
        sender (TextField): The sender of the message.
        sender_name (TextField): The name of the sender.
        sender_email (TextField): The email address of the sender.
        recipients (JSONField): The recipients of the message.
        subject (TextField): The subject of the message.
        body (TextField): The body of the message.
        labels (JSONField): The labels of the message.
        raw (JSONField): The raw data of the message.
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
    thread_id = TextField()
    sender = TextField()
    sender_name = TextField()
    sender_email = TextField()
    recipients = JSONField()
    subject = TextField()
    body = TextField()
    labels = JSONField()
    raw = JSONField()
    size = IntegerField()
    timestamp = DateTimeField()
    is_read = BooleanField()
    is_outgoing = BooleanField()
    last_indexed = DateTimeField()

    class Meta:
        database = database_proxy
        db_table = "messages"


def init_db(data_dir: str, enable_logging=False) -> SqliteDatabase:
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
