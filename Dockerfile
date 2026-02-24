FROM python:3.11-slim

# Build arguments
ARG VERSION=1.0.0

LABEL maintainer="Audiobook Sync Contributors"
LABEL description="Sync audiobook progress from Audiobookshelf to StoryGraph and Hardcover"
LABEL version="${VERSION}"

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV TZ=UTC
# Chrome/Selenium environment
ENV CHROME_BIN=/usr/bin/google-chrome
ENV CHROMIUM_BIN=/usr/bin/chromium
ENV SE_CHROME_BINARY_PATH=/usr/bin/chromium

# Set work directory
WORKDIR /app

# Install system dependencies including Chromium for Selenium
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    # Chromium and dependencies for Selenium/StoryGraph
    chromium \
    chromium-driver \
    wget \
    gnupg \
    ca-certificates \
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libatspi2.0-0 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libwayland-client0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxkbcommon0 \
    libxrandr2 \
    xdg-utils \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create data directory
RUN mkdir -p /data

# Expose port
EXPOSE 8765

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8765/health || exit 1

# Run application
CMD ["python", "-m", "app.main"]
