"""This module provides a FastMCP tool for fetching emails from Gmail."""

import ast
import datetime
import json
import logging
import os
from typing import Any

from fastmcp import FastMCP

from gmail import get_emails, send_email

# Set up completely independent logging for this module
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
NUMERIC_LEVEL = getattr(logging, LOG_LEVEL, logging.INFO)

# Create logger for this module
logger = logging.getLogger(__name__)
logger.setLevel(NUMERIC_LEVEL)

# Remove any existing handlers to start fresh
logger.handlers = []

# Create file handler
file_handler = logging.FileHandler("mcp_gmail.log", mode="a")
file_handler.setLevel(NUMERIC_LEVEL)
file_formatter = logging.Formatter("%(asctime)s - %(filename)s:%(lineno)d - %(levelname)s - %(message)s")
file_handler.setFormatter(file_formatter)
logger.addHandler(file_handler)


# Create console handler with filtering for clean output
# pylint: disable=too-few-public-methods
class MCPConsoleFilter(logging.Filter):
    """Filter to only show logs from mcp_gmail, gmail, and main modules."""

    def filter(self, record):
        # Only show logs from our modules, not third-party libraries
        return record.name.startswith(("mcp_gmail", "gmail", "assistant", "__main__")) or record.name == "root"


console_handler = logging.StreamHandler()
console_handler.setLevel(NUMERIC_LEVEL)
console_formatter = logging.Formatter("%(asctime)s - %(filename)s:%(lineno)d - %(levelname)s - %(message)s")
console_handler.setFormatter(console_formatter)
console_handler.addFilter(MCPConsoleFilter())
logger.addHandler(console_handler)

# Don't propagate to root logger to keep it completely independent
logger.propagate = False

# Suppress noisy third-party loggers
noisy_loggers = [
    "PIL",
    "PIL.Image",
    "asyncio",
    "urllib3",
    "urllib3.connectionpool",
    "httpcore",
    "httpcore.connection",
    "httpcore.http11",
    "httpx",
    "gradio",
    "matplotlib",
    "websockets",
    "anyio",
    "starlette",
    "fastapi",
    "uvicorn",
    "multipart",
    "mcp.server",
]

for noisy_logger in noisy_loggers:
    third_party_logger = logging.getLogger(noisy_logger)
    third_party_logger.setLevel(logging.WARNING)
    third_party_logger.propagate = False

logger.info(f"mcp_gmail logging configured - Level: {LOG_LEVEL}")


# Log that this module is initialized
logger.info("mcp_gmail module initialized")

# Initialize FastMCP server
logger.info("Initializing FastMCP server with name 'gmail_mails'")
mcp = FastMCP(
    name="gmail_mails",
    instructions=(
        "Interact with Gmail: fetch emails, create drafts, and send emails using the Gmail API. "
        "Drafts are created by default for safety."
    ),
)
logger.debug("FastMCP server initialized successfully")


def parse_input(input_str: str) -> dict:
    """
    Parse the input string into a dictionary.
    """
    input_str = input_str.strip()
    try:
        return json.loads(input_str)
    except json.JSONDecodeError:
        return ast.literal_eval(input_str.replace("null", "None").replace("true", "True").replace("false", "False"))


@mcp.tool(
    name="List Available Tools",
    description="List all available tools.",
)
def list_gmail_tools() -> str:
    """List all available tools."""
    logger.info("Listing available tools")
    try:
        tools = mcp.list_tools()  # type: ignore # pylint: disable=no-member
        logger.debug(f"Available tools: {tools}")
        return tools
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error(f"Error listing tools: {e}", exc_info=True)
        return f"Error listing tools: {e}"


