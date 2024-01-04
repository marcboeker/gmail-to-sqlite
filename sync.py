from email.utils import parseaddr, parsedate_to_datetime

from googleapiclient.discovery import build
from peewee import IntegrityError

import db
import message

MAX_RESULTS = 500


def all_messages(credentials, only_new=False, exclude_raw=False) -> int:
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
        last = db.last_indexed()
        if last:
            query.append(f"after:{int(last.timestamp())}")

        first = db.first_indexed()
        if first:
            query.append(f"before:{int(first.timestamp())}")

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
        for i, m in enumerate(messages, start=total_messages - len(messages) + 1):
            try:
                raw_msg = (
                    service.users().messages().get(userId="me", id=m["id"]).execute()
                )
                msg = message.Message.from_raw(raw_msg)
                db.create_message(msg, raw_msg, exclude_raw)

            except IntegrityError as e:
                print(f"Could not process message {m['id']}: {str(e)}")
            except TimeoutError as e:
                print(f"Could not get message from Gmail {m['id']}: {str(e)}")

            print(f"Synced message {msg.id} from {msg.timestamp} (Count: {i})")

        if "nextPageToken" in results:
            page_token = results["nextPageToken"]
        else:
            run = False

    return total_messages


def single_message(credentials, message_id, exclude_raw=False) -> None:
    """
    Syncs a single message from Gmail using the provided credentials and message ID.

    Args:
        credentials: The credentials used to authenticate the Gmail API.
        message_id: The ID of the message to fetch.

    Returns:
        None
    """

    service = build("gmail", "v1", credentials=credentials)
    try:
        raw_msg = service.users().messages().get(userId="me", id=message_id).execute()
        msg = message.Message.from_raw(raw_msg)
        db.create_message(msg, raw_msg, exclude_raw=exclude_raw)
    except IntegrityError as e:
        print(f"Could not process message {m['id']}: {str(e)}")
    except TimeoutError as e:
        print(f"Could not get message from Gmail {m['id']}: {str(e)}")

    print(f"Synced message {msg.id} from {msg.timestamp}")
