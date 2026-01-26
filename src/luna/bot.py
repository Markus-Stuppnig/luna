import asyncio
import hashlib
import sqlite3
from telebot.async_telebot import AsyncTeleBot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from luna.config import (
    TELEGRAM_BOT_TOKEN, ALLOWED_USER_IDS, DAILY_SUMMARY_HOUR,
    DAILY_SUMMARY_MINUTE, USER_CHAT_ID, DB_PATH, get_logger
)
from luna import llm
from luna import memory

# Temporary storage for pending facts that need disambiguation
# Format: {fact_hash: {"fact": str, "matches": list, "timestamp": float}}
pending_facts: dict[str, dict] = {}

# =============================================================================
# LOGGING SETUP
# =============================================================================
logger = get_logger("bot")
logger.info("Bot module loading...")
logger.debug(f"Imported modules: telebot, apscheduler, config, llm, memory")

# =============================================================================
# BOT INITIALIZATION
# =============================================================================
logger.info("Initializing Telegram bot...")
logger.debug(f"Bot token length: {len(TELEGRAM_BOT_TOKEN) if TELEGRAM_BOT_TOKEN else 0}")
bot = AsyncTeleBot(TELEGRAM_BOT_TOKEN)
logger.info("Telegram bot initialized successfully")

logger.info("Initializing AsyncIO scheduler...")
scheduler = AsyncIOScheduler()
logger.info("Scheduler initialized successfully")


def is_authorized(message) -> bool:
    """Check if user is authorized to use the bot."""
    logger.debug(f"is_authorized() called")
    logger.debug(f"Message from user ID: {message.from_user.id}")
    logger.debug(f"Username: {message.from_user.username}")
    logger.debug(f"First name: {message.from_user.first_name}")
    logger.debug(f"Last name: {message.from_user.last_name}")
    logger.debug(f"ALLOWED_USER_IDS: {ALLOWED_USER_IDS}")

    if not ALLOWED_USER_IDS:
        logger.warning(f"ALLOWED_USER_IDS is empty - denying access")
        logger.warning(f"Unauthorized access attempt from user {message.from_user.id}")
        return False

    is_auth = message.from_user.id in ALLOWED_USER_IDS
    if is_auth:
        logger.info(f"User {message.from_user.id} ({message.from_user.username}) is AUTHORIZED")
    else:
        logger.warning(f"User {message.from_user.id} ({message.from_user.username}) is NOT AUTHORIZED")
        logger.warning(f"Attempted user ID {message.from_user.id} not in allowed list: {ALLOWED_USER_IDS}")

    return is_auth


@bot.message_handler(commands=['start'])
async def send_welcome(message):
    logger.info("=" * 60)
    logger.info("/start command received")
    logger.debug(f"Chat ID: {message.chat.id}")
    logger.debug(f"Message ID: {message.message_id}")
    logger.debug(f"Date: {message.date}")
    logger.debug(f"Full message object: {message}")

    if not is_authorized(message):
        logger.warning("Sending unauthorized response")
        await bot.reply_to(message, "Nicht autorisiert.")
        logger.debug("Unauthorized response sent")
        return

    logger.info("Sending welcome message...")
    await bot.reply_to(message,
        "Hallo! Ich bin Luna, dein persönlicher Assistent.\n\n"
        "Ich kann:\n"
        "- Fragen beantworten (Text oder Sprache)\n"
        "- Deinen Kalender checken (/heute, /morgen)\n"
        "- Mir Dinge über deine Kontakte merken\n"
        "- Dir jeden Morgen eine Zusammenfassung schicken\n\n"
        "Befehle:\n"
        "/kontakte - Kontakte von Google synchronisieren\n"
        "/fakten - Gespeicherte Notizen anzeigen\n"
        "/kontakt <name> - Kontakt suchen\n"
        "/heute, /morgen - Kalender-Events\n"
        "/clear - Konversation löschen\n\n"
        "Schreib mir einfach oder schick eine Sprachnachricht!"
    )
    logger.info("Welcome message sent successfully")


