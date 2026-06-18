"""
Shared Gmail auth — used by both the Email Intel agent (read) and the report sender (send).
Scopes cover read + send so one token covers both.
"""
import base64
import os
import pickle
from pathlib import Path

from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
]

JARVIS_ROOT = Path(__file__).parent
CREDENTIALS_PATH = JARVIS_ROOT / "credentials.json"
TOKEN_PATH = JARVIS_ROOT / "token.pickle"


def _write_from_env(env_var: str, path: Path) -> None:
    """Decode a base64 env var and write it to disk if the file isn't already there."""
    value = os.getenv(env_var)
    if value and not path.exists():
        value = value.strip().replace("\n", "").replace("\r", "").replace(" ", "")
        value += "=" * (-len(value) % 4)
        path.write_bytes(base64.b64decode(value))


_write_from_env("GOOGLE_CREDENTIALS_B64", CREDENTIALS_PATH)
_write_from_env("GOOGLE_TOKEN_B64", TOKEN_PATH)


def get_gmail_service():
    creds = None
    if TOKEN_PATH.exists():
        with open(TOKEN_PATH, "rb") as f:
            creds = pickle.load(f)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_PATH), SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_PATH, "wb") as f:
            pickle.dump(creds, f)

    return build("gmail", "v1", credentials=creds)
