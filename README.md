# YouTube to Bluesky Auto-Poster 🎬📢

Automatically monitor your YouTube channel for new videos and post them to Bluesky with rich preview cards.

![Python](https://img.shields.io/badge/Python-3.7+-blue.svg)
![License](https://img.shields.io/badge/License-MIT-green.svg)

## Features

- 🔄 **Automatic Monitoring** - Continuously monitors your YouTube channel's RSS feed for new uploads
- 🖼️ **Rich Preview Cards** - Posts include video thumbnails and proper link embeds
- 💾 **Persistent Database** - Remembers which videos have been posted, survives restarts
- ⚙️ **Easy Configuration** - Simple YAML config file with helpful comments
- 🛡️ **Database Build Mode** - Initialize without posting to avoid duplicate posts
- 🎨 **Colored Output** - Clear, color-coded terminal output for easy monitoring

## Requirements

- Python 3.7 or higher
- A YouTube channel with a Channel ID
- A Bluesky account with an App Password

## Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/yourusername/youtube-to-bluesky.git
   cd youtube-to-bluesky
   ```

2. **Install dependencies:**
   ```bash
   pip install feedparser atproto requests pyyaml
   ```

## Configuration

1. **Run the script for the first time:**
   ```bash
   python youtube_to_bluesky.py
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
   post_template: "🎬 New video: {title}"

   # How often to check for new videos (in seconds)
   check_interval_seconds: 600

   # File to store which videos we've already posted about
   seen_videos_file: "youtube_bluesky_seen.json"
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
python youtube_to_bluesky.py

# Using a custom config file location
python youtube_to_bluesky.py --config /path/to/config.yaml
```

### Build Database Mode

Use this mode when first setting up the script to register existing videos without posting them:

```bash
python youtube_to_bluesky.py --build-db

# With custom config
python youtube_to_bluesky.py --config /path/to/config.yaml --build-db
```

This is useful for:
- Initial setup (so only future videos get posted)
- Recovering from a lost database file
- Adding the script to an existing channel

## Command Line Options

| Option | Short | Description |
|--------|-------|-------------|
| `--config` | `-c` | Path to the configuration YAML file (default: `config.yaml`) |
| `--build-db` | | Build the database of seen videos without posting |

## How It Works

1. **Fetch RSS Feed** - The script fetches your YouTube channel's RSS feed
2. **Check for New Videos** - Compares feed entries against the database of seen videos
3. **Download Thumbnail** - Gets the highest quality thumbnail available
4. **Post to Bluesky** - Creates a post with the video title, link, and thumbnail embed
5. **Update Database** - Marks the video as posted to prevent duplicates
6. **Sleep** - Waits for the configured interval before checking again

## Project Structure

```
youtube-to-bluesky/
├── youtube_to_bluesky.py   # Main script
├── config.yaml             # Your configuration (created on first run)
├── youtube_bluesky_seen.json  # Database of posted videos (auto-generated)
└── README.md               # This file
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

## Running as a Service

For continuous operation, consider running the script as a system service:

### Using systemd (Linux)

Create `/etc/systemd/system/youtube-bluesky.service`:
```ini
[Unit]
Description=YouTube to Bluesky Auto-Poster
After=network.target

[Service]
Type=simple
User=your-username
WorkingDirectory=/path/to/youtube-to-bluesky
ExecStart=/usr/bin/python3 youtube_to_bluesky.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Then enable and start:
```bash
sudo systemctl enable youtube-bluesky
sudo systemctl start youtube-bluesky
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
