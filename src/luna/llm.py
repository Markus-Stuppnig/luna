import anthropic
import re
from datetime import datetime
from zoneinfo import ZoneInfo

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from luna.config import (
    ANTHROPIC_API_KEY, LLM_MODEL, MCP_CALENDAR_DIR, MCP_CONTACTS_DIR,
    GOOGLE_CREDENTIALS_PATH, GOOGLE_TOKEN_PATH, DB_PATH, get_logger
)
from luna import memory

# =============================================================================
# LOGGING SETUP
# =============================================================================
logger = get_logger("llm")
logger.info("LLM module loading...")
logger.debug(f"ANTHROPIC_API_KEY: {'*' * 10 + ANTHROPIC_API_KEY[-4:] if ANTHROPIC_API_KEY else 'NOT SET'}")
logger.debug(f"LLM_MODEL: {LLM_MODEL}")

logger.info("Initializing Anthropic client...")
client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
logger.info("Anthropic client initialized successfully")

# =============================================================================
# CALENDAR TOOLS FOR ANTHROPIC API
# =============================================================================
CALENDAR_TOOLS = [
    {
        "name": "get_events_today",
        "description": "Holt alle Kalender-Events für heute. Nutze dieses Tool wenn der User nach heutigen Terminen fragt.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "get_events_tomorrow",
        "description": "Holt alle Kalender-Events für morgen. Nutze dieses Tool wenn der User nach morgigen Terminen fragt.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "get_upcoming_events",
        "description": "Holt Kalender-Events für die nächsten N Tage. Nutze dieses Tool wenn der User nach Terminen in den nächsten Tagen/dieser Woche fragt.",
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "Anzahl der Tage in die Zukunft (Standard: 7)"
                }
            },
            "required": []
        }
    },
    {
        "name": "get_events_for_date",
        "description": "Holt alle Kalender-Events für ein bestimmtes Datum. Nutze dieses Tool wenn der User nach Terminen an einem spezifischen Tag fragt.",
        "input_schema": {
            "type": "object",
            "properties": {
                "date": {
                    "type": "string",
                    "description": "Datum im Format YYYY-MM-DD"
                }
            },
            "required": ["date"]
        }
    },
    {
        "name": "create_event",
        "description": "Erstellt einen neuen Kalender-Termin. Nutze dieses Tool wenn der User einen neuen Termin erstellen möchte.",
        "input_schema": {
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
                    "description": "Endzeit im Format YYYY-MM-DDTHH:MM. Falls nicht angegeben, wird 1 Stunde nach Start verwendet."
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
    },
    {
        "name": "create_reminder",
        "description": "Erstellt eine Erinnerung. Luna sendet zur angegebenen Zeit eine Nachricht. Nutze bei 'erinnere mich an...' oder 'reminder'.",
        "input_schema": {
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
    }
]


async def call_mcp_tool(tool_name: str, arguments: dict = None) -> str:
    """Call a tool on the MCP Calendar server."""
    logger.info(f"call_mcp_tool() called: {tool_name} with args {arguments}")

    if arguments is None:
        arguments = {}

    server_params = StdioServerParameters(
        command="uv",
        args=["run", "mcp-google-calendar"],
        cwd=str(MCP_CALENDAR_DIR),
        env={
            "GOOGLE_CREDENTIALS_PATH": str(GOOGLE_CREDENTIALS_PATH),
            "GOOGLE_TOKEN_PATH": str(GOOGLE_TOKEN_PATH),
        }
    )

    try:
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                logger.info(f"MCP session initialized, calling tool: {tool_name}")

                result = await session.call_tool(tool_name, arguments)

                if result.content:
                    text_result = result.content[0].text
                    logger.info(f"MCP tool result: {text_result[:100]}...")
                    return text_result
                else:
                    logger.warning("MCP tool returned no content")
                    return "Keine Ergebnisse."
    except Exception as e:
        logger.error(f"MCP tool call failed: {e}", exc_info=True)
        return f"Fehler beim Abrufen der Kalenderdaten: {str(e)}"


async def call_mcp_contacts_tool(tool_name: str, arguments: dict = None) -> str:
    """Call a tool on the MCP Contacts server."""
    logger.info(f"call_mcp_contacts_tool() called: {tool_name} with args {arguments}")

    if arguments is None:
        arguments = {}

    server_params = StdioServerParameters(
        command="uv",
        args=["run", "mcp-google-contacts"],
        cwd=str(MCP_CONTACTS_DIR),
        env={
            "GOOGLE_CREDENTIALS_PATH": str(GOOGLE_CREDENTIALS_PATH),
            "GOOGLE_TOKEN_PATH": str(GOOGLE_TOKEN_PATH),
            "LUNA_DB_PATH": str(DB_PATH),
        }
    )

    try:
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                logger.info(f"MCP Contacts session initialized, calling tool: {tool_name}")

                result = await session.call_tool(tool_name, arguments)

                if result.content:
                    text_result = result.content[0].text
                    logger.info(f"MCP Contacts tool result: {text_result[:100]}...")
                    return text_result
                else:
                    logger.warning("MCP Contacts tool returned no content")
                    return "Keine Ergebnisse."
    except Exception as e:
        logger.error(f"MCP Contacts tool call failed: {e}", exc_info=True)
        return f"Fehler beim Abrufen der Kontaktdaten: {str(e)}"


async def handle_create_reminder(arguments: dict) -> str:
    """Handle the create_reminder tool call locally."""
    logger.info(f"handle_create_reminder() called with args {arguments}")

    message = arguments.get("message", "")
    remind_at_str = arguments.get("remind_at", "")

    if not message or not remind_at_str:
        return "Fehler: message und remind_at sind erforderlich."

    try:
        # Parse the datetime
        remind_at = datetime.fromisoformat(remind_at_str)

        # Add timezone if not present
        TIMEZONE = ZoneInfo("Europe/Vienna")
        if remind_at.tzinfo is None:
            remind_at = remind_at.replace(tzinfo=TIMEZONE)

        # Create the reminder
        reminder_id = memory.add_reminder(message, remind_at)

        # Format for user
        remind_at_local = remind_at.astimezone(TIMEZONE)
        time_str = remind_at_local.strftime("%d.%m. um %H:%M")

        return f"Erinnerung erstellt: '{message}' am {time_str}"

    except ValueError as e:
        logger.error(f"Invalid datetime format: {remind_at_str}")
        return f"Fehler: Ungültiges Datumsformat. Bitte YYYY-MM-DDTHH:MM verwenden."
    except Exception as e:
        logger.error(f"Failed to create reminder: {e}", exc_info=True)
        return f"Fehler beim Erstellen der Erinnerung: {str(e)}"


SYSTEM_PROMPT = """Du bist Luna, persönliche Assistentin von Markus. Antworte immer auf Deutsch.

Stil: Direkt, locker, keine Floskeln. Max 1-2 Sätze. Komm sofort zum Punkt.

Deine Tools:
- Kalender: Termine abrufen/erstellen
- Kontakte: Notizen zu Personen speichern
- Erinnerungen: create_reminder für "erinnere mich an..."

Erinnerungen:
Bei "erinnere mich in X an Y" → berechne remind_at aus aktueller Zeit + X.
Beispiele: "in 2 Stunden" → jetzt + 2h, "morgen um 9" → nächster Tag 09:00

Fakten speichern:
Wenn Markus was über jemanden erzählt: [SAVE_FACT|Name|Fakt]

Nutze gespeicherte Infos wenn relevant."""

logger.debug(f"System prompt loaded ({len(SYSTEM_PROMPT)} characters)")


def build_context(user_message: str, calendar_events: list = None) -> str:
    """Build context string for the LLM using local contacts from database."""
    logger.info("build_context() called")

    context_parts = []

    # Use Vienna timezone and German weekday/month names
    TIMEZONE = ZoneInfo("Europe/Vienna")
    now = datetime.now(TIMEZONE)

    weekdays_de = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
    months_de = ["", "Januar", "Februar", "März", "April", "Mai", "Juni",
                 "Juli", "August", "September", "Oktober", "November", "Dezember"]

    weekday = weekdays_de[now.weekday()]
    month = months_de[now.month]
    time_str = f"{weekday}, {now.day}. {month} {now.year}, {now.strftime('%H:%M')} Uhr (Wien)"
    context_parts.append(f"Aktuelle Zeit: {time_str}")
    logger.debug(f"Added current time to context: {time_str}")

    if calendar_events:
        context_parts.append("\nKalender-Events:")
        for event in calendar_events[:10]:
            context_parts.append(f"- {event}")
            logger.debug(f"Added calendar event to context: {event}")
        logger.info(f"Added {min(len(calendar_events), 10)} calendar events to context")

    # Load contacts from local database
    logger.info("Loading contacts from local database...")
    all_contacts = memory.get_all_local_contacts()
    logger.debug(f"Loaded {len(all_contacts)} contacts from local DB")

    logger.info("Extracting potential names from user message...")
    potential_names = user_message.split(" ")
    logger.debug(f"Potential names: {potential_names}")

    matched_contacts = []
    contacts_with_notes = []

    logger.info(f"Processing {len(potential_names)} potential contact names...")
    for name in potential_names:
        if len(name) < 2:  # Skip very short words
            continue
        logger.debug(f"Processing name: {name}")

        # Match against local contacts
        for contact in all_contacts:
            if name.lower() in contact['name'].lower():
                contact_info = f"{contact['name']}"
                if contact.get('organization'):
                    contact_info += f" ({contact['organization']})"
                if contact_info not in matched_contacts:
                    matched_contacts.append(contact_info)
                    logger.debug(f"Matched contact: {contact_info}")

                    # If contact has notes, include them
                    if contact.get('notes'):
                        contacts_with_notes.append({
                            "name": contact['name'],
                            "notes": contact['notes']
                        })

    if matched_contacts:
        context_parts.append("\nErkannte Kontakte:")
        for c in matched_contacts:
            context_parts.append(f"- {c}")
        logger.info(f"Added {len(matched_contacts)} matched contacts to context")

    if contacts_with_notes:
        context_parts.append("\nGespeicherte Notizen zu Kontakten:")
        for c in contacts_with_notes:
            context_parts.append(f"- {c['name']}: {c['notes']}")
        logger.info(f"Added notes for {len(contacts_with_notes)} contacts to context")

    context = "\n".join(context_parts)
    logger.info(f"build_context() complete - {len(context)} characters")
    logger.debug(f"Full context:\n{context}")

    return context


def parse_save_facts(response: str) -> tuple[str, list[tuple[str, str]]]:
    """Extract SAVE_FACT commands from response and return clean response."""
    logger.info("parse_save_facts() called")
    logger.debug(f"Response length: {len(response)} characters")
    logger.debug(f"Response: {response[:200]}..." if len(response) > 200 else f"Response: {response}")

    facts = []
    pattern = r'\[SAVE_FACT\|([^|]+)\|([^\]]+)\]'

    matches = re.findall(pattern, response)
    logger.debug(f"Found {len(matches)} SAVE_FACT patterns")

    for contact, fact in matches:
        facts.append((contact.strip(), fact.strip()))
        logger.info(f"Extracted fact - Contact: {contact.strip()}, Fact: {fact.strip()}")

    # Remove the SAVE_FACT tags from response
    clean_response = re.sub(pattern, '', response).strip()
    logger.debug(f"Clean response length: {len(clean_response)} characters")
    logger.debug(f"Clean response: {clean_response[:200]}..." if len(clean_response) > 200 else f"Clean response: {clean_response}")

    logger.info(f"parse_save_facts() returning {len(facts)} facts")
    return clean_response, facts


def find_matching_contacts(contact_name: str) -> list[dict]:
    """Find contacts matching a name. Returns list of matching contacts."""
    logger.info(f"find_matching_contacts() called for '{contact_name}'")
    matches = memory.search_contacts_by_name(contact_name)
    logger.debug(f"Found {len(matches)} matching contacts")
    return matches


def process_facts_for_saving(facts: list[tuple[str, str]]) -> tuple[list[dict], list[dict]]:
    """
    Process extracted facts and determine which can be saved directly vs need disambiguation.

    Returns:
        - auto_save: list of {contact_id, contact_name, fact} - single match, save directly
        - needs_disambiguation: list of {contact_name, fact, matches} - multiple matches, need user input
    """
    logger.info(f"process_facts_for_saving() called with {len(facts)} facts")

    auto_save = []
    needs_disambiguation = []

    for contact_name, fact in facts:
        matches = find_matching_contacts(contact_name)

        if len(matches) == 0:
            logger.warning(f"No contact found for '{contact_name}' - skipping fact")
            # Could optionally create a notes-only contact here
            continue
        elif len(matches) == 1:
            # Single match - can save directly
            auto_save.append({
                "contact_id": matches[0]["id"],
                "contact_name": matches[0]["name"],
                "fact": fact
            })
            logger.info(f"Single match for '{contact_name}' -> {matches[0]['name']}")
        else:
            # Multiple matches - need disambiguation
            needs_disambiguation.append({
                "contact_name": contact_name,
                "fact": fact,
                "matches": matches
            })
            logger.info(f"Multiple matches for '{contact_name}' - needs disambiguation")

    return auto_save, needs_disambiguation


async def chat(user_message: str, calendar_events: list = None) -> tuple[str, list[dict]]:
    """
    Send a message to Claude and get a response.
    Handles tool use for calendar and fact extraction/storage.

    Returns:
        - response: The clean response text
        - needs_disambiguation: List of facts that need user disambiguation
    """
    logger.info("=" * 60)
    logger.info("chat() called")

    # Build context using local contacts from database
    logger.info("Building context for LLM...")
    context = build_context(user_message, None)
    logger.debug(f"Context built ({len(context)} characters)")

    # Get conversation history
    logger.info("Fetching conversation history...")
    history = memory.get_recent_conversations(limit=10)
    logger.debug(f"Retrieved {len(history)} conversation messages")

    # Build messages
    logger.info("Building messages array for API call...")
    messages = []
    for msg in history:
        messages.append({"role": msg["role"], "content": msg["content"]})
        logger.debug(f"Added history message: {msg['role']}")

    user_content = f"{user_message}\n\n[Kontext: {context}]"
    messages.append({"role": "user", "content": user_content})
    logger.debug(f"Added current user message ({len(user_content)} characters)")
    logger.info(f"Total messages for API: {len(messages)}")

    # Tool use loop - keep calling until we get a final text response
    max_iterations = 10
    iteration = 0

    while iteration < max_iterations:
        iteration += 1
        logger.info(f"API call iteration {iteration}")

        # Call Claude with tools
        response = client.messages.create(
            model=LLM_MODEL,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            tools=CALENDAR_TOOLS,
            messages=messages
        )

        logger.info(f"API response received - stop_reason: {response.stop_reason}")

        # Check if we need to handle tool use
        if response.stop_reason == "tool_use":
            # Process all tool calls in the response
            tool_results = []

            for content_block in response.content:
                if content_block.type == "tool_use":
                    tool_name = content_block.name
                    tool_input = content_block.input
                    tool_use_id = content_block.id

                    logger.info(f"Tool call requested: {tool_name} with input {tool_input}")

                    # Handle reminder tool locally, others via MCP
                    if tool_name == "create_reminder":
                        result = await handle_create_reminder(tool_input)
                    else:
                        # Call the MCP server
                        result = await call_mcp_tool(tool_name, tool_input)

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_use_id,
                        "content": result
                    })

            # Add assistant response and tool results to messages
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})

        else:
            # No more tool calls - extract the final text response
            assistant_message = ""
            for content_block in response.content:
                if hasattr(content_block, "text"):
                    assistant_message += content_block.text

            logger.info(f"Final response received ({len(assistant_message)} characters)")
            break
    else:
        logger.warning("Max iterations reached in tool use loop")
        assistant_message = "Entschuldigung, ich hatte Probleme bei der Verarbeitung deiner Anfrage."

    # Parse and process facts
    logger.info("Parsing response for SAVE_FACT commands...")
    clean_response, facts = parse_save_facts(assistant_message)

    needs_disambiguation = []
    if facts:
        logger.info(f"Processing {len(facts)} extracted facts...")
        auto_save, needs_disambiguation = process_facts_for_saving(facts)

        # Save facts that have a single match
        for item in auto_save:
            logger.debug(f"Auto-saving fact to contact {item['contact_id']}: {item['fact']}")
            memory.update_contact_notes(item['contact_id'], item['fact'], append=True)
            logger.info(f"Fact saved for {item['contact_name']}")

        if needs_disambiguation:
            logger.info(f"{len(needs_disambiguation)} facts need disambiguation")
    else:
        logger.debug("No facts to save")

    # Save conversation
    logger.info("Saving conversation to memory...")
    logger.debug(f"Saving user message: {user_message[:50]}...")
    memory.add_conversation("user", user_message)
    logger.debug(f"Saving assistant response: {clean_response[:50]}...")
    memory.add_conversation("assistant", clean_response)
    logger.info("Conversation saved successfully")

    logger.info(f"chat() returning response ({len(clean_response)} characters)")
    return clean_response, needs_disambiguation


