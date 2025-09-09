"""This module provides a FastMCP tool for working with Google Calendar."""

import ast
import datetime
import json
import logging
import os
from typing import Any

from fastmcp import FastMCP

from google_calendar import (
    create_event,
    delete_event,
    find_meeting_slots,
    get_events,
    get_free_busy,
    update_event,
)

# Set up completely independent logging for this module
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
NUMERIC_LEVEL = getattr(logging, LOG_LEVEL, logging.INFO)

# Create logger for this module
logger = logging.getLogger(__name__)
logger.setLevel(NUMERIC_LEVEL)

# Remove any existing handlers to start fresh
logger.handlers = []

# Create file handler
file_handler = logging.FileHandler("mcp_calendar.log", mode="a")
file_handler.setLevel(NUMERIC_LEVEL)
file_formatter = logging.Formatter("%(asctime)s - %(filename)s:%(lineno)d - %(levelname)s - %(message)s")
file_handler.setFormatter(file_formatter)
logger.addHandler(file_handler)


# Create console handler with filtering for clean output
# pylint: disable=too-few-public-methods
class MCPConsoleFilter(logging.Filter):
    """Filter to only show logs from mcp_calendar, google_calendar, and main modules."""

    def filter(self, record):
        # Only show logs from our modules, not third-party libraries
        return (
            record.name.startswith(("mcp_calendar", "google_calendar", "assistant", "__main__"))
            or record.name == "root"
        )


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

logger.info(f"mcp_calendar logging configured - Level: {LOG_LEVEL}")


# Log that this module is initialized
logger.info("mcp_calendar module initialized")

