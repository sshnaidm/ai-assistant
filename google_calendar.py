"""This module provides functions to interact with Google Calendar."""

import os
from datetime import datetime, time, timedelta
from typing import Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

# Try to import centralized logging, fall back to basic config if not available
try:
    from logging_config import setup_logging

    logger = setup_logging(__name__)
except ImportError:
    import logging

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s:%(lineno)d - %(message)s",
        handlers=[logging.FileHandler("mcp_calendar.log"), logging.StreamHandler()],
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

logger.info("google_calendar module initialized")


def authenticate_calendar():
    """Authenticate and return a Google Calendar service object."""
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
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open("token.json", "w", encoding="utf-8") as token:
            logger.info("Saving new credentials to token.json.")
            token.write(creds.to_json())

    service = build("calendar", "v3", credentials=creds)
    logger.info("Calendar service built successfully.")
    return service


def list_calendars() -> str:
    """
    List all calendars accessible to the user.

    Returns:
        str: Formatted string with calendar names and IDs.
    """
    logger.info("Listing all accessible calendars")

    try:
        service = authenticate_calendar()

        # Call the Calendar API
        calendar_list = service.calendarList().list().execute()  # pylint: disable=no-member
        calendars = calendar_list.get("items", [])

        if not calendars:
            return "No calendars found."

        result = f"Found {len(calendars)} calendar(s):\n"
        result += "=" * 50 + "\n"

        for cal in calendars:
            result += f"📅 {cal['summary']}\n"
            result += f"   ID: {cal['id']}\n"
            if cal.get("primary"):
                result += "   (Primary Calendar)\n"
            if cal.get("description"):
                result += f"   Description: {cal['description']}\n"
            result += "\n"

        logger.info(f"Successfully listed {len(calendars)} calendars")
        return result

    except HttpError as error:
        logger.error(f"An HTTP error occurred: {error}", exc_info=True)
        return f"Failed to list calendars: {error}"
    except Exception as e:
        logger.error(f"An error occurred: {e}", exc_info=True)
        return f"An error occurred while listing calendars: {e}"


def get_events(
    calendar_id: str = "primary",
    time_min: Optional[str] = None,
    time_max: Optional[str] = None,
    max_results: int = 10,
    query: Optional[str] = None,
    single_events: bool = True,
    order_by: str = "startTime",
) -> str:
    """
    Fetch events from Google Calendar.

    Args:
        calendar_id: Calendar ID or 'primary' for the primary calendar.
        time_min: Lower bound for event's end time (ISO format or 'now').
        time_max: Upper bound for event's start time (ISO format).
        max_results: Maximum number of events to return.
        query: Free text search terms to find events.
        single_events: Whether to expand recurring events.
        order_by: Order of the events ('startTime' or 'updated').

    Returns:
        str: Formatted string containing event details.
    """
    logger.info(
        f"Fetching events from calendar '{calendar_id}' with time_min='{time_min}', "
        f"time_max='{time_max}', max_results={max_results}, query='{query}'"
    )

    try:
        service = authenticate_calendar()

        # Set default time_min to now if not specified
        if time_min == "now" or time_min is None:
            time_min = datetime.utcnow().isoformat() + "Z"
        elif not time_min.endswith("Z") and "+" not in time_min:
            time_min = time_min + "Z"

        # Set default time_max to 7 days from now if not specified
        if time_max is None:
            time_max = (datetime.utcnow() + timedelta(days=7)).isoformat() + "Z"
        elif not time_max.endswith("Z") and "+" not in time_max:
            time_max = time_max + "Z"

        # Build the request parameters
        event_params = {
            "calendarId": calendar_id,
            "timeMin": time_min,
            "timeMax": time_max,
            "maxResults": max_results,
            "singleEvents": single_events,
            "orderBy": order_by,
        }

        if query:
            event_params["q"] = query

        # Call the Calendar API
        logger.info(f"Executing calendar query with params: {event_params}")
        events_result = service.events().list(**event_params).execute()  # pylint: disable=no-member
        events = events_result.get("items", [])

        if not events:
            return "No upcoming events found."

        # Format the results
        result = f"Found {len(events)} event(s):\n"
        result += "=" * 50 + "\n\n"

        for event in events:
            # Event title and ID
            summary = event.get("summary", "No Title")
            event_id = event.get("id", "No ID")
            result += f"📌 {summary}\n"
            result += f"   ID: {event_id}\n"

            # Event time
            start = event.get("start", {})
            end = event.get("end", {})

            if "dateTime" in start:
                start_time = start["dateTime"]
                end_time = end.get("dateTime", "")
                result += f"   🕐 {start_time} → {end_time}\n"
            elif "date" in start:
                # All-day event
                result += f"   📅 All day: {start['date']}\n"

            # Location
            if event.get("location"):
                result += f"   📍 Location: {event['location']}\n"

            # Description
            if event.get("description"):
                desc = event["description"][:100]  # Truncate long descriptions
                if len(event["description"]) > 100:
                    desc += "..."
                result += f"   📝 Description: {desc}\n"

            # Attendees
            attendees = event.get("attendees", [])
            if attendees:
                attendee_list = [a.get("email", "Unknown") for a in attendees[:3]]
                if len(attendees) > 3:
                    attendee_list.append(f"... and {len(attendees) - 3} more")
                result += f"   👥 Attendees: {', '.join(attendee_list)}\n"

            # Meeting link
            if event.get("hangoutLink"):
                result += f"   🔗 Meet: {event['hangoutLink']}\n"

            # Status
            if event.get("status"):
                result += f"   Status: {event['status']}\n"

            result += "\n"

        logger.info(f"Successfully fetched {len(events)} events")
        return result

    except HttpError as error:
        logger.error(f"An HTTP error occurred: {error}", exc_info=True)
        return f"Failed to fetch events: {error}"
    except Exception as e:
        logger.error(f"An error occurred: {e}", exc_info=True)
        return f"An error occurred while fetching events: {e}"


