"""
MCP Server for Google Contacts.

Provides tools to sync and manage contacts via the Model Context Protocol.
Contacts are cached locally in SQLite with a notes field for storing facts.
"""

import asyncio
import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path

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
DB_PATH = Path(os.getenv("LUNA_DB_PATH", Path(__file__).parent.parent.parent.parent / "data" / "luna.db"))
SCOPES = GOOGLE_SCOPES

server = Server("google-contacts")


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


def get_people_service():
    """Get Google People API service."""
    creds = get_google_credentials()
    return build("people", "v1", credentials=creds)


def get_db_connection():
    """Get SQLite database connection."""
    return sqlite3.connect(DB_PATH)


def fetch_google_contacts() -> list[dict]:
    """Fetch all contacts from Google People API."""
    service = get_people_service()

    results = service.people().connections().list(
        resourceName="people/me",
        pageSize=1000,
        personFields="names,emailAddresses,phoneNumbers,organizations"
    ).execute()

    contacts = []
    for person in results.get("connections", []):
        names = person.get("names", [])
        emails = person.get("emailAddresses", [])
        phones = person.get("phoneNumbers", [])
        orgs = person.get("organizations", [])

        name = names[0].get("displayName", "") if names else ""
        if not name:
            continue  # Skip contacts without names

        contacts.append({
            "google_id": person.get("resourceName", ""),
            "name": name,
            "emails": [e.get("value", "") for e in emails],
            "phones": [p.get("value", "") for p in phones],
            "organization": orgs[0].get("name", "") if orgs else ""
        })

    return contacts


