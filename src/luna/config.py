import os
import logging
import sys
from pathlib import Path
from dotenv import load_dotenv


load_dotenv()

# =============================================================================
# PATH CONFIGURATION
# =============================================================================
# Project root is two levels up from this file (src/luna/config.py -> project root)
PROJECT_ROOT = Path(__file__).parent.parent.parent

# Data directory for runtime files (database, logs)
DATA_DIR = Path(os.getenv("LUNA_DATA_DIR", PROJECT_ROOT / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Credentials directory
CREDENTIALS_DIR = Path(os.getenv("LUNA_CREDENTIALS_DIR", PROJECT_ROOT / "credentials"))

# MCP Calendar directory
MCP_CALENDAR_DIR = PROJECT_ROOT / "mcp_calendar"

# =============================================================================
# LOGGING CONFIGURATION
# =============================================================================
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)-20s | %(funcName)-25s | %(lineno)4d | %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
LOG_LEVEL = logging.INFO

# Configure root logger
logging.basicConfig(
    level=LOG_LEVEL,
    format=LOG_FORMAT,
    datefmt=LOG_DATE_FORMAT,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(DATA_DIR / "luna_debug.log", mode="a", encoding="utf-8")
    ]
)

logging.captureWarnings(True)


def get_logger(name: str) -> logging.Logger:
    """Get a logger for a specific module with debug level enabled."""
    logger = logging.getLogger(name)
    logger.setLevel(LOG_LEVEL)
    return logger


logger = get_logger("config")
logger.info("=" * 80)
logger.info("LUNA STARTING - Logging system initialized")
logger.info("=" * 80)
logger.debug(f"PROJECT_ROOT: {PROJECT_ROOT}")
logger.debug(f"DATA_DIR: {DATA_DIR}")
logger.debug(f"CREDENTIALS_DIR: {CREDENTIALS_DIR}")

# =============================================================================
# BOT CONFIGURATION
# =============================================================================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ALLOWED_USER_IDS = [int(id) for id in os.getenv("ALLOWED_USER_IDS", "").split(",") if id]
USER_CHAT_ID = int(os.getenv("USER_CHAT_ID", "0")) or None

# =============================================================================
# LLM CONFIGURATION
# =============================================================================
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "claude-sonnet-4-20250514")

# =============================================================================
# GOOGLE API CONFIGURATION
# =============================================================================
GOOGLE_CREDENTIALS_PATH = CREDENTIALS_DIR / "credentials.json"
GOOGLE_TOKEN_PATH = CREDENTIALS_DIR / "token.json"

# Import scopes from shared module (single source of truth)
sys.path.insert(0, str(PROJECT_ROOT))
from google_scopes import GOOGLE_SCOPES

# =============================================================================
# DATABASE CONFIGURATION
# =============================================================================
DB_PATH = DATA_DIR / "luna.db"

# =============================================================================
# SCHEDULER CONFIGURATION
# =============================================================================
DAILY_SUMMARY_HOUR = int(os.getenv("DAILY_SUMMARY_HOUR", "7"))
DAILY_SUMMARY_MINUTE = int(os.getenv("DAILY_SUMMARY_MINUTE", "0"))

# =============================================================================
# LOG CONFIGURATION VALUES
# =============================================================================
logger.info("Configuration loaded successfully")
logger.debug(f"TELEGRAM_BOT_TOKEN: {'*' * 10 + TELEGRAM_BOT_TOKEN[-4:] if TELEGRAM_BOT_TOKEN else 'NOT SET'}")
logger.debug(f"ALLOWED_USER_IDS: {ALLOWED_USER_IDS}")
logger.debug(f"USER_CHAT_ID: {USER_CHAT_ID}")
logger.debug(f"ANTHROPIC_API_KEY: {'*' * 10 + ANTHROPIC_API_KEY[-4:] if ANTHROPIC_API_KEY else 'NOT SET'}")
logger.debug(f"LLM_MODEL: {LLM_MODEL}")
logger.debug(f"GOOGLE_CREDENTIALS_PATH: {GOOGLE_CREDENTIALS_PATH} (exists: {GOOGLE_CREDENTIALS_PATH.exists()})")
logger.debug(f"GOOGLE_TOKEN_PATH: {GOOGLE_TOKEN_PATH} (exists: {GOOGLE_TOKEN_PATH.exists()})")
logger.debug(f"DB_PATH: {DB_PATH}")
logger.debug(f"DAILY_SUMMARY_HOUR: {DAILY_SUMMARY_HOUR}")
logger.debug(f"DAILY_SUMMARY_MINUTE: {DAILY_SUMMARY_MINUTE}")
logger.info("=" * 80)