def create_event(
    summary: str,
    start_time: str,
    end_time: str,
    calendar_id: str = "primary",
    description: Optional[str] = None,
    location: Optional[str] = None,
    attendees: Optional[List[str]] = None,
    timezone: str = "UTC",
    all_day: bool = False,
    reminders: Optional[Dict] = None,
    recurrence: Optional[List[str]] = None,
    send_notifications: bool = False,
) -> str:
    """
    Create a new calendar event.

    Args:
        summary: Event title/summary.
        start_time: Start time (ISO format or 'YYYY-MM-DD' for all-day).
        end_time: End time (ISO format or 'YYYY-MM-DD' for all-day).
        calendar_id: Calendar ID or 'primary' for the primary calendar.
        description: Event description.
        location: Event location.
        attendees: List of attendee email addresses.
        timezone: Timezone for the event (e.g., 'America/New_York').
        all_day: Whether this is an all-day event.
        reminders: Custom reminders (e.g.{"useDefault": False, "overrides": [{"method": "email", "minutes": 24 * 60}]}).
        recurrence: Recurrence rules (e.g., ['RRULE:FREQ=WEEKLY;COUNT=10']).
        send_notifications: Whether to send email notifications to attendees (default: False).

    Returns:
        str: Success message with event details or error message.
    """
    logger.info(f"Creating event '{summary}' from {start_time} to {end_time} " f"in calendar '{calendar_id}'")

    try:
        service = authenticate_calendar()

        # Build the event object
        event = {
            "summary": summary,
        }

        # Handle time/date
        if all_day:
            # All-day event uses 'date' field
            event["start"] = {"date": start_time, "timeZone": timezone}
            event["end"] = {"date": end_time, "timeZone": timezone}
        else:
            # Timed event uses 'dateTime' field
            if not start_time.endswith("Z") and "+" not in start_time and "-" not in start_time[-6:]:
                # Add timezone if not present
                event["start"] = {"dateTime": start_time, "timeZone": timezone}
                event["end"] = {"dateTime": end_time, "timeZone": timezone}
            else:
                event["start"] = {"dateTime": start_time}
                event["end"] = {"dateTime": end_time}

        # Add optional fields
        if description:
            event["description"] = description

        if location:
            event["location"] = location

        if attendees:
            event["attendees"] = [{"email": email} for email in attendees]

        if reminders:
            event["reminders"] = reminders
        else:
            # Use default reminders
            event["reminders"] = {"useDefault": True}

        if recurrence:
            event["recurrence"] = recurrence

        # Create the event
        logger.info(f"Creating event with data: {event}")
        # Determine sendUpdates parameter based on whether there are attendees
        send_updates = "all" if (attendees and send_notifications) else "none"
        # pylint: disable=no-member
        created_event = service.events().insert(calendarId=calendar_id, body=event, sendUpdates=send_updates).execute()

        event_id = created_event.get("id")
        event_link = created_event.get("htmlLink")

        result = "✅ Event created successfully!\n"
        result += f"Event ID: {event_id}\n"
        result += f"Title: {summary}\n"
        result += f"Time: {start_time} → {end_time}\n"
        if location:
            result += f"Location: {location}\n"
        if attendees:
            result += f"Attendees: {', '.join(attendees)}\n"
        result += f"Link: {event_link}\n"

        logger.info(f"Event created with ID: {event_id}")
        return result

    except HttpError as error:
        logger.error(f"An HTTP error occurred: {error}", exc_info=True)
        return f"Failed to create event: {error}"
    except Exception as e:
        logger.error(f"An error occurred: {e}", exc_info=True)
        return f"An error occurred while creating event: {e}"


