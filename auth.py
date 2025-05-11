import json
import os

import google.oauth2
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
OAUTH2_CREDENTIALS = "credentials.json"


def get_credentials(data_dir: str) -> google.oauth2.credentials.Credentials:
    """
    Retrieves the authentication credentials for the specified data_dir by either loading
    it from the <data_dir>/credentials.json file or by running the authentication flow.

    Args:
        data_dir (str): The path where to store data.

    Returns:
        google.oauth2.credentials.Credentials: The authentication credentials.
    """

    if not os.path.exists(OAUTH2_CREDENTIALS):
        raise ValueError("credentials.json not found")

    flow = InstalledAppFlow.from_client_secrets_file(OAUTH2_CREDENTIALS, SCOPES)

    stored_token_file = f"{data_dir}/token.json"
    if not os.path.exists(stored_token_file):
        credentials = flow.run_local_server(port=0)
        with open(stored_token_file, "w") as f:
            f.write(credentials.to_json())
    else:
        with open(stored_token_file, "r") as f:
            credentials_dict = json.load(f)
        credentials = google.oauth2.credentials.Credentials.from_authorized_user_info(
            credentials_dict
        )

    return credentials
