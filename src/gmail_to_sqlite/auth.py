import os

import google.oauth2
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
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

    creds = None
    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    if os.path.exists("token.json"):
      creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
      if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
      else:
        flow = InstalledAppFlow.from_client_secrets_file(
            "credentials.json", SCOPES
        )
        creds = flow.run_local_server(port=0)
      # Save the credentials for the next run
      with open("token.json", "w") as token:
        token.write(creds.to_json())

    return creds