def update_event(
    event_id: str,
    calendar_id: str = "primary",
    summary: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    description: Optional[str] = None,
    location: Optional[str] = None,
    attendees: Optional[List[str]] = None,
    send_notifications: bool = False,
) -> str:
    """
    Update an existing calendar event.

    Args:
        event_id: The ID of the event to update.
        calendar_id: Calendar ID or 'primary' for the primary calendar.
        summary: New event title (if changing).
        start_time: New start time (if changing).
        end_time: New end time (if changing).
        description: New description (if changing).
        location: New location (if changing).
        attendees: New attendee list (if changing).
        send_notifications: Whether to send email notifications to attendees (default: False).

    Returns:
        str: Success message or error message.
    """
    logger.info(f"Updating event '{event_id}' in calendar '{calendar_id}'")

    try:
        service = authenticate_calendar()

        # First, get the existing event
        event = service.events().get(calendarId=calendar_id, eventId=event_id).execute()  # pylint: disable=no-member

        # Update only the fields that were provided
        if summary is not None:
            event["summary"] = summary

        if start_time is not None:
            if "date" in event["start"]:
                event["start"]["date"] = start_time
            else:
                event["start"]["dateTime"] = start_time

        if end_time is not None:
            if "date" in event["end"]:
                event["end"]["date"] = end_time
            else:
                event["end"]["dateTime"] = end_time

        if description is not None:
            event["description"] = description

        if location is not None:
            event["location"] = location

        if attendees is not None:
            event["attendees"] = [{"email": email} for email in attendees]

        # Update the event
        # Determine sendUpdates parameter
        send_updates = "all" if send_notifications else "none"
        updated_event = (
            service.events()
            .update(calendarId=calendar_id, eventId=event_id, body=event, sendUpdates=send_updates)
            .execute()
        )

        result = "✅ Event updated successfully!\n"
        result += f"Event ID: {event_id}\n"
        result += f"Title: {updated_event.get('summary', 'No Title')}\n"
        result += f"Link: {updated_event.get('htmlLink', 'N/A')}\n"

        logger.info(f"Event {event_id} updated successfully")
        return result

    except HttpError as error:
        logger.error(f"An HTTP error occurred: {error}", exc_info=True)
        return f"Failed to update event: {error}"
    except Exception as e:
        logger.error(f"An error occurred: {e}", exc_info=True)
        return f"An error occurred while updating event: {e}"


def delete_event(
    event_id: str,
    calendar_id: str = "primary",
    send_notifications: bool = False,
) -> str:
    """
    Delete a calendar event.

    Args:
        event_id: The ID of the event to delete.
        calendar_id: Calendar ID or 'primary' for the primary calendar.
        send_notifications: Whether to send cancellation notifications to attendees (default: False).

    Returns:
        str: Success message or error message.
    """
    logger.info(f"Deleting event '{event_id}' from calendar '{calendar_id}'")

    try:
        service = authenticate_calendar()

        # Delete the event
        # Determine sendUpdates parameter
        send_updates = "all" if send_notifications else "none"
        service.events().delete(calendarId=calendar_id, eventId=event_id, sendUpdates=send_updates).execute()

        result = "✅ Event deleted successfully!\n"
        result += f"Event ID: {event_id}\n"

        logger.info(f"Event {event_id} deleted successfully")
        return result

    except HttpError as error:
        logger.error(f"An HTTP error occurred: {error}", exc_info=True)
        return f"Failed to delete event: {error}"
    except Exception as e:
        logger.error(f"An error occurred: {e}", exc_info=True)
        return f"An error occurred while deleting event: {e}"


