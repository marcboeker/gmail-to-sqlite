import argparse
import os
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", help="The command to run: {sync}")
    parser.add_argument(
        "--data-dir", help="The path where the data should be stored", required=True
    )
    parser.add_argument(
        "--only-new",
        help="Fetch only the messages that have not been synced before",
        action="store_true",
    )
    parser.add_argument(
        "--exclude-raw",
        help="Do not store raw messages in the database",
        action="store_true",
    )

    args = parser.parse_args()

    prepare_data_dir(args.data_dir)
    credentials = auth.get_credentials(args.data_dir)

    db = db.init(args.data_dir)
    if args.command == "sync":
        sync.all_messages(
            credentials, only_new=args.only_new, exclude_raw=args.exclude_raw
        )
        # sync.single_message(
        #     credentials, "", exclude_raw=args.exclude_raw
        # )

    db.close()
