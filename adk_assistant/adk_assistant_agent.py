#!/usr/bin/env python3
"""ADK-based agent that uses the same tools as `assistant.py`, with no Gradio or LangChain.

This script is fully independent of `assistant.py` and builds an agent using the
Google ADK framework only. It wraps existing MCP tool functions exposed by
`additional_mcp`, `mcp_calendar`, and `mcp_gmail` without modifying those files.
"""
# flake8: noqa: E402
import pathlib
import sys

sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))

import asyncio
import os
from typing import List, Optional


from google import adk  # type: ignore
from google.adk.models import Gemini  # type: ignore
from google.adk.runners import Runner  # type: ignore
from google.adk.sessions import InMemorySessionService  # type: ignore
from google.adk.tools.function_tool import FunctionTool  # type: ignore
from google.genai import types  # type: ignore

# Upstream tools (do not modify these modules)
import mcp_calendar
import mcp_gmail

try:
    from logging_config import setup_logging

    logger = setup_logging(__name__)
except Exception:  # pylint: disable=broad-exception-caught
    import logging

    logging.basicConfig(level=logging.ERROR)
    logger = logging.getLogger(__name__)

ADK_INSTRUCTIONS = """
You are a helpful assistant that manages emails and calendar. You can use tools to act.

Custom rules:
- When asked to plan a day, create calendar events for the requested date with reasonable durations and descriptions.
- If asked to show a plan, only read and present existing events; do not create new ones.


Never end your response without taking an action if the task is incomplete.

# Important rules:
- Always call get_today_date tool to get today's date and weekday before creating calendar events and
  to understand the current date and weekday.
- Use reasonable defaults when information is missing:
  - Email sending: prefer draft_mode=true unless the user explicitly asks to send.
  - Meeting duration: default 30 minutes.
  - Calendar event duration: default 30 minutes.
But try to ask the user for clarification if possible.
"""


# Strictly typed wrappers around MCP tools (avoid typing.Any for ADK tool schema)

def list_gmail_tools() -> str:
    """List all available Gmail MCP tools."""
    return mcp_gmail.list_gmail_tools.fn()  # type: ignore[attr-defined]


def list_calendar_tools() -> str:
    """List all available Google Calendar MCP tools."""
    return mcp_calendar.list_calendar_tools.fn()  # type: ignore[attr-defined]


def get_emails_tool(
    gmail_query: str = "to:me in:inbox",
    count: int = 100,
    page: int = 1,
    full_body: bool = False,
) -> str:
    """Search Gmail by query, with pagination and optional full body."""
    return mcp_gmail.get_emails_tool.fn(  # type: ignore[attr-defined]
        gmail_query=gmail_query,
        count=count,
        page=page,
        full_body=full_body,
    )


