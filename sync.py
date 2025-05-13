from email.utils import parseaddr, parsedate_to_datetime

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from peewee import IntegrityError
import concurrent.futures
import requests
import ssl
import time

import db
import message

MAX_RESULTS = 500
MAX_THREADS = 5  # Adjust as needed
MAX_FETCH_RETRIES = 3
RETRY_SLEEP = 1.5
FETCH_SLEEP = 0.2  # Sleep between fetches to avoid API throttling


def get_labels(service) -> dict:
    """
    Retrieves all labels from the Gmail API for the authenticated user.

    Args:
        service (object): The Gmail API service object.

    Returns:
        dict: A dictionary containing the labels, where the key is the label ID and the value is the label name.
    """

    # Get all labels
    labels = {}
    for label in service.users().labels().list(userId="me").execute()["labels"]:
        labels[label["id"]] = label["name"]

    return labels


def all_messages(credentials, full_sync=False) -> int:
    """
    Fetches messages from the Gmail API using the provided credentials.

    Args:
        credentials (object): The credentials object used to authenticate the API request.
        full_sync (bool): Whether to do a full sync or not.

    Returns:
        int: The number of messages fetched.
    """

    query = []
    if not full_sync:
        last = db.last_indexed()
        if last:
            query.append(f"after:{int(last.timestamp())}")

        first = db.first_indexed()
        if first:
            query.append(f"before:{int(first.timestamp())}")

    service = build("gmail", "v1", credentials=credentials)

    labels = get_labels(service)

    page_token = None
    run = True
    total_messages = 0
    BATCH_SIZE = 100  # Gmail API batchGet limit

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
        message_ids = [m["id"] for m in messages]

        # Process in batches (parallel fetch)
        for batch_start in range(0, len(message_ids), BATCH_SIZE):
            batch_ids = message_ids[batch_start:batch_start+BATCH_SIZE]
            print(f"\nProcessing batch {batch_start // BATCH_SIZE + 1} (messages {batch_start + 1}-{batch_start + len(batch_ids)})")
            print(f"Batch message IDs: {batch_ids}")

            def fetch_message(msg_id):
                for attempt in range(1, MAX_FETCH_RETRIES + 1):
                    try:
                        # Rebuild the service for each thread to avoid sharing connections
                        local_service = build("gmail", "v1", credentials=credentials, cache_discovery=False)
                        raw_msg = (
                            local_service.users()
                            .messages()
                            .get(userId="me", id=msg_id, format="full")
                            .execute()
                        )
                        return (msg_id, raw_msg, None)
                    except HttpError as e:
                        if attempt < MAX_FETCH_RETRIES:
                            print(f"HTTP error on attempt {attempt} for message {msg_id}: {e}. Retrying...")
                            time.sleep(RETRY_SLEEP * attempt)
                        else:
                            return (msg_id, None, e)
                    except Exception as e:
                        if attempt < MAX_FETCH_RETRIES:
                            print(f"Error on attempt {attempt} for message {msg_id}: {e}. Retrying...")
                            time.sleep(RETRY_SLEEP * attempt)
                        else:
                            return (msg_id, None, e)

            batch_messages = []
            with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
                future_to_id = {executor.submit(fetch_message, msg_id): msg_id for msg_id in batch_ids}
                for future in concurrent.futures.as_completed(future_to_id):
                    msg_id = future_to_id[future]
                    msg_id, raw_msg, error = future.result()
                    if error:
                        print(f"Failed to fetch message {msg_id}: {error}")
                        continue
                    batch_messages.append(raw_msg)

            print(f"Fetched {len(batch_messages)} messages in this batch. Processing...")
            for i, raw_msg in enumerate(batch_messages, start=total_messages + 1):
                try:
                    msg = message.Message.from_raw(raw_msg, labels)
                    db.create_message(msg)
                    print(f"Synced message {msg.id} from {msg.timestamp} (Count: {i})")
                except IntegrityError as e:
                    print(f"Could not process message {raw_msg.get('id', '?')}: {str(e)}")
                except TimeoutError as e:
                    print(f"Could not get message from Gmail {raw_msg.get('id', '?')}: {str(e)}")
                except Exception as e:
                    print(f"Error processing message {raw_msg.get('id', '?')}: {str(e)}")

            total_messages += len(batch_ids)

        if "nextPageToken" in results:
            page_token = results["nextPageToken"]
        else:
            run = False

    return total_messages


def single_message(credentials, message_id: str) -> None:
    """
    Syncs a single message from Gmail using the provided credentials and message ID.

    Args:
        credentials: The credentials used to authenticate the Gmail API.
        message_id: The ID of the message to fetch.

    Returns:
        None
    """

    service = build("gmail", "v1", credentials=credentials)
    labels = get_labels(service)
    try:
        raw_msg = service.users().messages().get(userId="me", id=message_id).execute()
        msg = message.Message.from_raw(raw_msg, labels)
        db.create_message(msg)
    except IntegrityError as e:
        print(f"Could not process message {message_id}: {str(e)}")
    except TimeoutError as e:
        print(f"Could not get message from Gmail {message_id}: {str(e)}")

    print(f"Synced message {message_id} from {msg.timestamp}")