# Initialize FastMCP server
logger.info("Initializing FastMCP server with name 'google_calendar'")
mcp = FastMCP(
    name="google_calendar",
    instructions=(
        "Interact with Google Calendar: fetch events, create events, update events, delete events, "
        "find meeting slots, and plan your day. Supports timezone detection and different work weeks."
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
def list_calendar_tools() -> str:
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
    name="Get Calendar Events",
    description="""
    Fetch events from Google Calendar with various filtering options.

    Input can be a JSON object or individual parameters:
    - `calendar_id` (str): Calendar ID or 'primary' for main calendar. Default: "primary"
    - `time_min` (str): Lower bound for event's end time (ISO format or 'now'). Default: "now"
    - `time_max` (str): Upper bound for event's start time (ISO format). Default: 7 days from now
    - `max_results` (int): Maximum number of events to return. Default: 10
    - `query` (str): Free text search terms to find events

    Examples:
    {"time_min": "2024-01-15T00:00:00Z", "time_max": "2024-01-16T00:00:00Z"}
    {"query": "meeting with John", "max_results": 5}
    {"calendar_id": "work@example.com", "time_min": "now", "max_results": 20}

    Returns formatted list of events with title, time, location, description, and event IDs.
    """,
)
def get_events_tool(
    calendar_id: Any = "primary",
    time_min: Any = None,
    time_max: Any = None,
    max_results: Any = 10,
    query: Any = None,
) -> str:
    """Fetch events from Google Calendar."""

    logger.info(f"get_events_tool called with calendar_id='{calendar_id}', time_min={time_min}, time_max={time_max}")

    # Check if calendar_id is a JSON string
    if isinstance(calendar_id, str) and calendar_id.strip().startswith("{") and calendar_id.strip().endswith("}"):
        logger.debug("Detected JSON string in 'calendar_id' parameter, parsing...")
        params = parse_input(calendar_id)
        logger.debug(f"Parsed JSON: {params}")

        calendar_id = params.get("calendar_id", "primary")
        time_min = params.get("time_min", time_min)
        time_max = params.get("time_max", time_max)
        max_results = params.get("max_results", max_results)
        query = params.get("query", query)

    try:
        logger.info("Calling get_events with validated parameters")
        result = get_events(calendar_id, time_min, time_max, max_results, query)
        logger.info(f"Successfully fetched events, result length: {len(result)} chars")
        return result
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error(f"Error while fetching events: {e}", exc_info=True)
        return f"Error while fetching events: {e}"


@mcp.tool(
    name="Create Calendar Event",
    description="""
    Create a new event in Google Calendar.

    Input should be a JSON object with the following fields:
    - `summary` (str): Event title. Required.
    - `start_time` (str): Start time in ISO format (e.g., "2024-01-15T10:00:00"). Required.
    - `end_time` (str): End time in ISO format. Required.
    - `calendar_id` (str): Calendar ID or 'primary'. Default: "primary"
    - `description` (str): Event description
    - `location` (str): Event location
    - `attendees` (list): List of attendee emails
    - `recurrence` (list): RRULE strings for recurring events
    - `reminders` (dict): Custom reminder settings
    - `send_notifications` (bool): Send email invites to attendees. Default: true

    Examples:
    {"summary": "Team Meeting", "start_time": "2024-01-15T10:00:00", "end_time": "2024-01-15T11:00:00"}
    {
        "summary": "Weekly Standup",
        "start_time": "2024-01-15T09:00:00",
        "end_time": "2024-01-15T09:30:00",
        "description": "Weekly team sync",
        "location": "Conference Room A",
        "attendees": ["colleague@example.com"],
        "recurrence": ["RRULE:FREQ=WEEKLY;COUNT=10"]
    }

    Returns confirmation with event details and link.
    """,
)
def create_event_tool(
    summary: Any,
    start_time: Any = None,
    end_time: Any = None,
    calendar_id: Any = "primary",
    description: Any = None,
    location: Any = None,
    attendees: Any = None,
    recurrence: Any = None,
    reminders: Any = None,
    send_notifications: Any = False,
) -> str:
    """Create a new calendar event."""

    logger.info(f"create_event_tool called with summary='{summary}', start={start_time}, end={end_time}")

    # Check if summary is a JSON string
    if isinstance(summary, str) and summary.strip().startswith("{") and summary.strip().endswith("}"):
        logger.debug("Detected JSON string in 'summary' parameter, parsing...")
        params = parse_input(summary)
        logger.debug(f"Parsed JSON: {params}")

        summary = params.get("summary")
        start_time = params.get("start_time")
        end_time = params.get("end_time")
        calendar_id = params.get("calendar_id", calendar_id)
        description = params.get("description", description)
        location = params.get("location", location)
        attendees = params.get("attendees", attendees)
        recurrence = params.get("recurrence", recurrence)
        reminders = params.get("reminders", reminders)
        send_notifications = params.get("send_notifications", send_notifications)

    # Validate required fields
    if not summary:
        logger.warning("Missing required field: 'summary'")
        return "Validation error: 'summary' field is required."
    if not start_time:
        logger.warning("Missing required field: 'start_time'")
        return "Validation error: 'start_time' field is required."
    if not end_time:
        logger.warning("Missing required field: 'end_time'")
        return "Validation error: 'end_time' field is required."

    # Parse attendees if string
    if attendees and isinstance(attendees, str):
        attendees = [a.strip() for a in attendees.split(",")]

    try:
        logger.info(f"Creating event: {summary}")
        result = create_event(
            summary=summary,
            start_time=start_time,
            end_time=end_time,
            calendar_id=calendar_id,
            description=description,
            location=location,
            attendees=attendees,
            recurrence=recurrence,
            reminders=reminders,
            send_notifications=send_notifications,
        )
        logger.info("Successfully created event")
        return result
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error(f"Error while creating event: {e}", exc_info=True)
        return f"Error while creating event: {e}"


@mcp.tool(
    name="Update Calendar Event",
    description="""
    Update an existing calendar event.

    Input should be a JSON object with the following fields:
    - `event_id` (str): The event ID to update. Required.
    - `calendar_id` (str): Calendar ID or 'primary'. Default: "primary"
    - `summary` (str): New event title
    - `start_time` (str): New start time in ISO format
    - `end_time` (str): New end time in ISO format
    - `description` (str): New description
    - `location` (str): New location
    - `attendees` (list): New list of attendee emails
    - `send_notifications` (bool): Send update notifications to attendees. Default: true

    Example:
    {"event_id": "abc123", "summary": "Updated Meeting Title", "location": "Room 302"}

    Note: Get event_id from the "Get Calendar Events" tool output.
    Returns confirmation of the update.
    """,
)
def update_event_tool(
    event_id: Any,
    calendar_id: Any = "primary",
    summary: Any = None,
    start_time: Any = None,
    end_time: Any = None,
    description: Any = None,
    location: Any = None,
    attendees: Any = None,
    send_notifications: Any = False,
) -> str:
    """Update an existing calendar event."""

    logger.info(f"update_event_tool called with event_id='{event_id}'")

    # Check if event_id is a JSON string
    if isinstance(event_id, str) and event_id.strip().startswith("{") and event_id.strip().endswith("}"):
        logger.debug("Detected JSON string in 'event_id' parameter, parsing...")
        params = parse_input(event_id)
        logger.debug(f"Parsed JSON: {params}")

        event_id = params.get("event_id")
        calendar_id = params.get("calendar_id", calendar_id)
        summary = params.get("summary", summary)
        start_time = params.get("start_time", start_time)
        end_time = params.get("end_time", end_time)
        description = params.get("description", description)
        location = params.get("location", location)
        attendees = params.get("attendees", attendees)
        send_notifications = params.get("send_notifications", send_notifications)

    if not event_id:
        logger.warning("Missing required field: 'event_id'")
        return "Validation error: 'event_id' field is required."

    # Parse attendees if string
    if attendees and isinstance(attendees, str):
        attendees = [a.strip() for a in attendees.split(",")]

    try:
        logger.info(f"Updating event: {event_id}")
        result = update_event(
            event_id=event_id,
            calendar_id=calendar_id,
            summary=summary,
            start_time=start_time,
            end_time=end_time,
            description=description,
            location=location,
            attendees=attendees,
            send_notifications=send_notifications,
        )
        logger.info("Successfully updated event")
        return result
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error(f"Error while updating event: {e}", exc_info=True)
        return f"Error while updating event: {e}"


@mcp.tool(
    name="Delete Calendar Event",
    description="""
    Delete a calendar event.

    Input should be a JSON object with:
    - `event_id` (str): The event ID to delete. Required.
    - `calendar_id` (str): Calendar ID or 'primary'. Default: "primary"
    - `send_notifications` (bool): Send cancellation notifications to attendees. Default: true

    Example:
    {"event_id": "abc123xyz"}
    {"event_id": "abc123xyz", "calendar_id": "work@example.com"}

    Note: Get event_id from the "Get Calendar Events" tool output.
    Returns confirmation of deletion.
    """,
)
def delete_event_tool(
    event_id: Any,
    calendar_id: Any = "primary",
    send_notifications: Any = False,
) -> str:
    """Delete a calendar event."""

    logger.info(f"delete_event_tool called with event_id='{event_id}'")

    # Check if event_id is a JSON string
    if isinstance(event_id, str) and event_id.strip().startswith("{") and event_id.strip().endswith("}"):
        logger.debug("Detected JSON string in 'event_id' parameter, parsing...")
        params = parse_input(event_id)
        logger.debug(f"Parsed JSON: {params}")

        event_id = params.get("event_id")
        calendar_id = params.get("calendar_id", calendar_id)
        send_notifications = params.get("send_notifications", send_notifications)

    if not event_id:
        logger.warning("Missing required field: 'event_id'")
        return "Validation error: 'event_id' field is required."

    try:
        logger.info(f"Deleting event: {event_id}")
        result = delete_event(event_id, calendar_id, send_notifications)
        logger.info("Successfully deleted event")
        return result
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error(f"Error while deleting event: {e}", exc_info=True)
        return f"Error while deleting event: {e}"


@mcp.tool(
    name="Find Meeting Slots",
    description="""
    Find available meeting slots that work for multiple attendees.
    Automatically detects timezones and respects each person's working hours.

    Input should be a JSON object with:
    - `attendees` (list): List of attendee emails. Required.
    - `duration_minutes` (int): Meeting duration in minutes. Default: 30
    - `date_start` (str): Start date in ISO format (YYYY-MM-DD). Default: today
    - `date_end` (str): End date in ISO format. Default: 7 days from start
    - `preferred_time_start` (str): Preferred start time in ISO format (HH:MM). Default: None
    - `preferred_time_end` (str): Preferred end time in ISO format (HH:MM). Default: None
    Note: If both preferred_time_start and preferred_time_end are provided, they OVERRIDE `earliest_hour`/`latest_hour`.
    Note: The preferred times are interpreted in the PRIMARY calendar's timezone (the organizer/user).
    - `earliest_hour` (int): Earliest hour for meetings (local time). Default: 7
    - `latest_hour` (int): Latest hour for meetings (local time). Default: 20
    - `max_suggestions` (int): Maximum number of slots to suggest. Default: 10

    If you don't find any slots or they are not suitable, increase `max_suggestions` to find more slots.

    Examples:
    {"attendees": ["colleague@example.com"], "duration_minutes": 60}
    {
        "attendees": ["person1@example.com", "person2@example.com"],
        "duration_minutes": 30,
        "date_start": "2024-01-15",
        "date_end": "2024-01-20",
        "preferred_time_start": "09:00",
        "preferred_time_end": "17:00",
        "earliest_hour": 7,
        "latest_hour": 20,
        "max_suggestions": 20
    }

    Another example (preferred window only, in primary timezone):
    {
        "attendees": ["colleague@example.com"],
        "date_start": "2025-09-09",
        "date_end": "2025-09-09",
        "preferred_time_start": "11:00",
        "preferred_time_end": "17:00",
        "duration_minutes": 30
    }

    Returns available time slots with timezone information.
    Handles different work weeks (e.g., Sunday-Thursday for Israel).
    """,
)
def find_meeting_slots_tool(
    attendees: Any,
    duration_minutes: Any = 30,
    date_start: Any = None,
    date_end: Any = None,
    preferred_time_start: Any = None,
    preferred_time_end: Any = None,
    earliest_hour: Any = 7,
    latest_hour: Any = 20,
    max_suggestions: Any = 10,
) -> str:
    """Find available meeting slots for multiple attendees."""

    logger.info(f"find_meeting_slots_tool called with attendees={attendees}, duration={duration_minutes}")

    # Check if attendees is a JSON string
    if isinstance(attendees, str) and attendees.strip().startswith("{") and attendees.strip().endswith("}"):
        logger.debug("Detected JSON string in 'attendees' parameter, parsing...")
        params = parse_input(attendees)
        logger.debug(f"Parsed JSON: {params}")

        attendees = params.get("attendees")
        duration_minutes = params.get("duration_minutes", duration_minutes)
        date_start = params.get("date_start", date_start)
        date_end = params.get("date_end", date_end)
        preferred_time_start = params.get("preferred_time_start", preferred_time_start)
        preferred_time_end = params.get("preferred_time_end", preferred_time_end)
        earliest_hour = params.get("earliest_hour", earliest_hour)
        latest_hour = params.get("latest_hour", latest_hour)
        max_suggestions = params.get("max_suggestions", max_suggestions)

    # Parse attendees if string
    if isinstance(attendees, str):
        attendees = [a.strip() for a in attendees.split(",")]

    if not attendees:
        logger.warning("Missing required field: 'attendees'")
        return "Validation error: 'attendees' field is required."

    # Convert to int if string
    if isinstance(duration_minutes, str):
        duration_minutes = int(duration_minutes)
    if isinstance(earliest_hour, str):
        earliest_hour = int(earliest_hour)
    if isinstance(latest_hour, str):
        latest_hour = int(latest_hour)
    if isinstance(max_suggestions, str):
        max_suggestions = int(max_suggestions)
    # Keep preferred times as simple HH:MM strings; parsing is handled in google_calendar.py

    try:
        logger.info(f"Finding {duration_minutes}-min slots for {len(attendees)} attendees")
        result = find_meeting_slots(
            attendees=attendees,
            duration_minutes=duration_minutes,
            date_start=date_start,
            date_end=date_end,
            preferred_time_start=preferred_time_start,
            preferred_time_end=preferred_time_end,
            earliest_hour=earliest_hour,
            latest_hour=latest_hour,
            max_suggestions=max_suggestions,
        )
        logger.info("Successfully found meeting slots")
        return result
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error(f"Error while finding meeting slots: {e}", exc_info=True)
        return f"Error while finding meeting slots: {e}"


@mcp.tool(
    name="Get Free Busy Information",
    description="""
    Get free/busy information for one or more calendars.
    Shows when people are busy without revealing event details.

    Input should be a JSON object with:
    - `time_min` (str): Start time in ISO format (e.g., "2024-01-15T00:00:00Z"). Required.
    - `time_max` (str): End time in ISO format. Required.
    - `calendars` (list): List of calendar IDs/emails to check. Default: ["primary"]
    - `timezone` (str): Timezone for the query. Default: "UTC"

    Examples:
    {
        "time_min": "2024-01-15T09:00:00Z",
        "time_max": "2024-01-15T17:00:00Z",
        "calendars": ["primary"]
    }
    {
        "time_min": "2024-01-15T00:00:00Z",
        "time_max": "2024-01-16T00:00:00Z",
        "calendars": ["colleague1@example.com", "colleague2@example.com", "primary"]
    }

    Returns busy time blocks for each calendar.
    Useful for:
    - Checking someone's availability without seeing their events
    - Finding when multiple people are free
    - Privacy-preserving availability checks
    """,
)
def get_free_busy_tool(
    time_min: Any,
    time_max: Any = None,
    calendars: Any = None,
    timezone: Any = "UTC",
) -> str:
    """Get free/busy information for calendars."""

    logger.info(f"get_free_busy_tool called with time_min={time_min}, time_max={time_max}")

    # Check if time_min is a JSON string
    if isinstance(time_min, str) and time_min.strip().startswith("{") and time_min.strip().endswith("}"):
        logger.debug("Detected JSON string in 'time_min' parameter, parsing...")
        params = parse_input(time_min)
        logger.debug(f"Parsed JSON: {params}")

        time_min = params.get("time_min")
        time_max = params.get("time_max")
        calendars = params.get("calendars", calendars)
        timezone = params.get("timezone", timezone)

    # Validate required fields
    if not time_min:
        logger.warning("Missing required field: 'time_min'")
        return "Validation error: 'time_min' field is required."
    if not time_max:
        logger.warning("Missing required field: 'time_max'")
        return "Validation error: 'time_max' field is required."

    # Default calendars to primary if not specified
    if not calendars:
        calendars = ["primary"]

    # Parse calendars if string
    if isinstance(calendars, str):
        if calendars.strip().startswith("["):
            # Try to parse as JSON array
            try:
                calendars = json.loads(calendars)
            except Exception:  # pylint: disable=broad-exception-caught
                calendars = [c.strip() for c in calendars.split(",")]
        else:
            calendars = [c.strip() for c in calendars.split(",")]

    try:
        logger.info(f"Getting free/busy for {len(calendars)} calendars")
        result = get_free_busy(time_min, time_max, calendars, timezone)
        logger.info("Successfully fetched free/busy information")
        return result
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error(f"Error while getting free/busy: {e}", exc_info=True)
        return f"Error while getting free/busy: {e}"


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
    logger.debug(f"get_today_date must be empty dict: {test}")
    now = datetime.datetime.now()
    payload = {"date": now.strftime("%Y-%m-%d"), "weekday": now.strftime("%A")}
    result = json.dumps(payload)
    logger.debug(f"Returning date payload: {result}")
    return result


if __name__ == "__main__":
    logger.info("Starting MCP Google Calendar server...")

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
