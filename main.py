import argparse
import logging
import os
import signal  # Added for signal handling
import sys

import auth
import db
import sync


def prepare_data_dir(data_dir: str) -> None:
    """
    Get the project name from command line arguments and create a directory for it if it doesn't exist.

    Raises:
        ValueError: If project name is not provided.

    Returns:
        None
    """

    if not os.path.exists(data_dir):
        os.makedirs(data_dir)


def setup_signal_handler(shutdown_requested=None, executor=None, futures=None):
    """
    Set up a signal handler for graceful shutdown.

    Args:
        shutdown_requested: A mutable container (list) that holds the shutdown state.
                           shutdown_requested[0] will be set to True when shutdown is requested.
        executor: The executor instance to manage cancellation of tasks.
        futures: Dictionary mapping futures to their IDs.

    Returns:
        The original signal handler.
    """

    def handle_sigint(sig, frame):
        if shutdown_requested is not None:
            if not shutdown_requested[0]:
                logging.info(
                    "Shutdown requested. Waiting for current tasks to complete..."
                )
                shutdown_requested[0] = True

                # Cancel non-running futures if executor and futures are provided
                if executor and futures:
                    for future in list(futures.keys()):
                        if not future.running():
                            future.cancel()
            else:
                logging.warning("Forced shutdown. Exiting immediately.")
                sys.exit(1)
        else:
            # Fallback if shutdown_requested is None
            logging.warning(
                "Forced shutdown. No graceful shutdown available. Exiting immediately."
            )
            sys.exit(1)

    # Store the original handler
    original_sigint_handler = signal.getsignal(signal.SIGINT)
    signal.signal(signal.SIGINT, handle_sigint)
    return original_sigint_handler


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s: %(message)s",
        handlers=[logging.StreamHandler()],
    )

    parser = argparse.ArgumentParser()
    parser.add_argument("command", help="The command to run: {sync, sync-message}")
    parser.add_argument(
        "--data-dir", help="The path where the data should be stored", required=True
    )
    parser.add_argument(
        "--full-sync",
        help="Force a full sync of all messages",
        action="store_true",
    )
    parser.add_argument(
        "--message-id",
        help="The ID of the message to sync",
    )

    default_workers = max(1, os.cpu_count() or 4)
    parser.add_argument(
        "--workers",
        help="Number of worker threads for parallel fetching",
        type=int,
        default=default_workers,
    )

    args = parser.parse_args()

    prepare_data_dir(args.data_dir)
    credentials = auth.get_credentials(args.data_dir)

    # Set up shared shutdown flag for signal handling - using a list to make it mutable
    shutdown_state = [False]

    def check_shutdown():
        return shutdown_state[0]

    original_sigint_handler = setup_signal_handler(shutdown_requested=shutdown_state)

    try:
        db_conn = db.init(args.data_dir)
        if args.command == "sync":
            sync.all_messages(
                credentials,
                full_sync=args.full_sync,
                num_workers=args.workers,
                check_shutdown=check_shutdown,
            )
        elif args.command == "sync-message":
            if args.message_id is None:
                logging.error("Please provide a message ID for sync-message command.")
                sys.exit(1)
            sync.single_message(
                credentials, args.message_id, check_shutdown=check_shutdown
            )

        db_conn.close()
    finally:
        signal.signal(signal.SIGINT, original_sigint_handler)
