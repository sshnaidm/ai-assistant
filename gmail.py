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
from pathlib import Path
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
        handlers=[
            logging.FileHandler(Path(__file__).resolve().parent / "mcp_gmail.log"),
            logging.StreamHandler(),
        ],
    )
    logger = logging.getLogger(__name__)

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from auth import get_credentials

logger.info("gmail module initialized")


def get_gmail_service():
    """Build and return Gmail API service using central auth."""
    creds = get_credentials()
    return build("gmail", "v1", credentials=creds)


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


def get_emails(gmail_query: str = "to:me in:Inbox", count: int = 50, page: int = 1, full_body: bool = False):
    """Fetches emails based on the provided query."""
    logger.info(
        f"Starting get_emails with gmail_query='{gmail_query}' count='{count}' page='{page}', full_body='{full_body}'"
    )

    count = int(count)
    page = int(page)
    if isinstance(full_body, str):
        full_body = full_body.lower() in ("true", "1", "yes")

    try:
        service = get_gmail_service()
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
        service = get_gmail_service()
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


def get_thread(thread_id: str) -> str:
    """Fetch all messages in a specific email thread by thread_id."""
    logger.info(f"Fetching thread with ID: {thread_id}")
    try:
        service = get_gmail_service()
        thread = service.users().threads().get(userId="me", id=thread_id).execute()
        messages = thread.get("messages", [])

        if not messages:
            return f"No messages found for thread ID: {thread_id}"

        result = f"--- Thread Report (ID: {thread_id}, {len(messages)} messages) ---\n"
        for msg in messages:
            headers = {h["name"]: h["value"] for h in msg["payload"].get("headers", [])}
            result += f"\nMessage ID: {msg['id']}\n"
            result += f"From: {headers.get('From', 'Unknown')}\n"
            result += f"To: {headers.get('To', 'Unknown')}\n"
            result += f"Date: {headers.get('Date', 'Unknown')}\n"
            result += f"Subject: {headers.get('Subject', 'No Subject')}\n"
            body = get_message_body(msg["payload"])
            result += f"Body:\n{body}\n"
            result += "-" * 40 + "\n"

        return result
    except Exception as e:
        logger.error(f"Error fetching thread {thread_id}: {e}", exc_info=True)
        return f"An error occurred while fetching thread: {e}"


def reply_to_email(
    thread_id: str,
    body: str,
    to: Optional[str] = None,
    subject: Optional[str] = None,
    html_body: Optional[str] = None,
    draft_mode: bool = True,
) -> str:
    """Reply to an existing email thread."""
    logger.info(f"Replying to thread ID: {thread_id}")
    try:
        service = get_gmail_service()
        thread = service.users().threads().get(userId="me", id=thread_id).execute()
        messages = thread.get("messages", [])

        if not messages:
            return f"Thread {thread_id} not found."

        last_msg = messages[-1]
        headers = {h["name"]: h["value"] for h in last_msg["payload"].get("headers", [])}

        if not to:
            to = headers.get("Reply-To") or headers.get("From")
        if not subject:
            orig_subject = headers.get("Subject", "")
            subject = orig_subject if orig_subject.lower().startswith("re:") else f"Re: {orig_subject}"

        message_id_header = headers.get("Message-ID") or headers.get("Message-Id")

        message = MIMEText(body, "plain") if not html_body else MIMEMultipart("alternative")
        if html_body:
            message.attach(MIMEText(body, "plain"))
            message.attach(MIMEText(html_body, "html"))

        message["to"] = to
        message["subject"] = subject
        if message_id_header:
            message["In-Reply-To"] = message_id_header
            message["References"] = message_id_header

        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
        body_message = {"raw": raw_message, "threadId": thread_id}

        if draft_mode:
            draft = {"message": body_message}
            res = service.users().drafts().create(userId="me", body=draft).execute()
            return f"Reply draft created successfully! Draft ID: {res['id']}\nThread ID: {thread_id}"
        res = service.users().messages().send(userId="me", body=body_message).execute()
        return f"Reply sent successfully! Message ID: {res['id']}\nThread ID: {thread_id}"
    except Exception as e:
        logger.error(f"Error replying to thread {thread_id}: {e}", exc_info=True)
        return f"Failed to reply to thread: {e}"


def modify_labels(
    message_id: str,
    add_labels: Optional[List[str]] = None,
    remove_labels: Optional[List[str]] = None,
) -> str:
    """Modify labels on a message (e.g. archive by removing INBOX, star by adding STARRED, mark read)."""
    logger.info(f"Modifying labels for message {message_id}")
    try:
        service = get_gmail_service()
        body = {
            "addLabelIds": add_labels or [],
            "removeLabelIds": remove_labels or [],
        }
        res = service.users().messages().modify(userId="me", id=message_id, body=body).execute()
        return f"Labels modified successfully for message {message_id}. Current labels: {res.get('labelIds', [])}"
    except Exception as e:
        logger.error(f"Error modifying labels for message {message_id}: {e}", exc_info=True)
        return f"Failed to modify labels: {e}"


# Example usage:
# print(get_emails("to:me in:inbox", count=5, page=1, full_body=False))
# print(get_emails("Gemini OR 'Gemini API keys' OR Copilot OR 'Gemini CLI'", count=50, page=1, full_body=False))
# print(send_email(to="recipient@example.com", subject="Test", body="Hello!", draft_mode=True))
