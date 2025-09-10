## Gmail + Google Calendar AI Assistant (with MCP)

End-to-end assistant for Gmail and Google Calendar with:

- **FastMCP servers**: `mcp_gmail.py` and `mcp_calendar.py` expose tools for any MCP-capable IDE/agent.
- **Gradio chat agent**: `assistant.py` provides an interactive ReAct agent UI.
- **Non-interactive CLI agent**: `automation_agent.py` runs a one-shot prompt for cron/systemd.
- **Robust logging**: unified file logging and filtered console logs.

### Supported functionality

- **Gmail**
  - Search emails with flexible queries and pagination.
  - Send emails or create drafts (safe by default) with CC/BCC and attachments.
  - Utility: today’s date with weekday for constructing date filters.

- **Google Calendar**
  - Read events (time window, query, calendar selection, includes `event_id`).
  - Create, update, delete events (with optional attendee notifications).
  - Free/busy lookups for multiple calendars.
  - Find meeting slots with timezone-aware working hours and preferred windows.
  - Utility: today’s date with weekday.

- **Agents**
  - `assistant.py`: interactive agent with clarifying questions.
  - `automation_agent.py`: non-interactive agent (no `ask_user`), strict literal-JSON tool inputs.

### Google ADK agents (Web UI and CLI)

This repo also includes Google ADK-based agents that wrap the same Gmail/Calendar tools and can be used with the ADK Dev UI or the terminal.

- Package: `adk_assistant/`
  - `adk_assistant/adk_assistant_agent.py`: agent definition using ADK `FunctionTool`s; supports terminal chat.
  - `adk_assistant/agent.py`: ADK discovery entrypoint that exposes `root_agent`, `agent`, and `agents=[root_agent]`.

Prerequisites:
- `pip install google-adk`
- Model auth: set `GOOGLE_API_KEY` (or use Vertex AI vars per ADK docs)

