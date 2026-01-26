import sqlite3
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


# Initialize DB on import
logger.info("Initializing database on module import...")
init_db()
logger.info("Memory module fully loaded and database initialized")
