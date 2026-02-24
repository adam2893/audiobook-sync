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

# Set work directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
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
