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
    image: adam28693/audiobook-sync:latest
    container_name: audiobook-sync
    ports:
      - "8765:8765"
    volumes:
      - ./data:/data
    environment:
      - ABS_URL=http://your-audiobookshelf:13378
      - ABS_TOKEN=your-api-token
      - STORYGRAPH_COOKIE=your-remember-user-token-cookie
      - STORYGRAPH_USERNAME=your-username
      - HARDCOVER_API_KEY=your-api-key
    restart: unless-stopped
```

2. Start the container:

```bash
docker-compose up -d
```

3. Open your browser to `http://localhost:8765` to access the web UI.

### Using Docker

```bash
docker run -d \
  -p 8765:8765 \
  -v $(pwd)/data:/data \
  -e ABS_URL=http://your-audiobookshelf:13378 \
  -e ABS_TOKEN=your-api-token \
  -e STORYGRAPH_COOKIE=your-remember-user-token-cookie \
  -e STORYGRAPH_USERNAME=your-username \
  -e HARDCOVER_API_KEY=your-api-key \
  --name audiobook-sync \
  adam28693/audiobook-sync:latest
```

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `ABS_URL` | Audiobookshelf server URL | - |
| `ABS_TOKEN` | Audiobookshelf API token | - |
| `STORYGRAPH_COOKIE` | StoryGraph `remember_user_token` cookie | - |
| `STORYGRAPH_USERNAME` | StoryGraph username (optional) | - |
| `HARDCOVER_API_KEY` | Hardcover API key | - |
| `SYNC_INTERVAL_MINUTES` | Sync interval in minutes | 60 |
| `MIN_LISTEN_MINUTES` | Minimum listen time before syncing | 10 |
| `ENABLE_STORYGRAPH` | Enable StoryGraph sync | true |
| `ENABLE_HARDCOVER` | Enable Hardcover sync | true |
| `DATABASE_URL` | SQLite database path | sqlite:///data/audiobook-sync.db |
| `SECRET_KEY` | Flask secret key for sessions | (auto-generated) |
| `LOG_LEVEL` | Logging level | INFO |
| `TZ` | Timezone | UTC |
| `PORT` | Web server port | 8765 |

### Web UI Configuration

You can also configure the service through the web UI at `http://localhost:8765/config`. The web UI allows you to:

- Configure Audiobookshelf connection
- Configure StoryGraph cookie
- Configure Hardcover API key
- Set sync interval and minimum listen time
- Test connections before saving

## Getting API Keys and Cookies

### Audiobookshelf

1. Open Audiobookshelf
2. Go to Settings → Users
3. Create a new user or edit existing user
4. Copy the API token

### Hardcover

1. Go to [hardcover.app/account](https://hardcover.app/account)
2. Scroll down to API Keys
3. Generate a new API key
4. Copy only the token part (after "Bearer ") - e.g., if it shows "Bearer abc123", copy only "abc123"

### StoryGraph (Cookie-Based Authentication)

StoryGraph doesn't have an official API and uses bot protection. This service uses cookie-based authentication with Selenium to bypass these restrictions.

**How to get your StoryGraph cookie:**

1. Log in to [StoryGraph](https://app.thestorygraph.com) in your browser
2. Open Developer Tools:
   - **Chrome/Edge**: Press `F12` or right-click → Inspect
   - **Firefox**: Press `F12` or right-click → Inspect
   - **Safari**: Enable Developer menu in Preferences, then press `F12`
3. Go to the **Application** tab (Chrome/Edge) or **Storage** tab (Firefox)
4. Expand **Cookies** → click on `app.thestorygraph.com`
5. Find the cookie named `remember_user_token`
6. Copy its **Value** (this is what you need for `STORYGRAPH_COOKIE`)

![Cookie extraction example](https://developer.mozilla.org/en-US/docs/Web/HTTP/Cookies/cookie.png)

**Note:** The cookie value is a long string that looks like:
```
eyJfcmFpbHMiOnsibWVzc2FnZSI6IkJBaEpJ...
```

**Important:**
- The cookie will expire eventually - you'll need to update it periodically
- Keep your cookie secure - it provides full access to your StoryGraph account
- If sync stops working, try getting a fresh cookie

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

1. Go to the Docker tab in Unraid
2. Click "Add Container"
3. Configure the container:
   - **Repository**: `adam28693/audiobook-sync:latest`
   - **Network**: bridge
   - **Port**: 8765
   - **Volume**: `/data` → Your preferred data location
4. Add environment variables for your configuration
5. Start the container

## Development

### Prerequisites

- Python 3.11+
- Chrome/Chromium (for StoryGraph Selenium support)

### Setup

```bash
# Clone the repository
git clone https://github.com/adam2893/audiobook-sync.git
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

### StoryGraph Cookie Issues

If StoryGraph sync isn't working:
1. **Cookie expired**: Get a fresh cookie from your browser
2. **Invalid cookie**: Make sure you copied the entire cookie value
3. **Chrome/Chromium not found**: Ensure Chromium is installed in the Docker container (it's included in the official image)

### Connection Errors

If you see connection errors:
1. Verify the Audiobookshelf URL is accessible from the container
2. Check that the API token is valid
3. Ensure the container has network access

### Docker Container Size

The Docker image includes Chromium for StoryGraph support, making it larger than typical Python images (~500MB). This is necessary because StoryGraph uses bot protection that requires a real browser.

## Known Limitations

- **StoryGraph**: Uses unofficial API (Selenium-based web scraping), may break if StoryGraph changes their site
- **Cookie Expiration**: StoryGraph cookies expire periodically and need to be refreshed
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