@bot.message_handler(commands=['heute'])
async def today_events(message):
    logger.info("=" * 60)
    logger.info("/heute command received")
    logger.debug(f"Chat ID: {message.chat.id}")
    logger.debug(f"User: {message.from_user.id} ({message.from_user.username})")

    if not is_authorized(message):
        logger.warning("Unauthorized /heute request - ignoring")
        return

    try:
        logger.info("Fetching today's calendar events via MCP...")
        result = await llm.call_mcp_tool("get_events_today")
        logger.debug(f"MCP result: {result}")

        response = f"Heute:\n{result}"
        logger.info("Sending events to user")
        await bot.reply_to(message, response)
        logger.debug("Events response sent")
    except Exception as e:
        logger.error(f"Calendar error in /heute: {str(e)}", exc_info=True)
        logger.error(f"Exception type: {type(e).__name__}")
        await bot.reply_to(message, f"Kalenderfehler: {str(e)}")
        logger.debug("Error response sent to user")


@bot.message_handler(commands=['morgen'])
async def tomorrow_events(message):
    logger.info("=" * 60)
    logger.info("/morgen command received")
    logger.debug(f"Chat ID: {message.chat.id}")
    logger.debug(f"User: {message.from_user.id} ({message.from_user.username})")

    if not is_authorized(message):
        logger.warning("Unauthorized /morgen request - ignoring")
        return

    try:
        logger.info("Fetching tomorrow's calendar events via MCP...")
        result = await llm.call_mcp_tool("get_events_tomorrow")
        logger.debug(f"MCP result: {result}")

        response = f"Morgen:\n{result}"
        logger.info("Sending events to user")
        await bot.reply_to(message, response)
        logger.debug("Events response sent")
    except Exception as e:
        logger.error(f"Calendar error in /morgen: {str(e)}", exc_info=True)
        logger.error(f"Exception type: {type(e).__name__}")
        await bot.reply_to(message, f"Kalenderfehler: {str(e)}")
        logger.debug("Error response sent to user")


@bot.message_handler(commands=['fakten'])
async def list_facts(message):
    """List all contacts with notes."""
    logger.info("=" * 60)
    logger.info("/fakten command received")
    logger.debug(f"Chat ID: {message.chat.id}")
    logger.debug(f"User: {message.from_user.id} ({message.from_user.username})")

    if not is_authorized(message):
        logger.warning("Unauthorized /fakten request - ignoring")
        return

    logger.info("Fetching contacts with notes...")
    contacts = memory.get_contacts_with_notes()
    logger.debug(f"Found {len(contacts)} contacts with notes")

    if contacts:
        response = "Gespeicherte Notizen:\n\n"
        for c in contacts[:20]:  # Limit to 20
            response += f"**{c['name']}**\n{c['notes']}\n\n"
            logger.debug(f"Added notes for: {c['name']}")
        logger.info(f"Sending notes for {min(len(contacts), 20)} contacts to user")
        await bot.reply_to(message, response, parse_mode="Markdown")
        logger.debug("Notes response sent")
    else:
        logger.info("No notes found - sending empty response")
        await bot.reply_to(message, "Noch keine Notizen zu Kontakten gespeichert!\n\nNutze /kontakte um Kontakte von Google zu synchronisieren.")
        logger.debug("Empty notes response sent")


