import sqlite3
import json
from datetime import datetime
from luna.config import DB_PATH, get_logger

# =============================================================================
# LOGGING SETUP
# =============================================================================
logger = get_logger("memory")
logger.info("Memory module loading...")
logger.debug(f"DB_PATH: {DB_PATH}")


def init_db():
    """Initialize the database with required tables."""
    logger.info("init_db() called")
    logger.debug(f"Connecting to database at {DB_PATH}")

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    logger.debug("Database connection established")

    # Facts table - stores information about contacts
    logger.info("Creating 'facts' table if not exists...")
    c.execute("""
        CREATE TABLE IF NOT EXISTS facts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contact_name TEXT NOT NULL,
            fact TEXT NOT NULL,
            context TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            reminded BOOLEAN DEFAULT FALSE
        )
    """)
    logger.debug("Facts table created/verified")

    # Conversation history for context
    logger.info("Creating 'conversations' table if not exists...")
    c.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    logger.debug("Conversations table created/verified")

    # Contacts table - cached from Google Contacts with local notes
    logger.info("Creating 'contacts' table if not exists...")
    c.execute("""
        CREATE TABLE IF NOT EXISTS contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            google_id TEXT UNIQUE,
            name TEXT NOT NULL,
            emails TEXT,
            phones TEXT,
            organization TEXT,
            notes TEXT,
            synced_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    logger.debug("Contacts table created/verified")

    # Reminders table - time-based notifications
    logger.info("Creating 'reminders' table if not exists...")
    c.execute("""
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message TEXT NOT NULL,
            remind_at TIMESTAMP NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            sent BOOLEAN DEFAULT FALSE
        )
    """)
    logger.debug("Reminders table created/verified")

    # Create index for faster name lookups
    c.execute("CREATE INDEX IF NOT EXISTS idx_contacts_name ON contacts(name)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_contacts_google_id ON contacts(google_id)")
    logger.debug("Contacts indexes created/verified")

    conn.commit()
    logger.debug("Schema changes committed")

    conn.close()
    logger.debug("Database connection closed")

    logger.info("init_db() completed successfully")


def add_fact(contact_name: str, fact: str, context: str = None):
    """Store a fact about a contact."""
    logger.info("add_fact() called")
    logger.debug(f"Contact name: {contact_name}")
    logger.debug(f"Fact: {fact}")
    logger.debug(f"Context: {context}")

    logger.debug(f"Connecting to database at {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    contact_lower = contact_name.lower()
    logger.debug(f"Normalized contact name: {contact_lower}")

    logger.info(f"Inserting fact for contact '{contact_lower}'...")
    c.execute(
        "INSERT INTO facts (contact_name, fact, context) VALUES (?, ?, ?)",
        (contact_lower, fact, context)
    )

    last_id = c.lastrowid
    logger.debug(f"Inserted row ID: {last_id}")

    conn.commit()
    logger.debug("Transaction committed")

    conn.close()
    logger.debug("Database connection closed")

    logger.info(f"add_fact() completed - fact ID: {last_id}")


def get_facts_for_contact(contact_name: str) -> list[dict]:
    """Retrieve all facts about a contact."""
    logger.info(f"get_facts_for_contact() called for '{contact_name}'")

    logger.debug(f"Connecting to database at {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    search_pattern = f"%{contact_name.lower()}%"
    logger.debug(f"Search pattern: {search_pattern}")

    logger.info(f"Querying facts for contact like '{search_pattern}'...")
    c.execute(
        "SELECT fact, context, created_at, reminded FROM facts WHERE contact_name LIKE ?",
        (search_pattern,)
    )

    rows = c.fetchall()
    logger.debug(f"Query returned {len(rows)} rows")

    conn.close()
    logger.debug("Database connection closed")

    result = [{"fact": r[0], "context": r[1], "created_at": r[2], "reminded": r[3]} for r in rows]

    logger.info(f"get_facts_for_contact() returning {len(result)} facts")
    for i, r in enumerate(result):
        logger.debug(f"Fact {i+1}: {r['fact'][:50]}..." if len(r['fact']) > 50 else f"Fact {i+1}: {r['fact']}")

    return result


def get_unreminded_facts() -> list[dict]:
    """Get facts that haven't been reminded yet."""
    logger.info("get_unreminded_facts() called")

    logger.debug(f"Connecting to database at {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    logger.info("Querying unreminded facts...")
    c.execute(
        "SELECT id, contact_name, fact, context FROM facts WHERE reminded = FALSE"
    )

    rows = c.fetchall()
    logger.debug(f"Query returned {len(rows)} rows")

    conn.close()
    logger.debug("Database connection closed")

    result = [{"id": r[0], "contact_name": r[1], "fact": r[2], "context": r[3]} for r in rows]

    logger.info(f"get_unreminded_facts() returning {len(result)} facts")
    for r in result:
        logger.debug(f"Unreminded fact ID {r['id']}: {r['contact_name']} - {r['fact'][:30]}...")

    return result


def mark_fact_reminded(fact_id: int):
    """Mark a fact as reminded."""
    logger.info(f"mark_fact_reminded() called for fact ID {fact_id}")

    logger.debug(f"Connecting to database at {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    logger.info(f"Updating fact {fact_id} to reminded=TRUE...")
    c.execute("UPDATE facts SET reminded = TRUE WHERE id = ?", (fact_id,))

    rows_affected = c.rowcount
    logger.debug(f"Rows affected: {rows_affected}")

    conn.commit()
    logger.debug("Transaction committed")

    conn.close()
    logger.debug("Database connection closed")

    logger.info(f"mark_fact_reminded() completed - {rows_affected} rows updated")


def search_facts(query: str) -> list[dict]:
    """Search facts by keyword."""
    logger.info(f"search_facts() called with query='{query}'")

    logger.debug(f"Connecting to database at {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    search_pattern = f"%{query}%"
    logger.debug(f"Search pattern: {search_pattern}")

    logger.info(f"Searching facts matching '{search_pattern}'...")
    c.execute(
        "SELECT contact_name, fact, context, created_at FROM facts WHERE fact LIKE ? OR contact_name LIKE ?",
        (search_pattern, search_pattern)
    )

    rows = c.fetchall()
    logger.debug(f"Query returned {len(rows)} rows")

    conn.close()
    logger.debug("Database connection closed")

    result = [{"contact_name": r[0], "fact": r[1], "context": r[2], "created_at": r[3]} for r in rows]

    logger.info(f"search_facts() returning {len(result)} facts")
    for r in result:
        logger.debug(f"Found: {r['contact_name']} - {r['fact'][:30]}...")

    return result


def add_conversation(role: str, content: str):
    """Store a conversation message."""
    logger.info(f"add_conversation() called")
    logger.debug(f"Role: {role}")
    logger.debug(f"Content length: {len(content)} characters")
    logger.debug(f"Content preview: {content[:100]}..." if len(content) > 100 else f"Content: {content}")

    logger.debug(f"Connecting to database at {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    logger.info(f"Inserting conversation message with role='{role}'...")
    c.execute(
        "INSERT INTO conversations (role, content) VALUES (?, ?)",
        (role, content)
    )

    last_id = c.lastrowid
    logger.debug(f"Inserted row ID: {last_id}")

    conn.commit()
    logger.debug("Transaction committed")

    conn.close()
    logger.debug("Database connection closed")

    logger.info(f"add_conversation() completed - message ID: {last_id}")


def get_recent_conversations(limit: int = 20) -> list[dict]:
    """Get recent conversation history."""
    logger.info(f"get_recent_conversations() called with limit={limit}")

    logger.debug(f"Connecting to database at {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    logger.info(f"Querying {limit} most recent conversations...")
    c.execute(
        "SELECT role, content FROM conversations ORDER BY created_at DESC LIMIT ?",
        (limit,)
    )

    rows = c.fetchall()
    logger.debug(f"Query returned {len(rows)} rows")

    conn.close()
    logger.debug("Database connection closed")

    # Reverse to get chronological order
    result = [{"role": r[0], "content": r[1]} for r in reversed(rows)]

    logger.info(f"get_recent_conversations() returning {len(result)} messages (chronological order)")
    for i, r in enumerate(result):
        logger.debug(f"Conversation {i+1}: [{r['role']}] {r['content'][:50]}...")

    return result


# =============================================================================
# CONTACTS FUNCTIONS
# =============================================================================

def upsert_contact(google_id: str, name: str, emails: list, phones: list, organization: str = None) -> int:
    """Insert or update a contact from Google. Returns contact ID."""
    logger.info(f"upsert_contact() called for '{name}'")
    logger.debug(f"google_id: {google_id}")

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    emails_json = json.dumps(emails) if emails else None
    phones_json = json.dumps(phones) if phones else None
    now = datetime.now().isoformat()

    # Check if contact exists
    c.execute("SELECT id, notes FROM contacts WHERE google_id = ?", (google_id,))
    existing = c.fetchone()

    if existing:
        contact_id = existing[0]
        # Update but preserve notes
        c.execute("""
            UPDATE contacts
            SET name = ?, emails = ?, phones = ?, organization = ?, synced_at = ?, updated_at = ?
            WHERE google_id = ?
        """, (name, emails_json, phones_json, organization, now, now, google_id))
        logger.debug(f"Updated existing contact ID {contact_id}")
    else:
        c.execute("""
            INSERT INTO contacts (google_id, name, emails, phones, organization, synced_at, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (google_id, name, emails_json, phones_json, organization, now, now, now))
        contact_id = c.lastrowid
        logger.debug(f"Inserted new contact ID {contact_id}")

    conn.commit()
    conn.close()

    return contact_id


def get_contact_by_id(contact_id: int) -> dict | None:
    """Get a contact by ID."""
    logger.debug(f"get_contact_by_id() called for ID {contact_id}")

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("""
        SELECT id, google_id, name, emails, phones, organization, notes, synced_at, created_at, updated_at
        FROM contacts WHERE id = ?
    """, (contact_id,))
    row = c.fetchone()
    conn.close()

    if row:
        return {
            "id": row[0],
            "google_id": row[1],
            "name": row[2],
            "emails": json.loads(row[3]) if row[3] else [],
            "phones": json.loads(row[4]) if row[4] else [],
            "organization": row[5],
            "notes": row[6],
            "synced_at": row[7],
            "created_at": row[8],
            "updated_at": row[9]
        }
    return None


def search_contacts_by_name(query: str) -> list[dict]:
    """Search contacts by name (case-insensitive, partial match)."""
    logger.info(f"search_contacts_by_name() called with query='{query}'")

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    search_pattern = f"%{query}%"
    c.execute("""
        SELECT id, google_id, name, emails, phones, organization, notes
        FROM contacts WHERE name LIKE ? COLLATE NOCASE
        ORDER BY name
    """, (search_pattern,))
    rows = c.fetchall()
    conn.close()

    result = [{
        "id": r[0],
        "google_id": r[1],
        "name": r[2],
        "emails": json.loads(r[3]) if r[3] else [],
        "phones": json.loads(r[4]) if r[4] else [],
        "organization": r[5],
        "notes": r[6]
    } for r in rows]

    logger.debug(f"Found {len(result)} contacts matching '{query}'")
    return result


def get_all_local_contacts() -> list[dict]:
    """Get all locally cached contacts."""
    logger.info("get_all_local_contacts() called")

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("""
        SELECT id, google_id, name, emails, phones, organization, notes
        FROM contacts ORDER BY name
    """)
    rows = c.fetchall()
    conn.close()

    result = [{
        "id": r[0],
        "google_id": r[1],
        "name": r[2],
        "emails": json.loads(r[3]) if r[3] else [],
        "phones": json.loads(r[4]) if r[4] else [],
        "organization": r[5],
        "notes": r[6]
    } for r in rows]

    logger.debug(f"Returning {len(result)} total contacts")
    return result


def get_contacts_with_notes() -> list[dict]:
    """Get all contacts that have notes."""
    logger.info("get_contacts_with_notes() called")

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("""
        SELECT id, google_id, name, emails, phones, organization, notes
        FROM contacts
        WHERE notes IS NOT NULL AND notes != ''
        ORDER BY name
    """)
    rows = c.fetchall()
    conn.close()

    result = [{
        "id": r[0],
        "google_id": r[1],
        "name": r[2],
        "emails": json.loads(r[3]) if r[3] else [],
        "phones": json.loads(r[4]) if r[4] else [],
        "organization": r[5],
        "notes": r[6]
    } for r in rows]

    logger.info(f"Found {len(result)} contacts with notes")
    return result


def update_contact_notes(contact_id: int, notes: str, append: bool = True) -> bool:
    """Update or append to a contact's notes. Returns success status."""
    logger.info(f"update_contact_notes() called for contact ID {contact_id}")
    logger.debug(f"append={append}, notes length={len(notes)}")

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    if append:
        # Get existing notes
        c.execute("SELECT notes FROM contacts WHERE id = ?", (contact_id,))
        row = c.fetchone()
        if not row:
            conn.close()
            logger.warning(f"Contact ID {contact_id} not found")
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

    logger.info(f"Notes updated: {success}")
    return success


def delete_contacts_not_in_google_without_notes(google_ids: set) -> int:
    """Delete contacts that are no longer in Google AND have no notes. Returns count deleted."""
    logger.info(f"delete_contacts_not_in_google_without_notes() called with {len(google_ids)} Google IDs")

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Find contacts not in Google IDs list and without notes
    placeholders = ",".join("?" * len(google_ids)) if google_ids else "''"
    query = f"""
        DELETE FROM contacts
        WHERE google_id NOT IN ({placeholders})
        AND (notes IS NULL OR notes = '')
    """

    if google_ids:
        c.execute(query, tuple(google_ids))
    else:
        c.execute("DELETE FROM contacts WHERE notes IS NULL OR notes = ''")

    deleted_count = c.rowcount
    conn.commit()
    conn.close()

    logger.info(f"Deleted {deleted_count} contacts no longer in Google (without notes)")
    return deleted_count


def get_local_google_ids() -> set:
    """Get all Google IDs currently in local database."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT google_id FROM contacts WHERE google_id IS NOT NULL")
    ids = {row[0] for row in c.fetchall()}
    conn.close()
    return ids


# =============================================================================
# REMINDER FUNCTIONS
# =============================================================================

def add_reminder(message: str, remind_at: datetime) -> int:
    """Create a new reminder. Returns reminder ID."""
    logger.info(f"add_reminder() called: '{message}' at {remind_at}")

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute(
        "INSERT INTO reminders (message, remind_at) VALUES (?, ?)",
        (message, remind_at.isoformat())
    )

    reminder_id = c.lastrowid
    conn.commit()
    conn.close()

    logger.info(f"Reminder created with ID {reminder_id}")
    return reminder_id


def get_due_reminders() -> list[dict]:
    """Get all reminders that are due and not yet sent."""
    logger.debug("get_due_reminders() called")

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    now = datetime.now().isoformat()
    c.execute(
        "SELECT id, message, remind_at FROM reminders WHERE remind_at <= ? AND sent = FALSE",
        (now,)
    )

    rows = c.fetchall()
    conn.close()

    result = [{"id": r[0], "message": r[1], "remind_at": r[2]} for r in rows]
    logger.debug(f"Found {len(result)} due reminders")
    return result


def mark_reminder_sent(reminder_id: int):
    """Mark a reminder as sent."""
    logger.info(f"mark_reminder_sent() called for ID {reminder_id}")

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("UPDATE reminders SET sent = TRUE WHERE id = ?", (reminder_id,))

    conn.commit()
    conn.close()

    logger.debug(f"Reminder {reminder_id} marked as sent")


def get_pending_reminders() -> list[dict]:
    """Get all pending (unsent) reminders."""
    logger.debug("get_pending_reminders() called")

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute(
        "SELECT id, message, remind_at FROM reminders WHERE sent = FALSE ORDER BY remind_at"
    )

    rows = c.fetchall()
    conn.close()

    result = [{"id": r[0], "message": r[1], "remind_at": r[2]} for r in rows]
    logger.debug(f"Found {len(result)} pending reminders")
    return result


def delete_reminder(reminder_id: int) -> bool:
    """Delete a reminder. Returns True if deleted."""
    logger.info(f"delete_reminder() called for ID {reminder_id}")

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))

    deleted = c.rowcount > 0
    conn.commit()
    conn.close()

    logger.debug(f"Reminder {reminder_id} deleted: {deleted}")
    return deleted


# Initialize DB on import
logger.info("Initializing database on module import...")
init_db()
logger.info("Memory module fully loaded and database initialized")
