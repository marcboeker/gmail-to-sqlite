import argparse
import os
import sys

from . import auth
from . import db
from . import sync


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


def main():
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

    parser.add_argument(
        "--clobber",
        help="attributes to clobber. Options: " +
             "thread_id, sender, recipients, subject, body, size, timestamp, is_outgoing, " +
             "is_read, labels",
        nargs="*"
    )

    args = parser.parse_args()

    prepare_data_dir(args.data_dir)
    credentials = auth.get_credentials(args.data_dir)

    db_conn = db.init(args.data_dir)
    if args.command == "sync":
        sync.all_messages(credentials, full_sync=args.full_sync, clobber=args.clobber or [])
    elif args.command == "sync-message":
        if args.message_id is None:
            print("Please provide a message ID")
            sys.exit(1)
        sync.single_message(credentials, args.message_id, clobber=args.clobber or [])

    db_conn.close()