@bot.message_handler(commands=['kontakt'])
async def search_contact(message):
    logger.info("=" * 60)
    logger.info("/kontakt command received")
    logger.debug(f"Chat ID: {message.chat.id}")
    logger.debug(f"User: {message.from_user.id} ({message.from_user.username})")
    logger.debug(f"Full message text: {message.text}")

    if not is_authorized(message):
        logger.warning("Unauthorized /kontakt request - ignoring")
        return

    query = message.text.replace('/kontakt', '').strip()
    logger.debug(f"Extracted search query: '{query}'")

    if not query:
        logger.warning("Empty search query - sending usage instructions")
        await bot.reply_to(message, "Nutzung: /kontakt Name")
        logger.debug("Usage instructions sent")
        return

    logger.info(f"Searching for contact: '{query}'")
    from luna import contacts
    logger.debug("Contacts module imported")

    results = contacts.search_contact(query)
    logger.debug(f"Search returned {len(results)} results")
    logger.debug(f"Results: {results}")

    if results:
        response = "Gefunden:\n"
        for c in results:
            logger.debug(f"Processing contact: {c['name']}")
            response += f"\n{c['name']}\n"
            if c['phones']:
                response += f"Tel: {c['phones'][0]}\n"
                logger.debug(f"Added phone: {c['phones'][0]}")
            if c['emails']:
                response += f"Email: {c['emails'][0]}\n"
                logger.debug(f"Added email: {c['emails'][0]}")
        logger.info(f"Sending {len(results)} contact results to user")
        await bot.reply_to(message, response)
        logger.debug("Contact results sent")
    else:
        logger.info(f"No contacts found for query '{query}'")
        await bot.reply_to(message, f"Kein Kontakt '{query}' gefunden.")
        logger.debug("No results response sent")


@bot.message_handler(commands=['kontakte'])
async def sync_contacts(message):
    """Sync contacts from Google to local database."""
    logger.info("=" * 60)
    logger.info("/kontakte command received")
    logger.debug(f"Chat ID: {message.chat.id}")
    logger.debug(f"User: {message.from_user.id} ({message.from_user.username})")

    if not is_authorized(message):
        logger.warning("Unauthorized /kontakte request - ignoring")
        return

    await bot.send_chat_action(message.chat.id, 'typing')

    try:
        logger.info("Calling MCP contacts sync tool...")
        result = await llm.call_mcp_contacts_tool("sync_contacts")
        logger.debug(f"Sync result: {result}")

        await bot.reply_to(message, result)
        logger.info("Contacts sync completed")
    except Exception as e:
        logger.error(f"Contacts sync error: {str(e)}", exc_info=True)
        await bot.reply_to(message, f"Fehler beim Synchronisieren: {str(e)}")


