import anthropic
import re
from datetime import datetime
from zoneinfo import ZoneInfo

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from luna.config import (
    ANTHROPIC_API_KEY, LLM_MODEL, MCP_CALENDAR_DIR,
    GOOGLE_CREDENTIALS_PATH, GOOGLE_TOKEN_PATH, get_logger
)
from luna import memory
from luna import contacts as gcontacts

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

SYSTEM_PROMPT = """Du bist Luna, ein persönlicher Assistent für Markus Stuppnig, deinen Chef. Du sprichst Deutsch und bist freundlich, hilfsbereit und prägnant.

Deine Hauptaufgaben:
1. Allgemeine Fragen beantworten
2. Kalender-Informationen bereitstellen
3. Dich an persönliche Details über Kontakte erinnern und diese nutzen

WICHTIG - Kontakt-Informationen speichern:
Wenn der Nutzer dir etwas über eine Person erzählt (z.B. "Julias Freundin Lara hat sich das Bein gebrochen"),
antworte mit einem speziellen Format am ENDE deiner Antwort:
[SAVE_FACT|Kontaktname|Fakt]

Beispiel: "Das tut mir leid zu hören! Ich hoffe, Lara erholt sich schnell. [SAVE_FACT|Julia|Freundin Lara hat sich das Bein gebrochen]"

Wenn relevante Kontakt-Informationen im Kontext sind, erinnere den Nutzer daran und schlage vor, nachzufragen.

Halte deine Antworten sehr kurz und natürlich - wie eine gute Assistentin."""

logger.debug(f"System prompt loaded ({len(SYSTEM_PROMPT)} characters)")


def build_context(user_message: str, calendar_events: list = None, all_contacts: list = None) -> str:
    """Build context string for the LLM."""
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

    logger.info("Extracting potential names from user message...")
    potential_names = user_message.split(" ")
    logger.debug(f"Potential names: {potential_names}")

    relevant_facts = []
    matched_contacts = []

    if all_contacts is None:
        all_contacts = []
        logger.debug("No contacts provided, using empty list")

    logger.info(f"Processing {len(potential_names)} potential contact names...")
    for name in potential_names:
        logger.debug(f"Processing name: {name}")

        # Match against real contacts
        for contact in all_contacts:
            if name.lower() in contact['name'].lower():
                contact_info = f"{contact['name']}"
                if contact.get('organization'):
                    contact_info += f" ({contact['organization']})"
                matched_contacts.append(contact_info)
                logger.debug(f"Matched contact: {contact_info}")
                break

        # Get stored facts
        logger.debug(f"Searching for facts about {name}...")
        facts = memory.get_facts_for_contact(name)
        logger.debug(f"Found {len(facts)} facts for {name}")
        for fact in facts:
            fact_str = f"{name}: {fact['fact']}"
            relevant_facts.append(fact_str)
            logger.debug(f"Added fact: {fact_str}")

    if matched_contacts:
        context_parts.append("\nErkannte Kontakte:")
        for c in matched_contacts:
            context_parts.append(f"- {c}")
            print(c)
        logger.info(f"Added {len(matched_contacts)} matched contacts to context")

    if relevant_facts:
        context_parts.append("\nGespeicherte Fakten:")
        for fact in relevant_facts:
            context_parts.append(f"- {fact}")
        logger.info(f"Added {len(relevant_facts)} relevant facts to context")

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


async def chat(user_message: str, calendar_events: list = None) -> str:
    """
    Send a message to Claude and get a response.
    Handles tool use for calendar and fact extraction/storage.
    """
    logger.info("=" * 60)
    logger.info("chat() called")

    # Load contacts once
    logger.info("Attempting to load Google contacts...")
    try:
        all_contacts = gcontacts.get_all_contacts()
        logger.info(f"Loaded {len(all_contacts)} contacts successfully")
    except Exception as e:
        logger.warning(f"Failed to load contacts: {e}", exc_info=True)
        all_contacts = []

    # Build context with contacts (no longer passing calendar_events - LLM will fetch via tools)
    logger.info("Building context for LLM...")
    context = build_context(user_message, None, all_contacts)
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

    user_content = f"{context}\n\nNutzer: {user_message}"
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

    # Parse and save any facts
    logger.info("Parsing response for SAVE_FACT commands...")
    clean_response, facts = parse_save_facts(assistant_message)

    if facts:
        logger.info(f"Saving {len(facts)} extracted facts...")
        for contact, fact in facts:
            logger.debug(f"Saving fact: {contact} -> {fact}")
            memory.add_fact(contact, fact, context=user_message)
            logger.info(f"Fact saved for {contact}")
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
    return clean_response


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
