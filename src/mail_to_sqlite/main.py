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
    parser.add_argument(
        "--data-dir", help="The path where the data should be stored", required=True
    )
    parser.add_argument(
        "--provider", 
        help="Email provider to use (gmail or imap)",
        default="gmail",
        choices=["gmail", "imap"]
    )
    parser.add_argument(
        "--full-sync",
        help="Force a full sync of all messages",
        action="store_true",
    )
    parser.add_argument(
        "--message-id",
        help="The ID of a single message to sync",
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
    db_conn = db.init(args.data_dir)
    
    if args.message_id is None:
        sync.all_messages(args.provider, args.data_dir, full_sync=args.full_sync, 
                         clobber=args.clobber or [])
    else: 
        sync.single_message(args.provider, args.data_dir, args.message_id, 
                          clobber=args.clobber or [])

    db_conn.close()
