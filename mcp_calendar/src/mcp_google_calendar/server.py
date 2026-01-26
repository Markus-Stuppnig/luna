"""
MCP Server for Google Calendar.

Provides tools to read calendar events via the Model Context Protocol.
"""

import asyncio
import os
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# Import shared scopes from project root
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from google_scopes import GOOGLE_SCOPES

# Configuration
CREDENTIALS_PATH = Path(os.getenv("GOOGLE_CREDENTIALS_PATH", "credentials.json"))
TOKEN_PATH = Path(os.getenv("GOOGLE_TOKEN_PATH", "token.json"))
SCOPES = GOOGLE_SCOPES
TIMEZONE = ZoneInfo(os.getenv("CALENDAR_TIMEZONE", "Europe/Vienna"))

server = Server("google-calendar")


def get_google_credentials() -> Credentials:
    """Get or refresh Google API credentials."""
    creds = None

    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_PATH), SCOPES)
            creds = flow.run_local_server(port=0)

        with open(TOKEN_PATH, "w") as token:
            token.write(creds.to_json())

    return creds


def get_calendar_service():
    """Get Google Calendar API service."""
    creds = get_google_credentials()
    return build("calendar", "v3", credentials=creds)


def format_event(event: dict) -> str:
    """Format a calendar event for display."""
    start = event["start"].get("dateTime", event["start"].get("date"))
    summary = event.get("summary", "Kein Titel")

    if "T" in start:
        # Parse and convert to local timezone
        dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
        dt_local = dt.astimezone(TIMEZONE)
        return f"{dt_local.strftime('%H:%M')} - {summary}"
    else:
        return f"Ganztägig - {summary}"


def format_event_with_date(event: dict) -> str:
    """Format a calendar event with date for multi-day views."""
    start = event["start"].get("dateTime", event["start"].get("date"))
    summary = event.get("summary", "Kein Titel")

    if "T" in start:
        dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
        dt_local = dt.astimezone(TIMEZONE)
        return f"{dt_local.strftime('%d.%m %H:%M')} - {summary}"
    else:
        # All-day event - just show date
        date = datetime.strptime(start, "%Y-%m-%d")
        return f"{date.strftime('%d.%m')} Ganztägig - {summary}"


def get_events_for_range(start_time: datetime, end_time: datetime) -> list[dict]:
    """Get calendar events for a specific time range from all calendars."""
    service = get_calendar_service()

    # Ensure times have timezone info
    if start_time.tzinfo is None:
        start_time = start_time.replace(tzinfo=TIMEZONE)
    if end_time.tzinfo is None:
        end_time = end_time.replace(tzinfo=TIMEZONE)

    # Get all calendars
    calendars = service.calendarList().list().execute()
    all_events = []

    for cal in calendars.get("items", []):
        cal_id = cal["id"]

        # Skip holiday calendars
        if "holiday@group" in cal_id:
            continue

        try:
            events_result = service.events().list(
                calendarId=cal_id,
                timeMin=start_time.isoformat(),
                timeMax=end_time.isoformat(),
                singleEvents=True,
                orderBy="startTime",
                timeZone=str(TIMEZONE)
            ).execute()

            all_events.extend(events_result.get("items", []))
        except Exception:
            # Skip calendars we can't access
            continue

    # Sort all events by start time
    all_events.sort(key=lambda e: e["start"].get("dateTime", e["start"].get("date", "")))

    return all_events


