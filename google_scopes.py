"""
Google API scopes used by Luna.

This is the single source of truth for OAuth scopes.
Both the main bot and MCP calendar server import from here.
"""

GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/contacts.readonly",
]