def get_free_busy(
    time_min: str,
    time_max: str,
    calendars: Optional[List[str]] = None,
    timezone: str = "UTC",
) -> str:
    """
    Get free/busy information for calendars.

    Args:
        time_min: Start of the interval (ISO format).
        time_max: End of the interval (ISO format).
        calendars: List of calendar IDs to check (default: primary).
        timezone: Timezone for the response.

    Returns:
        str: Formatted free/busy information.
    """
    logger.info(f"Getting free/busy info from {time_min} to {time_max}")

    try:
        service = authenticate_calendar()

        if calendars is None:
            calendars = ["primary"]

        # Prepare the request body
        body = {
            "timeMin": time_min if time_min.endswith("Z") else time_min + "Z",
            "timeMax": time_max if time_max.endswith("Z") else time_max + "Z",
            "timeZone": timezone,
            "items": [{"id": cal} for cal in calendars],
        }

        # Get free/busy info
        freebusy_result = service.freebusy().query(body=body).execute()

        result = "Free/Busy Information:\n"
        result += "=" * 50 + "\n"

        for calendar_id, calendar_info in freebusy_result.get("calendars", {}).items():
            result += f"\n📅 Calendar: {calendar_id}\n"

            busy_times = calendar_info.get("busy", [])
            if not busy_times:
                result += "   ✅ Completely free during this period\n"
            else:
                result += "   Busy times:\n"
                for busy in busy_times:
                    start = busy.get("start", "Unknown")
                    end = busy.get("end", "Unknown")
                    result += f"   🔴 {start} → {end}\n"

        logger.info("Successfully retrieved free/busy information")
        return result

    except HttpError as error:
        logger.error(f"An HTTP error occurred: {error}", exc_info=True)
        return f"Failed to get free/busy info: {error}"
    except Exception as e:
        logger.error(f"An error occurred: {e}", exc_info=True)
        return f"An error occurred while getting free/busy info: {e}"


def quick_add_event(
    text: str,
    calendar_id: str = "primary",
) -> str:
    """
    Quick add an event using natural language.
    Google Calendar will parse the text to create an event.

    Args:
        text: Natural language description (e.g., "Dinner with John tomorrow at 7pm").
        calendar_id: Calendar ID or 'primary' for the primary calendar.

    Returns:
        str: Success message with event details or error message.
    """
    logger.info(f"Quick adding event with text: '{text}'")

    try:
        service = authenticate_calendar()

        # Use quickAdd to create event from natural language
        created_event = service.events().quickAdd(calendarId=calendar_id, text=text).execute()

        event_id = created_event.get("id")
        summary = created_event.get("summary", "No Title")
        start = created_event.get("start", {})

        result = "✅ Event created successfully!\n"
        result += f"Event ID: {event_id}\n"
        result += f"Title: {summary}\n"

        if "dateTime" in start:
            result += f"Time: {start['dateTime']}\n"
        elif "date" in start:
            result += f"Date: {start['date']}\n"

        result += f"Link: {created_event.get('htmlLink', 'N/A')}\n"

        logger.info(f"Quick event created with ID: {event_id}")
        return result

    except HttpError as error:
        logger.error(f"An HTTP error occurred: {error}", exc_info=True)
        return f"Failed to quick add event: {error}"
    except Exception as e:
        logger.error(f"An error occurred: {e}", exc_info=True)
        return f"An error occurred while quick adding event: {e}"


def get_calendar_timezone(calendar_id: str) -> Optional[str]:
    """
    Get the timezone of a specific calendar.

    Args:
        calendar_id: Calendar ID (email address) or 'primary'.

    Returns:
        Timezone string (e.g., 'America/New_York') or None if not accessible.
    """
    logger.info(f"Getting timezone for calendar: {calendar_id}")

    try:
        service = authenticate_calendar()
        calendar = service.calendars().get(calendarId=calendar_id).execute()
        timezone = calendar.get("timeZone", None)
        logger.info(f"Calendar {calendar_id} timezone: {timezone}")
        return timezone
    except HttpError as error:
        logger.warning(f"Cannot access calendar {calendar_id}: {error}")
        return None
    except Exception as e:
        logger.warning(f"Error getting timezone for {calendar_id}: {e}")
        return None


