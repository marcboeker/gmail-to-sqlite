import concurrent.futures
import logging
import time
from email.utils import parseaddr, parsedate_to_datetime

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from peewee import IntegrityError

import db
import message

MAX_RESULTS = 500


def _fetch_message_details(service, message_id: str, labels: dict):
    """
    Fetches and processes a single message's details with retries.
    """
    max_retries = 3
    retry_delay_seconds = 5

    for attempt in range(max_retries):
        try:
            raw_msg = (
                service.users().messages().get(userId="me", id=message_id).execute()
            )
            msg = message.Message.from_raw(raw_msg, labels)
            db.create_message(msg)
            logging.info(
                f"Successfully synced message {msg.id} (Original ID: {message_id}) from {msg.timestamp}"
            )
            return True
        except IntegrityError as e:
            logging.error(
                f"Could not process message {message_id} due to integrity error (will not retry): {str(e)}"
            )
            return False
        except HttpError as e:
            if e.resp.status >= 500 and attempt < max_retries - 1:
                logging.warning(
                    f"Attempt {attempt + 1}/{max_retries} failed for message {message_id} due to server error {e.resp.status}. Retrying in {retry_delay_seconds}s..."
                )
                time.sleep(retry_delay_seconds)
            else:
                logging.error(
                    f"Failed to fetch message {message_id} after {attempt + 1} attempts due to HttpError {e.resp.status}: {str(e)}"
                )
                return False
        except TimeoutError as e:
            if attempt < max_retries - 1:
                logging.warning(
                    f"Attempt {attempt + 1}/{max_retries} failed for message {message_id} due to timeout. Retrying in {retry_delay_seconds}s..."
                )
                time.sleep(retry_delay_seconds)
            else:
                logging.error(
                    f"Failed to fetch message {message_id} after {attempt + 1} attempts due to timeout: {str(e)}"
                )
                return False
        except Exception as e:
            logging.error(
                f"An unexpected error occurred while processing message {message_id} on attempt {attempt + 1}: {str(e)}"
            )
            if attempt < max_retries - 1:
                time.sleep(retry_delay_seconds)
            else:
                return False
    return False


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


def _create_service(credentials):
    """
    Creates a new Gmail API service object with the provided credentials.
    Use this to create a fresh service object for each thread.

    Args:
        credentials: The credentials object used to authenticate the API request.

    Returns:
        object: A new Gmail API service object.
    """
    return build("gmail", "v1", credentials=credentials)


def all_messages(credentials, db_conn, full_sync=False, num_workers: int = 4) -> int:
    """
    Fetches messages from the Gmail API using the provided credentials, in parallel.

    Args:
        credentials (object): The credentials object used to authenticate the API request.
        db_conn (object): The database connection object.
        full_sync (bool): Whether to do a full sync or not.
        num_workers (int): Number of worker threads for parallel fetching.

    Returns:
        int: The number of messages successfully synced.
    """

    query = []
    if not full_sync:
        last = db.last_indexed()
        if last:
            query.append(f"after:{int(last.timestamp())}")

        first = db.first_indexed()
        if first:
            query.append(f"before:{int(first.timestamp())}")

    service = _create_service(credentials)
    labels = get_labels(service)

    all_message_ids = []
    page_token = None
    run = True
    logging.info("Collecting all message IDs...")
    while run:
        results = (
            service.users()
            .messages()
            .list(
                userId="me",
                maxResults=MAX_RESULTS,
                pageToken=page_token,
                q=(
                    " | ".join(query) if query else None
                ),  # Ensure q is not empty string if query is empty
            )
            .execute()
        )
        messages_page = results.get("messages", [])
        for m_info in messages_page:
            all_message_ids.append(m_info["id"])

        if "nextPageToken" in results:
            page_token = results["nextPageToken"]
        else:
            run = False

    logging.info(f"Found {len(all_message_ids)} messages to sync.")

    total_synced_count = 0
    processed_count = 0

    # Define a worker function that creates its own service for thread safety
    def thread_worker(message_id):
        thread_service = _create_service(credentials)
        return _fetch_message_details(thread_service, message_id, labels)

    with concurrent.futures.ThreadPoolExecutor(max_workers=num_workers) as executor:
        future_to_id = {
            executor.submit(thread_worker, msg_id): msg_id for msg_id in all_message_ids
        }

        for future in concurrent.futures.as_completed(future_to_id):
            message_id = future_to_id[future]
            processed_count += 1
            try:
                if future.result():  # If _fetch_message_details returns True
                    total_synced_count += 1
                # Progress can be reported here based on processed_count
                if processed_count % 50 == 0 or processed_count == len(all_message_ids):
                    logging.info(
                        f"Processed {processed_count}/{len(all_message_ids)} messages..."
                    )
            except Exception as exc:
                # This catches exceptions from future.result() itself (e.g., if the task raised an unhandled one)
                # _fetch_message_details is expected to catch its own errors and return False
                logging.error(
                    f"Message ID {message_id} generated an exception during future processing: {exc}"
                )

    logging.info(
        f"Total messages successfully synced: {total_synced_count} out of {len(all_message_ids)}"
    )
    return total_synced_count


def single_message(credentials, message_id: str) -> None:
    """
    Syncs a single message from Gmail using the provided credentials and message ID.

    Args:
        credentials: The credentials used to authenticate the Gmail API.
        message_id: The ID of the message to fetch.

    Returns:
        None
    """

    service = _create_service(credentials)
    labels = get_labels(service)
    # For single_message, we can reuse _fetch_message_details for consistency in fetching logic and error handling
    # However, the original instruction implies modifying single_message directly.
    # I will follow the direct modification approach for single_message as per the prompt for now.
    # A cleaner approach might be to have single_message call _fetch_message_details.
    max_retries = 3
    retry_delay_seconds = 5
    for attempt in range(max_retries):
        try:
            raw_msg = (
                service.users().messages().get(userId="me", id=message_id).execute()
            )
            msg = message.Message.from_raw(raw_msg, labels)
            db.create_message(msg)
            logging.info(
                f"Successfully synced message {msg.id} (Original ID: {message_id}) from {msg.timestamp}"
            )
            return  # Success
        except IntegrityError as e:
            logging.error(
                f"Could not process message {message_id} due to integrity error (will not retry): {str(e)}"
            )
            return  # Non-retryable
        except HttpError as e:
            if e.resp.status >= 500 and attempt < max_retries - 1:
                logging.warning(
                    f"Attempt {attempt + 1}/{max_retries} failed for message {message_id} due to server error {e.resp.status}. Retrying in {retry_delay_seconds}s..."
                )
                time.sleep(retry_delay_seconds)
            else:
                logging.error(
                    f"Failed to fetch message {message_id} after {attempt + 1} attempts due to HttpError {e.resp.status}: {str(e)}"
                )
                return  # Final failure
        except TimeoutError as e:
            if attempt < max_retries - 1:
                logging.warning(
                    f"Attempt {attempt + 1}/{max_retries} failed for message {message_id} due to timeout. Retrying in {retry_delay_seconds}s..."
                )
                time.sleep(retry_delay_seconds)
            else:
                logging.error(
                    f"Failed to fetch message {message_id} after {attempt + 1} attempts due to timeout: {str(e)}"
                )
                return  # Final failure
        except Exception as e:
            logging.error(
                f"An unexpected error occurred while processing message {message_id} on attempt {attempt + 1}: {str(e)}"
            )
            if attempt < max_retries - 1:
                time.sleep(retry_delay_seconds)
            else:
                return  # Final failure for other exceptions
    logging.error(f"Failed to sync message {message_id} after all retries.")
