import concurrent.futures
import logging
import socket
import time
from typing import Any, Callable, Dict, List, Optional, Set

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from peewee import IntegrityError

from . import db, message
from .constants import (
    DEFAULT_WORKERS,
    GMAIL_API_VERSION,
    MAX_RESULTS_PER_PAGE,
    MAX_RETRY_ATTEMPTS,
    RETRY_DELAY_SECONDS,
    PROGRESS_LOG_INTERVAL,
    COLLECTION_LOG_INTERVAL,
)


class SyncError(Exception):
    """Custom exception for synchronization errors."""

    pass


def _fetch_message(
    service: Any,
    message_id: str,
    labels: Dict[str, str],
    check_interrupt: Optional[Callable[[], bool]] = None,
) -> message.Message:
    """
    Fetches a single message from Gmail API with retry logic and robust error handling.

    Args:
        service: The Gmail API service object.
        message_id: The ID of the message to fetch.
        labels: Dictionary mapping label IDs to label names.
        check_interrupt: Optional callback that returns True if process should be interrupted.

    Returns:
        Message: The parsed message object.

    Raises:
        InterruptedError: If the process was interrupted.
        SyncError: If the message cannot be fetched after all retries.
    """
    for attempt in range(MAX_RETRY_ATTEMPTS):
        if check_interrupt and check_interrupt():
            raise InterruptedError("Process was interrupted")

        try:
            raw_msg = (
                service.users().messages().get(userId="me", id=message_id).execute()
            )
            return message.Message.from_raw(raw_msg, labels)

        except HttpError as e:
            if e.resp.status >= 500 and attempt < MAX_RETRY_ATTEMPTS - 1:
                logging.warning(
                    f"Attempt {attempt + 1}/{MAX_RETRY_ATTEMPTS} failed for message {message_id} "
                    f"due to server error {e.resp.status}. Retrying in {RETRY_DELAY_SECONDS}s..."
                )
                if check_interrupt and check_interrupt():
                    raise InterruptedError("Process was interrupted")
                time.sleep(RETRY_DELAY_SECONDS)
            else:
                error_msg = (
                    f"Failed to fetch message {message_id} after {attempt + 1} attempts "
                    f"due to HttpError {e.resp.status}: {str(e)}"
                )
                logging.error(error_msg)
                raise SyncError(error_msg)

        except (TimeoutError, socket.timeout) as e:
            if attempt < MAX_RETRY_ATTEMPTS - 1:
                logging.warning(
                    f"Attempt {attempt + 1}/{MAX_RETRY_ATTEMPTS} failed for message {message_id} "
                    f"due to timeout. Retrying in {RETRY_DELAY_SECONDS}s..."
                )
                if check_interrupt and check_interrupt():
                    raise InterruptedError("Process was interrupted")
                time.sleep(RETRY_DELAY_SECONDS)
            else:
                error_msg = (
                    f"Failed to fetch message {message_id} after {attempt + 1} attempts "
                    f"due to timeout: {str(e)}"
                )
                logging.error(error_msg)
                raise SyncError(error_msg)

        except Exception as e:
            logging.error(
                f"Unexpected error processing message {message_id} on attempt {attempt + 1}: {str(e)}"
            )
            if attempt < MAX_RETRY_ATTEMPTS - 1:
                if check_interrupt and check_interrupt():
                    raise InterruptedError("Process was interrupted")
                time.sleep(RETRY_DELAY_SECONDS)
            else:
                error_msg = f"Failed to fetch message {message_id} after {MAX_RETRY_ATTEMPTS} attempts"
                logging.error(error_msg)
                raise SyncError(error_msg)

    # This should never be reached due to the exception handling above
    raise SyncError(f"Unexpected error: failed to fetch message {message_id}")


