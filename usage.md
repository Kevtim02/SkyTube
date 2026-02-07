# YouTube to Bluesky Auto-Poster

This Python script monitors a YouTube channel's RSS feed for new videos and automatically posts about them on Bluesky with a rich preview card including the video thumbnail.

## Table of Contents
- [Requirements](#requirements)
- [Features](#features)
- [Installation](#installation)
- [Usage](#usage)
  - [Normal Mode](#normal-mode)
  - [Database Build Mode](#database-build-mode)
- [Configuration](#configuration)
  - [Configuration Options](#configuration-options)
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
- Python 3.7 or higher
- A YouTube channel
- A Bluesky account

## Features
- **Automatic Monitoring**: Continuously monitors your YouTube channel's RSS feed for new videos.
- **Rich Preview Cards**: Posts to Bluesky include a link preview card with the video thumbnail, title, and description.
- **Thumbnail Support**: Automatically downloads and uploads video thumbnails in the highest available quality.
- **Database Persistence**: Tracks posted videos in a JSON file to prevent duplicate posts across restarts.
- **Database Build Mode**: Register existing videos without posting, so only future uploads get announced.
- **YAML Configuration**: Easy-to-edit configuration file with helpful comments.
- **Colored Output**: Color-coded terminal output for errors (red), success (green), and warnings (yellow).
- **Interactive Setup**: Prompts to create an example config file if none exists.
- **Customizable Post Template**: Configure your post message format with template variables.
- **Configurable Check Interval**: Set how often the script checks for new videos.
- **Error Recovery**: Continues running even if individual checks fail.

## Installation

1. **Clone or download the script**:
   ```bash
   git clone https://github.com/yourusername/youtube-to-bluesky.git
   cd youtube-to-bluesky
   ```

2. **Install the required Python packages**:
   ```bash
   pip install feedparser atproto requests pyyaml
   ```

3. **Run the script once to generate a config file**:
   ```bash
   python youtube_to_bluesky.py
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
python youtube_to_bluesky.py
```

With a custom config file location:
```bash
python youtube_to_bluesky.py --config /path/to/config.yaml
```

### Database Build Mode
To register all existing videos without posting (useful for initial setup):

```bash
python youtube_to_bluesky.py --build-db
```

This will:
- Fetch all videos currently in your YouTube RSS feed
- Add them to the seen videos database
- **Not post anything to Bluesky**
- Allow you to run the script normally afterward, posting only truly new videos

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
| `post_template` | Template for the post text. Use `{title}` for video title | `🎬 New video: {title}` |
| `check_interval_seconds` | How often to check for new videos (in seconds) | `600` |
| `seen_videos_file` | Path to the JSON file storing seen video IDs | `youtube_bluesky_seen.json` |

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

> ⚠️ **Security Tip**: Use an App Password instead of your main password. App passwords can be revoked individually if compromised.

## Command Line Arguments

| Argument | Short | Description |
|----------|-------|-------------|
| `--config` | `-c` | Path to the configuration YAML file (default: `config.yaml`) |
| `--build-db` | - | Build/rebuild the database of seen videos without posting |
| `--help` | `-h` | Show help message and exit |

### Examples

```bash
# Use default config.yaml in current directory
python youtube_to_bluesky.py

# Use a specific config file
python youtube_to_bluesky.py --config /home/user/myconfig.yaml

# Build database without posting
python youtube_to_bluesky.py --build-db

# Build database with specific config
python youtube_to_bluesky.py --config /home/user/myconfig.yaml --build-db
```

## Script Details

### How It Works

1. **Startup**: The script loads configuration from the YAML file and validates required settings.

2. **Feed Monitoring**: Every `check_interval_seconds`, the script fetches the YouTube channel's RSS feed.

3. **New Video Detection**: Each video ID is compared against the local database of seen videos.

4. **Posting to Bluesky**: For new videos, the script:
   - Downloads the video thumbnail (tries multiple quality levels)
   - Uploads the thumbnail to Bluesky
   - Creates a post with an embed card containing the video link, title, and thumbnail

5. **Database Update**: Successfully posted videos are added to the seen videos database.

### File Structure

```
youtube-to-bluesky/
├── youtube_to_bluesky.py      # Main script
├── config.yaml                 # Your configuration (create this)
├── youtube_bluesky_seen.json   # Auto-generated database of posted videos
└── README.md                   # This file
```

## Running as a Service

### Using systemd (Linux)

Create a service file at `/etc/systemd/system/youtube-bluesky.service`:

```ini
[Unit]
Description=YouTube to Bluesky Auto-Poster
After=network.target

[Service]
Type=simple
User=yourusername
WorkingDirectory=/path/to/script
ExecStart=/usr/bin/python3 /path/to/script/youtube_to_bluesky.py --config /path/to/config.yaml
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start the service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable youtube-bluesky
sudo systemctl start youtube-bluesky
```

Check the status:

```bash
sudo systemctl status youtube-bluesky
```

View logs:

```bash
journalctl -u youtube-bluesky -f
```

### Using screen (Linux)

```bash
screen -S youtube-bluesky
python youtube_to_bluesky.py
# Press Ctrl+A, then D to detach
```

Reattach with:
```bash
screen -r youtube-bluesky
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

### Checking Logs

The script outputs timestamped logs to the console. For persistent logging with systemd:

```bash
journalctl -u youtube-bluesky --since "1 hour ago"
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