Run with the Web UI (Dev UI):
```bash
cd /home/sshnaidm/sources/ai-assistant
adk web
# then open the provided URL and select the agent exposed by adk_assistant
```
If your ADK version requires an explicit agent target, use:
```bash
adk web --agent adk_assistant.agent:root_agent
```
See ADK Quickstart for structure and details: [link](https://google.github.io/adk-docs/get-started/quickstart/#create-multitoolagentjava).

Run in the terminal (two options):
```bash
# Option A: ADK CLI
adk run adk_assistant.agent:root_agent

# Option B: the built-in terminal runner in this repo
python -m adk_assistant.adk_assistant_agent
```
Notes:
- The terminal runner prints both tool outputs (e.g., created event details) and model text responses.
- Tool descriptions shown in the ADK UI are synced from the MCP tool descriptions.

## Prerequisites

- Python 3.9+
- Google Cloud OAuth credentials enabling Gmail and Calendar APIs
- Optional: Ollama for local models

## Setup

### 1) Google Cloud: APIs, OAuth client, and credentials

1. Enable APIs: Gmail API and Google Calendar API.
2. Create OAuth client ID (Desktop app) and download the JSON.
3. Save the file to `~/.config/credentials.json` (or set `CREDENTIALS_FILE`).

```bash
mkdir -p ~/.config
mv /path/to/downloaded/client_secret.json ~/.config/credentials.json
```

### 2) Clone and install

```bash
git clone https://github.com/sshnaidm/ai-assistant
cd ai-assistant
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3) Environment variables

- `CREDENTIALS_FILE` (recommended): absolute path to credentials JSON.
- `LOG_LEVEL`: INFO (default), DEBUG, WARNING, ERROR.
- `GOOGLE_API_KEY`: required if using Gemini.

```bash
export CREDENTIALS_FILE="$HOME/.config/credentials.json"
export LOG_LEVEL=INFO
export GOOGLE_API_KEY=your_key_here  # if using Gemini
```

First run will create `token.json` with granted scopes. If you later change scopes, delete `token.json` and re-auth.

## Running

### Gradio chat agent

```bash
python assistant.py
```

Configure model in `models.py` and `assistant.py`. The agent can ask clarifying questions via `ask_user`.

### Non-interactive one-shot agent

```bash
python automation_agent.py --prompt "summarize yesterday's emails and draft a reply to me" \
  --max-iterations 6 --timeout 180
```

Notes:
- Uses a minimal profile (no `ask_user`), strict literal-JSON tool inputs.
- Safe defaults (e.g., Gmail drafts by default).

### Start MCP servers directly

- Gmail MCP server

```bash
CREDENTIALS_FILE=$HOME/.config/credentials.json python mcp_gmail.py
```

- Google Calendar MCP server

```bash
CREDENTIALS_FILE=$HOME/.config/credentials.json python mcp_calendar.py
```

## Available MCP tools

### Gmail (`mcp_gmail.py`)
- `Get Emails from Gmail` → `get_emails_tool`
  - Input: `gmail_query`, `count`, `page`, `full_body`
  - Example: `{ "gmail_query": "to:me in:inbox", "count": 50 }`
- `Send or Draft Email via Gmail` → `send_email_tool`
  - Input: `to`, `subject`, `body`, `from_email`, `cc`, `bcc`, `attachments`, `html_body`, `draft_mode`
  - Safety: `draft_mode=true` by default
- `Get Today's Date` → `get_today_date`
  - Output: `{ "date": "YYYY-MM-DD", "weekday": "Monday" }`

### Google Calendar (`mcp_calendar.py`)
- `Get Calendar Events` → `get_events_tool`
  - Input: `calendar_id`, `time_min`, `time_max`, `max_results`, `query`
  - Returns events with `event_id`
- `Create Calendar Event` → `create_event_tool`
- `Update Calendar Event` → `update_event_tool`
- `Delete Calendar Event` → `delete_event_tool`
- `Find Meeting Slots` → `find_meeting_slots_tool`
  - Inputs include `attendees`, `duration_minutes`, `date_start`, `date_end`, `preferred_time_start`, `preferred_time_end`, `earliest_hour`, `latest_hour`, `max_suggestions`
  - Timezone-aware; preferred times interpreted in primary calendar’s timezone
- `Get Free Busy Information` → `get_free_busy_tool`
- `Get Today's Date` → `get_today_date`

## Configure MCP clients

### Cursor

Option A: Project-level `.cursor/mcp.json` (create in your repo root):

```json
{
  "mcpServers": {
    "gmail_mails": {
      "command": "python",
      "args": ["/path/to/dir/ai-assistant/mcp_gmail.py"],
      "env": {
        "CREDENTIALS_FILE": "~/.config/credentials.json",
        "LOG_LEVEL": "INFO"
      }
    },
    "google_calendar": {
      "command": "python",
      "args": ["/path/to/dir/ai-assistant/mcp_calendar.py"],
      "env": {
        "CREDENTIALS_FILE": "~/.config/credentials.json",
        "LOG_LEVEL": "INFO"
      }
    }
  }
}
```

Option B: Cursor Settings → MCP → Add servers (same fields as above). Ensure absolute paths.

### Claude Code (Claude Desktop)

Create or edit `~/.config/Claude/claude_desktop_config.json` (Linux; macOS and Windows use their respective app config dirs):

```json
{
  "mcpServers": {
    "gmail_mails": {
      "command": "python",
      "args": ["/path/to/dir/ai-assistant/mcp_gmail.py"],
      "env": {
        "CREDENTIALS_FILE": "~/.config/credentials.json",
        "LOG_LEVEL": "INFO"
      }
    },
    "google_calendar": {
      "command": "python",
      "args": ["/path/to/dir/ai-assistant/mcp_calendar.py"],
      "env": {
        "CREDENTIALS_FILE": "~/.config/credentials.json",
        "LOG_LEVEL": "INFO"
      }
    }
  }
}
```

Restart Claude Desktop after editing. The tools will appear in the Tools panel.

### Gemini CLI

Gemini’s official CLI does not currently support MCP servers directly. Recommended options:

- Use this repo’s non-interactive runner:

```bash
python automation_agent.py --prompt "plan 30-min meeting with alice@example.com this Friday afternoon"
```

- Or use an MCP-capable client (Cursor, Claude Desktop) to access the same tools.

## Logging

- Central log file (for modules that opt-in): `gmail_agent.log` via `logging_config.py`.
- Independent logs per MCP server: `mcp_gmail.log`, `mcp_calendar.log`.
- Control verbosity with `LOG_LEVEL`. Console output filters third-party noise.

## Tips & Troubleshooting

- OAuth scopes changed? Delete `token.json` and re-auth.
- Attachments not found? Use absolute paths for reliability.
- Calendar preferred times ignored? Ensure `preferred_time_start`/`preferred_time_end` are HH:MM strings.

## Project structure

- `assistant.py`: Gradio chat agent (interactive).
- `automation_agent.py`: Non-interactive, one-shot agent runner.
- `gmail.py`: Gmail API interactions (search, send/draft).
- `google_calendar.py`: Calendar API interactions (events, free/busy, slots).
- `mcp_gmail.py`: FastMCP Gmail tools server.
- `mcp_calendar.py`: FastMCP Calendar tools server.
- `models.py`: LLM initialization and choices (Gemini, Ollama, OpenAI).
- `logging_config.py`: Optional centralized logging setup.
- `requirements.txt`: Dependencies.
- `token.json`: Generated after first auth (do not commit).
