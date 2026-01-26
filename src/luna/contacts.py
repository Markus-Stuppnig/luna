from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from luna.config import GOOGLE_CREDENTIALS_PATH, GOOGLE_TOKEN_PATH, GOOGLE_SCOPES, get_logger

# =============================================================================
# LOGGING SETUP
# =============================================================================
logger = get_logger("contacts")
logger.info("Contacts module loading...")
logger.debug(f"GOOGLE_CREDENTIALS_PATH: {GOOGLE_CREDENTIALS_PATH}")
logger.debug(f"GOOGLE_TOKEN_PATH: {GOOGLE_TOKEN_PATH}")
logger.debug(f"GOOGLE_SCOPES: {GOOGLE_SCOPES}")


def get_google_credentials():
    """Get or refresh Google API credentials."""
    logger.info("get_google_credentials() called")
    creds = None

    logger.debug(f"Checking if token file exists: {GOOGLE_TOKEN_PATH}")
    if GOOGLE_TOKEN_PATH.exists():
        logger.info(f"Token file found at {GOOGLE_TOKEN_PATH}")
        logger.debug("Loading credentials from token file...")
        creds = Credentials.from_authorized_user_file(str(GOOGLE_TOKEN_PATH), GOOGLE_SCOPES)
        logger.debug(f"Credentials loaded - valid: {creds.valid if creds else 'None'}")
        if creds:
            logger.debug(f"Credentials expired: {creds.expired}")
            logger.debug(f"Credentials has refresh_token: {bool(creds.refresh_token)}")
    else:
        logger.warning(f"Token file not found at {GOOGLE_TOKEN_PATH}")

    if not creds or not creds.valid:
        logger.info("Credentials are missing or invalid")
        if creds and creds.expired and creds.refresh_token:
            logger.info("Attempting to refresh expired credentials...")
            logger.debug("Calling creds.refresh(Request())...")
            creds.refresh(Request())
            logger.info("Credentials refreshed successfully")
        else:
            logger.info("Need to perform OAuth flow for new credentials")
            logger.debug(f"Loading client secrets from {GOOGLE_CREDENTIALS_PATH}")
            flow = InstalledAppFlow.from_client_secrets_file(
                str(GOOGLE_CREDENTIALS_PATH), GOOGLE_SCOPES
            )
            logger.info("Starting local server for OAuth flow...")
            creds = flow.run_local_server(port=0)
            logger.info("OAuth flow completed successfully")

        logger.info(f"Saving credentials to {GOOGLE_TOKEN_PATH}")
        with open(GOOGLE_TOKEN_PATH, "w") as token:
            token.write(creds.to_json())
        logger.debug("Credentials saved to token file")

    logger.info("get_google_credentials() returning valid credentials")
    return creds


def get_people_service():
    """Get Google People API service."""
    creds = get_google_credentials()
    service = build("people", "v1", credentials=creds)
    return service


def get_all_contacts() -> list[dict]:
    """Get all contacts with names and basic info."""
    logger.info("get_all_contacts() called")
    service = get_people_service()

    logger.info("Fetching contacts from Google People API...")

    results = service.people().connections().list(
        resourceName="people/me",
        pageSize=1000,
        personFields="names,emailAddresses,phoneNumbers,organizations"
    ).execute()

    connections = results.get("connections", [])
    logger.info(f"Retrieved {len(connections)} connections from API")

    contacts = []
    for i, person in enumerate(connections):
        logger.debug(f"Processing person {i+1}/{len(connections)}")
        names = person.get("names", [])
        logger.debug(f"Person has {len(names)} names")

        if names:
            display_name = names[0].get("displayName", "")
            logger.debug(f"Display name: {display_name}")

            contact = {
                "name": display_name,
                "emails": [e["value"] for e in person.get("emailAddresses", [])],
                "phones": [p["value"] for p in person.get("phoneNumbers", [])],
                "organization": None
            }

            logger.debug(f"Emails: {contact['emails']}")
            logger.debug(f"Phones: {contact['phones']}")

            orgs = person.get("organizations", [])
            if orgs:
                contact["organization"] = orgs[0].get("name")
                logger.debug(f"Organization: {contact['organization']}")

            contacts.append(contact)
            logger.debug(f"Added contact: {display_name}")
        else:
            logger.debug(f"Skipping person {i+1} - no names found")

    logger.info(f"get_all_contacts() returning {len(contacts)} contacts")
    return contacts


def search_contact(name: str) -> list[dict]:
    """Search for contacts by name."""
    logger.info(f"search_contact() called with name='{name}'")
    logger.debug("Fetching all contacts for search...")

    contacts = get_all_contacts()
    logger.debug(f"Got {len(contacts)} contacts to search through")

    name_lower = name.lower()
    logger.debug(f"Searching for (lowercase): '{name_lower}'")

    results = [c for c in contacts if name_lower in c["name"].lower()]

    logger.info(f"search_contact() found {len(results)} matches for '{name}'")
    for r in results:
        logger.debug(f"Match: {r['name']}")

    return results


def get_contact_names() -> list[str]:
    """Get just the names of all contacts."""
    logger.info("get_contact_names() called")
    logger.debug("Fetching all contacts...")

    contacts = get_all_contacts()
    names = [c["name"] for c in contacts]

    logger.info(f"get_contact_names() returning {len(names)} names")
    logger.debug(f"First 10 names: {names[:10]}")

    return names