def get_labels(service: Any) -> Dict[str, str]:
    """
    Retrieves all labels from the Gmail API.

    Args:
        service: The Gmail API service object.

    Returns:
        Dict[str, str]: Mapping of label IDs to label names.

    Raises:
        SyncError: If labels cannot be retrieved.
    """
    try:
        labels = {}
        response = service.users().labels().list(userId="me").execute()
        for label in response.get("labels", []):
            labels[label["id"]] = label["name"]
        return labels
    except Exception as e:
        raise SyncError(f"Failed to retrieve labels: {e}")


def _create_service(credentials: Any) -> Any:
    """
    Creates a new Gmail API service object.

    Args:
        credentials: The credentials object for API authentication.

    Returns:
        The Gmail API service object.

    Raises:
        SyncError: If service creation fails.
    """
    try:
        return build("gmail", GMAIL_API_VERSION, credentials=credentials)
    except Exception as e:
        raise SyncError(f"Failed to create Gmail service: {e}")


def get_message_ids_from_gmail(
    service: Any,
    query: Optional[str] = None,
    check_shutdown: Optional[Callable[[], bool]] = None,
) -> List[str]:
    """
    Fetches all message IDs from Gmail matching the query.

    Args:
        service: The Gmail API service object.
        query: Optional query string to filter messages.
        check_shutdown: Callback that returns True if shutdown is requested.

    Returns:
        List[str]: List of message IDs from Gmail.

    Raises:
        SyncError: If message ID collection fails.
    """
    all_message_ids = []
    page_token = None
    collected_count = 0

    logging.info("Collecting all message IDs from Gmail...")
    if query:
        logging.info(f"Filtering messages with query: {query}")

    try:
        while not (check_shutdown and check_shutdown()):
            list_params = {
                "userId": "me",
                "maxResults": MAX_RESULTS_PER_PAGE,
            }

            if page_token:
                list_params["pageToken"] = page_token

            if query:
                list_params["q"] = query

            results = service.users().messages().list(**list_params).execute()
            messages_page = results.get("messages", [])

            for m_info in messages_page:
                all_message_ids.append(m_info["id"])
                collected_count += 1

                if collected_count % COLLECTION_LOG_INTERVAL == 0:
                    logging.info(
                        f"Collected {collected_count} message IDs from Gmail..."
                    )

            page_token = results.get("nextPageToken")
            if not page_token:
                break

    except KeyboardInterrupt:
        logging.info("Message ID collection interrupted by user")
    except Exception as e:
        raise SyncError(f"Failed to collect message IDs: {e}")

    if check_shutdown and check_shutdown():
        logging.info(
            "Shutdown requested during message ID collection. Exiting gracefully."
        )
        return []

    logging.info(f"Collected {len(all_message_ids)} message IDs from Gmail")
    return all_message_ids


def _detect_and_mark_deleted_messages(
    gmail_message_ids: List[str], check_shutdown: Optional[Callable[[], bool]] = None
) -> Optional[int]:
    """
    Helper function to detect and mark deleted messages based on comparison
    between Gmail message IDs and database message IDs.

    Args:
        gmail_message_ids (list): List of message IDs from Gmail.
        check_shutdown (callable): A callback function that returns True if shutdown is requested.

    Returns:
        int: Number of messages newly marked as deleted, or None if no action taken.
    """
    try:
        db_message_ids = set(db.get_all_message_ids())
        logging.info(
            f"Retrieved {len(db_message_ids)} message IDs from database for deletion detection"
        )

        if not db_message_ids:
            logging.info("No messages in database to check for deletion")
            return None

        if check_shutdown and check_shutdown():
            logging.info(
                "Shutdown requested during deletion detection. Exiting gracefully."
            )
            return None

        already_deleted_ids = set(db.get_deleted_message_ids())
        if already_deleted_ids:
            logging.info(
                f"Found {len(already_deleted_ids)} already deleted messages to skip"
            )

        gmail_ids_set = set(gmail_message_ids)
        potential_deleted_ids = db_message_ids - gmail_ids_set
        new_deleted_ids = (
            list(potential_deleted_ids - already_deleted_ids)
            if already_deleted_ids
            else list(potential_deleted_ids)
        )

        if new_deleted_ids:
            logging.info(f"Found {len(new_deleted_ids)} new deleted messages to mark")
            db.mark_messages_as_deleted(new_deleted_ids)
            logging.info(
                f"Deletion sync complete. {len(new_deleted_ids)} messages newly marked as deleted."
            )
            return len(new_deleted_ids)
        else:
            logging.info("No new deleted messages found")
            return None
    except Exception as e:
        logging.error(f"Error during deletion detection: {str(e)}")
        return None


