from googleapiclient.discovery import build
from peewee import IntegrityError

from . import db
from . import message

MAX_RESULTS = 500


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


def all_messages(credentials, full_sync=False, clobber=[]) -> int:
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
                msg = message.Message.from_raw(raw_msg, labels)
                db.create_message(msg, clobber)

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


def single_message(credentials, message_id: str, clobber=[]) -> None:
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
        db.create_message(msg, clobber)
    except IntegrityError as e:
        print(f"Could not process message {message_id}: {str(e)}")
    except TimeoutError as e:
        print(f"Could not get message from Gmail {message_id}: {str(e)}")

    print(f"Synced message {message_id} from {msg.timestamp}")
