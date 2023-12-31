import os
import sys

from auth import get_auth
from db import Message, init_db
from messages import fetch_message, fetch_messages


def get_project():
    """
    Get the project name from command line arguments and create a directory for it if it doesn't exist.

    Raises:
        ValueError: If project name is not provided.

    Returns:
        str: The project name.
    """
    if len(sys.argv) < 2:
        raise ValueError("Project name must be provided")
    project = sys.argv[1]

    if not os.path.exists(project):
        os.makedirs(project)

    return project


if __name__ == "__main__":
    project = get_project()
    db = init_db(project)
    credentials = get_auth(project)
    # Fetch a single message by ID
    # fetch_message(credentials, "<message_id>")
    fetch_messages(credentials)
    db.close()
