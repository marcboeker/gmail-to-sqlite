import base64
import json
from datetime import datetime
from email.utils import parseaddr, parsedate_to_datetime

from bs4 import BeautifulSoup
from googleapiclient.discovery import build
from peewee import IntegrityError

from db import Message

MAX_RESULTS = 500


def parse_addresses(addresses: str, type: str) -> list:
    """
    Parse a list of email addresses.

    Args:
        addresses (str): The list of email addresses to parse.
        type (str): The type of the email addresses (to, cc, bcc).

    Returns:
        list: The parsed email addresses.
    """
    parsed_addresses = []
    for address in addresses.split(";"):
        name, email = parseaddr(address)
        if len(email) > 0:
            parsed_addresses.append(
                {"email": email.lower(), "name": name, "type": type}
            )

    return parsed_addresses


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


def html2text(html: str) -> str:
    """
    Convert HTML to plain text.

    Args:
        html (str): The HTML to convert.

    Returns:
        str: The converted HTML.
    """
    soup = BeautifulSoup(html, features="html.parser")
    return soup.get_text()


def process_message(service, id: str, exclude_raw=False):
    """
    Process a message retrieved from Gmail.

    Args:
        service: The service object used to retrieve the message.
        id (str): The ID of the message to be processed.
        exclude_raw (bool): Whether to store the raw message in the database or not.

    Returns:
        The timestamp of the processed message.
    """

    msg = service.users().messages().get(userId="me", id=id).execute()
    sender_name = ""
    sender_email = ""
    recipients = []
    subject = ""
    body = ""
    size = msg["sizeEstimate"]
    timestamp = None
    is_read = False
    is_outgoing = False
    last_indexed = datetime.now()

    for header in msg["payload"]["headers"]:
        name = header["name"].lower()
        if name == "from":
            sender_name, sender_email = parseaddr(header["value"])
        elif name == "to":
            recipients.extend(parse_addresses(header["value"], "to"))
        elif name == "cc":
            recipients.extend(parse_addresses(header["value"], "cc"))
        elif name == "bcc":
            recipients.extend(parse_addresses(header["value"], "bcc"))
        elif name == "subject":
            subject = header["value"]
        elif name == "date":
            timestamp = parsedate_to_datetime(header["value"])

    # Determine if the message has been read.
    labels = msg["labelIds"]
    if "labelIds" in msg:
        labels = msg["labelIds"]
        if "UNREAD" in labels:
            is_read = False
        else:
            is_read = True

        if "SENT" in labels:
            is_outgoing = True

    # For non multipart messages, extract the body from the message.
    if "body" in msg["payload"]:
        if "data" in msg["payload"]["body"]:
            body = base64.urlsafe_b64decode(msg["payload"]["body"]["data"]).decode(
                "utf-8"
            )

            if (
                "mimeType" in msg["payload"]["body"]
                and msg["payload"]["mimeType"] == "text/html"
            ):
                body = html2text(body)

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

                if part["mimeType"] == "text/html":
                    body = html2text(body)

                if len(body) > 0:
                    break

    try:
        message = (
            Message.insert(
                message_id=id,
                thread_id=msg["threadId"],
                sender={"name": sender_name, "email": sender_email},
                recipients=recipients,
                subject=subject,
                body=body,
                labels=labels,
                raw=None if exclude_raw else msg,
                size=size,
                timestamp=timestamp,
                is_read=is_read,
                is_outgoing=is_outgoing,
                last_indexed=last_indexed,
            )
            .on_conflict(
                conflict_target=[Message.message_id],
                preserve=[
                    Message.thread_id,
                    Message.sender,
                    Message.recipients,
                    Message.subject,
                    Message.body,
                    Message.raw,
                    Message.size,
                    Message.timestamp,
                    Message.is_outgoing,
                ],
                update={
                    Message.is_read: is_read,
                    Message.last_indexed: last_indexed,
                    Message.labels: labels,
                },
            )
            .execute()
        )
    except IntegrityError as e:
        print(f"Could not save message with ID {id}:", str(e))

    return timestamp


def sync_messages(credentials, only_new=False, exclude_raw=False) -> int:
    """
    Fetches messages from the Gmail API using the provided credentials.

    Args:
        credentials (object): The credentials object used to authenticate the API request.
        only_new (bool): Whether to sync only the messages that have not been synced before.
        exclude_raw (bool): Whether to store the raw message in the database or not.

    Returns:
        int: The number of messages fetched.
    """

    query = []
    if only_new:
        last_message = Message.select().order_by(Message.timestamp.desc()).first()
        if last_message:
            ts = datetime.fromisoformat(last_message.timestamp)
            query.append(f"after:{int(ts.timestamp())}")

        first_message = Message.select().order_by(Message.timestamp.asc()).first()
        if first_message:
            ts = datetime.fromisoformat(first_message.timestamp)
            query.append(f"before:{int(ts.timestamp())}")

    service = build("gmail", "v1", credentials=credentials)

    page_token = None
    run = True
    total_messages = 0
    while run:
        results = (
            service.users()
            .messages()
            .list(
                userId="me",
                maxResults=MAX_RESULTS,
                pageToken=page_token,
                q=" | ".join(query),
            )
            .execute()
        )
        messages = results.get("messages", [])

        total_messages += len(messages)
        for i, message in enumerate(messages, start=total_messages - len(messages) + 1):
            try:
                date = process_message(service, message["id"], exclude_raw=exclude_raw)
                print(f"Syncing message {message['id']} from {date} (Count: {i})")
            except TimeoutError as e:
                print(f"Could not sync message {message['id']}: {str(e)}")

        if "nextPageToken" in results:
            page_token = results["nextPageToken"]
        else:
            run = False

    return total_messages


def sync_message(credentials, message_id) -> None:
    """
    Syncs a single message from Gmail using the provided credentials and message ID.

    Args:
        credentials: The credentials used to authenticate the Gmail API.
        message_id: The ID of the message to fetch.

    Returns:
        None
    """
    service = build("gmail", "v1", credentials=credentials)
    process_message(service, message_id)
