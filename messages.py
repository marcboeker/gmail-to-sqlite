import base64
import json
from datetime import datetime
from email.utils import parseaddr, parsedate_to_datetime

from googleapiclient.discovery import build
from peewee import IntegrityError

from db import Message

MAX_RESULTS = 500


def decode_body(part) -> str:
    """
    Decode the body of a message part.

    Args:
        part (dict): The message part to decode.

    Returns:
        str: The decoded body of the message part.
    """
    if "data" in part["body"]:
        return base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8")
    elif "parts" in part:
        for subpart in part["parts"]:
            decoded_body = decode_body(subpart)
            if decoded_body:
                return decoded_body

    return ""


def process_message(service, id):
    """
    Process a message retrieved from Gmail.

    Args:
        service: The service object used to retrieve the message.
        id: The ID of the message to be processed.

    Returns:
        The timestamp of the processed message.
    """

    msg = service.users().messages().get(userId="me", id=id).execute()
    sender = ""
    sender_name = ""
    sender_email = ""
    recipients = []
    subject = ""
    body = ""
    size = msg["sizeEstimate"]
    timestamp = None
    is_read = False
    last_indexed = datetime.now()

    for header in msg["payload"]["headers"]:
        if header["name"] == "From":
            sender = header["value"]
            sender_name, sender_email = parseaddr(sender)
        elif header["name"] == "To":
            for r in header["value"].split(";"):
                pr = parseaddr(r)
                recipients.append({"name": pr[0], "email": pr[1]})
        elif header["name"] == "Subject":
            subject = header["value"]
        elif header["name"] == "Date":
            timestamp = parsedate_to_datetime(header["value"])

    # Determine if the message has been read.
    if "labelIds" in msg:
        labels = msg["labelIds"]
        if "UNREAD" in labels:
            is_read = False
        else:
            is_read = True

    # For non multipart messages, extract the body from the message.
    if "body" in msg["payload"]:
        if "data" in msg["payload"]["body"]:
            body = base64.urlsafe_b64decode(msg["payload"]["body"]["data"]).decode(
                "utf-8"
            )

    # For multipart messages, get the body from the parts.
    if "parts" in msg["payload"] and len(body) == 0:
        for part in msg["payload"]["parts"]:
            if (
                part["mimeType"] == "text/html"
                or part["mimeType"] == "text/plain"
                or part["mimeType"] == "multipart/related"
                or part["mimeType"] == "multipart/alternative"
            ):
                body = decode_body(part)
                if len(body) > 0:
                    break

    try:
        message = (
            Message.insert(
                message_id=id,
                sender=sender,
                sender_name=sender_name,
                sender_email=sender_email,
                recipients=recipients,
                subject=subject,
                body=body,
                raw=msg,
                size=size,
                timestamp=timestamp,
                is_read=is_read,
                last_indexed=last_indexed,
            )
            .on_conflict(
                conflict_target=[Message.message_id],
                preserve=[
                    Message.sender,
                    Message.sender_name,
                    Message.sender_email,
                    Message.recipients,
                    Message.subject,
                    Message.body,
                    Message.raw,
                    Message.size,
                    Message.timestamp,
                ],
                update={Message.is_read: is_read, Message.last_indexed: last_indexed},
            )
            .execute()
        )
    except IntegrityError as e:
        print(f"Could not save message with ID {id}:", str(e))

    return timestamp


def fetch_messages(credentials) -> int:
    """
    Fetches messages from the Gmail API using the provided credentials.

    Args:
        credentials (object): The credentials object used to authenticate the API request.

    Returns:
        int: The number of messages fetched.
    """

    service = build("gmail", "v1", credentials=credentials)

    page_token = None
    run = True
    total_messages = 0
    while run:
        results = (
            service.users()
            .messages()
            .list(userId="me", maxResults=MAX_RESULTS, pageToken=page_token)
            .execute()
        )
        messages = results.get("messages", [])

        total_messages += len(messages)
        for i, message in enumerate(messages, start=total_messages - len(messages) + 1):
            date = process_message(service, message["id"])
            print(f"Added message {i} of {total_messages} ({date})")

        if "nextPageToken" in results:
            page_token = results["nextPageToken"]
        else:
            run = False

    return total_messages


def fetch_message(credentials, message_id) -> None:
    """
    Fetches a message from Gmail using the provided credentials and message ID.

    Args:
        credentials: The credentials used to authenticate the Gmail API.
        message_id: The ID of the message to fetch.

    Returns:
        None
    """
    service = build("gmail", "v1", credentials=credentials)
    process_message(service, message_id)