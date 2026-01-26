# Luna

Personal Telegram assistant with Google Calendar and Contacts integration.

## Features

- Telegram bot with natural language understanding (Claude)
- Google Calendar integration (view and create events)
- Google Contacts integration
- Fact memory (remembers things about your contacts)
- Daily morning summaries

## Project Structure

```
luna/
├── src/luna/           # Main bot code
├── mcp_calendar/       # MCP server for Google Calendar
├── scripts/            # Utility scripts
├── docker/             # Docker deployment files
├── credentials/        # Google OAuth credentials (gitignored)
├── data/               # Runtime data: database, logs (gitignored)
└── google_scopes.py    # Shared Google API scopes
```

## Setup

### 1. Install dependencies

```bash
uv sync
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env with your API keys
```

### 3. Set up Google API credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project and enable Calendar API and People API
3. Create OAuth 2.0 credentials (Desktop app)
4. Download as `credentials.json` and place in `credentials/`

### 4. Authenticate with Google

Run the auth script to generate `token.json`:

```bash
uv run python scripts/auth_google.py
```

This opens a browser for OAuth. Grant access to Calendar and Contacts.

### 5. Run the bot

```bash
uv run python -m luna.bot
```

## Docker Deployment

### Build and run

```bash
cd docker
docker compose up -d --build
```

### View logs

```bash
docker compose logs -f luna
```

### Stop

```bash
docker compose down
```

### Auto-start on boot

Docker containers with `restart: always` automatically start on boot.

Enable Docker daemon on boot:

```bash
sudo systemctl enable docker
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | Telegram Bot API token |
| `ALLOWED_USER_IDS` | Comma-separated list of allowed Telegram user IDs |
| `USER_CHAT_ID` | Chat ID for daily summaries |
| `ANTHROPIC_API_KEY` | Claude API key |
| `DAILY_SUMMARY_HOUR` | Hour for daily summary (default: 7) |
| `DAILY_SUMMARY_MINUTE` | Minute for daily summary (default: 0) |

## Bot Commands

- `/start` - Welcome message
- `/heute` - Today's calendar events
- `/morgen` - Tomorrow's events
- `/fakten` - List stored facts
- `/kontakt <name>` - Search contacts
- `/clear` - Clear conversation history