@mcp.tool(
    name="Get Emails from Gmail",
    description="""
    Fetch Gmail emails using a query. Supports filtering, page size, pagination, and snippet/full body.

    Input should be a JSON object with the following fields (string forms are accepted and parsed):
    - `gmail_query` (str): Gmail search query. Default: "to:me in:inbox".
      Dates can be specified in the format "YYYY-MM-DD", e.g. "after:2023-01-01 before:2023-01-31".
    - `count` (int|str): Emails per page. Default: 100. Range: 1..1000.
    - `page` (int|str): Page number. Default: 1. Minimum: 1.
    - `full_body` (bool|str): If true, include full body; otherwise include snippet. Default: false.

    Example:
    {"gmail_query": "to:me in:inbox", "count": 100, "page": 1, "full_body": false}
    {"gmail_query": "in:inbox subject:meeting"}
    {"gmail_query": "from:user in:inbox", count: 50, page: 1, full_body: True}
    {"gmail_query": "to:me", count: 50}

    Requires a Google OAuth client secrets file available via the `CREDENTIALS_FILE` environment variable.
    """,
)
def get_emails_tool(
    # Parameters may arrive as strings from upstream models; we parse them below.
    gmail_query: Any = "to:me in:inbox",
    count: Any = 100,
    page: Any = 1,
    full_body: Any = False,
) -> str:
    """Fetches emails based on the provided query."""

    logger.info(f"get_emails_tool called with query='{gmail_query}', count={count}, page={page}, full_body={full_body}")

    # Check if gmail_query is a JSON string
    if isinstance(gmail_query, str) and gmail_query.strip().startswith("{") and gmail_query.strip().endswith("}"):
        logger.debug("Detected JSON string in 'gmail_query' parameter, parsing...")
        params = parse_input(gmail_query)
        logger.debug(f"Parsed JSON: {params}")

        gmail_query = params.get("gmail_query", gmail_query)
        count = params.get("count", count)
        page = params.get("page", page)
        full_body = params.get("full_body", full_body)

        logger.debug("After JSON parsing:")
        logger.debug(f"  gmail_query: {gmail_query!r}")
        logger.debug(f"  count: {count!r}")
        logger.debug(f"  page: {page!r}")
        logger.debug(f"  full_body: {full_body!r}")

    try:
        logger.info("Calling get_emails with validated parameters")
        result = get_emails(gmail_query, count, page, full_body)
        logger.info(f"Successfully fetched emails, result length: {len(result)} chars")
        return result
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error(f"Error while fetching emails: {e}", exc_info=True)
        return f"Error while fetching emails: {e}"