def all_messages(
    credentials: Any,
    full_sync: bool = False,
    num_workers: int = DEFAULT_WORKERS,
    check_shutdown: Optional[Callable[[], bool]] = None,
    query: Optional[str] = None,
) -> int:
    """
    Fetches messages from the Gmail API using the provided credentials, in parallel.
    Also detects and marks deleted messages.

    Args:
        credentials (object): The credentials object for API authentication.
        full_sync (bool): If True, syncs all messages regardless of previous syncs.
        num_workers (int): Number of worker threads for parallel fetching.
        check_shutdown (callable): A callback that returns True if shutdown is requested.
        query (str, optional): A Gmail query string to filter messages.

    Returns:
        int: The number of messages successfully synced.
    """
    executor = None
    future_to_id = {}

    try:
        service = _create_service(credentials)
        labels = get_labels(service)
        all_message_ids = []
        base_query = query if query else ""

        if not full_sync:
            # Fetch messages newer than the last indexed
            last = db.last_indexed()
            if last:
                new_query = f"{base_query} after:{int(last.timestamp())}".strip()
                logging.info(f"Fetching new messages with query: {new_query}")
                all_message_ids.extend(
                    get_message_ids_from_gmail(service, new_query, check_shutdown)
                )

            # Fetch messages older than the first indexed (backfill)
            first = db.first_indexed()
            if first:
                old_query = f"{base_query} before:{int(first.timestamp())}".strip()
                logging.info(f"Backfilling old messages with query: {old_query}")
                all_message_ids.extend(
                    get_message_ids_from_gmail(service, old_query, check_shutdown)
                )

            # If it's the very first sync, there's no last or first, so run with the base query
            if not last and not first:
                logging.info(f"Performing initial sync with query: {base_query}")
                all_message_ids.extend(
                    get_message_ids_from_gmail(service, base_query, check_shutdown)
                )
        else:
            # Full sync requested
            logging.info(f"Performing full sync with query: {base_query}")
            all_message_ids = get_message_ids_from_gmail(
                service, base_query, check_shutdown
            )

        if check_shutdown and check_shutdown():
            logging.info(
                "Shutdown requested during message ID collection. Exiting gracefully."
            )
            return 0

        if full_sync:
            _detect_and_mark_deleted_messages(all_message_ids, check_shutdown)

        logging.info(f"Found {len(all_message_ids)} messages to sync.")

        total_synced_count = 0
        processed_count = 0

        def thread_worker(message_id: str) -> bool:
            if check_shutdown and check_shutdown():
                return False

            service = _create_service(credentials)

            try:
                msg = _fetch_message(
                    service,
                    message_id,
                    labels,
                    check_interrupt=check_shutdown,
                )
                try:
                    db.create_message(msg)
                    logging.info(
                        f"Successfully synced message {msg.id} (Original ID: {message_id}) from {msg.timestamp}"
                    )
                    return True
                except IntegrityError as e:
                    logging.error(
                        f"Could not process message {message_id} due to integrity error: {str(e)}"
                    )
                    return False
            except InterruptedError:
                logging.info(f"Message fetch for {message_id} was interrupted")
                return False
            except Exception as e:
                logging.error(f"Failed to fetch message {message_id}: {str(e)}")
                return False

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=num_workers
        ) as executor_instance:
            executor = executor_instance
            future_to_id = {
                executor.submit(thread_worker, msg_id): msg_id
                for msg_id in all_message_ids
            }

            for future in concurrent.futures.as_completed(future_to_id):
                if check_shutdown and check_shutdown() and not future.running():
                    continue

                message_id = future_to_id[future]
                processed_count += 1
                try:
                    if not future.cancelled():
                        if future.result():
                            total_synced_count += 1
                    if (
                        processed_count % PROGRESS_LOG_INTERVAL == 0
                        or processed_count == len(all_message_ids)
                    ):
                        logging.info(
                            f"Processed {processed_count}/{len(all_message_ids)} messages..."
                        )
                except concurrent.futures.CancelledError:
                    logging.info(
                        f"Task for message {message_id} was cancelled due to shutdown"
                    )
                except Exception as exc:
                    logging.error(
                        f"Message ID {message_id} generated an exception during future processing: {exc}"
                    )
                    logging.error(
                        f"Message ID {message_id} generated an exception during future processing: {exc}"
                    )

        if check_shutdown and check_shutdown():
            logging.info("Sync process was interrupted. Partial results saved.")
        else:
            logging.info(
                f"Total messages successfully synced: {total_synced_count} out of {len(all_message_ids)}"
            )
        return total_synced_count
    finally:
        pass


