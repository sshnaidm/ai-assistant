"""This module provides a function to fetch emails from a Gmail account."""

import base64
import mimetypes
import os
from email import encoders
from email.mime.audio import MIMEAudio
from email.mime.base import MIMEBase
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List, Optional

# Try to import centralized logging, fall back to basic config if not available
try:
    from logging_config import setup_logging

    logger = setup_logging(__name__)
except ImportError:
    import logging

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s:%(lineno)d - %(message)s",
        handlers=[logging.FileHandler("mcp_gmail.log"), logging.StreamHandler()],
    )
    logger = logging.getLogger(__name__)

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# If modifying these scopes, delete the file token.json.
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",  # For creating drafts
    "https://www.googleapis.com/auth/gmail.send",  # For sending emails
    "https://www.googleapis.com/auth/calendar.readonly",  # For reading calendar events
    "https://www.googleapis.com/auth/calendar.events",  # For creating/modifying calendar events
]
CREDENTIALS_FILE = os.environ.get("CREDENTIALS_FILE", os.path.expanduser("~/.config/credentials.json"))

logger.info("gmail module initialized")


def get_message_body(payload: dict) -> str:
    """
    Parses a message payload to find the 'text/plain' part and decodes it.
    This function will recursively search through multipart messages.
    """
    logger.debug(f"Parsing message part with mimeType: {payload.get('mimeType')}")
    if "parts" in payload:
        for part in payload["parts"]:
            if part["mimeType"] == "text/plain":
                data = part["body"]["data"]
                logger.debug("Found text/plain part, decoding body.")
                return base64.urlsafe_b64decode(data).decode("utf-8")
            # Recursive call for nested multipart messages
            if "parts" in part:
                body = get_message_body(part)
                if body:
                    return body
    # Handle simple, non-multipart messages
    elif "body" in payload and "data" in payload["body"]:
        data = payload["body"]["data"]
        logger.debug("Found body in non-multipart message, decoding.")
        return base64.urlsafe_b64decode(data).decode("utf-8")
    logger.debug("No text/plain part found in this payload section.")
    return ""  # Return empty string if no plain text part is found


# pylint: disable=too-many-locals,too-many-statements
def get_emails(gmail_query: str = "to:me in:Inbox", count: int = 50, page: int = 1, full_body: bool = False):
    """Fetches emails based on the provided query.
    Args:
        gmail_query (str): Gmail query to filter emails. Default is 'to:me in:inbox'.
        count (int): Number of emails to fetch per page. Default is 100.
        page (int): Page number for pagination. Default is 1.
        full_body (bool): If True, fetches the full body of the email. If False, fetches only the snippet.
    Returns:
        str: A formatted string containing emails details.
    """
    logger.info(
        f"Starting get_emails with gmail_query='{gmail_query}' count='{count}' page='{page}', full_body='{full_body}'"
    )

    logger.info(f"Fetching emails with query='{gmail_query}', count={count}, page={page}, full_body={full_body}")
    creds = None
    # The file token.json stores the user's access and refresh tokens.
    if os.path.exists("token.json"):
        logger.info("Found token.json, loading credentials.")
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            logger.info("Credentials expired, refreshing token.")
            creds.refresh(Request())
        else:
            logger.info("No valid credentials found, starting OAuth flow.")
            # YOU MUST HAVE your credentials.json file from Google Cloud here
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open("token.json", "w", encoding="utf-8") as token:
            logger.info("Saving new credentials to token.json.")
            token.write(creds.to_json())

    try:
        service = build("gmail", "v1", credentials=creds)
        logger.info("Gmail service built successfully.")

        # Get a list of messages
        logger.info(f"Executing search with query: {gmail_query}")
        results = service.users().messages().list(userId="me", q=gmail_query).execute()  # pylint: disable=no-member

        messages = results.get("messages", [])

        if not messages:
            logger.warning(f"No messages found for query: {gmail_query}")
            return f"No messages found for query: {gmail_query}"
        logger.info(f"Found {len(messages)} messages for query: {gmail_query}")
        result = f"Found {len(messages)} messages for query: {gmail_query}\n"
        result += "--- Email Report ---\n"
        for message in messages[(page - 1) * count: page * count]:
            logger.debug(f"Fetching details for message ID: {message['id']}")
            msg = service.users().messages().get(userId="me", id=message["id"]).execute()  # pylint: disable=no-member
            headers = msg["payload"]["headers"]
            headers_dict = {header["name"]: header["value"] for header in headers}
            result += "#" * 10 + f" Message ID: {msg['id']} " + "#" * 10
            result += f"\nFrom: {headers_dict.get('From', 'Unknown Sender')}\n"
            result += f"Subject: {headers_dict.get('Subject', 'No Subject')}\n"
            if full_body:
                body = get_message_body(msg["payload"])
                result += f"Mail body: {body}\n"
            else:
                result += f"Snippet: {msg.get('snippet', 'No snippet available')}\n"
        return result
    except (ValueError, FileNotFoundError) as e:
        logger.error(f"An error occurred: {e}", exc_info=True)
        return f"An error occurred while fetching emails: {e}"


# pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-branches
def send_email(
    to: str | List[str],
    subject: str,
    body: str,
    from_email: Optional[str] = None,
    cc: Optional[str | List[str]] = None,
    bcc: Optional[str | List[str]] = None,
    attachments: Optional[List[str]] = None,
    html_body: Optional[str] = None,
    draft_mode: bool = True,  # Safety first - create draft by default
) -> str:
    """
    Send an email or create a draft via Gmail API.

    Args:
        to: Recipient email address(es). Can be string or list of strings.
        subject: Email subject line.
        body: Plain text body of the email.
        from_email: Optional sender email (must be authorized account or alias).
        cc: Optional CC recipients. Can be string or list of strings.
        bcc: Optional BCC recipients. Can be string or list of strings.
        attachments: Optional list of file paths to attach.
        html_body: Optional HTML version of the email body.
        draft_mode: If True (default), creates a draft. If False, sends immediately.

    Returns:
        str: Success message with email/draft ID or error message.
    """
    logger.info(
        f"Starting send_email with to='{to}', subject='{subject:20}'..., body='{body:20}'..., "
        f"from_email='{from_email}', cc='{cc}', bcc='{bcc}', attachments='{attachments}', html_body='{html_body}', "
        f"draft_mode={draft_mode}"
    )

    # Normalize recipients to lists
    if isinstance(to, str):
        to = [to]
    if cc and isinstance(cc, str):
        cc = [cc]
    if bcc and isinstance(bcc, str):
        bcc = [bcc]

    try:
        # Get credentials
        creds = None
        if os.path.exists("token.json"):
            logger.info("Found token.json, loading credentials.")
            creds = Credentials.from_authorized_user_file("token.json", SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                logger.info("Credentials expired, refreshing token.")
                creds.refresh(Request())
            else:
                logger.info("No valid credentials found, starting OAuth flow.")
                flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
                creds = flow.run_local_server(port=0)
            # Save the credentials
            with open("token.json", "w", encoding="utf-8") as token:
                logger.info("Saving new credentials to token.json.")
                token.write(creds.to_json())

        service = build("gmail", "v1", credentials=creds)
        logger.info("Gmail service built successfully.")

        # Create message
        if attachments and len(attachments) > 0:
            # Create multipart message for attachments
            message = MIMEMultipart()
        elif html_body:
            # Create multipart/alternative for HTML
            message = MIMEMultipart("alternative")
        else:
            # Simple text message
            message = MIMEText(body)

        # Set headers
        message["to"] = ", ".join(to)
        message["subject"] = subject
        if from_email:
            message["from"] = from_email
        if cc:
            message["cc"] = ", ".join(cc)
        if bcc:
            message["bcc"] = ", ".join(bcc)

        # Add body parts for multipart messages
        if isinstance(message, MIMEMultipart):
            # Add text part
            message.attach(MIMEText(body, "plain"))

            # Add HTML part if provided
            if html_body:
                message.attach(MIMEText(html_body, "html"))

            # Add attachments
            if attachments:
                for file_path in attachments:
                    if not os.path.isfile(file_path):
                        logger.warning(f"Attachment file not found: {file_path}")
                        continue

                    # Guess the content type
                    content_type, _ = mimetypes.guess_type(file_path)
                    if content_type is None:
                        content_type = "application/octet-stream"

                    main_type, sub_type = content_type.split("/", 1)

                    # Read file and create appropriate MIME type
                    with open(file_path, "rb") as fp:
                        if main_type == "text":
                            msg = MIMEText(fp.read().decode("utf-8"), _subtype=sub_type)
                        elif main_type == "image":
                            msg = MIMEImage(fp.read(), _subtype=sub_type)
                        elif main_type == "audio":
                            msg = MIMEAudio(fp.read(), _subtype=sub_type)
                        else:
                            msg = MIMEBase(main_type, sub_type)
                            msg.set_payload(fp.read())
                            encoders.encode_base64(msg)

                    # Add header with filename
                    filename = os.path.basename(file_path)
                    msg.add_header("Content-Disposition", "attachment", filename=filename)
                    message.attach(msg)
                    logger.info(f"Attached file: {filename}")

        # Encode message
        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
        body_message = {"raw": raw_message}

        if draft_mode:
            # Create draft
            draft = {"message": body_message}
            # pylint: disable=no-member
            result = service.users().drafts().create(userId="me", body=draft).execute()
            draft_id = result["id"]
            logger.info(f"Draft created with ID: {draft_id}")
            return f"Draft created successfully! Draft ID: {draft_id}\nSubject: {subject}\nTo: {', '.join(to)}"
        # Send email
        # pylint: disable=no-member
        result = service.users().messages().send(userId="me", body=body_message).execute()
        message_id = result["id"]
        logger.info(f"Email sent with ID: {message_id}")
        return f"Email sent successfully! Message ID: {message_id}\nSubject: {subject}\nTo: {', '.join(to)}"

    except HttpError as error:
        logger.error(f"An HTTP error occurred: {error}", exc_info=True)
        return f"Failed to {'create draft' if draft_mode else 'send email'}: {error}"
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error(f"An error occurred: {e}", exc_info=True)
        return f"An error occurred while {'creating draft' if draft_mode else 'sending email'}: {e}"


# Example usage:
# print(get_emails("to:me in:inbox", count=5, page=1, full_body=False))
# print(get_emails("Gemini OR 'Gemini API keys' OR Copilot OR 'Gemini CLI'", count=50, page=1, full_body=False))
# print(send_email(to="recipient@example.com", subject="Test", body="Hello!", draft_mode=True))