def infer_timezone_from_events(calendar_id: str) -> Optional[str]:
    """
    Infer timezone from recent calendar events.

    Args:
        calendar_id: Calendar ID (email address) or 'primary'.

    Returns:
        Most common timezone string from recent events or None.
    """
    logger.info(f"Inferring timezone from events for: {calendar_id}")

    try:
        service = authenticate_calendar()

        # Get events from the last 30 days
        time_min = (datetime.utcnow() - timedelta(days=30)).isoformat() + "Z"
        time_max = datetime.utcnow().isoformat() + "Z"

        events_result = (
            service.events()
            .list(
                calendarId=calendar_id,
                timeMin=time_min,
                timeMax=time_max,
                maxResults=50,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )

        events = events_result.get("items", [])

        # If no events found, can't infer timezone
        if not events:
            logger.info(f"No events found for {calendar_id} in the last 30 days")
            return None

        # Count timezone occurrences
        timezone_counts = {}
        for event in events:
            # Check start time for timezone
            start = event.get("start", {})
            if "dateTime" in start and "timeZone" in start:
                # Use explicit timezone from the API (most reliable)
                tz = start["timeZone"]
                timezone_counts[tz] = timezone_counts.get(tz, 0) + 1
            # Also check end time as a fallback (some events might have timezone only in end)
            end = event.get("end", {})
            if "dateTime" in end and "timeZone" in end and "timeZone" not in start:
                tz = end["timeZone"]
                timezone_counts[tz] = timezone_counts.get(tz, 0) + 1

        # Return most common timezone
        if timezone_counts:
            most_common = max(timezone_counts.items(), key=lambda x: x[1])
            logger.info(f"Inferred timezone for {calendar_id}: {most_common[0]} (found in {most_common[1]} events)")
            return most_common[0]

        logger.info(f"No timezone information found in events for {calendar_id}")
        return None

    except Exception as e:
        logger.warning(f"Error inferring timezone for {calendar_id}: {e}")
        return None


def get_workweek_for_timezone(timezone: str) -> List[int]:
    """
    Get the working days for a given timezone.

    Returns list of weekday numbers where 0=Monday, 6=Sunday.
    """
    # Define work weeks for different regions
    # Israel and some Middle Eastern countries: Sunday-Thursday
    israel_workweek = [6, 0, 1, 2, 3]  # Sunday=6, Mon=0, Tue=1, Wed=2, Thu=3

    # Most Arab countries: Sunday-Thursday
    arab_workweek_1 = [6, 0, 1, 2, 3]  # Sunday-Thursday

    # Western countries: Monday-Friday
    western_workweek = [0, 1, 2, 3, 4]  # Mon-Fri

    # Map timezones to work weeks
    if timezone in ["Asia/Jerusalem", "Asia/Tel_Aviv"]:
        return israel_workweek
    if timezone in ["Asia/Riyadh", "Asia/Dubai", "Asia/Kuwait", "Asia/Amman"]:
        return arab_workweek_1
    return western_workweek


def find_working_hours_overlap(
    attendee_timezones: Dict[str, str], date: datetime, local_start_hour: int = 9, local_end_hour: int = 17
) -> Optional[Tuple[datetime, datetime]]:
    """
    Find the overlap of working hours for all attendees on a specific date.
    Takes into account different work weeks (e.g., Sunday-Thursday in Israel).

    Args:
        attendee_timezones: Dict mapping attendee email to timezone string.
        date: The date to check.
        local_start_hour: Start of working day in local time (default 9).
        local_end_hour: End of working day in local time (default 17).

    Returns:
        Tuple of (start, end) datetime in UTC for the overlap, or None if no overlap.
    """
    overlap_start = None
    overlap_end = None
    weekday = date.weekday()

    for attendee, tz_str in attendee_timezones.items():
        try:
            # Check if this is a working day for this timezone
            workweek = get_workweek_for_timezone(tz_str)
            if weekday not in workweek:
                logger.debug(f"{attendee} ({tz_str}): Not a working day (weekday={weekday})")
                return None  # If any attendee is off, no meeting possible

            # Create timezone-aware datetime for this attendee's working hours
            tz = ZoneInfo(tz_str)
            local_start = datetime.combine(date.date(), time(local_start_hour, 0), tzinfo=tz)
            local_end = datetime.combine(date.date(), time(local_end_hour, 0), tzinfo=tz)

            # Convert to UTC (naive datetime for comparison)
            utc_start = local_start.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
            utc_end = local_end.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)

            # Find intersection
            if overlap_start is None:
                overlap_start = utc_start
                overlap_end = utc_end
            else:
                overlap_start = max(overlap_start, utc_start)
                overlap_end = min(overlap_end, utc_end)

            logger.debug(
                f"{attendee} ({tz_str}): {local_start_hour}:00-{local_end_hour}:00 -> UTC "
                f"{utc_start.time()}-{utc_end.time()}"
            )

        except Exception as e:
            logger.warning(f"Error processing timezone for {attendee}: {e}")
            # Fall back to UTC if timezone processing fails
            if overlap_start is None:
                overlap_start = datetime.combine(date.date(), time(local_start_hour, 0))
                overlap_end = datetime.combine(date.date(), time(local_end_hour, 0))

    # Check if there's a valid overlap
    if overlap_start and overlap_end and overlap_start < overlap_end:
        return (overlap_start, overlap_end)
    return None


