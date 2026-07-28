"""Centralized authentication module for Google APIs (Gmail, Calendar, etc.)."""

import os
from typing import List
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",  # For creating drafts
    "https://www.googleapis.com/auth/gmail.send",     # For sending emails
    "https://www.googleapis.com/auth/gmail.modify",   # For modifying labels/threads
    "https://www.googleapis.com/auth/calendar.readonly",  # For reading calendar events
    "https://www.googleapis.com/auth/calendar.events",   # For creating/modifying calendar events
]

CREDENTIALS_FILE = os.environ.get("CREDENTIALS_FILE", os.path.expanduser("~/.config/credentials.json"))
TOKEN_FILE = os.environ.get("TOKEN_FILE", os.path.join(os.path.dirname(os.path.abspath(__file__)), "token.json"))


def get_credentials(scopes: List[str] = None) -> Credentials:
    """
    Load or authenticate OAuth2 credentials for Google APIs.
    """
    if scopes is None:
        scopes = SCOPES

    creds = None
    if os.path.exists(TOKEN_FILE):
        try:
            creds = Credentials.from_authorized_user_file(TOKEN_FILE, scopes)
        except Exception:
            creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDENTIALS_FILE):
                raise FileNotFoundError(
                    f"Credentials file not found at {CREDENTIALS_FILE}. "
                    "Please set CREDENTIALS_FILE environment variable or place "
                    "client_secret.json at ~/.config/credentials.json"
                )
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, scopes)
            creds = flow.run_local_server(port=0)

        with open(TOKEN_FILE, "w", encoding="utf-8") as token:
            token.write(creds.to_json())

    return creds
