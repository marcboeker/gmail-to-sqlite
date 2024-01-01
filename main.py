import argparse
import os
import sys

from auth import get_auth
from db import Message, init_db
from messages import fetch_message, sync_messages


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


def index(data_dir: str):
    """
    Index command-line command.
    """

    credentials = get_auth(data_dir)
    sync_messages(credentials)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", help="The command to run: {index}")
    parser.add_argument(
        "--data-dir", help="The path where the data should be stored", required=True
    )

    args = parser.parse_args()

    prepare_data_dir(args.data_dir)

    db = init_db(args.data_dir)
    if args.command == "index":
        index(args.data_dir)

    db.close()