def find_meeting_slots(
    attendees: List[str],
    duration_minutes: int = 30,
    date_start: Optional[str] = None,  # ISO format: "2024-12-20"
    date_end: Optional[str] = None,  # ISO format: "2024-12-27"
    preferred_time_start: Optional[str] = None,
    preferred_time_end: Optional[str] = None,
    earliest_hour: int = 7,
    latest_hour: int = 20,
    timezone: str = "UTC",
    max_suggestions: int = 10,
    weekdays_only: bool = True,  # Skip weekends
    allowed_weekdays: Optional[List[int]] = None,  # [0=Mon, 1=Tue, ..., 6=Sun]
    use_attendee_timezones: bool = True,  # Use each attendee's local timezone for working hours
) -> str:
    """
    Find mutual free time slots for a meeting with multiple attendees.

    Automatically detects each attendee's timezone and respects their local work week:
    - Israel/Middle East: Sunday-Thursday
    - Western countries: Monday-Friday
    - Customizable per region

    Args:
        attendees: List of email addresses to check availability.
        duration_minutes: Meeting duration in minutes.
        date_start: Start date for search in ISO format (default: today).
        date_end: End date for search in ISO format (default: 7 days from start).
        preferred_time_start: Preferred start time in ISO format (HH:MM). Default: None
        preferred_time_end: Preferred end time in ISO format (HH:MM). Default: None
        earliest_hour: Earliest hour for meeting in each person's local time (default 7 AM).
        latest_hour: Latest hour for meeting end in each person's local time (default 8 PM).
        timezone: Default timezone if detection is disabled.
        max_suggestions: Maximum number of slot suggestions to return.
        weekdays_only: If True, respect each region's work week (e.g., Sun-Thu for Israel).
        allowed_weekdays: Override to force specific days [0=Monday, ..., 6=Sunday].
        use_attendee_timezones: If True, detect and use each attendee's timezone.

    Returns:
        str: Formatted list of available time slots.
    """
    logger.info(f"Finding {duration_minutes}-min meeting slots for {len(attendees)} attendees")

    try:
        service = authenticate_calendar()

        # Set search window
        now = datetime.now()

        # Parse date range
        if date_start:
            start_date = datetime.fromisoformat(date_start)
        else:
            start_date = now

        if date_end:
            end_date = datetime.fromisoformat(date_end)
        else:
            # Default to 7 days from start
            end_date = start_date + timedelta(days=7)

        # Set time bounds for API query
        time_min = start_date.replace(hour=0, minute=0, second=0, microsecond=0).isoformat() + "Z"
        time_max = end_date.replace(hour=23, minute=59, second=59, microsecond=0).isoformat() + "Z"

        logger.info(f"Searching from {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")

        # Step 1: Detect timezones for all attendees if enabled
        attendee_timezones = {}
        all_calendars = ["primary"] + attendees  # Include organizer

        if use_attendee_timezones:
            for calendar_id in all_calendars:
                # Try to get timezone from calendar properties
                tz = get_calendar_timezone(calendar_id)

                # If not accessible, try to infer from events
                if not tz:
                    tz = infer_timezone_from_events(calendar_id)

                # Fall back to UTC if nothing works
                if not tz:
                    logger.warning(f"Could not determine timezone for {calendar_id}, using UTC")
                    tz = "UTC"

                attendee_timezones[calendar_id] = tz
                logger.info(f"Using timezone {tz} for {calendar_id}")
        else:
            # Use the provided timezone for everyone
            for calendar_id in all_calendars:
                attendee_timezones[calendar_id] = timezone

        # Get free/busy information for all attendees
        body = {
            "timeMin": time_min,
            "timeMax": time_max,
            "timeZone": timezone,
            "items": [{"id": cal} for cal in all_calendars],
        }
        logger.debug(f"Free/busy body: {body}")

        freebusy_result = service.freebusy().query(body=body).execute()

        logger.debug(f"Free/busy result: {freebusy_result}")

        # Parse busy times for each person
        all_busy_times = {}
        for calendar_id, calendar_info in freebusy_result.get("calendars", {}).items():
            busy_times = []
            for busy in calendar_info.get("busy", []):
                # Parse as timezone-naive datetimes (removing 'Z' suffix)
                start = datetime.fromisoformat(busy["start"].replace("Z", ""))
                end = datetime.fromisoformat(busy["end"].replace("Z", ""))
                busy_times.append((start, end))
            all_busy_times[calendar_id] = busy_times

        logger.debug(f"All busy times: {all_busy_times}")

        # Find free slots
        free_slots = []

        # Process each day in the date range
        current_date = start_date.date()
        end_date_only = end_date.date()

        while current_date <= end_date_only and len(free_slots) < max_suggestions:
            # Check if current day is allowed
            current_datetime = datetime.combine(current_date, time(0, 0))
            if allowed_weekdays and current_datetime.weekday() not in allowed_weekdays:
                current_date += timedelta(days=1)
                continue

            # Skip weekends based on each attendee's work week
            if use_attendee_timezones and weekdays_only:
                # Check if this day is a working day for ALL attendees
                is_working_day = True
                for cal_id, tz in attendee_timezones.items():
                    workweek = get_workweek_for_timezone(tz)
                    if current_datetime.weekday() not in workweek:
                        is_working_day = False
                        logger.debug(f"{current_date}: Not a working day for {cal_id} in {tz}")
                        break

                if not is_working_day:
                    current_date += timedelta(days=1)
                    continue
            elif weekdays_only and current_datetime.weekday() in [5, 6]:
                # Default weekend check if not using timezone detection
                current_date += timedelta(days=1)
                continue

            # Determine daily search window
            if preferred_time_start or preferred_time_end:
                try:
                    # Use preferred window in PRIMARY calendar's timezone
                    primary_tz = ZoneInfo(attendee_timezones.get("primary", "UTC"))
                    if preferred_time_start:
                        start_h, start_m = [int(x) for x in str(preferred_time_start).split(":")[:2]]
                    else:
                        start_h, start_m = int(earliest_hour), 0
                    if preferred_time_end:
                        end_h, end_m = [int(x) for x in str(preferred_time_end).split(":")[:2]]
                    else:
                        end_h, end_m = int(latest_hour), 0

                    local_start = datetime.combine(current_date, time(start_h, start_m)).replace(tzinfo=primary_tz)
                    local_end = datetime.combine(current_date, time(end_h, end_m)).replace(tzinfo=primary_tz)

                    day_start = local_start.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
                    day_end = local_end.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)

                    logger.debug(
                        f"Preferred window on {current_date} (primary {primary_tz}): "
                        f"{local_start.time()}-{local_end.time()} -> UTC {day_start.time()}-{day_end.time()}"
                    )

                    if day_start >= day_end:
                        logger.debug(
                            f"Preferred window invalid or zero-length for {current_date}: "
                            f"{preferred_time_start}-{preferred_time_end}"
                        )
                        current_date += timedelta(days=1)
                        continue
                except Exception as e:
                    logger.warning(f"Failed to apply preferred_time window, falling back to working hours: {e}")
                    # Fallback to overlap/fixed window
                    if use_attendee_timezones:
                        overlap = find_working_hours_overlap(
                            attendee_timezones, current_datetime, earliest_hour, latest_hour
                        )
                        if not overlap:
                            current_date += timedelta(days=1)
                            continue
                        day_start, day_end = overlap
                        logger.debug(f"Overlap window (UTC) on {current_date}: {day_start.time()}-{day_end.time()}")
                    else:
                        day_start = datetime.combine(current_date, time(earliest_hour, 0))
                        day_end = datetime.combine(current_date, time(latest_hour, 0))
                        logger.debug(f"Fixed window (UTC) on {current_date}: {day_start.time()}-{day_end.time()}")
            else:
                # No preferred window: use working hours logic
                if use_attendee_timezones:
                    overlap = find_working_hours_overlap(
                        attendee_timezones, current_datetime, earliest_hour, latest_hour
                    )

                    if not overlap:
                        logger.info(f"No working hours overlap on {current_date} for attendees in different timezones")
                        current_date += timedelta(days=1)
                        continue

                    day_start, day_end = overlap
                    logger.debug(f"Overlap window (UTC) on {current_date}: {day_start.time()}-{day_end.time()}")
                else:
                    # Use fixed hours if not using timezone detection
                    day_start = datetime.combine(current_date, time(earliest_hour, 0))
                    day_end = datetime.combine(current_date, time(latest_hour, 0))
                    logger.debug(f"Fixed window (UTC) on {current_date}: {day_start.time()}-{day_end.time()}")

            # Start checking slots from the beginning of working hours
            current = day_start

            # If we're starting today, adjust to current time
            if current_date == now.date() and current < now:
                # Round up to next 30-minute slot
                current = now.replace(minute=(now.minute // 30 + 1) * 30 % 60, second=0, microsecond=0)
                if current.minute == 0:
                    current = current.replace(hour=current.hour + 1)

            # Check slots within the working hours window
            while current < day_end and len(free_slots) < max_suggestions:
                slot_end = current + timedelta(minutes=duration_minutes)

                # Check if slot fits within working hours
                if slot_end > day_end:
                    break

                # Check if this slot is free for all attendees
                is_free = True
                for calendar_id, busy_times in all_busy_times.items():
                    for busy_start, busy_end in busy_times:
                        # Check if our slot overlaps with any busy time
                        if not (slot_end <= busy_start or current >= busy_end):
                            logger.debug(
                                "Rejecting slot %s-%s due to busy block %s-%s in %s",
                                current.time(),
                                slot_end.time(),
                                busy_start.time(),
                                busy_end.time(),
                                calendar_id,
                            )
                            is_free = False
                            break
                    if not is_free:
                        break

                if is_free:
                    free_slots.append((current, slot_end))

                # Move to next slot (30-minute increments)
                current += timedelta(minutes=30)

            # Move to next day
            current_date += timedelta(days=1)

        logger.debug(f"Free slots: {free_slots}")

        # Format results
        if not free_slots:
            days_searched = (end_date - start_date).days
            return f"No mutual free slots found in the next {days_searched} days."

        result = f"🗓️ Available {duration_minutes}-minute meeting slots:\n"
        result += "=" * 50 + "\n\n"

        # Display all slot times in the primary calendar's timezone for clarity
        primary_tz_str = attendee_timezones.get("primary", "UTC")
        try:
            primary_tz = ZoneInfo(primary_tz_str)
        except Exception:
            primary_tz = ZoneInfo("UTC")
        result += f"Times shown in primary timezone: {primary_tz_str}\n\n"

        for i, (start, end) in enumerate(free_slots, 1):
            # Convert from UTC-naive to primary timezone for display
            start_local = start.replace(tzinfo=ZoneInfo("UTC")).astimezone(primary_tz)
            end_local = end.replace(tzinfo=ZoneInfo("UTC")).astimezone(primary_tz)

            result += f"Option {i}:\n"
            result += f"  📅 {start_local.strftime('%A, %B %d, %Y')}\n"
            result += f"  ⏰ {start_local.strftime('%I:%M %p')} - {end_local.strftime('%I:%M %p')}\n"
            result += f"  Duration: {duration_minutes} minutes\n"
            result += "\n"

        result += f"Attendees checked: {', '.join(attendees)}\n"
        if preferred_time_start or preferred_time_end:
            # Show preferred window in primary tz for clarity
            primary_tz = attendee_timezones.get("primary", "UTC")
            start_str = (str(preferred_time_start)[:5]) if preferred_time_start else f"{int(earliest_hour):02d}:00"
            end_str = (str(preferred_time_end)[:5]) if preferred_time_end else f"{int(latest_hour):02d}:00"
            result += f"Preferred window (primary {primary_tz}): {start_str}-{end_str}\n"
            if use_attendee_timezones:
                result += "Timezones detected:\n"
                for cal_id, tz in attendee_timezones.items():
                    result += f"  • {cal_id}: {tz}\n"
        else:
            if use_attendee_timezones:
                result += "Timezones detected:\n"
                for cal_id, tz in attendee_timezones.items():
                    result += f"  • {cal_id}: {tz} (local {earliest_hour:02d}:00-{latest_hour:02d}:00)\n"
            else:
                result += f"Working hours: {earliest_hour:02d}:00 - {latest_hour:02d}:00 ({timezone})\n"

        logger.debug(f"Result: {result}")

        return result

    except HttpError as error:
        logger.error(f"An HTTP error occurred: {error}", exc_info=True)
        return f"Failed to find meeting slots: {error}"
    except Exception as e:
        logger.error(f"An error occurred: {e}", exc_info=True)
        return f"An error occurred while finding meeting slots: {e}"


# Example usage:
# print(list_calendars())
# print(get_events(calendar_id="primary", max_results=5))
# today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).isoformat() + "Z"
# today_end = datetime.now().replace(hour=23, minute=59, second=59, microsecond=999999).isoformat() + "Z"
# print(get_events(calendar_id="primary", time_min=today_start, time_max=today_end, max_results=5))
# print(create_event("Test Meeting", "2025-09-09T10:00:00", "2025-09-09T11:00:00", description="Test weekly sync"))
# print(update_event("prqskq3fjbunuhaqapejdvgk1g", summary="Updated Meeting Title"))
# print(delete_event("prqskq3fjbunuhaqapejdvgk1g"))
# print(get_free_busy("2025-09-09T10:00:00", "2025-09-11T20:00:00", calendars=["primary"]))
# print(quick_add_event("Lunch with Sarah tomorrow at noon"))
# print(find_meeting_slots(["colleague@example.com"], duration_minutes=30, date_start="2025-09-09",
# date_end="2025-09-11"))
# print(schedule_meeting_with_attendees(["colleague@example.com"], "Project Review", duration_minutes=60,
# auto_book_first=True))
