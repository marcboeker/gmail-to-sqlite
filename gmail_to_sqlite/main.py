import argparse
import logging
import os
import signal
import sys
from typing import Any, Callable, List, Optional

from . import auth, db, sync
from .constants import DEFAULT_WORKERS, LOG_FORMAT


class ApplicationError(Exception):
    """Custom exception for application-level errors."""

    pass


def prepare_data_dir(data_dir: str) -> None:
    """
    Create the data directory if it doesn't exist.

    Args:
        data_dir (str): The path where to store data.

    Raises:
        ApplicationError: If directory creation fails.
    """
    try:
        if not os.path.exists(data_dir):
            os.makedirs(data_dir)
    except Exception as e:
        raise ApplicationError(f"Failed to create data directory {data_dir}: {e}")


def setup_signal_handler(
    shutdown_requested: Optional[List[bool]] = None,
    executor: Any = None,
    futures: Any = None,
) -> Any:
    """
    Set up a signal handler for graceful shutdown.

    Args:
        shutdown_requested: Mutable container for shutdown state.
        executor: The executor instance to manage task cancellation.
        futures: Dictionary mapping futures to their IDs.

    Returns:
        The original signal handler.
    """

    def handle_sigint(sig: Any, frame: Any) -> None:
        if shutdown_requested is not None:
            if not shutdown_requested[0]:
                logging.info(
                    "Shutdown requested. Waiting for current tasks to complete..."
                )
                shutdown_requested[0] = True

                # Cancel non-running futures if provided
                if executor and futures:
                    for future in list(futures.keys()):
                        if not future.running():
                            future.cancel()
            else:
                logging.warning("Forced shutdown. Exiting immediately.")
                sys.exit(1)
        else:
            logging.warning(
                "Forced shutdown. No graceful shutdown available. Exiting immediately."
            )
            sys.exit(1)

    original_sigint_handler = signal.getsignal(signal.SIGINT)
    signal.signal(signal.SIGINT, handle_sigint)
    return original_sigint_handler


def setup_logging() -> None:
    """Set up application logging configuration."""
    logging.basicConfig(
        level=logging.INFO,
        format=LOG_FORMAT,
        handlers=[logging.StreamHandler()],
    )


def create_argument_parser() -> argparse.ArgumentParser:
    """Create and configure the command line argument parser."""
    parser = argparse.ArgumentParser(
        description="Gmail to SQLite synchronization tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Commands:
  sync                     Sync all messages (incremental by default)
  sync-message             Sync a single message by ID
  sync-deleted-messages    Detect and mark deleted messages

Examples:
  %(prog)s sync --data-dir ./data
  %(prog)s sync --data-dir ./data --full-sync
  %(prog)s sync-message --data-dir ./data --message-id abc123
        """,
    )

    parser.add_argument(
        "command",
        choices=["sync", "sync-message", "sync-deleted-messages"],
        help="The command to run",
    )
    parser.add_argument(
        "--data-dir", required=True, help="The path where the data should be stored"
    )
    parser.add_argument(
        "--full-sync",
        action="store_true",
        help="Force a full sync of all messages and detect deleted messages",
    )
    parser.add_argument(
        "--message-id",
        help="The ID of the message to sync (required for sync-message command)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=DEFAULT_WORKERS,
        help=f"Number of worker threads for parallel fetching (default: {DEFAULT_WORKERS})",
    )

    return parser


def main() -> None:
    """Main application entry point."""
    setup_logging()

    try:
        parser = create_argument_parser()
        args = parser.parse_args()

        # Validate command-specific arguments
        if args.command == "sync-message" and not args.message_id:
            parser.error("--message-id is required for sync-message command")

        prepare_data_dir(args.data_dir)
        credentials = auth.get_credentials(args.data_dir)

        # Set up shutdown handling
        shutdown_state = [False]

        def check_shutdown() -> bool:
            return shutdown_state[0]

        original_sigint_handler = setup_signal_handler(
            shutdown_requested=shutdown_state
        )

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
                sync.single_message(
                    credentials, args.message_id, check_shutdown=check_shutdown
                )
            elif args.command == "sync-deleted-messages":
                sync.sync_deleted_messages(credentials, check_shutdown=check_shutdown)

            db_conn.close()
            logging.info("Operation completed successfully")

        except (auth.AuthenticationError, db.DatabaseError, sync.SyncError) as e:
            logging.error(f"Operation failed: {e}")
            sys.exit(1)
        except Exception as e:
            logging.error(f"Unexpected error: {e}")
            sys.exit(1)
        finally:
            signal.signal(signal.SIGINT, original_sigint_handler)

    except KeyboardInterrupt:
        logging.info("Operation cancelled by user")
        sys.exit(0)


if __name__ == "__main__":
    main()