def sync_deleted_messages(
    credentials: Any, 
    check_shutdown: Optional[Callable[[], bool]] = None,
    query: Optional[str] = None,
) -> None:
    """
    Compares message IDs in Gmail with those in the database and marks missing messages as deleted.
    This function only updates the is_deleted flag and doesn't download full message content.
    It skips messages that are already marked as deleted for efficiency.

    Args:
        credentials: The credentials used to authenticate the Gmail API.
        check_shutdown (callable): A callback function that returns True if shutdown is requested.
        query (str, optional): A Gmail query string to filter messages.

    Returns:
        int: Number of messages marked as deleted.
    """
    try:
        service = _create_service(credentials)
        gmail_message_ids = get_message_ids_from_gmail(
            service, check_shutdown=check_shutdown, query=query
        )

        if check_shutdown and check_shutdown():
            logging.info(
                "Shutdown requested during message ID collection. Exiting gracefully."
            )
            return None

        _detect_and_mark_deleted_messages(gmail_message_ids, check_shutdown)
    except Exception as e:
        logging.error(f"Error during deletion sync: {str(e)}")
        return None


def single_message(
    credentials: Any,
    message_id: str,
    check_shutdown: Optional[Callable[[], bool]] = None,
) -> None:
    """
    Syncs a single message from Gmail using the provided credentials and message ID.

    Args:
        credentials: The credentials used to authenticate the Gmail API.
        message_id: The ID of the message to fetch.
        check_shutdown (callable): A callback function that returns True if shutdown is requested.

    Returns:
        None
    """
    try:
        service = _create_service(credentials)
        labels = get_labels(service)

        if check_shutdown and check_shutdown():
            logging.info("Shutdown requested. Exiting gracefully.")
            return None

        try:
            msg = _fetch_message(
                service,
                message_id,
                labels,
                check_interrupt=check_shutdown,
            )
            if check_shutdown and check_shutdown():
                logging.info(
                    "Shutdown requested after message fetch. Exiting gracefully."
                )
                return None

            try:
                db.create_message(msg)
                logging.info(
                    f"Successfully synced message {msg.id} (Original ID: {message_id}) from {msg.timestamp}"
                )
            except IntegrityError as e:
                logging.error(
                    f"Could not process message {message_id} due to integrity error: {str(e)}"
                )
        except InterruptedError:
            logging.info(f"Message fetch for {message_id} was interrupted")
        except Exception as e:
            logging.error(f"Failed to fetch message {message_id}: {str(e)}")
    finally:
        pass
