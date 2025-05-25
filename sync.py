import concurrent.futures
import logging
import signal
import socket
import time
from email.utils import parseaddr, parsedate_to_datetime

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from peewee import IntegrityError

import db
import message

MAX_RESULTS = 500


def _fetch_message(service, message_id: str, labels: dict, check_interrupt=None):
    """
    Fetches a single message from Gmail API with retry logic.

    Args:
        service: The Gmail API service object.
        message_id: The ID of the message to fetch.
        labels: Dictionary of labels mapping ID to name.
        check_interrupt: Optional callback function that returns True if process should be interrupted.

    Returns:
        Message object if successful.

    Raises:
        HttpError: If the message cannot be fetched from the Gmail API.
        TimeoutError: If the request times out.
        Exception: For any other unexpected errors.
        InterruptedError: If the process was interrupted by check_interrupt.
    """
    max_retries = 3
    retry_delay_seconds = 5

    for attempt in range(max_retries):
        if check_interrupt and check_interrupt():
            raise InterruptedError("Process was interrupted")

        try:
            raw_msg = (
                service.users().messages().get(userId="me", id=message_id).execute()
            )
            msg = message.Message.from_raw(raw_msg, labels)
            return msg
        except HttpError as e:
            if e.resp.status >= 500 and attempt < max_retries - 1:
                logging.warning(
                    f"Attempt {attempt + 1}/{max_retries} failed for message {message_id} due to server error {e.resp.status}. Retrying in {retry_delay_seconds}s..."
                )
                if check_interrupt and check_interrupt():
                    raise InterruptedError("Process was interrupted")
                time.sleep(retry_delay_seconds)
            else:
                logging.error(
                    f"Failed to fetch message {message_id} after {attempt + 1} attempts due to HttpError {e.resp.status}: {str(e)}"
                )
                raise
        except (TimeoutError, socket.timeout) as e:
            if attempt < max_retries - 1:
                logging.warning(
                    f"Attempt {attempt + 1}/{max_retries} failed for message {message_id} due to timeout. Retrying in {retry_delay_seconds}s..."
                )
                if check_interrupt and check_interrupt():
                    raise InterruptedError("Process was interrupted")
                time.sleep(retry_delay_seconds)
            else:
                logging.error(
                    f"Failed to fetch message {message_id} after {attempt + 1} attempts due to timeout: {str(e)}"
                )
                raise
        except Exception as e:
            logging.error(
                f"An unexpected error occurred while processing message {message_id} on attempt {attempt + 1}: {str(e)}"
            )
            if attempt < max_retries - 1:
                if check_interrupt and check_interrupt():
                    raise InterruptedError("Process was interrupted")
                time.sleep(retry_delay_seconds)
            else:
                raise

    logging.error(f"Failed to fetch message {message_id} after all retries.")
    raise RuntimeError(
        f"Failed to fetch message {message_id} after {max_retries} attempts"
    )


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


def all_messages(
    credentials,
    full_sync=False,
    num_workers: int = 4,
    check_shutdown=None,
) -> int:
    """
    Fetches messages from the Gmail API using the provided credentials, in parallel.

    Args:
        credentials (object): The credentials object used to authenticate the API request.
        db_conn (object): The database connection object.
        full_sync (bool): Whether to do a full sync or not.
        num_workers (int): Number of worker threads for parallel fetching.
        check_shutdown (callable): A callback function that returns True if shutdown is requested.

    Returns:
        int: The number of messages successfully synced.
    """
    executor = None
    future_to_id = {}

    try:
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
        while run and not (check_shutdown and check_shutdown()):
            try:
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
            except KeyboardInterrupt:
                break

        if check_shutdown and check_shutdown():
            logging.info(
                "Shutdown requested during message ID collection. Exiting gracefully."
            )
            return 0

        logging.info(f"Found {len(all_message_ids)} messages to sync.")

        total_synced_count = 0
        processed_count = 0

        def thread_worker(message_id):
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
                    if processed_count % 50 == 0 or processed_count == len(
                        all_message_ids
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

        if check_shutdown and check_shutdown():
            logging.info("Sync process was interrupted. Partial results saved.")
        else:
            logging.info(
                f"Total messages successfully synced: {total_synced_count} out of {len(all_message_ids)}"
            )
        return total_synced_count
    finally:
        # Signal handler restoration is now handled in main.py
        pass


def single_message(credentials, message_id: str, check_shutdown=None) -> None:
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
        # Signal handler restoration is now handled in main.py
        pass