@bot.message_handler(commands=['clear'])
async def clear_context(message):
    """Clear conversation history."""
    logger.info("=" * 60)
    logger.info("/clear command received")
    logger.debug(f"Chat ID: {message.chat.id}")
    logger.debug(f"User: {message.from_user.id} ({message.from_user.username})")

    if not is_authorized(message):
        logger.warning("Unauthorized /clear request - ignoring")
        return

    logger.warning("CLEARING ALL CONVERSATION HISTORY")

    logger.debug(f"Opening database at: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    logger.debug("Executing DELETE FROM conversations")
    c.execute("DELETE FROM conversations")
    deleted_count = c.rowcount
    logger.info(f"Deleted {deleted_count} conversation records")

    conn.commit()
    logger.debug("Transaction committed")
    conn.close()
    logger.debug("Database connection closed")

    await bot.reply_to(message, "Konversationsverlauf gelöscht!")
    logger.info("Clear confirmation sent to user")


async def show_contact_disambiguation(chat_id: int, disambiguation_item: dict) -> None:
    """Show inline buttons to select correct contact for a fact."""
    import time

    fact = disambiguation_item["fact"]
    matches = disambiguation_item["matches"]
    contact_name = disambiguation_item["contact_name"]

    # Create a hash for this pending fact
    fact_hash = hashlib.md5(f"{fact}{time.time()}".encode()).hexdigest()[:8]

    # Store pending fact
    pending_facts[fact_hash] = {
        "fact": fact,
        "matches": matches,
        "timestamp": time.time()
    }

    # Create inline keyboard
    markup = InlineKeyboardMarkup()
    for contact in matches[:5]:  # Limit to 5 options
        org_str = f" ({contact.get('organization', '')})" if contact.get('organization') else ""
        btn = InlineKeyboardButton(
            text=f"{contact['name']}{org_str}",
            callback_data=f"sf:{contact['id']}:{fact_hash}"
        )
        markup.add(btn)

    # Add cancel button
    markup.add(InlineKeyboardButton(text="Abbrechen", callback_data=f"sf:cancel:{fact_hash}"))

    await bot.send_message(
        chat_id,
        f"Mehrere Kontakte gefunden für '{contact_name}'.\nWelcher ist gemeint?\n\nFakt: {fact}",
        reply_markup=markup
    )
    logger.info(f"Sent disambiguation buttons for fact_hash {fact_hash}")


@bot.callback_query_handler(func=lambda call: call.data.startswith("sf:"))
async def handle_save_fact_callback(call):
    """Handle contact selection for fact saving."""
    logger.info("=" * 60)
    logger.info("Callback query received for fact saving")
    logger.debug(f"Callback data: {call.data}")

    parts = call.data.split(":")
    if len(parts) != 3:
        logger.error(f"Invalid callback data format: {call.data}")
        await bot.answer_callback_query(call.id, "Fehler: Ungültiges Format")
        return

    contact_id_str = parts[1]
    fact_hash = parts[2]

    # Handle cancel
    if contact_id_str == "cancel":
        pending_facts.pop(fact_hash, None)
        await bot.answer_callback_query(call.id, "Abgebrochen")
        await bot.delete_message(call.message.chat.id, call.message.message_id)
        logger.info("Fact saving cancelled by user")
        return

    # Get pending fact data
    fact_data = pending_facts.pop(fact_hash, None)
    if not fact_data:
        await bot.answer_callback_query(call.id, "Fakt nicht mehr verfügbar")
        await bot.delete_message(call.message.chat.id, call.message.message_id)
        logger.warning(f"Pending fact {fact_hash} not found")
        return

    # Save fact to selected contact
    try:
        contact_id = int(contact_id_str)
        success = memory.update_contact_notes(contact_id, fact_data["fact"], append=True)

        if success:
            await bot.answer_callback_query(call.id, "Fakt gespeichert!")
            logger.info(f"Fact saved to contact {contact_id}")
        else:
            await bot.answer_callback_query(call.id, "Fehler beim Speichern")
            logger.error(f"Failed to save fact to contact {contact_id}")

        await bot.delete_message(call.message.chat.id, call.message.message_id)

    except ValueError as e:
        logger.error(f"Invalid contact_id: {contact_id_str}")
        await bot.answer_callback_query(call.id, "Fehler: Ungültige Kontakt-ID")


@bot.message_handler(func=lambda message: True)
async def handle_text(message):
    """Handle all text messages."""
    print(f"Chat ID: {message.chat.id}")
    logger.info("=" * 60)
    logger.info("Text message received")
    logger.debug(f"Chat ID: {message.chat.id}")
    logger.debug(f"Message ID: {message.message_id}")
    logger.debug(f"User: {message.from_user.id} ({message.from_user.username})")
    logger.debug(f"Message text: {message.text}")
    logger.debug(f"Message length: {len(message.text)} characters")
    logger.debug(f"Message date: {message.date}")

    if not is_authorized(message):
        logger.warning("Unauthorized text message - ignoring")
        return

    logger.info("Sending 'typing' chat action...")
    await bot.send_chat_action(message.chat.id, 'typing')
    logger.debug("Typing indicator sent")

    try:
        # Get LLM response - LLM will fetch calendar via tools if needed
        logger.info("Calling LLM for response...")
        logger.debug(f"User message: {message.text}")

        response, needs_disambiguation = await llm.chat(message.text)

        logger.info("LLM response received")
        logger.debug(f"Response length: {len(response)} characters")
        logger.debug(f"Response preview: {response[:200]}..." if len(response) > 200 else f"Response: {response}")
        logger.debug(f"Needs disambiguation: {len(needs_disambiguation)} items")

        logger.info("Sending response to user...")
        await bot.reply_to(message, response)
        logger.info("Response sent successfully")

        # Handle any facts that need disambiguation
        for item in needs_disambiguation:
            logger.info(f"Showing disambiguation for '{item['contact_name']}'")
            await show_contact_disambiguation(message.chat.id, item)

    except Exception as e:
        logger.error(f"Error handling text message: {str(e)}", exc_info=True)
        logger.error(f"Exception type: {type(e).__name__}")
        logger.error(f"Exception args: {e.args}")
        await bot.reply_to(message, f"Fehler: {str(e)}")
        logger.debug("Error response sent to user")


async def send_daily_summary():
    """Send daily morning summary."""
    logger.info("=" * 60)
    logger.info("DAILY SUMMARY TASK TRIGGERED")
    logger.debug(f"Current time check - sending to USER_CHAT_ID: {USER_CHAT_ID}")

    if not USER_CHAT_ID:
        logger.warning("USER_CHAT_ID not configured - skipping daily summary")
        return

    try:
        logger.info("Fetching today's calendar events via MCP...")
        events_text = await llm.call_mcp_tool("get_events_today")
        logger.debug(f"MCP events result: {events_text}")

        logger.info("Fetching unreminded facts...")
        unreminded = memory.get_unreminded_facts()
        logger.debug(f"Found {len(unreminded)} unreminded facts")
        logger.debug(f"Unreminded facts: {unreminded}")

        # Format facts for summary
        facts_str = [f"{f['contact_name'].title()}: {f['fact']}" for f in unreminded[:5]]
        logger.debug(f"Formatted facts for summary: {facts_str}")

        logger.info("Generating daily summary via LLM...")
        summary = await llm.generate_daily_summary(events_text, facts_str)
        logger.debug(f"Generated summary length: {len(summary)} characters")
        logger.debug(f"Summary: {summary}")

        logger.info(f"Sending daily summary to chat {USER_CHAT_ID}...")
        await bot.send_message(USER_CHAT_ID, f"Guten Morgen!\n\n{summary}")
        logger.info("Daily summary sent successfully!")

    except Exception as e:
        logger.error(f"Daily summary error: {str(e)}", exc_info=True)
        logger.error(f"Exception type: {type(e).__name__}")


async def check_reminders():
    """Check for due reminders and send them."""
    logger.debug("check_reminders() triggered")

    if not USER_CHAT_ID:
        logger.warning("USER_CHAT_ID not configured - skipping reminder check")
        return

    try:
        due_reminders = memory.get_due_reminders()

        for reminder in due_reminders:
            logger.info(f"Sending reminder {reminder['id']}: {reminder['message']}")

            await bot.send_message(
                USER_CHAT_ID,
                f"⏰ Erinnerung: {reminder['message']}"
            )

            memory.mark_reminder_sent(reminder['id'])
            logger.debug(f"Reminder {reminder['id']} marked as sent")

    except Exception as e:
        logger.error(f"Reminder check error: {str(e)}", exc_info=True)


async def main():
    logger.info("=" * 80)
    logger.info("MAIN FUNCTION STARTING")
    logger.info("=" * 80)

    # Schedule daily summary
    logger.info(f"Scheduling daily summary job at {DAILY_SUMMARY_HOUR:02d}:{DAILY_SUMMARY_MINUTE:02d}")
    scheduler.add_job(
        send_daily_summary,
        'cron',
        hour=DAILY_SUMMARY_HOUR,
        minute=DAILY_SUMMARY_MINUTE
    )
    logger.debug("Daily summary job added to scheduler")

    # Schedule reminder checker (every 30 seconds)
    logger.info("Scheduling reminder check job (every 30 seconds)")
    scheduler.add_job(
        check_reminders,
        'interval',
        seconds=30
    )
    logger.debug("Reminder check job added to scheduler")

    logger.info("Starting scheduler...")
    scheduler.start()
    logger.info("Scheduler started successfully")

    # Log all scheduled jobs
    jobs = scheduler.get_jobs()
    logger.debug(f"Scheduled jobs count: {len(jobs)}")
    for job in jobs:
        logger.debug(f"Job: {job.id} - Next run: {job.next_run_time}")

    logger.info("=" * 80)
    logger.info("Luna is running...")
    logger.info("=" * 80)
    print("Luna is running...")

    logger.info("Starting infinity polling...")
    await bot.infinity_polling()


if __name__ == "__main__":
    logger.info("Script executed directly - running main()")
    asyncio.run(main())
