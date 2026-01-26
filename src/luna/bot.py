import asyncio
import sqlite3
from telebot.async_telebot import AsyncTeleBot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from luna.config import (
    TELEGRAM_BOT_TOKEN, ALLOWED_USER_IDS, DAILY_SUMMARY_HOUR,
    DAILY_SUMMARY_MINUTE, USER_CHAT_ID, DB_PATH, get_logger
)
from luna import llm
from luna import memory

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
    """List all stored facts."""
    logger.info("=" * 60)
    logger.info("/fakten command received")
    logger.debug(f"Chat ID: {message.chat.id}")
    logger.debug(f"User: {message.from_user.id} ({message.from_user.username})")

    if not is_authorized(message):
        logger.warning("Unauthorized /fakten request - ignoring")
        return

    logger.info("Searching for all facts in memory...")
    facts = memory.search_facts("")
    logger.debug(f"Found {len(facts)} facts total")

    if facts:
        logger.debug(f"First 5 facts: {facts[:5]}")
        response = "Gespeicherte Fakten:\n\n"
        for f in facts[:20]:  # Limit to 20
            response += f"- {f['contact_name'].title()}: {f['fact']}\n"
            logger.debug(f"Added fact: {f['contact_name']} - {f['fact'][:50]}...")
        logger.info(f"Sending {min(len(facts), 20)} facts to user")
        await bot.reply_to(message, response)
        logger.debug("Facts response sent")
    else:
        logger.info("No facts found - sending empty response")
        await bot.reply_to(message, "Noch keine Fakten gespeichert!")
        logger.debug("Empty facts response sent")


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

        response = await llm.chat(message.text)

        logger.info("LLM response received")
        logger.debug(f"Response length: {len(response)} characters")
        logger.debug(f"Response preview: {response[:200]}..." if len(response) > 200 else f"Response: {response}")

        logger.info("Sending response to user...")
        await bot.reply_to(message, response)
        logger.info("Response sent successfully")

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
