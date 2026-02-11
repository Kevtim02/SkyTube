# SkyTube — YouTube to Bluesky Auto-Poster

This Python script monitors a YouTube channel for new videos (via RSS feed or YouTube Data API) and automatically posts about them on Bluesky with a rich preview card including the video thumbnail.

## Table of Contents
- [Requirements](#requirements)
- [Features](#features)
- [Installation](#installation)
- [Usage](#usage)
  - [Normal Mode](#normal-mode)
  - [YouTube API Mode](#youtube-api-mode)
  - [Dual Mode](#dual-mode)
  - [Database Build Mode](#database-build-mode)
  - [File Logging](#file-logging)
  - [No Cache Mode](#no-cache-mode)
- [Configuration](#configuration)
  - [Configuration Options](#configuration-options)
  - [YouTube API Configuration (Optional)](#youtube-api-configuration-optional)
  - [Dual Mode Configuration (Optional)](#dual-mode-configuration-optional)
  - [Finding Your YouTube Channel ID](#finding-your-youtube-channel-id)
  - [Creating a Bluesky App Password](#creating-a-bluesky-app-password)
- [Command Line Arguments](#command-line-arguments)
- [Script Details](#script-details)
  - [How It Works](#how-it-works)
  - [File Structure](#file-structure)
- [Running as a Service](#running-as-a-service)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)
- [License](#license)

## Requirements
- Python 3.9 or higher
- A YouTube channel
- A Bluesky account
- *(Optional)* A YouTube Data API key if using `--use-api` mode

## Features
- **Automatic Monitoring**: Continuously monitors your YouTube channel for new videos.
- **Dual Video Source**: Fetch videos via RSS feed (default), YouTube Data API (`--use-api`), or both (`--dual-mode`) for maximum reliability.
- **Rich Preview Cards**: Posts to Bluesky include a link preview card with the video thumbnail, title, and description.
- **Thumbnail Support**: Automatically downloads and uploads video thumbnails in the highest available quality (maxres → hq → mq).
- **Database Persistence**: Tracks posted videos in a JSON file to prevent duplicate posts across restarts.
- **Database Build Mode**: Register existing videos without posting, so only future uploads get announced.
- **File Logging**: Optional persistent log file (`skytube.log`) via the `--log` flag for diagnostics and record keeping.
- **No Cache Mode**: Disable caching for API requests via `--no-cache` flag to get fresh data and bypass stale cached responses.
- **Dual Mode**: Query both RSS and API simultaneously - posts videos found in either source, with configurable preference for duplicate handling.
- **YAML Configuration**: Easy-to-edit configuration file with helpful comments.
- **Colored Output**: Color-coded terminal output for errors (red), success (green), warnings (yellow), and info (blue/cyan).
- **Interactive Setup**: Prompts to create an example config file if none exists.
- **Customizable Post Template**: Configure your post message format with `{title}` and `{url}` template variables.
- **Configurable Check Interval**: Set how often the script checks for new videos.
- **Error Recovery**: Continues running even if individual checks fail, with detailed error hints.

## Installation

1. **Clone or download the script**:
   ```bash
   git clone https://github.com/yourusername/skytube.git
   cd skytube
   ```

2. **Install the required Python packages**:
   ```bash
   pip install feedparser atproto requests pyyaml
   ```

3. **Run the script once to generate a config file**:
   ```bash
   python skytube.py
   ```
   When prompted, type `yes` to create an example configuration file.

4. **Edit the configuration file** with your settings:
   ```bash
   nano config.yaml
   ```

## Usage

### Normal Mode
To start monitoring your YouTube channel and automatically post new videos to Bluesky:

```bash
python skytube.py
```

With a custom config file location:
```bash
python skytube.py --config /path/to/config.yaml
```

### YouTube API Mode
Use the YouTube Data API instead of RSS for more reliable video fetching:

```bash
python skytube.py --use-api
```

This mode requires `youtube_api_key` to be set in your config file. The API is more reliable than RSS and supports fetching more than the 15 most recent videos.

### Dual Mode

Query both RSS feed and YouTube Data API simultaneously for maximum reliability:

```bash
# Dual mode - checks both RSS and API
python skytube.py --dual-mode

# Dual mode with cache disabled for API requests
python skytube.py --dual-mode --no-cache

# Dual mode with file logging
python skytube.py --dual-mode --log
```

**Features:**
- Posts videos found in **either** RSS or API
- API metadata is preferred when a video is found in both sources (configurable)
- Continues working if one source fails temporarily
- Maximizes chance of detecting new videos quickly

**Requirements:**
- Requires `youtube_api_key` to be set in your config file
- See [Dual Mode Configuration](#dual-mode-configuration-optional) for preference settings

This is the recommended mode for production use when running as a systemd service.

### Database Build Mode
To register all existing videos without posting (useful for initial setup):

```bash
python skytube.py --build-db
```

This will:
- Fetch all videos currently in your YouTube feed (RSS or API)
- Add them to the seen videos database
- **Not post anything to Bluesky**
- Allow you to run the script normally afterward, posting only truly new videos

You can also combine it with other flags:
```bash
python skytube.py --use-api --build-db
```

### File Logging
Enable persistent file logging to `skytube.log`:

```bash
python skytube.py --log
```

The log file is written in append mode so logs persist across restarts. All console output (with timestamps and log levels) is mirrored to the file. Combine with other flags as needed:

```bash
python skytube.py --log --use-api
```

### No Cache Mode
Disable caching for YouTube API requests to get fresh data:

```bash
python skytube.py --use-api --no-cache
```

This adds cache-control headers and unique timestamps to API requests, preventing YouTube's servers from returning stale cached responses. Useful when:
- The API returns the same videos for hours after a new video is published
- You're experiencing delays in detecting new uploads
- Running as a systemd service where the process stays active for long periods

Combine with other flags:
```bash
python skytube.py --log --use-api --no-cache
```

## Configuration

The script uses a YAML configuration file (`config.yaml` by default). An example configuration:

```yaml
# YouTube to Bluesky Auto-Poster Configuration
# =============================================

# Your YouTube channel ID (find it in the channel URL after /channel/)
youtube_channel_id: "UCxxxxxxxxxxxxxxxx"

# Your Bluesky credentials
# TIP: Use an "App Password" from Bluesky settings, not your main password!
bluesky_handle: "yourhandle.bsky.social"
bluesky_password: "xxxx-xxxx-xxxx-xxxx"

# The message template for your Bluesky post
# {title} will be replaced with the video title
# {url} will be replaced with the video URL
post_template: "🎬 New video: {title}"

# How often to check for new videos (in seconds)
# 300 = 5 minutes, 600 = 10 minutes, 900 = 15 minutes
check_interval_seconds: 600

# File to store which videos we've already posted about
seen_videos_file: "youtube_bluesky_seen.json"
```

### Configuration Options

| Option | Description | Default |
|--------|-------------|---------|
| `youtube_channel_id` | Your YouTube channel ID (required) | - |
| `bluesky_handle` | Your Bluesky handle (required) | - |
| `bluesky_password` | Your Bluesky app password (required) | - |
| `post_template` | Template for the post text. Use `{title}` for video title and `{url}` for video URL | `🎬 New video: {title}` |
| `check_interval_seconds` | How often to check for new videos (in seconds) | `600` |
| `seen_videos_file` | Path to the JSON file storing seen video IDs | `youtube_bluesky_seen.json` |

### YouTube API Configuration (Optional)

If you want to use the YouTube Data API instead of RSS, add these to your `config.yaml`:

```yaml
# YouTube Data API key
# Get one from: https://console.cloud.google.com/apis/credentials
youtube_api_key: "YOUR_YOUTUBE_API_KEY_HERE"

# Maximum number of videos to fetch per API request (1-50)
# Only used when --use-api is enabled
api_max_results: 15
```

| Option | Description | Default |
|--------|-------------|---------|
| `youtube_api_key` | YouTube Data API v3 key (required for `--use-api`) | - |
| `api_max_results` | Maximum number of videos to fetch per check (positive integer) | `15` |

To obtain a YouTube API key:
1. Go to [Google Cloud Console](https://console.cloud.google.com/apis/credentials)
2. Create a new project (or select an existing one)
3. Enable the **YouTube Data API v3**
4. Create an API key under **Credentials**

### Dual Mode Configuration (Optional)

When using `--dual-mode`, you can configure which source's metadata is preferred when a video is found in both RSS and API:

```yaml
# Which source to prefer when video found in both sources
# Options: "api" or "rss"
# Default: "api" (API metadata is preferred)
dual_mode_preference: "api"
```

| Option | Description | Default |
|--------|-------------|---------|
| `dual_mode_preference` | Which source to prefer when video found in both RSS and API ("api" or "rss") | `api` |

**Note:** This setting only affects which metadata is used when a video exists in both sources. The video will be posted regardless of which source it came from.

### Finding Your YouTube Channel ID

1. Go to your YouTube channel page
2. Look at the URL:
   - If it's `youtube.com/channel/UCxxxxxxxxxx`, the ID is `UCxxxxxxxxxx`
   - If it's `youtube.com/@username`, you'll need to:
     1. View page source (Ctrl+U)
     2. Search for `browse_id` or `channelId`
     3. Copy the ID that starts with `UC`

### Creating a Bluesky App Password

1. Log in to [Bluesky](https://bsky.app)
2. Go to **Settings** → **Privacy and Security** → **App Passwords**
3. Click **Add App Password**
4. Give it a name (e.g., "YouTube Poster")
5. Copy the generated password and paste it in your config file

> **Security Tip**: Use an App Password instead of your main password. App passwords can be revoked individually if compromised.

## Command Line Arguments

| Argument | Short | Description |
|----------|-------|-------------|
| `--config` | `-c` | Path to the configuration YAML file (default: `config.yaml`) |
| `--build-db` | - | Build/rebuild the database of seen videos without posting |
| `--use-api` | - | Use YouTube Data API instead of RSS feed (requires `youtube_api_key` in config) |
| `--dual-mode` | - | Use both RSS and API simultaneously (requires `youtube_api_key` in config) |
| `--log` | - | Enable continuous file logging to `skytube.log` in the current directory |
| `--no-cache` | - | Disable caching for YouTube API requests |
| `--help` | `-h` | Show help message and exit |

### Examples

```bash
# Use default config.yaml in current directory
python skytube.py

# Use a specific config file
python skytube.py --config /home/user/myconfig.yaml

# Use YouTube Data API instead of RSS
python skytube.py --use-api

# Build database without posting
python skytube.py --build-db

# Build database using API
python skytube.py --use-api --build-db

# Build database with specific config
python skytube.py --config /home/user/myconfig.yaml --build-db

# Enable file logging
python skytube.py --log

# File logging with API mode
python skytube.py --log --use-api

# All flags combined
python skytube.py --log --use-api --build-db

# Disable API caching to get fresh data
python skytube.py --use-api --no-cache

# File logging with API mode and no cache
python skytube.py --log --use-api --no-cache

# Dual mode - use both RSS and API
python skytube.py --dual-mode

# Dual mode with no cache and file logging
python skytube.py --dual-mode --no-cache --log

# Build database using dual mode
python skytube.py --dual-mode --build-db
```

## Script Details

### How It Works

1. **Startup**: The script loads configuration from the YAML file and validates required settings.

2. **Feed Monitoring**: Every `check_interval_seconds`, the script fetches the latest videos from the YouTube channel using either the RSS feed (default), the YouTube Data API (`--use-api`), or both (`--dual-mode`).

3. **Duplicate Detection**: Each video's ID is compared against the stored database (`seen_videos_file`). Only new videos trigger a post.

4. **Posting to Bluesky**: For new videos, the script:
   - Downloads the video thumbnail (tries maxres, then hq, then mq quality)
   - Uploads the thumbnail to Bluesky
   - Creates a post with an embed card containing the video link, title, and thumbnail

5. **Database Update**: Successfully posted videos are added to the seen videos database and saved immediately.

6. **Sleep**: The script waits for the configured interval before checking again.

### File Structure

```
skytube/
├── skytube.py                  # Main script
├── config.yaml                 # Your configuration (created on first run)
├── youtube_bluesky_seen.json   # Auto-generated database of posted videos
├── skytube.log                 # Log file (created when using --log)
├── usage.md                    # This file
└── README.md                   # Project README
```

## Running as a Service

### Using systemd (Linux)

Create a service file at `/etc/systemd/system/skytube.service`:

```ini
[Unit]
Description=YouTube to Bluesky Auto-Poster
After=network.target

[Service]
Type=simple
User=yourusername
WorkingDirectory=/path/to/skytube
ExecStart=/usr/bin/python3 /path/to/skytube/skytube.py --config /path/to/config.yaml
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start the service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable skytube
sudo systemctl start skytube
```

Check the status:

```bash
sudo systemctl status skytube
```

View logs:

```bash
journalctl -u skytube -f
```

> **Tip**: You can also add `--log` to the `ExecStart` line to write persistent logs to `skytube.log` in addition to journald.

### Using screen (Linux)

```bash
screen -S skytube
python skytube.py
# Press Ctrl+A, then D to detach
```

Reattach with:
```bash
screen -r skytube
```

## Troubleshooting

### Common Issues

| Issue | Solution |
|-------|----------|
| "Configuration file not found" | Run the script once and type `yes` to create an example config, then edit it |
| "Missing or invalid configuration" | Check that all required fields in `config.yaml` are filled in (not placeholder values) |
| "Feed parsing issue" | Verify your YouTube channel ID is correct |
| "Error posting to Bluesky" | Check your Bluesky credentials; ensure you're using an App Password |
| Duplicate posts | Delete `youtube_bluesky_seen.json` and run `--build-db` to rebuild the database |
| Thumbnail not showing | Some videos may not have high-res thumbnails; the script falls back to lower quality |
| Videos not detected for hours | YouTube API may be caching responses; use `--no-cache` flag with `--use-api` |

### YouTube API Errors

| HTTP Status | Cause | Solution |
|-------------|-------|----------|
| 403 | Invalid API key or quota exceeded | Verify your API key is valid and YouTube Data API v3 is enabled |
| 404 | Playlist/channel not found | Verify your channel ID is correct (must start with `UC`) |
| 429 | Rate limit hit | Wait and try again; the script will return partial results if available |

### Checking Logs

The script outputs timestamped, color-coded logs to the console. For persistent file logging, use the `--log` flag:

```bash
python skytube.py --log
```

This writes all output to `skytube.log` in the current working directory. If running as a systemd service, you can also check journald:

```bash
journalctl -u skytube --since "1 hour ago"
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

**Disclaimer**: This script is not affiliated with YouTube or Bluesky. Use responsibly and in accordance with both platforms' terms of service.
