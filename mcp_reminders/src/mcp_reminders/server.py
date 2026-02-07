"""
MCP Server for Reminders.

Provides timer-based reminders with HTTP callback to Luna bot.
Each reminder gets its own asyncio timer - no polling.
"""

import asyncio
import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# Configuration
DB_PATH = Path(os.getenv("LUNA_DB_PATH", "data/luna.db"))
CALLBACK_URL = os.getenv("LUNA_CALLBACK_URL", "http://localhost:8765/reminder")
TIMEZONE = ZoneInfo("Europe/Vienna")

server = Server("reminders")

# Track active timers: {reminder_id: asyncio.Task}
active_timers: dict[int, asyncio.Task] = {}


def get_db_connection():
    """Get SQLite database connection."""
    return sqlite3.connect(DB_PATH)


def add_reminder_to_db(message: str, remind_at: datetime) -> int:
    """Insert reminder into database. Returns reminder ID."""
    conn = get_db_connection()
    c = conn.cursor()

    c.execute(
        "INSERT INTO reminders (message, remind_at) VALUES (?, ?)",
        (message, remind_at.isoformat())
    )

    reminder_id = c.lastrowid
    conn.commit()
    conn.close()

    return reminder_id


def mark_reminder_sent(reminder_id: int):
    """Mark a reminder as sent in the database."""
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("UPDATE reminders SET sent = TRUE WHERE id = ?", (reminder_id,))
    conn.commit()
    conn.close()


def delete_reminder_from_db(reminder_id: int) -> bool:
    """Delete a reminder from database. Returns True if deleted."""
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))
    deleted = c.rowcount > 0
    conn.commit()
    conn.close()
    return deleted


def get_pending_reminders() -> list[dict]:
    """Get all pending (unsent) reminders from database."""
    conn = get_db_connection()
    c = conn.cursor()

    c.execute(
        "SELECT id, message, remind_at FROM reminders WHERE sent = FALSE ORDER BY remind_at"
    )

    rows = c.fetchall()
    conn.close()

    return [{"id": r[0], "message": r[1], "remind_at": r[2]} for r in rows]


async def fire_reminder(reminder_id: int, message: str):
    """Send reminder via HTTP callback to Luna bot."""
    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                CALLBACK_URL,
                json={"id": reminder_id, "message": message},
                timeout=10.0
            )
        mark_reminder_sent(reminder_id)
    except Exception as e:
        print(f"Failed to fire reminder {reminder_id}: {e}")
    finally:
        # Remove from active timers
        active_timers.pop(reminder_id, None)


async def schedule_reminder(reminder_id: int, message: str, remind_at: datetime):
    """Schedule a reminder to fire at the specified time."""
    now = datetime.now(TIMEZONE)

    # Parse remind_at if it's a string
    if isinstance(remind_at, str):
        remind_at = datetime.fromisoformat(remind_at)

    # Add timezone if missing
    if remind_at.tzinfo is None:
        remind_at = remind_at.replace(tzinfo=TIMEZONE)

    delay = (remind_at - now).total_seconds()

    if delay <= 0:
        # Already due, fire immediately
        await fire_reminder(reminder_id, message)
    else:
        # Wait and then fire
        await asyncio.sleep(delay)
        await fire_reminder(reminder_id, message)


def start_reminder_timer(reminder_id: int, message: str, remind_at: datetime):
    """Start an asyncio task for a reminder."""
    # Cancel existing timer if any
    if reminder_id in active_timers:
        active_timers[reminder_id].cancel()

    # Create new timer task
    task = asyncio.create_task(schedule_reminder(reminder_id, message, remind_at))
    active_timers[reminder_id] = task


def cancel_reminder_timer(reminder_id: int):
    """Cancel a reminder's timer if it exists."""
    task = active_timers.pop(reminder_id, None)
    if task:
        task.cancel()


async def restore_pending_reminders():
    """Restore timers for all pending reminders on server start."""
    reminders = get_pending_reminders()
    for r in reminders:
        start_reminder_timer(r["id"], r["message"], r["remind_at"])
    print(f"Restored {len(reminders)} pending reminder timers")


@server.list_tools()
async def list_tools() -> list[Tool]:
    """List available reminder tools."""
    return [
        Tool(
            name="create_reminder",
            description="Erstellt eine Erinnerung. Luna sendet zur angegebenen Zeit eine Nachricht.",
            inputSchema={
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "Woran erinnert werden soll"
                    },
                    "remind_at": {
                        "type": "string",
                        "description": "Wann erinnern im ISO Format YYYY-MM-DDTHH:MM"
                    }
                },
                "required": ["message", "remind_at"]
            }
        ),
        Tool(
            name="list_reminders",
            description="Zeigt alle ausstehenden Erinnerungen.",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        Tool(
            name="delete_reminder",
            description="Löscht eine Erinnerung.",
            inputSchema={
                "type": "object",
                "properties": {
                    "reminder_id": {
                        "type": "integer",
                        "description": "ID der Erinnerung"
                    }
                },
                "required": ["reminder_id"]
            }
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Handle tool calls."""

    if name == "create_reminder":
        message = arguments.get("message", "")
        remind_at_str = arguments.get("remind_at", "")

        if not message or not remind_at_str:
            return [TextContent(type="text", text="Fehler: message und remind_at sind erforderlich.")]

        try:
            remind_at = datetime.fromisoformat(remind_at_str)
            if remind_at.tzinfo is None:
                remind_at = remind_at.replace(tzinfo=TIMEZONE)

            # Save to DB
            reminder_id = add_reminder_to_db(message, remind_at)

            # Start timer
            start_reminder_timer(reminder_id, message, remind_at)

            # Format response
            time_str = remind_at.strftime("%d.%m. um %H:%M")
            return [TextContent(type="text", text=f"Erinnerung erstellt: '{message}' am {time_str}")]

        except ValueError as e:
            return [TextContent(type="text", text=f"Fehler: Ungültiges Datumsformat. Bitte YYYY-MM-DDTHH:MM verwenden.")]

    elif name == "list_reminders":
        reminders = get_pending_reminders()

        if not reminders:
            return [TextContent(type="text", text="Keine ausstehenden Erinnerungen.")]

        lines = ["Ausstehende Erinnerungen:"]
        for r in reminders:
            remind_at = datetime.fromisoformat(r["remind_at"])
            if remind_at.tzinfo is None:
                remind_at = remind_at.replace(tzinfo=TIMEZONE)
            time_str = remind_at.strftime("%d.%m. %H:%M")
            lines.append(f"• [{r['id']}] {time_str}: {r['message']}")

        return [TextContent(type="text", text="\n".join(lines))]

    elif name == "delete_reminder":
        reminder_id = arguments.get("reminder_id")

        if not reminder_id:
            return [TextContent(type="text", text="Fehler: reminder_id ist erforderlich.")]

        # Cancel timer
        cancel_reminder_timer(reminder_id)

        # Delete from DB
        deleted = delete_reminder_from_db(reminder_id)

        if deleted:
            return [TextContent(type="text", text=f"Erinnerung {reminder_id} gelöscht.")]
        else:
            return [TextContent(type="text", text=f"Erinnerung {reminder_id} nicht gefunden.")]

    else:
        return [TextContent(type="text", text=f"Unbekanntes Tool: {name}")]


async def run_server():
    """Run the MCP server."""
    # Restore pending reminders on startup
    await restore_pending_reminders()

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