async def generate_daily_summary(calendar_events: str, contacts_with_facts: list = None) -> str:
    """Generate a morning summary of the day ahead."""
    logger.info("=" * 60)
    logger.info("generate_daily_summary() called")
    logger.debug(f"Calendar events: {calendar_events}")
    logger.debug(f"Contacts with facts: {contacts_with_facts}")

    events_str = calendar_events if calendar_events else '- Keine Termine'
    facts_str = '\n'.join(['- ' + c for c in contacts_with_facts]) if contacts_with_facts else '- Keine besonderen Erinnerungen'

    prompt = f"""Erstelle eine kurze Morgenzusammenfassung für den Tag.

Kalender-Events heute:
{events_str}

Erinnerungen an Kontakte die heute relevant sein könnten:
{facts_str}

Halte es kurz, freundlich und hilfreich. Maximal 3-4 Sätze."""

    logger.debug(f"Generated prompt ({len(prompt)} characters):")
    logger.debug(prompt)

    logger.info("Calling Anthropic API for daily summary...")
    logger.debug(f"Model: {LLM_MODEL}")
    logger.debug(f"Max tokens: 512")

    response = client.messages.create(
        model=LLM_MODEL,
        max_tokens=512,
        system="Du bist Luna, ein freundlicher persönlicher Assistent. Antworte auf Deutsch.",
        messages=[{"role": "user", "content": prompt}]
    )

    logger.info("API response received for daily summary")

    summary = response.content[0].text
    logger.info(f"generate_daily_summary() returning ({len(summary)} characters)")

    return summary