def sync_contacts_to_db() -> dict:
    """Sync contacts from Google to local database. Returns sync stats."""
    google_contacts = fetch_google_contacts()
    google_ids = set()

    conn = get_db_connection()
    c = conn.cursor()

    inserted = 0
    updated = 0
    now = datetime.now().isoformat()

    for contact in google_contacts:
        google_id = contact["google_id"]
        google_ids.add(google_id)

        emails_json = json.dumps(contact["emails"]) if contact["emails"] else None
        phones_json = json.dumps(contact["phones"]) if contact["phones"] else None

        # Check if exists
        c.execute("SELECT id FROM contacts WHERE google_id = ?", (google_id,))
        existing = c.fetchone()

        if existing:
            # Update but preserve notes
            c.execute("""
                UPDATE contacts
                SET name = ?, emails = ?, phones = ?, organization = ?, synced_at = ?, updated_at = ?
                WHERE google_id = ?
            """, (contact["name"], emails_json, phones_json, contact["organization"], now, now, google_id))
            updated += 1
        else:
            c.execute("""
                INSERT INTO contacts (google_id, name, emails, phones, organization, synced_at, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (google_id, contact["name"], emails_json, phones_json, contact["organization"], now, now, now))
            inserted += 1

    # Delete contacts no longer in Google (but only if they have no notes)
    if google_ids:
        placeholders = ",".join("?" * len(google_ids))
        c.execute(f"""
            DELETE FROM contacts
            WHERE google_id NOT IN ({placeholders})
            AND (notes IS NULL OR notes = '')
        """, tuple(google_ids))
        deleted = c.rowcount
    else:
        deleted = 0

    conn.commit()
    conn.close()

    return {
        "total_google": len(google_contacts),
        "inserted": inserted,
        "updated": updated,
        "deleted": deleted
    }


def search_contacts(query: str) -> list[dict]:
    """Search local contacts by name."""
    conn = get_db_connection()
    c = conn.cursor()

    search_pattern = f"%{query}%"
    c.execute("""
        SELECT id, google_id, name, emails, phones, organization, notes
        FROM contacts WHERE name LIKE ? COLLATE NOCASE
        ORDER BY name
        LIMIT 20
    """, (search_pattern,))
    rows = c.fetchall()
    conn.close()

    return [{
        "id": r[0],
        "google_id": r[1],
        "name": r[2],
        "emails": json.loads(r[3]) if r[3] else [],
        "phones": json.loads(r[4]) if r[4] else [],
        "organization": r[5],
        "notes": r[6]
    } for r in rows]


def get_contact_notes(contact_id: int) -> dict | None:
    """Get a contact with their notes."""
    conn = get_db_connection()
    c = conn.cursor()

    c.execute("""
        SELECT id, name, notes FROM contacts WHERE id = ?
    """, (contact_id,))
    row = c.fetchone()
    conn.close()

    if row:
        return {"id": row[0], "name": row[1], "notes": row[2]}
    return None


def update_notes(contact_id: int, notes: str, append: bool = True) -> bool:
    """Update or append to a contact's notes."""
    conn = get_db_connection()
    c = conn.cursor()

    if append:
        c.execute("SELECT notes FROM contacts WHERE id = ?", (contact_id,))
        row = c.fetchone()
        if not row:
            conn.close()
            return False

        existing_notes = row[0] or ""
        timestamp = datetime.now().strftime("%Y-%m-%d")
        new_entry = f"{timestamp}: {notes}"

        if existing_notes:
            updated_notes = f"{existing_notes}\n{new_entry}"
        else:
            updated_notes = new_entry
    else:
        updated_notes = notes

    now = datetime.now().isoformat()
    c.execute("UPDATE contacts SET notes = ?, updated_at = ? WHERE id = ?", (updated_notes, now, contact_id))

    success = c.rowcount > 0
    conn.commit()
    conn.close()

    return success


def list_contacts_with_notes_db() -> list[dict]:
    """Get all contacts that have notes."""
    conn = get_db_connection()
    c = conn.cursor()

    c.execute("""
        SELECT id, name, organization, notes
        FROM contacts
        WHERE notes IS NOT NULL AND notes != ''
        ORDER BY name
    """)
    rows = c.fetchall()
    conn.close()

    return [{
        "id": r[0],
        "name": r[1],
        "organization": r[2],
        "notes": r[3]
    } for r in rows]


@server.list_tools()
async def list_tools() -> list[Tool]:
    """List available contacts tools."""
    return [
        Tool(
            name="sync_contacts",
            description="Synchronisiert alle Kontakte von Google Contacts in die lokale Datenbank. Sollte nur aufgerufen werden wenn der User /kontakte eingibt.",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        Tool(
            name="search_contacts",
            description="Sucht lokale Kontakte nach Name. Gibt bis zu 20 passende Kontakte zurück.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Suchbegriff für den Kontaktnamen"
                    }
                },
                "required": ["query"]
            }
        ),
        Tool(
            name="get_contact_notes",
            description="Holt die Notizen/Fakten zu einem bestimmten Kontakt.",
            inputSchema={
                "type": "object",
                "properties": {
                    "contact_id": {
                        "type": "integer",
                        "description": "ID des Kontakts"
                    }
                },
                "required": ["contact_id"]
            }
        ),
        Tool(
            name="update_contact_notes",
            description="Aktualisiert oder ergänzt die Notizen eines Kontakts. Nutze append=true um neue Fakten hinzuzufügen.",
            inputSchema={
                "type": "object",
                "properties": {
                    "contact_id": {
                        "type": "integer",
                        "description": "ID des Kontakts"
                    },
                    "notes": {
                        "type": "string",
                        "description": "Die neue Notiz oder der neue Fakt"
                    },
                    "append": {
                        "type": "boolean",
                        "description": "Wenn true, wird die Notiz angehängt. Wenn false, werden alle Notizen ersetzt.",
                        "default": True
                    }
                },
                "required": ["contact_id", "notes"]
            }
        ),
        Tool(
            name="list_contacts_with_notes",
            description="Gibt alle Kontakte zurück, die Notizen/Fakten gespeichert haben.",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Handle tool calls."""

    if name == "sync_contacts":
        try:
            stats = sync_contacts_to_db()
            result = (
                f"Kontakte synchronisiert:\n"
                f"• {stats['total_google']} Kontakte von Google\n"
                f"• {stats['inserted']} neu hinzugefügt\n"
                f"• {stats['updated']} aktualisiert\n"
                f"• {stats['deleted']} gelöscht (ohne Notizen)"
            )
            return [TextContent(type="text", text=result)]
        except Exception as e:
            return [TextContent(type="text", text=f"Fehler beim Synchronisieren: {str(e)}")]

    elif name == "search_contacts":
        query = arguments.get("query", "")
        contacts = search_contacts(query)

        if contacts:
            result = f"Gefundene Kontakte für '{query}':\n"
            for c in contacts:
                org_str = f" ({c['organization']})" if c['organization'] else ""
                result += f"• [{c['id']}] {c['name']}{org_str}\n"
            return [TextContent(type="text", text=result)]
        else:
            return [TextContent(type="text", text=f"Keine Kontakte gefunden für '{query}'.")]

    elif name == "get_contact_notes":
        contact_id = arguments.get("contact_id")
        contact = get_contact_notes(contact_id)

        if contact:
            notes = contact['notes'] or "Keine Notizen vorhanden."
            result = f"Notizen für {contact['name']}:\n{notes}"
            return [TextContent(type="text", text=result)]
        else:
            return [TextContent(type="text", text=f"Kontakt mit ID {contact_id} nicht gefunden.")]

    elif name == "update_contact_notes":
        contact_id = arguments.get("contact_id")
        notes = arguments.get("notes", "")
        append = arguments.get("append", True)

        success = update_notes(contact_id, notes, append)

        if success:
            return [TextContent(type="text", text=f"Notiz gespeichert für Kontakt ID {contact_id}.")]
        else:
            return [TextContent(type="text", text=f"Fehler: Kontakt mit ID {contact_id} nicht gefunden.")]

    elif name == "list_contacts_with_notes":
        contacts = list_contacts_with_notes_db()

        if contacts:
            result = "Kontakte mit Notizen:\n\n"
            for c in contacts:
                org_str = f" ({c['organization']})" if c['organization'] else ""
                result += f"**{c['name']}**{org_str}\n{c['notes']}\n\n"
            return [TextContent(type="text", text=result)]
        else:
            return [TextContent(type="text", text="Keine Kontakte mit Notizen gefunden.")]

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
