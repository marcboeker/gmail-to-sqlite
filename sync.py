from email.utils import parseaddr, parsedate_to_datetime

from googleapiclient.discovery import build
from peewee import IntegrityError

import db
import message

MAX_RESULTS = 500
DB_BATCH_SIZE = 100 # Number of messages to write to DB in one go


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


def _get_all_gmail_message_ids(service) -> set:
    """Helper function to retrieve all message IDs from Gmail."""
    all_gmail_ids = set()
    page_token = None
    while True:
        try:
            response = (
                service.users()
                .messages()
                .list(userId="me", pageToken=page_token, fields="nextPageToken,messages/id") # Only fetch IDs
                .execute()
            )
        except Exception as e:
            print(f"Error fetching message IDs from Gmail: {e}")
            # Depending on the error, you might want to retry or bail out
            break 

        messages = response.get("messages", [])
        for msg_data in messages:
            all_gmail_ids.add(msg_data["id"])

        page_token = response.get("nextPageToken")
        if not page_token:
            break
    return all_gmail_ids


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

    # --- Detect and mark deleted messages --- 
    print("Checking for deleted messages...")
    local_active_ids = db.get_active_message_ids()
    gmail_all_ids = _get_all_gmail_message_ids(service)

    ids_to_mark_deleted = list(local_active_ids - gmail_all_ids)
    if ids_to_mark_deleted:
        db.mark_messages_as_deleted(ids_to_mark_deleted)
        print(f"Marked {len(ids_to_mark_deleted)} messages as deleted.")
    else:
        print("No messages found to mark as deleted.")
    # --- End of deletion check ---

    labels = get_labels(service)

    page_token = None
    run = True
    total_messages_processed_in_run = 0 # Renamed from total_messages to avoid confusion with count from API
    current_batch_count = 0
    message_object_batch = []

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

        messages_from_api = results.get("messages", [])
        if not messages_from_api:
            print("No new messages found in this page.")
            break # No messages in this page, could be end of sync for non-full syncs

        for i, m_summary in enumerate(messages_from_api):
            current_total_count = total_messages_processed_in_run + current_batch_count + 1
            try:
                raw_msg = (
                    service.users().messages().get(userId="me", id=m_summary["id"]).execute()
                )
                msg = message.Message.from_raw(raw_msg, labels)
                message_object_batch.append(msg)
                current_batch_count += 1

                if current_batch_count >= DB_BATCH_SIZE:
                    # Log date range of the batch
                    first_msg_time = message_object_batch[0].timestamp.strftime('%Y-%m-%d %H:%M:%S') if message_object_batch else "N/A"
                    last_msg_time = message_object_batch[-1].timestamp.strftime('%Y-%m-%d %H:%M:%S') if message_object_batch else "N/A"
                    date_log = f" ({first_msg_time} - {last_msg_time})" if first_msg_time != "N/A" else ""
                    
                    db.create_messages_batch(message_object_batch)
                    print(f"Synced batch of {len(message_object_batch)} messages{date_log} (Total processed in run: {current_total_count})")
                    total_messages_processed_in_run += len(message_object_batch)
                    message_object_batch = []
                    current_batch_count = 0

            except IntegrityError as e:
                print(f"DB IntegrityError for message {m_summary['id']}: {str(e)} - Skipping.")
            except TimeoutError as e:
                print(f"Timeout fetching message from Gmail {m_summary['id']}: {str(e)} - Skipping.")
            except Exception as e:
                print(f"Error processing message {m_summary.get('id', 'UNKNOWN')}: {str(e)} - Skipping.")

        # Process any remaining messages in the batch from the current page
        if message_object_batch:
            # Log date range of the final batch from page
            first_msg_time = message_object_batch[0].timestamp.strftime('%Y-%m-%d %H:%M:%S')
            last_msg_time = message_object_batch[-1].timestamp.strftime('%Y-%m-%d %H:%M:%S')
            date_log = f" ({first_msg_time} - {last_msg_time})"

            db.create_messages_batch(message_object_batch)
            print(f"Synced final batch of {len(message_object_batch)} messages from page{date_log} (Total processed in run: {total_messages_processed_in_run + len(message_object_batch)})")
            total_messages_processed_in_run += len(message_object_batch)
            message_object_batch = []
            current_batch_count = 0

        page_token = results.get("nextPageToken")
        if not page_token:
            run = False

    print(f"Finished sync. Total messages processed in this run: {total_messages_processed_in_run}")
    return total_messages_processed_in_run


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
