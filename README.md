# SkyTube - YouTube to Bluesky Auto-Poster 🎬📢

Automatically monitor your YouTube channel for new videos and post them to Bluesky with rich preview cards.

![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)

## Features

- 🔄 **Automatic Monitoring** - Continuously monitors your YouTube channel for new uploads
- 📡 **Dual Video Source** - Fetch videos via RSS feed (default) or the YouTube Data API (`--use-api`)
- 🖼️ **Rich Preview Cards** - Posts include video thumbnails and proper link embeds
- 💾 **Persistent Database** - Remembers which videos have been posted, survives restarts
- ⚙️ **Easy Configuration** - Simple YAML config file with helpful comments
- 🛡️ **Database Build Mode** - Initialize without posting to avoid duplicate posts
- 📝 **File Logging** - Optional persistent log file for diagnostics (`--log`)
- 🚫 **No Cache Mode** - Bypass API caching to get fresh data (`--no-cache`)
- 🎨 **Colored Output** - Clear, color-coded terminal output for easy monitoring

## Requirements

- Python 3.9 or higher
- A YouTube channel with a Channel ID
- A Bluesky account with an App Password
- *(Optional)* A YouTube Data API key if using `--use-api` mode

## Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/yourusername/skytube.git
   cd skytube
   ```

2. **Install dependencies:**
   ```bash
   pip install feedparser atproto requests pyyaml
   ```

## Configuration

1. **Run the script for the first time:**
   ```bash
   python skytube.py
   ```
   The script will offer to create an example configuration file for you.

2. **Edit `config.yaml`** with your settings:
   ```yaml
   # Your YouTube channel ID (find it in the channel URL after /channel/)
   youtube_channel_id: "UCxxxxxxxxxxxxxxxx"

   # Your Bluesky credentials
   # TIP: Use an "App Password" from Bluesky settings, not your main password!
   bluesky_handle: "yourhandle.bsky.social"
   bluesky_password: "your-app-password-here"

   # The message template for your Bluesky post
   # {title} will be replaced with the video title
   # {url} will be replaced with the video URL
   post_template: "🎬 New video: {title}"

   # How often to check for new videos (in seconds)
   check_interval_seconds: 600

   # File to store which videos we've already posted about
   seen_videos_file: "youtube_bluesky_seen.json"
   ```

3. **(Optional) YouTube API configuration** - add these to `config.yaml` if you plan to use `--use-api`:
   ```yaml
   # YouTube Data API key (https://console.cloud.google.com/apis/credentials)
   youtube_api_key: "YOUR_YOUTUBE_API_KEY_HERE"

   # Maximum number of videos to fetch per check (default: 15)
   api_max_results: 15
   ```

### Finding Your YouTube Channel ID

1. Go to your YouTube channel
2. Look at the URL - it will be in one of these formats:
   - `youtube.com/channel/UCxxxxxxxxxxxxxxxx` (the ID is after `/channel/`)
   - If you have a custom URL, go to your channel, click "About", then look for the channel ID

### Creating a Bluesky App Password

1. Log into Bluesky
2. Go to **Settings** → **App Passwords**
3. Click **Add App Password**
4. Give it a name (e.g., "YouTube Bot") and copy the generated password

## Usage

### Normal Mode (Monitor and Post)

```bash
# Using default config.yaml in the same directory
python skytube.py

# Using a custom config file location
python skytube.py --config /path/to/config.yaml
```

### YouTube API Mode

Use the YouTube Data API instead of RSS for more reliable video fetching:

```bash
python skytube.py --use-api
```

Requires `youtube_api_key` to be set in your config file.

### Build Database Mode

Use this mode when first setting up the script to register existing videos without posting them:

```bash
python skytube.py --build-db

# With custom config
python skytube.py --config /path/to/config.yaml --build-db

# Build database using API
python skytube.py --use-api --build-db
```

This is useful for:
- Initial setup (so only future videos get posted)
- Recovering from a lost database file
- Adding the script to an existing channel

### File Logging

Enable persistent file logging to `skytube.log`:

```bash
python skytube.py --log

# Combine with other flags
python skytube.py --log --use-api
```

The log file is written in append mode, so logs persist across restarts.

### No Cache Mode

Disable caching for YouTube API requests to get fresh data (useful when running as a service):

```bash
python skytube.py --use-api --no-cache

# Combine with other flags
python skytube.py --log --use-api --no-cache
```

This adds cache-control headers and unique timestamps to each API request, preventing YouTube's servers from returning stale cached responses. Particularly useful when running as a systemd service where the process stays active for long periods.

## Command Line Options

| Option | Short | Description |
|--------|-------|-------------|
| `--config` | `-c` | Path to the configuration YAML file (default: `config.yaml`) |
| `--build-db` | | Build the database of seen videos without posting |
| `--use-api` | | Use YouTube Data API instead of RSS feed (requires `youtube_api_key` in config) |
| `--log` | | Enable continuous file logging to `skytube.log` |
| `--no-cache` | | Disable caching for YouTube API requests (requires `--use-api`) |

## How It Works

1. **Fetch Videos** - The script fetches your YouTube channel's videos via RSS feed or YouTube Data API
2. **Check for New Videos** - Compares entries against the database of seen videos
3. **Download Thumbnail** - Gets the highest quality thumbnail available (maxres → hq → mq)
4. **Post to Bluesky** - Creates a post with the video title, link, and thumbnail embed
5. **Update Database** - Marks the video as posted to prevent duplicates
6. **Sleep** - Waits for the configured interval before checking again

## Project Structure

```
skytube/
├── skytube.py                 # Main script
├── config.yaml                # Your configuration (created on first run)
├── youtube_bluesky_seen.json  # Database of posted videos (auto-generated)
├── skytube.log                # Log file (created when using --log)
└── README.md                  # This file
```

## Troubleshooting

### "Feed parsing issue" warning
- Verify your YouTube channel ID is correct
- Check your internet connection
- The RSS feed might be temporarily unavailable

### "Error posting to Bluesky"
- Verify your Bluesky handle and app password are correct
- Check if you've hit Bluesky's rate limits
- Ensure your account is in good standing

### No thumbnails appearing
- Some videos may not have high-resolution thumbnails available
- The script automatically falls back to lower quality thumbnails
- Posts will still work without thumbnails

### YouTube API errors
- **HTTP 403** - Check that your API key is valid and YouTube Data API v3 is enabled
- **HTTP 404** - Verify your channel ID is correct (must start with `UC`)
- **HTTP 429** - You've hit the API rate limit; wait and try again

### Videos not detected for hours
- YouTube API may cache responses for several hours
- **Solution**: Use the `--no-cache` flag with `--use-api` to bypass caching
- This is particularly useful when running as a systemd service

## Running as a Service

For continuous operation, consider running the script as a system service:

### Using systemd (Linux)

Create `/etc/systemd/system/skytube.service`:
```ini
[Unit]
Description=YouTube to Bluesky Auto-Poster
After=network.target

[Service]
Type=simple
User=your-username
WorkingDirectory=/path/to/skytube
ExecStart=/usr/bin/python3 skytube.py --use-api --log --no-cache
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Then enable and start:
```bash
sudo systemctl enable skytube
sudo systemctl start skytube
```

## Contributing

Contributions are welcome! Feel free to:
- Report bugs
- Suggest new features
- Submit pull requests

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- [atproto](https://github.com/MarshalX/atproto) - Python library for the AT Protocol
- [feedparser](https://github.com/kurtmckee/feedparser) - RSS/Atom feed parser

---

Made with ❤️ for the Bluesky community
