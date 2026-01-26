# Luna Telegram Bot - Docker Image
FROM python:3.12-slim

# Install uv for fast package management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Set working directory
WORKDIR /app

# Copy all project files needed for build
COPY pyproject.toml uv.lock README.md google_scopes.py ./

# Copy MCP calendar package
COPY mcp_calendar/ ./mcp_calendar/

# Copy source code
COPY src/ ./src/

# Install dependencies
RUN uv sync --frozen --no-dev

# Create data directory
RUN mkdir -p /app/data

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV LUNA_DATA_DIR=/app/data
ENV LUNA_CREDENTIALS_DIR=/app/credentials

# Run the bot
CMD ["uv", "run", "python", "-m", "luna.bot"]
