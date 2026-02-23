# Audiobook Sync Service

A Docker container application that syncs audiobook listening progress from [Audiobookshelf](https://www.audiobookshelf.org/) to [StoryGraph](https://thestorygraph.com/) and [Hardcover](https://hardcover.app/).

## Features

- **Automatic Progress Sync**: Syncs listening progress from Audiobookshelf to StoryGraph and Hardcover
- **Smart Book Matching**: Matches books by ISBN, ASIN, or title/author
- **Web UI**: Easy configuration through a web interface
- **Docker Ready**: Designed for easy deployment on Unraid, Docker Compose, or any Docker environment
- **Hourly Sync**: Configurable sync interval (default: 60 minutes)
- **Progress Filtering**: Only syncs books with minimum listen time (default: 10 minutes)

## Quick Start

### Using Docker Compose

1. Create a `docker-compose.yml` file:

```yaml
version: '3.8'

services:
  audiobook-sync:
    image: audiobook-sync:latest
    container_name: audiobook-sync
    ports:
      - "5000:5000"
    volumes:
      - ./data:/data
    environment:
      - ABS_URL=http://your-audiobookshelf:13378
      - ABS_TOKEN=your-api-token
      - STORYGRAPH_EMAIL=your@email.com
      - STORYGRAPH_PASSWORD=your-password
      - HARDCOVER_API_KEY=your-api-key
    restart: unless-stopped
```

2. Start the container:

```bash
docker-compose up -d
```

3. Open your browser to `http://localhost:5000` to access the web UI.

### Using Docker

```bash
docker build -t audiobook-sync .
docker run -d \
  -p 5000:5000 \
  -v $(pwd)/data:/data \
  -e ABS_URL=http://your-audiobookshelf:13378 \
  -e ABS_TOKEN=your-api-token \
  -e STORYGRAPH_EMAIL=your@email.com \
  -e STORYGRAPH_PASSWORD=your-password \
  -e HARDCOVER_API_KEY=your-api-key \
  --name audiobook-sync \
  audiobook-sync
```

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `ABS_URL` | Audiobookshelf server URL | - |
| `ABS_TOKEN` | Audiobookshelf API token | - |
| `STORYGRAPH_EMAIL` | StoryGraph login email | - |
| `STORYGRAPH_PASSWORD` | StoryGraph password | - |
| `HARDCOVER_API_KEY` | Hardcover API key | - |
| `SYNC_INTERVAL_MINUTES` | Sync interval in minutes | 60 |
| `MIN_LISTEN_MINUTES` | Minimum listen time before syncing | 10 |
| `ENABLE_STORYGRAPH` | Enable StoryGraph sync | true |
| `ENABLE_HARDCOVER` | Enable Hardcover sync | true |
| `DATABASE_URL` | SQLite database path | sqlite:///data/audiobook-sync.db |
| `SECRET_KEY` | Flask secret key for sessions | (auto-generated) |
| `LOG_LEVEL` | Logging level | INFO |
| `TZ` | Timezone | UTC |
| `PORT` | Web server port | 5000 |

### Web UI Configuration

You can also configure the service through the web UI at `http://localhost:5000/config`. The web UI allows you to:

- Configure Audiobookshelf connection
- Configure StoryGraph credentials
- Configure Hardcover API key
- Set sync interval and minimum listen time
- Test connections before saving

## Getting API Keys

### Audiobookshelf

1. Open Audiobookshelf
2. Go to Settings → Users
3. Create a new user or edit existing user
4. Copy the API token

### Hardcover

1. Go to [hardcover.app/account](https://hardcover.app/account)
2. Scroll down to API Keys
3. Generate a new API key

### StoryGraph

StoryGraph doesn't have an official API. This service uses your login credentials to interact with the website. Use your normal StoryGraph email and password.

## How It Works

1. **Fetch Progress**: The service connects to Audiobookshelf and retrieves all audiobooks with listening progress
2. **Filter Books**: Books with less than the minimum listen time are skipped
3. **Match Books**: For each book, the service tries to find a match in StoryGraph and/or Hardcover using:
   - ISBN (highest confidence)
   - ASIN (Audible ID)
   - Title + Author (fallback)
4. **Update Progress**: If a match is found, the progress percentage is updated in the target service
5. **Cache Mappings**: Book mappings are cached to speed up future syncs

## API Endpoints

The service provides a REST API for programmatic access:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/status` | GET | Get current sync status |
| `/api/sync` | POST | Trigger a manual sync |
| `/api/history` | GET | Get sync history |
| `/api/runs` | GET | Get sync runs |
| `/api/logs` | GET | Get recent logs |
| `/api/mappings` | GET | Get book mappings |
| `/api/stats` | GET | Get sync statistics |
| `/health` | GET | Health check endpoint |

## Unraid Installation

1. Install the Docker application from the Unraid Community Applications
2. Add a new container with the following settings:
   - **Repository**: `audiobook-sync:latest`
   - **Network**: bridge
   - **Port**: 5000
   - **Volume**: `/data` → Your preferred data location
3. Add environment variables for your configuration
4. Start the container

## Development

### Prerequisites

- Python 3.11+
- pip

### Setup

```bash
# Clone the repository
git clone https://github.com/your-repo/audiobook-sync.git
cd audiobook-sync

# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run the application
python -m app.main
```

### Project Structure

```
audiobook-sync/
├── app/
│   ├── api/           # API clients for external services
│   ├── db/            # Database models and connection
│   ├── sync/          # Sync engine and matching logic
│   ├── web/           # Flask web application
│   ├── config.py      # Configuration management
│   └── main.py        # Application entry point
├── data/              # SQLite database storage
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

## Troubleshooting

### Book Not Matching

If a book isn't matching, check:
1. Does the book have an ISBN or ASIN in Audiobookshelf?
2. Is the title exactly the same in both services?
3. Check the logs for matching attempts

### StoryGraph Login Failing

StoryGraph may block automated logins. If this happens:
1. Try logging in through a browser first
2. Wait a few hours before trying again
3. Consider using a dedicated account for the sync service

### Connection Errors

If you see connection errors:
1. Verify the Audiobookshelf URL is accessible from the container
2. Check that the API token is valid
3. Ensure the container has network access

## Known Limitations

- **StoryGraph**: Uses unofficial API (web scraping), may break if StoryGraph changes their site
- **No Bidirectional Sync**: Progress only syncs from Audiobookshelf to other services
- **No Rating/Review Sync**: Only progress and reading status are synced

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- [Audiobookshelf](https://www.audiobookshelf.org/) - Self-hosted audiobook server
- [StoryGraph](https://thestorygraph.com/) - Book tracking website
- [Hardcover](https://hardcover.app/) - Book tracking platform
- [storygraph-api](https://github.com/ym496/storygraph-api) - Unofficial StoryGraph API inspiration
