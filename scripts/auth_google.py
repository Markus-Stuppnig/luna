#!/usr/bin/env python3
"""
Standalone script to authenticate with Google APIs.
Run this once to generate token.json with the correct scopes.
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from google_auth_oauthlib.flow import InstalledAppFlow
from google_scopes import GOOGLE_SCOPES

def main():
    credentials_dir = project_root / "credentials"
    credentials_path = credentials_dir / "credentials.json"
    token_path = credentials_dir / "token.json"

    if not credentials_path.exists():
        print(f"Error: {credentials_path} not found")
        print("Please download your OAuth credentials from Google Cloud Console")
        sys.exit(1)

    print("Starting OAuth flow...")
    print("A browser window will open for authentication.")
    print()

    flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), GOOGLE_SCOPES)
    creds = flow.run_local_server(port=8080)

    with open(token_path, "w") as token:
        token.write(creds.to_json())

    print()
    print(f"Token saved to {token_path}")
    print("You can now run the bot!")


if __name__ == "__main__":
    main()