def send_email_tool(
    to: str,
    subject: str,
    body: str,
    from_email: Optional[str] = None,
    cc: Optional[str] = None,
    bcc: Optional[str] = None,
    attachments: Optional[List[str]] = None,
    html_body: Optional[str] = None,
    draft_mode: bool = True,
) -> str:
    """Send an email or create a draft (default) via Gmail."""
    return mcp_gmail.send_email_tool.fn(  # type: ignore[attr-defined]
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


def get_today_date() -> str:
    """Get today's date and weekday as JSON string."""
    return mcp_gmail.get_today_date.fn({})  # type: ignore[attr-defined]


def get_calendar_events(
    calendar_id: str = "primary",
    time_min: Optional[str] = None,
    time_max: Optional[str] = None,
    max_results: int = 10,
    query: Optional[str] = None,
) -> str:
    """Fetch Google Calendar events with optional filters."""
    return mcp_calendar.get_events_tool.fn(  # type: ignore[attr-defined]
        calendar_id=calendar_id,
        time_min=time_min,
        time_max=time_max,
        max_results=max_results,
        query=query,
    )


def create_calendar_event(
    summary: str,
    start_time: str,
    end_time: str,
    calendar_id: str = "primary",
    description: Optional[str] = None,
    location: Optional[str] = None,
    attendees: Optional[List[str]] = None,
    recurrence: Optional[List[str]] = None,
    reminders: Optional[dict] = None,
    send_notifications: bool = False,
) -> str:
    """Create a calendar event with ISO8601 start/end times."""
    return mcp_calendar.create_event_tool.fn(  # type: ignore[attr-defined]
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


def update_calendar_event(
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
    """Update an existing calendar event by event_id."""
    return mcp_calendar.update_event_tool.fn(  # type: ignore[attr-defined]
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


def delete_calendar_event(
    event_id: str,
    calendar_id: str = "primary",
    send_notifications: bool = False,
) -> str:
    """Delete a calendar event by event_id."""
    return mcp_calendar.delete_event_tool.fn(  # type: ignore[attr-defined]
        event_id=event_id,
        calendar_id=calendar_id,
        send_notifications=send_notifications,
    )


def find_meeting_slots(
    attendees: List[str],
    duration_minutes: int = 30,
    date_start: Optional[str] = None,
    date_end: Optional[str] = None,
    preferred_time_start: Optional[str] = None,
    preferred_time_end: Optional[str] = None,
    earliest_hour: int = 7,
    latest_hour: int = 20,
    max_suggestions: int = 10,
) -> str:
    """Find available meeting slots for multiple attendees."""
    return mcp_calendar.find_meeting_slots_tool.fn(  # type: ignore[attr-defined]
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


def get_free_busy(
    time_min: str,
    time_max: str,
    calendars: Optional[List[str]] = None,
    timezone: str = "UTC",
) -> str:
    """Get free/busy blocks for one or more calendars in a time range."""
    return mcp_calendar.get_free_busy_tool.fn(  # type: ignore[attr-defined]
        time_min=time_min,
        time_max=time_max,
        calendars=calendars,
        timezone=timezone,
    )


# after imports in adk_assistant_agent.py
get_emails_tool.__doc__ = mcp_gmail.get_emails_tool.description
send_email_tool.__doc__ = mcp_gmail.send_email_tool.description
list_gmail_tools.__doc__ = mcp_gmail.list_gmail_tools.description
list_calendar_tools.__doc__ = mcp_calendar.list_calendar_tools.description
get_today_date.__doc__ = mcp_gmail.get_today_date.description
get_calendar_events.__doc__ = mcp_calendar.get_events_tool.description
create_calendar_event.__doc__ = mcp_calendar.create_event_tool.description
update_calendar_event.__doc__ = mcp_calendar.update_event_tool.description
delete_calendar_event.__doc__ = mcp_calendar.delete_event_tool.description
find_meeting_slots.__doc__ = mcp_calendar.find_meeting_slots_tool.description
get_free_busy.__doc__ = mcp_calendar.get_free_busy_tool.description


def _build_tools():
    """Build ADK FunctionTools from the typed wrappers above."""
    return [
        FunctionTool(list_gmail_tools),
        FunctionTool(list_calendar_tools),
        FunctionTool(get_emails_tool),
        FunctionTool(send_email_tool),
        FunctionTool(get_today_date),
        FunctionTool(get_calendar_events),
        FunctionTool(create_calendar_event),
        FunctionTool(update_calendar_event),
        FunctionTool(delete_calendar_event),
        FunctionTool(find_meeting_slots),
        FunctionTool(get_free_busy),
    ]


def _build_adk_agent():
    """Build an ADK agent with the same tools and instructions."""
    # Ensure API key for Google AI API
    if not os.getenv("GOOGLE_API_KEY") and os.getenv("GEMINI_API_KEY"):
        os.environ["GOOGLE_API_KEY"] = os.getenv("GEMINI_API_KEY", "")

    agent = adk.Agent(  # type: ignore[attr-defined]
        name="my_adk_agent",
        model=Gemini(model="gemini-1.5-pro-latest"),
        instruction=ADK_INSTRUCTIONS,
        tools=_build_tools(),
    )
    return agent


def main():
    """Run the ADK agent using Runner with an in-memory session and simple CLI."""
    agent = _build_adk_agent()
    session_service = InMemorySessionService()
    runner = Runner(app_name="assistant", agent=agent, session_service=session_service)

    async def create_session_id() -> str:
        session = await session_service.create_session(user_id="user", app_name="assistant")
        return session.id

    session_id = asyncio.run(create_session_id())
    print("ADK agent is running. Type messages, or 'exit' to quit.")

    def _print_event(event):
        # print(f"[debug] {type(event).__name__}: {getattr(event,'__dict__',{})}")
        try:
            printed = False

            # 1) Print directly from event.content.parts
            content = getattr(event, "content", None)
            if content is not None:
                parts = getattr(content, "parts", None)
                if parts:
                    for part in parts:
                        # Model text output
                        txt = getattr(part, "text", None)
                        if txt:
                            print(txt.strip())
                            printed = True
                        # Tool function response output
                        func_resp = getattr(part, "function_response", None)
                        if func_resp is not None:
                            resp_payload = getattr(func_resp, "response", None)
                            if isinstance(resp_payload, dict):
                                for key in ("result", "output", "message"):
                                    if key in resp_payload and isinstance(resp_payload[key], str):
                                        print(resp_payload[key].strip())
                                        printed = True
                                        break
                            elif resp_payload:
                                print(str(resp_payload))
                                printed = True
                        # Tool function call (announce)
                        func_call = getattr(part, "function_call", None)
                        if func_call is not None:
                            try:
                                print(f"[tool-call] {func_call.name}({func_call.args})")
                            except Exception:
                                print(f"[tool-call] {getattr(func_call, 'name', 'unknown')}()")
                            printed = True
                if printed:
                    return

            # 2) Fallback to response.candidates
            resp = getattr(event, "response", None)
            if resp is not None:
                candidates = getattr(resp, "candidates", None)
                if candidates:
                    for cand in candidates:
                        c_content = getattr(cand, "content", None)
                        c_parts = getattr(c_content, "parts", None) if c_content else None
                        if c_parts:
                            for part in c_parts:
                                txt = getattr(part, "text", None)
                                if txt:
                                    print(txt.strip())
                                    return
                if hasattr(resp, "text"):
                    print(getattr(resp, "text"))
                    return

            # 3) Common direct fields
            for attr in ("tool_result", "result", "output", "message"):
                val = getattr(event, attr, None)
                if isinstance(val, str) and val.strip():
                    print(val)
                    return

            # 4) Last resort
            print(f"[event] {type(event).__name__}")
        except Exception as e:  # pylint: disable=broad-exception-caught
            print(f"[event-error] {type(event).__name__}: {e}")
    while True:
        try:
            user_msg = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting.")
            break
        if user_msg.lower() in {"exit", "quit"}:
            print("Goodbye.")
            break
        if not user_msg:
            continue
        content = types.Content(role="user", parts=[types.Part.from_text(text=user_msg)])
        try:
            for event in runner.run(user_id="user", session_id=session_id, new_message=content):
                _print_event(event)
        except Exception as e:  # pylint: disable=broad-exception-caught
            print(f"Error during run: {e}")


if __name__ == "__main__":
    main()

# Run this as `adk web` to get the web UI