@mcp.tool(
    name="Send or Draft Email via Gmail",
    description="""
    Send an email or create a draft via Gmail API. Supports multipart messages with attachments.

    SAFETY: By default, creates a DRAFT (does not send). Set draft_mode=false to send immediately.

    Input should be a JSON object with the following fields (string forms are accepted and parsed):
    - `to` (str|list): Recipient email(s). Required.
    - `subject` (str): Email subject.
    - `body` (str): Plain text body.
    - `from_email` (str): Optional sender email (must be authorized account or alias).
    - `cc` (str|list): Optional CC recipients.
    - `bcc` (str|list): Optional BCC recipients.
    - `attachments` (list): Optional list of file paths to attach.
    - `html_body` (str): Optional HTML version of the email body.
    - `draft_mode` (bool|str): If true (DEFAULT), creates draft. If false, sends immediately.

    Example:
    {"to": "user@example.com", "subject": "Hello", "body": "Message body", "draft_mode": true}
    {
        "to": "user@example.com", "subject": "Hello", "body": "Message body", "draft_mode": true,
        "from_email": "sender@example.com", "cc": "user2@example.com", "bcc": "user3@example.com",
        "attachments": ["/path/to/attachment1", "/path/to/attachment2"],
        "html_body": "<p>HTML version of the email body</p>"
    }
    {
        "to": "user@example.com, user2@example.com", "subject": "Hello", "body": "Message body", "draft_mode": true,
        "from_email": "sender@example.com", "cc": "user2@example.com, user3@example.com",
        "bcc": "user4@example.com, user5@example.com",
        "attachments": ["/path/to/attachment1", "/path/to/attachment2"],
        "html_body": "<p>HTML version of the email body</p>"
    }

    Requires Gmail compose/send permissions in addition to read permissions.

   """,
)
# pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-branches,too-many-locals
def send_email_tool(
    to: Any,
    subject: Any = None,
    body: Any = None,
    from_email: Any = None,
    cc: Any = None,
    bcc: Any = None,
    attachments: Any = None,
    html_body: Any = None,
    draft_mode: Any = True,  # Safety first - draft by default
) -> str:
    """Send an email or create a draft via Gmail API."""

    # Safe formatting for info level - handle None values
    subject_preview = (str(subject)[:20] + "...") if subject else "None"
    body_preview = (str(body)[:20] + "...") if body else "None"
    logger.info(
        f"send_email_tool called: to='{to}', subject='{subject_preview}', body='{body_preview}', "
        f"draft_mode={draft_mode}"
    )

    # Check if 'to' is a JSON string
    if isinstance(to, str) and to.strip().startswith("{") and to.strip().endswith("}"):
        logger.debug("Detected JSON string in 'to' parameter, parsing...")
        params = parse_input(to)
        logger.debug(f"Parsed JSON: {params}")

        to = params.get("to")
        subject = params.get("subject", subject)
        body = params.get("body", body)
        from_email = params.get("from_email", from_email)
        cc = params.get("cc", cc)
        bcc = params.get("bcc", bcc)
        attachments = params.get("attachments", attachments)
        html_body = params.get("html_body", html_body)
        draft_mode = params.get("draft_mode", draft_mode)

        logger.debug(
            "JSON parsed parameters to:{to!r}, subject:{subject!r}, body:{body!r}, draft_mode:{draft_mode!r}, "
            "from_email:{from_email!r}, cc:{cc!r}, bcc:{bcc!r}, attachments:{attachments!r}, html_body:{html_body!r}"
        )

    # Parse attachments - ensure it's a list
    if attachments:
        if isinstance(attachments, str):
            attachments = [attachments]
        elif not isinstance(attachments, list):
            attachments = list(attachments)
        logger.debug(f"Attachments parsed: {attachments}")

    # Validate required fields
    if not to:
        logger.warning("Missing required field: 'to'")
        return "Validation error: 'to' field is required."
    if not subject:
        logger.warning("Missing required field: 'subject'")
        return "Validation error: 'subject' field is required."
    if not body:
        logger.warning("Missing required field: 'body'")
        return "Validation error: 'body' field is required."

    # Safe formatting for validation log
    subject_display = (str(subject)[:50] + "...") if subject and len(str(subject)) > 50 else str(subject)
    logger.info(f"Validated email params - to: {to}, subject: '{subject_display}', draft_mode: {draft_mode}")

    try:
        action = "creating draft" if draft_mode else "sending email"
        logger.info(f"{action.capitalize()} for recipients: {to}")
        result = send_email(
            to=to,
            subject=subject,
            body=body,
            from_email=from_email,
            cc=cc,
            bcc=bcc,
            attachments=attachments,
            html_body=html_body,
            draft_mode=draft_mode,
        )
        logger.info(f"Successfully completed {action}")
        return result
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error(f"Error while {action}: {e}", exc_info=True)
        return f"Error while {action}: {e}"


@mcp.tool(
    name="Get Today's Date",
    description=(
        'Get today\'s date with weekday as JSON. Returns: {"date": "YYYY-MM-DD", "weekday": "Monday"}. '
        "Doesn't require any input parameters."
    ),
)
def get_today_date(test) -> str:
    """Return today's date and weekday as a JSON string."""
    logger.debug("get_today_date called")
    logger.debug(f"get_today_date Test parameter: {test}")
    now = datetime.datetime.now()
    payload = {
        "date": now.strftime("%Y-%m-%d"),
        "weekday": now.strftime("%A"),
    }
    result = json.dumps(payload)
    logger.debug(f"Returning date payload: {result}")
    return result


if __name__ == "__main__":
    logger.info("Starting MCP Gmail server...")

    credentials_file = os.getenv("CREDENTIALS_FILE")
    if not credentials_file:
        logger.error("CREDENTIALS_FILE environment variable is not set")
        raise ValueError("CREDENTIALS_FILE environment variable is not set for the server to run.")

    logger.info(f"Using credentials file: {credentials_file}")
    logger.info("Starting FastMCP server on default port...")

    try:
        # Run the FastMCP server
        mcp.run()
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error(f"Server error: {e}", exc_info=True)
        raise
