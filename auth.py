import os
from typing import Any, Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from constants import GMAIL_SCOPES, OAUTH2_CREDENTIALS_FILE, TOKEN_FILE_NAME


class AuthenticationError(Exception):
    """Custom exception for authentication-related errors."""

    pass


def get_credentials(data_dir: str) -> Any:
    """
    Retrieves the authentication credentials for the specified data_dir by either loading
    them from the token file or by running the authentication flow.

    Args:
        data_dir (str): The path where to store data.

    Returns:
        Any: The authentication credentials (compatible with Google API clients).

    Raises:
        AuthenticationError: If credentials cannot be obtained or are invalid.
        FileNotFoundError: If the OAuth2 credentials file is not found.
    """
    if not os.path.exists(OAUTH2_CREDENTIALS_FILE):
        raise FileNotFoundError(f"{OAUTH2_CREDENTIALS_FILE} not found")

    token_file_path = os.path.join(data_dir, TOKEN_FILE_NAME)
    creds: Optional[Any] = None

    # Load existing credentials if available
    if os.path.exists(token_file_path):
        try:
            creds = Credentials.from_authorized_user_file(token_file_path, GMAIL_SCOPES)
        except Exception as e:
            raise AuthenticationError(f"Failed to load existing credentials: {e}")

    # Refresh or obtain new credentials if needed
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                raise AuthenticationError(f"Failed to refresh credentials: {e}")
        else:
            try:
                flow = InstalledAppFlow.from_client_secrets_file(
                    OAUTH2_CREDENTIALS_FILE, GMAIL_SCOPES
                )
                # The flow returns credentials that may be of different types
                # but all are compatible with the API usage
                flow_creds = flow.run_local_server(port=0)
                creds = flow_creds
            except Exception as e:
                raise AuthenticationError(f"Failed to obtain new credentials: {e}")

        # Save credentials for future use
        if creds:
            try:
                with open(token_file_path, "w") as token:
                    token.write(creds.to_json())
            except Exception as e:
                raise AuthenticationError(f"Failed to save credentials: {e}")

    if not creds:
        raise AuthenticationError("Failed to obtain valid credentials")

    return creds