@server.list_tools()
async def list_tools() -> list[Tool]:
    """List available calendar tools."""
    return [
        Tool(
            name="get_events_today",
            description="Holt alle Kalender-Events für heute. Gibt eine Liste der Termine mit Uhrzeit und Titel zurück.",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        Tool(
            name="get_events_tomorrow",
            description="Holt alle Kalender-Events für morgen. Gibt eine Liste der Termine mit Uhrzeit und Titel zurück.",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        Tool(
            name="get_upcoming_events",
            description="Holt Kalender-Events für die nächsten N Tage. Gibt eine Liste der Termine mit Datum, Uhrzeit und Titel zurück.",
            inputSchema={
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "description": "Anzahl der Tage in die Zukunft (Standard: 7)",
                        "default": 7
                    }
                },
                "required": []
            }
        ),
        Tool(
            name="get_events_for_date",
            description="Holt alle Kalender-Events für ein bestimmtes Datum. Datum im Format YYYY-MM-DD.",
            inputSchema={
                "type": "object",
                "properties": {
                    "date": {
                        "type": "string",
                        "description": "Datum im Format YYYY-MM-DD"
                    }
                },
                "required": ["date"]
            }
        ),
        Tool(
            name="create_event",
            description="Erstellt einen neuen Kalender-Termin. Nutze dieses Tool wenn der User einen neuen Termin erstellen möchte.",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Titel des Termins"
                    },
                    "start_datetime": {
                        "type": "string",
                        "description": "Startzeit im Format YYYY-MM-DDTHH:MM (z.B. 2024-01-25T14:00)"
                    },
                    "end_datetime": {
                        "type": "string",
                        "description": "Endzeit im Format YYYY-MM-DDTHH:MM (z.B. 2024-01-25T15:00). Falls nicht angegeben, wird 1 Stunde nach Start verwendet."
                    },
                    "description": {
                        "type": "string",
                        "description": "Optionale Beschreibung des Termins"
                    },
                    "location": {
                        "type": "string",
                        "description": "Optionaler Ort des Termins"
                    },
                    "all_day": {
                        "type": "boolean",
                        "description": "Ob es ein ganztägiger Termin ist (Standard: false)"
                    }
                },
                "required": ["title", "start_datetime"]
            }
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Handle tool calls."""

    if name == "get_events_today":
        now = datetime.now(TIMEZONE)
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = start_of_day + timedelta(days=1)

        events = get_events_for_range(start_of_day, end_of_day)
        formatted = [format_event(e) for e in events]

        if formatted:
            result = "Termine heute:\n" + "\n".join(f"• {e}" for e in formatted)
        else:
            result = "Keine Termine heute."

        return [TextContent(type="text", text=result)]

    elif name == "get_events_tomorrow":
        now = datetime.now(TIMEZONE)
        tomorrow = now + timedelta(days=1)
        start_of_day = tomorrow.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = start_of_day + timedelta(days=1)

        events = get_events_for_range(start_of_day, end_of_day)
        formatted = [format_event(e) for e in events]

        if formatted:
            result = "Termine morgen:\n" + "\n".join(f"• {e}" for e in formatted)
        else:
            result = "Keine Termine morgen."

        return [TextContent(type="text", text=result)]

    elif name == "get_upcoming_events":
        days = arguments.get("days", 7)
        now = datetime.now(TIMEZONE)
        end_date = now + timedelta(days=days)

        events = get_events_for_range(now, end_date)
        formatted = [format_event_with_date(e) for e in events]

        if formatted:
            result = f"Termine der nächsten {days} Tage:\n" + "\n".join(f"• {e}" for e in formatted)
        else:
            result = f"Keine Termine in den nächsten {days} Tagen."

        return [TextContent(type="text", text=result)]

    elif name == "get_events_for_date":
        date_str = arguments.get("date")
        try:
            target_date = datetime.strptime(date_str, "%Y-%m-%d")
            target_date = target_date.replace(tzinfo=TIMEZONE)
        except ValueError:
            return [TextContent(type="text", text=f"Ungültiges Datumsformat: {date_str}. Bitte YYYY-MM-DD verwenden.")]

        start_of_day = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = start_of_day + timedelta(days=1)

        events = get_events_for_range(start_of_day, end_of_day)
        formatted = [format_event(e) for e in events]

        date_display = target_date.strftime("%d.%m.%Y")
        if formatted:
            result = f"Termine am {date_display}:\n" + "\n".join(f"• {e}" for e in formatted)
        else:
            result = f"Keine Termine am {date_display}."

        return [TextContent(type="text", text=result)]

    elif name == "create_event":
        title = arguments.get("title")
        start_str = arguments.get("start_datetime")
        end_str = arguments.get("end_datetime")
        description = arguments.get("description", "")
        location = arguments.get("location", "")
        all_day = arguments.get("all_day", False)

        try:
            if all_day:
                # All-day event - parse date only
                start_date = datetime.strptime(start_str[:10], "%Y-%m-%d")
                end_date = start_date + timedelta(days=1)
                event_body = {
                    "summary": title,
                    "start": {"date": start_date.strftime("%Y-%m-%d")},
                    "end": {"date": end_date.strftime("%Y-%m-%d")},
                }
            else:
                # Timed event
                start_dt = datetime.strptime(start_str, "%Y-%m-%dT%H:%M")
                start_dt = start_dt.replace(tzinfo=TIMEZONE)

                if end_str:
                    end_dt = datetime.strptime(end_str, "%Y-%m-%dT%H:%M")
                    end_dt = end_dt.replace(tzinfo=TIMEZONE)
                else:
                    # Default to 1 hour duration
                    end_dt = start_dt + timedelta(hours=1)

                event_body = {
                    "summary": title,
                    "start": {"dateTime": start_dt.isoformat(), "timeZone": str(TIMEZONE)},
                    "end": {"dateTime": end_dt.isoformat(), "timeZone": str(TIMEZONE)},
                }

            if description:
                event_body["description"] = description
            if location:
                event_body["location"] = location

            service = get_calendar_service()
            service.events().insert(calendarId="primary", body=event_body).execute()

            if all_day:
                result = f"✅ Ganztägiger Termin erstellt: {title} am {start_date.strftime('%d.%m.%Y')}"
            else:
                result = f"✅ Termin erstellt: {title} am {start_dt.strftime('%d.%m.%Y um %H:%M')} Uhr"

            return [TextContent(type="text", text=result)]

        except ValueError as e:
            return [TextContent(type="text", text=f"Ungültiges Datumsformat. Bitte YYYY-MM-DDTHH:MM verwenden. Fehler: {str(e)}")]
        except Exception as e:
            return [TextContent(type="text", text=f"Fehler beim Erstellen des Termins: {str(e)}")]

    else:
        return [TextContent(type="text", text=f"Unbekanntes Tool: {name}")]


async def run_server():
    """Run the MCP server (async)."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )


def main():
    """Entry point for the MCP server."""
    asyncio.run(run_server())


if __name__ == "__main__":
    main()
