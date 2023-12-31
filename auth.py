import json
import os

import google.oauth2
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
OAUTH2_CREDENTIALS = "credentials.json"


def get_auth(project: str) -> google.oauth2.credentials.Credentials:
    """
    Retrieves the authentication credentials for the specified project by either loading
    it from the <project>/credentials.json file or by running the authentication flow.

    Args:
        project (str): The name of the project.

    Returns:
        google.oauth2.credentials.Credentials: The authentication credentials.
    """

    if not os.path.exists(OAUTH2_CREDENTIALS):
        raise ValueError("credentials.json not found")

    flow = InstalledAppFlow.from_client_secrets_file(OAUTH2_CREDENTIALS, SCOPES)

    credentials_file = f"{project}/credentials.json"
    if not os.path.exists(credentials_file):
        credentials = flow.run_local_server(port=0)
        with open(credentials_file, "w") as f:
            f.write(credentials.to_json())
    else:
        with open(credentials_file, "r") as f:
            credentials_dict = json.load(f)
        credentials = google.oauth2.credentials.Credentials.from_authorized_user_info(
            credentials_dict
        )

    return credentials
