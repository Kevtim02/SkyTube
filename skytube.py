#!/usr/bin/env python3
"""
YouTube to Bluesky Auto-Poster
==============================
This script monitors a YouTube channel's RSS feed (or YouTube API) for new videos
and automatically posts about them on Bluesky with a rich preview card.

Requirements (install with pip):
    pip install feedparser atproto requests pyyaml

Usage:
    Normal mode (monitor and post):
        python youtube_to_bluesky.py
        python youtube_to_bluesky.py --config /path/to/config.yaml
    
    Use YouTube API instead of RSS feed:
        python youtube_to_bluesky.py --use-api
    
    Build database mode (register videos without posting):
        python youtube_to_bluesky.py --build-db
        python youtube_to_bluesky.py --config /path/to/config.yaml --build-db
"""

# ============================================================
# IMPORTS - These are external libraries we need
# ============================================================

import feedparser      # Parses RSS/Atom feeds (pip install feedparser)
import time            # For sleeping between checks
import os              # For file path operations
import json            # For saving/loading seen videos
import requests        # For downloading thumbnails (pip install requests)
import argparse        # For parsing command line arguments (built-in)
import yaml            # For parsing YAML config files (pip install pyyaml)
import sys             # For exiting the script with exit codes
from datetime import datetime  # For timestamps in logs

# The Bluesky/AT Protocol library (pip install atproto)
# Client: handles authentication and API calls
# models: contains data structures for embeds, posts, etc.
from atproto import Client, models


# ============================================================
# ANSI COLOR CODES - For colored terminal output
# ============================================================

class Colors:
    """
    ANSI escape codes for colored terminal output.
    
    These codes work on most Unix terminals (Linux, macOS) and modern
    Windows terminals. They change the text color when printed.
    
    Usage:
        print(f"{Colors.RED}This is red{Colors.RESET}")
    
    Note: Always use RESET after colored text to return to default color.
    """
    RED = '\033[91m'       # Bright red for errors
    GREEN = '\033[92m'     # Bright green for success
    YELLOW = '\033[93m'    # Yellow for warnings
    BLUE = '\033[94m'      # Blue for info
    MAGENTA = '\033[95m'   # Magenta for highlights
    CYAN = '\033[96m'      # Cyan for prompts
    RESET = '\033[0m'      # Reset to default terminal color
    BOLD = '\033[1m'       # Bold text (can combine with colors)


# ============================================================
# EXAMPLE CONFIGURATION - Used when creating a new config file
# ============================================================

# This is the template for creating a new config.yaml file
# It includes helpful comments to guide the user
EXAMPLE_CONFIG = """# YouTube to Bluesky Auto-Poster Configuration
# =============================================

# Your YouTube channel ID (find it in the channel URL after /channel/)
# Example: "UCxxxxxxxxxxxxxxxx"
youtube_channel_id: "YOUR_CHANNEL_ID_HERE"

# Your Bluesky credentials
# TIP: Use an "App Password" from Bluesky settings, not your main password!
bluesky_handle: "yourhandle.bsky.social"
bluesky_password: "your-app-password-here"

# The message template for your Bluesky post
# {title} will be replaced with the video title
post_template: "🎬 New video: {title}"

# How often to check for new videos (in seconds)
# 300 = 5 minutes, 600 = 10 minutes, 900 = 15 minutes
check_interval_seconds: 600

# File to store which videos we've already posted about
# This prevents duplicate posts if the script restarts
seen_videos_file: "youtube_bluesky_seen.json"

# =============================================
# YouTube API Configuration (Optional)
# =============================================
# If you want to use the YouTube Data API instead of RSS feed,
# you need to provide an API key. Get one from:
# https://console.cloud.google.com/apis/credentials
# 
# Then run the script with --use-api flag:
#   python youtube_to_bluesky.py --use-api
#
# youtube_api_key: "YOUR_YOUTUBE_API_KEY_HERE"

# Maximum number of videos to fetch per API request (1-50)
# Only used when --use-api is enabled
# api_max_results: 15
"""

# Global config variable that stores the loaded configuration
# Declared here so all functions can access it
# Will be populated in main() after loading the config file
config = {}

# Global variable to track whether to use YouTube API
# Set by command line argument --use-api
use_youtube_api = False


# ============================================================
# HELPER FUNCTIONS - Reusable pieces of code
# ============================================================

def log_message(message, color=None):
    """
    Prints a message with a timestamp and optional color.
    
    Args:
        message: The text to print
        color: Optional ANSI color code (from Colors class)
    """
    # Get current date/time in a readable format
    # Format: YYYY-MM-DD HH:MM:SS (e.g., 2026-01-15 18:30:45)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # If a color was specified, wrap the message with color codes
    if color:
        # Color code + message + reset code to restore default color
        print(f"{color}[{timestamp}] {message}{Colors.RESET}")
    else:
        # No color, just print the timestamped message
        print(f"[{timestamp}] {message}")


def log_error(message):
    """
    Prints an error message in red.
    Wrapper around log_message for convenience.
    
    Args:
        message: The error text to print
    """
    log_message(message, Colors.RED)


def log_success(message):
    """
    Prints a success message in green.
    Wrapper around log_message for convenience.
    
    Args:
        message: The success text to print
    """
    log_message(message, Colors.GREEN)


def log_warning(message):
    """
    Prints a warning message in yellow.
    Wrapper around log_message for convenience.
    
    Args:
        message: The warning text to print
    """
    log_message(message, Colors.YELLOW)


def create_example_config(config_path):
    """
    Creates an example configuration file at the specified path.
    
    This function writes the EXAMPLE_CONFIG template to a file,
    giving users a starting point for their configuration.
    
    Args:
        config_path: Path where the config file should be created
        
    Returns:
        True if file was created successfully, False otherwise
    """
    try:
        # Open file in write mode ("w") - creates file if it doesn't exist
        # If file exists, it will be overwritten
        with open(config_path, "w") as f:
            # Write the example configuration template
            f.write(EXAMPLE_CONFIG)
        return True
    except Exception as e:
        # Handle any errors (permission denied, disk full, etc.)
        log_error(f"Failed to create config file: {e}")
        return False


def load_config(config_path):
    """
    Loads configuration from a YAML file.
    If the file doesn't exist, prompts the user to create an example file.
    
    Args:
        config_path: Path to the config.yaml file
        
    Returns:
        Dictionary containing configuration values, or None if config not found
    """
    # First, check if the config file exists
    if not os.path.exists(config_path):
        # ==========================================
        # Config file not found - show error prompt
        # ==========================================
        
        # Display a prominent red error message with a border
        print()
        print(f"{Colors.RED}{Colors.BOLD}{'=' * 60}{Colors.RESET}")
        print(f"{Colors.RED}{Colors.BOLD}  ERROR: Configuration file not found!{Colors.RESET}")
        print(f"{Colors.RED}{Colors.BOLD}{'=' * 60}{Colors.RESET}")
        print()
        print(f"{Colors.RED}  Could not find: {config_path}{Colors.RESET}")
        print()
        
        # Offer to create an example config file for the user
        print(f"{Colors.CYAN}Would you like to create an example configuration file?{Colors.RESET}")
        print(f"{Colors.CYAN}This will create: {config_path}{Colors.RESET}")
        print()
        
        # Input loop - keep asking until we get a valid yes/no response
        while True:
            try:
                # Get user input, strip whitespace, convert to lowercase
                response = input(f"{Colors.BOLD}Create example config? (yes/no): {Colors.RESET}").strip().lower()
            except KeyboardInterrupt:
                # User pressed Ctrl+C to cancel
                print()  # New line after ^C
                log_warning("Cancelled by user")
                return None
            
            # Handle "yes" response
            if response in ["yes", "y"]:
                # Try to create the example config file
                if create_example_config(config_path):
                    # Success! Show instructions for next steps
                    print()
                    log_success(f"Example configuration file created: {config_path}")
                    print()
                    print(f"{Colors.YELLOW}Please edit the config file with your settings:{Colors.RESET}")
                    print(f"{Colors.YELLOW}  1. Add your YouTube channel ID{Colors.RESET}")
                    print(f"{Colors.YELLOW}  2. Add your Bluesky handle{Colors.RESET}")
                    print(f"{Colors.YELLOW}  3. Add your Bluesky app password{Colors.RESET}")
                    print(f"{Colors.YELLOW}  4. (Optional) Add YouTube API key for --use-api mode{Colors.RESET}")
                    print()
                    print(f"{Colors.CYAN}Then run the script again.{Colors.RESET}")
                # Return None to indicate we should exit (user needs to edit config)
                return None
            
            # Handle "no" response
            elif response in ["no", "n"]:
                log_warning("No config file created. Exiting.")
                return None
            
            # Handle invalid input
            else:
                print(f"{Colors.YELLOW}Please enter 'yes' or 'no'{Colors.RESET}")
    
    # ==========================================
    # Config file exists - load and parse it
    # ==========================================
    
    log_message(f"Loading config from: {config_path}")
    try:
        # Open file in read mode ("r")
        with open(config_path, "r") as f:
            # yaml.safe_load parses YAML safely (no code execution)
            # This is preferred over yaml.load for security
            user_config = yaml.safe_load(f)
            
            # Handle edge case: empty config file
            if user_config is None:
                log_warning("Config file is empty")
                return {}
            
            # Return the parsed configuration dictionary
            return user_config
    
    # Handle YAML syntax errors (invalid formatting)
    except yaml.YAMLError as e:
        log_error(f"Error parsing YAML config file: {e}")
        return None
    # Handle other errors (permission denied, file locked, etc.)
    except Exception as e:
        log_error(f"Error loading config file: {e}")
        return None


def validate_config(config, require_api_key=False):
    """
    Validates that required configuration values are set.
    
    Checks that essential fields are present and don't contain
    placeholder values from the example config.
    
    Args:
        config: The configuration dictionary
        require_api_key: If True, also validates youtube_api_key is present
        
    Returns:
        True if valid, False otherwise
    """
    # List of fields that must be set for the script to work
    required_fields = ["youtube_channel_id", "bluesky_handle", "bluesky_password"]
    
    # Track which fields are missing or invalid
    missing = []
    
    # Check each required field
    for field in required_fields:
        # Get the value, defaulting to empty string if not found
        value = config.get(field, "")
        
        # Check if field is missing, empty, or still has the placeholder value
        # Placeholder values are from the EXAMPLE_CONFIG template
        if not value or value in ["YOUR_CHANNEL_ID_HERE", "yourhandle.bsky.social", "your-app-password-here"]:
            missing.append(field)
    
    # If API key is required, check for it
    if require_api_key:
        api_key = config.get("youtube_api_key", "")
        if not api_key or api_key == "YOUR_YOUTUBE_API_KEY_HERE":
            missing.append("youtube_api_key")
    
    # If any fields are missing, show an error and return False
    if missing:
        # Display a prominent error message
        print()
        print(f"{Colors.RED}{Colors.BOLD}{'=' * 60}{Colors.RESET}")
        print(f"{Colors.RED}{Colors.BOLD}  ERROR: Missing or invalid configuration!{Colors.RESET}")
        print(f"{Colors.RED}{Colors.BOLD}{'=' * 60}{Colors.RESET}")
        print()
        print(f"{Colors.RED}  Please set the following values in your config file:{Colors.RESET}")
        # List each missing field
        for field in missing:
            print(f"{Colors.RED}    - {field}{Colors.RESET}")
        print()
        
        # If API key is missing, provide additional help
        if "youtube_api_key" in missing:
            print(f"{Colors.YELLOW}  To get a YouTube API key:{Colors.RESET}")
            print(f"{Colors.YELLOW}    1. Go to https://console.cloud.google.com/apis/credentials{Colors.RESET}")
            print(f"{Colors.YELLOW}    2. Create a new project (or select existing){Colors.RESET}")
            print(f"{Colors.YELLOW}    3. Enable the 'YouTube Data API v3'{Colors.RESET}")
            print(f"{Colors.YELLOW}    4. Create an API key under 'Credentials'{Colors.RESET}")
            print()
        
        return False
    
    # All required fields are present and valid
    return True


def load_seen_videos():
    """
    Loads the list of video IDs we've already posted about.
    This data is stored in a JSON file so it survives restarts.
    
    Returns:
        A set of video ID strings we've already seen
    """
    # Get the path to the seen videos file from config
    # Default to "youtube_bluesky_seen.json" if not specified
    seen_file = config.get("seen_videos_file", "youtube_bluesky_seen.json")
    
    # Check if the file exists
    if os.path.exists(seen_file):
        # Open and read the file
        with open(seen_file, "r") as f:
            # json.load converts JSON text back to Python data
            # We convert the list to a set for faster lookups
            return set(json.load(f))
    else:
        # No file yet - this is a fresh start, return empty set
        return set()


def save_seen_videos(seen_videos):
    """
    Saves the list of seen video IDs to a file.
    
    This persists the data so the script remembers which videos
    have already been posted, even after restarts.
    
    Args:
        seen_videos: A set of video ID strings
    """
    # Get the path to the seen videos file from config
    seen_file = config.get("seen_videos_file", "youtube_bluesky_seen.json")
    
    # Open file for writing (creates it if it doesn't exist)
    with open(seen_file, "w") as f:
        # Convert set to list (JSON doesn't support sets)
        # then write it to the file
        json.dump(list(seen_videos), f)


def get_youtube_feed():
    """
    Fetches and parses the YouTube channel's RSS feed.
    
    YouTube provides RSS feeds for every channel at a predictable URL.
    This function fetches the feed and parses it into a list of video entries.
    
    Returns:
        A list of video entries from the feed, or empty list on error
    """
    # Get the YouTube channel ID from config
    channel_id = config.get("youtube_channel_id", "")
    
    # Construct the RSS feed URL
    # YouTube provides RSS feeds at this URL format
    feed_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    
    log_message(f"Fetching RSS feed: {feed_url}")
    
    # Use feedparser to fetch and parse the RSS/Atom feed
    # feedparser handles all the complexity of parsing different feed formats
    feed = feedparser.parse(feed_url)
    
    # Check if parsing was successful
    # 'bozo' is True if there was a parsing error (feedparser terminology)
    if feed.bozo:
        log_warning(f"Feed parsing issue - {feed.bozo_exception}")
    
    # Return the list of video entries
    # Each entry contains: title, link, id, published date, etc.
    return feed.entries


def get_youtube_feed_api():
    """
    Fetches videos using the YouTube Data API instead of RSS.
    
    This function uses the YouTube Data API v3 to fetch the channel's
    uploaded videos. This method is more reliable than RSS and provides
    more detailed information, but requires an API key.
    
    The uploads playlist ID is derived from the channel ID by replacing
    the "UC" prefix with "UU".
    
    Uses pagination to fetch more than 50 videos when api_max_results
    is set higher than 50 in the config.
    
    Returns:
        A list of video entries (same format as RSS for compatibility),
        or empty list on error
    """
    # Get configuration values
    channel_id = config.get("youtube_channel_id", "")
    api_key = config.get("youtube_api_key", "")
    max_results = config.get("api_max_results", 15)
    
    # Validate we have an API key
    if not api_key:
        log_error("YouTube API key not configured. Add 'youtube_api_key' to config.yaml")
        return []
    
    # Convert channel ID to uploads playlist ID
    # YouTube channels with ID "UCxxxxxxxx" have an uploads playlist "UUxxxxxxxx"
    # This is a documented behavior of the YouTube Data API
    if channel_id.startswith("UC"):
        uploads_playlist_id = "UU" + channel_id[2:]
    else:
        log_error(f"Invalid channel ID format: {channel_id}")
        log_error("Channel ID should start with 'UC' (e.g., 'UCxxxxxxxxxxxxxxxx')")
        return []
    
    log_message(f"Fetching videos via YouTube API for playlist: {uploads_playlist_id}")
    log_message(f"Requesting up to {max_results} videos...")
    
    # List to store all video entries across all pages
    all_entries = []
    
    # Token for pagination - None for first request
    next_page_token = None
    
    # API endpoint URL
    url = "https://www.googleapis.com/youtube/v3/playlistItems"
    
    try:
        # Loop to handle pagination
        # Continue fetching until we have enough videos or no more pages
        while len(all_entries) < max_results:
            # Calculate how many more videos we need
            remaining = max_results - len(all_entries)
            
            # API maximum per request is 50
            per_page = min(remaining, 50)
            
            # Build the API request parameters
            params = {
                "part": "snippet,contentDetails",
                "playlistId": uploads_playlist_id,
                "maxResults": per_page,
                "key": api_key
            }
            
            # Add page token if we're fetching subsequent pages
            if next_page_token:
                params["pageToken"] = next_page_token
                log_message(f"Fetching next page of results...")
            
            # Make the API request
            response = requests.get(url, params=params, timeout=30)
            
            # Check for HTTP errors
            if response.status_code == 403:
                log_error("API request forbidden. Check that:")
                log_error("  1. Your API key is valid")
                log_error("  2. YouTube Data API v3 is enabled in your Google Cloud project")
                log_error("  3. You haven't exceeded your API quota")
                return all_entries if all_entries else []
            elif response.status_code == 404:
                log_error(f"Playlist not found. Check that channel ID '{channel_id}' is correct")
                return all_entries if all_entries else []
            
            response.raise_for_status()  # Raise exception for other HTTP errors
            
            # Parse the JSON response
            data = response.json()
            
            # Check for API errors in the response
            if "error" in data:
                error_msg = data["error"].get("message", "Unknown API error")
                log_error(f"YouTube API error: {error_msg}")
                return all_entries if all_entries else []
            
            # Process items from this page
            items = data.get("items", [])
            
            if not items:
                # No more items available
                log_message("No more videos available from API")
                break
            
            # Convert API response to the same format as RSS entries
            for item in items:
                snippet = item.get("snippet", {})
                content_details = item.get("contentDetails", {})
                
                # Get the video ID - try multiple locations
                video_id = content_details.get("videoId") or \
                           snippet.get("resourceId", {}).get("videoId", "")
                
                if not video_id:
                    continue  # Skip items without a video ID
                
                # Build an entry object compatible with feedparser format
                entry = {
                    "yt_videoid": video_id,
                    "id": video_id,
                    "title": snippet.get("title", "Unknown Title"),
                    "link": f"https://www.youtube.com/watch?v={video_id}",
                    "published": snippet.get("publishedAt", ""),
                    "description": snippet.get("description", ""),
                }
                all_entries.append(entry)
            
            log_message(f"Fetched {len(items)} videos (total: {len(all_entries)})")
            
            # Get the next page token for pagination
            next_page_token = data.get("nextPageToken")
            
            # If there's no next page token, we've fetched all available videos
            if not next_page_token:
                log_message("Reached end of playlist")
                break
            
            # Small delay between API requests to be respectful of rate limits
            time.sleep(0.5)
        
        log_success(f"YouTube API returned {len(all_entries)} videos total")
        return all_entries
        
    except requests.exceptions.Timeout:
        log_error("YouTube API request timed out")
        return all_entries if all_entries else []
    except requests.exceptions.RequestException as e:
        log_error(f"YouTube API request failed: {e}")
        return all_entries if all_entries else []
    except json.JSONDecodeError as e:
        log_error(f"Failed to parse YouTube API response: {e}")
        return all_entries if all_entries else []
    except Exception as e:
        log_error(f"Unexpected error fetching from YouTube API: {e}")
        return all_entries if all_entries else []


def get_videos():
    """
    Fetches videos from YouTube using either RSS or API based on configuration.
    
    This is a wrapper function that delegates to either get_youtube_feed()
    or get_youtube_feed_api() based on the --use-api flag.
    
    Returns:
        A list of video entries from the feed/API, or empty list on error
    """
    if use_youtube_api:
        return get_youtube_feed_api()
    else:
        return get_youtube_feed()


def extract_video_id(video_url):
    """
    Extracts the YouTube video ID from a URL.
    
    Handles both standard YouTube URLs and shortened youtu.be URLs:
    - https://www.youtube.com/watch?v=VIDEO_ID
    - https://youtu.be/VIDEO_ID
    
    Args:
        video_url: The full YouTube URL
        
    Returns:
        The video ID string (11 characters), or None if not found
    """
    video_id = None
    
    # Handle standard youtube.com/watch?v=VIDEO_ID format
    # Example: https://www.youtube.com/watch?v=dQw4w9WgXcQ
    if "v=" in video_url:
        # Split on "v=" and take the part after it
        # Then split on "&" to remove any additional parameters
        video_id = video_url.split("v=")[1].split("&")[0]
    
    # Handle shortened youtu.be/VIDEO_ID format
    # Example: https://youtu.be/dQw4w9WgXcQ
    elif "youtu.be/" in video_url:
        # Split on "youtu.be/" and take the part after it
        # Then split on "?" to remove any query parameters
        video_id = video_url.split("youtu.be/")[1].split("?")[0]
    
    return video_id


def get_video_thumbnail(client, video_url):
    """
    Downloads a YouTube video thumbnail and uploads it to Bluesky.
    
    YouTube provides thumbnails at predictable URLs based on video ID.
    This function tries multiple thumbnail qualities (highest first)
    and uploads the successful one to Bluesky.
    
    Args:
        client: The authenticated Bluesky client
        video_url: The YouTube video URL
        
    Returns:
        The uploaded blob object, or None if failed
    """
    # First, extract the video ID from the URL
    video_id = extract_video_id(video_url)
    
    # If we couldn't extract the video ID, we can't get the thumbnail
    if not video_id:
        log_warning("Could not extract video ID from URL")
        return None
    
    # YouTube provides thumbnails at predictable URLs in different sizes
    # We try the highest quality first, then fall back to lower qualities
    # maxresdefault: 1280x720 (not always available)
    # hqdefault: 480x360
    # mqdefault: 320x180
    thumbnail_urls = [
        f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg",
        f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg",
        f"https://img.youtube.com/vi/{video_id}/mqdefault.jpg",
    ]
    
    # Try each thumbnail URL until one works
    for thumb_url in thumbnail_urls:
        try:
            log_message(f"Downloading thumbnail: {thumb_url}")
            
            # Download the image with a 10-second timeout
            response = requests.get(thumb_url, timeout=10)
            # Raise an exception for HTTP errors (4xx, 5xx)
            response.raise_for_status()
            
            # Check if we got a valid image
            # maxresdefault sometimes returns a small placeholder if not available
            # Valid thumbnails are larger than 1KB
            if len(response.content) > 1000:
                # Upload the image to Bluesky
                # upload_blob returns an object with a 'blob' attribute
                upload_response = client.upload_blob(response.content)
                log_success("Thumbnail uploaded successfully")
                # Return the blob reference (used in the embed)
                return upload_response.blob
                
        except Exception as e:
            # This thumbnail quality failed, try the next one
            log_warning(f"Thumbnail download failed for {thumb_url}: {e}")
            continue
    
    # All thumbnail attempts failed
    log_warning("All thumbnail attempts failed")
    return None


def post_to_bluesky(video_title, video_url):
    """
    Creates a post on Bluesky with a rich link preview card.
    
    This function:
    1. Logs into Bluesky using credentials from config
    2. Downloads the video thumbnail from YouTube
    3. Uploads the thumbnail to Bluesky
    4. Creates a post with an embed card (link preview)
    
    Args:
        video_title: The title of the YouTube video
        video_url: The URL to the video
        
    Returns:
        True if posting succeeded, False otherwise
    """
    try:
        # Create a new Bluesky client instance
        client = Client()
        
        # Get credentials and settings from config
        handle = config.get("bluesky_handle", "")
        password = config.get("bluesky_password", "")
        post_template = config.get("post_template", "🎬 New video: {title}")
        
        # Log in to Bluesky account
        log_message(f"Logging in to Bluesky as {handle}...")
        client.login(handle, password)
        
        # Build the post text using the template from config
        # {title} and {url} are replaced with actual values
        post_text = post_template.format(title=video_title, url=video_url)
        
        # ==============================================
        # Download and upload the video thumbnail
        # ==============================================
        
        # Get the thumbnail blob (or None if it failed)
        thumb_blob = get_video_thumbnail(client, video_url)
        
        # ==============================================
        # Create the embed card (link preview)
        # ==============================================
        
        # Build the parameters for the external embed
        # This creates the "link card" that shows below the post
        external_params = {
            "uri": video_url,                    # The link URL
            "title": video_title,                # Title shown on the card
            "description": "Watch on YouTube",   # Description text
        }
        
        # Only add thumbnail if we successfully uploaded one
        # Posts without thumbnails still work, just without an image
        if thumb_blob:
            external_params["thumb"] = thumb_blob
        
        # Create the embed object using the AT Protocol models
        # AppBskyEmbedExternal is the type for external link embeds
        embed = models.AppBskyEmbedExternal.Main(
            external=models.AppBskyEmbedExternal.External(**external_params)
        )
        
        # ==============================================
        # Send the post with the embed card
        # ==============================================
        
        # send_post creates the post on Bluesky
        # text: the post content, embed: the link preview card
        client.send_post(text=post_text, embed=embed)
        
        log_success(f"✓ Posted successfully with preview: {video_title}")
        return True
        
    except Exception as e:
        # Something went wrong - log the error
        # Common errors: invalid credentials, rate limiting, network issues
        log_error(f"✗ Error posting to Bluesky: {e}")
        return False


def build_database():
    """
    Database building mode: Registers all current videos in the JSON file
    without posting to Bluesky.
    
    This is useful for:
    - Initial setup (so only future videos get posted)
    - Recovering from a lost database file
    - Adding the script to an existing channel
    
    The function fetches all videos from the RSS feed (or API) and marks them
    as "seen" without actually posting to Bluesky.
    """
    # Display header for database build mode
    log_message("=" * 50)
    log_message("DATABASE BUILD MODE", Colors.CYAN)
    if use_youtube_api:
        log_message("Using YouTube Data API to fetch videos...")
    else:
        log_message("Using RSS feed to fetch videos...")
    log_message("Registering all current videos without posting...")
    log_message("=" * 50)
    
    # Load existing seen videos (if any exist from a previous run)
    seen_videos = load_seen_videos()
    initial_count = len(seen_videos)
    log_message(f"Currently {initial_count} videos in database")
    
    # Fetch all videos from YouTube (RSS or API based on flag)
    entries = get_videos()
    
    # Check if we got any videos
    if not entries:
        log_warning("No entries found in feed")
        return
    
    log_message(f"Found {len(entries)} videos in feed")
    
    # Process each video entry
    new_count = 0
    for entry in entries:
        # Extract the video ID from the entry
        # YouTube RSS uses 'yt_videoid' or falls back to 'id'
        video_id = entry.get("yt_videoid", entry.get("id", ""))
        video_title = entry.get("title", "Unknown")
        
        # Check if this video is new to us
        if video_id and video_id not in seen_videos:
            # Add to our set of seen videos
            seen_videos.add(video_id)
            new_count += 1
            log_success(f"  ✓ Registered: {video_title}")
        else:
            # Already in database
            log_message(f"  - Already known: {video_title}")
    
    # Save the updated database to disk
    save_seen_videos(seen_videos)
    
    # Display summary
    log_message("=" * 50)
    log_success(f"Database build complete!")
    log_message(f"  - Previously known: {initial_count} videos")
    log_message(f"  - Newly registered: {new_count} videos")
    log_message(f"  - Total in database: {len(seen_videos)} videos")
    log_message("=" * 50)
    log_message("You can now run the script normally to post only NEW videos.", Colors.CYAN)


def check_for_new_videos(seen_videos):
    """
    Checks the YouTube feed for new videos and posts them to Bluesky.
    
    This is the main monitoring function that:
    1. Fetches the latest videos from the RSS feed (or API)
    2. Compares them against our database of seen videos
    3. Posts any new videos to Bluesky
    4. Updates the database
    
    Args:
        seen_videos: Set of video IDs we've already posted about
        
    Returns:
        Updated set of seen video IDs
    """
    # Fetch the latest videos from YouTube (RSS or API based on flag)
    entries = get_videos()
    
    # Check if we got any videos
    if not entries:
        log_warning("No entries found in feed")
        return seen_videos
    
    log_message(f"Found {len(entries)} videos in feed")
    
    # Process each video in the feed
    for entry in entries:
        # Extract the video ID from the entry
        # YouTube RSS entries have various ID formats
        video_id = entry.get("yt_videoid", entry.get("id", ""))
        
        # Get video details for posting
        video_title = entry.get("title", "New Video")
        video_url = entry.get("link", "")
        
        # Skip if we've already posted about this video
        if video_id in seen_videos:
            continue
        
        # This is a new video - highlight it
        log_message(f"New video found: {video_title}", Colors.MAGENTA)
        
        # Attempt to post to Bluesky
        if post_to_bluesky(video_title, video_url):
            # Success! Add to our database so we don't post again
            seen_videos.add(video_id)
            # Save immediately in case the script crashes later
            save_seen_videos(seen_videos)
        
        # Wait between posts to avoid rate limiting
        # Bluesky has rate limits on how fast you can post
        time.sleep(2)
    
    # Return the updated set of seen videos
    return seen_videos


def parse_arguments():
    """
    Parses command line arguments.
    
    Supported arguments:
        --config, -c: Path to the configuration YAML file
        --build-db: Build the database without posting
        --use-api: Use YouTube Data API instead of RSS feed
    
    Returns:
        The parsed arguments object (argparse.Namespace)
    """
    # Create argument parser with description
    parser = argparse.ArgumentParser(
        description="YouTube to Bluesky Auto-Poster",
        # RawDescriptionHelpFormatter preserves formatting in epilog
        formatter_class=argparse.RawDescriptionHelpFormatter,
        # Examples shown at the bottom of --help output
        epilog="""
Examples:
  python youtube_to_bluesky.py                              # Uses config.yaml in same directory
  python youtube_to_bluesky.py --config /path/to/config.yaml
  python youtube_to_bluesky.py --use-api                    # Use YouTube Data API instead of RSS
  python youtube_to_bluesky.py --build-db                   # Build database without posting
  python youtube_to_bluesky.py --use-api --build-db         # Build database using API
  python youtube_to_bluesky.py --config myconfig.yaml --build-db
        """
    )
    
    # --config / -c argument: specify config file path
    parser.add_argument(
        "--config", "-c",
        type=str,
        default="config.yaml",
        help="Path to the configuration YAML file (default: config.yaml)"
    )
    
    # --build-db flag: enable database building mode
    # action="store_true" means: if flag is present, value is True
    parser.add_argument(
        "--build-db",
        action="store_true",
        help="Build/rebuild the database of seen videos without posting. "
             "Useful for initializing the script so only future videos get posted."
    )
    
    # --use-api flag: use YouTube Data API instead of RSS feed
    parser.add_argument(
        "--use-api",
        action="store_true",
        help="Use YouTube Data API instead of RSS feed. "
             "Requires 'youtube_api_key' to be set in config file. "
             "More reliable than RSS but requires API quota."
    )
    
    # Parse and return the arguments
    return parser.parse_args()


# ============================================================
# MAIN LOOP - This is where the script starts running
# ============================================================

def main():
    """
    Main function that handles different modes based on command line arguments.
    
    This function:
    1. Parses command line arguments
    2. Loads and validates configuration
    3. Either builds the database (--build-db) or starts monitoring
    """
    # Declare that we want to modify the global variables
    global config
    global use_youtube_api
    
    # Parse command line arguments (--config, --build-db, --use-api)
    args = parse_arguments()
    
    # Set global flag for API usage
    use_youtube_api = args.use_api
    
    # Load configuration from the YAML file
    loaded_config = load_config(args.config)
    
    # If config loading failed or was cancelled, exit with error code
    if loaded_config is None:
        sys.exit(1)  # Exit code 1 indicates an error
    
    # Store the loaded config in the global variable
    config = loaded_config
    
    # Validate configuration based on the mode we're running in
    if args.build_db:
        # For database building, we only need the YouTube channel ID
        # (and API key if using --use-api)
        if not config.get("youtube_channel_id") or config.get("youtube_channel_id") == "YOUR_CHANNEL_ID_HERE":
            log_error("youtube_channel_id is required in config file")
            sys.exit(1)
        
        # If using API mode, also validate API key
        if use_youtube_api:
            api_key = config.get("youtube_api_key", "")
            if not api_key or api_key == "YOUR_YOUTUBE_API_KEY_HERE":
                log_error("youtube_api_key is required when using --use-api flag")
                print()
                print(f"{Colors.YELLOW}  To get a YouTube API key:{Colors.RESET}")
                print(f"{Colors.YELLOW}    1. Go to https://console.cloud.google.com/apis/credentials{Colors.RESET}")
                print(f"{Colors.YELLOW}    2. Create a new project (or select existing){Colors.RESET}")
                print(f"{Colors.YELLOW}    3. Enable the 'YouTube Data API v3'{Colors.RESET}")
                print(f"{Colors.YELLOW}    4. Create an API key under 'Credentials'{Colors.RESET}")
                print()
                sys.exit(1)
    else:
        # For normal operation, we need all credentials
        # Pass require_api_key=True if using API mode
        if not validate_config(config, require_api_key=use_youtube_api):
            sys.exit(1)
    
    # Check if we're in database building mode
    if args.build_db:
        # Run database build and exit
        build_database()
        return  # Exit after building database
    
    # ==========================================
    # Normal mode: continuous monitoring loop
    # ==========================================
    
    # Display startup banner
    log_message("=" * 50)
    log_message("YouTube to Bluesky Auto-Poster starting...", Colors.CYAN)
    log_message(f"Monitoring channel: {config.get('youtube_channel_id')}")
    if use_youtube_api:
        log_message("Video source: YouTube Data API", Colors.BLUE)
    else:
        log_message("Video source: RSS Feed", Colors.BLUE)
    log_message(f"Check interval: {config.get('check_interval_seconds', 600)} seconds")
    log_message("=" * 50)
    
    # Load any previously seen videos from the database
    seen_videos = load_seen_videos()
    log_message(f"Loaded {len(seen_videos)} previously seen videos")
    
    # Main monitoring loop - runs forever until script is stopped
    while True:
        try:
            # Check for new videos and post them
            seen_videos = check_for_new_videos(seen_videos)
            
        except Exception as e:
            # Catch any unexpected errors but keep the loop running
            # This prevents the script from crashing on temporary issues
            log_error(f"Error during check: {e}")
        
        # Wait before checking again
        # Get interval from config, default to 600 seconds (10 minutes)
        check_interval = config.get("check_interval_seconds", 600)
        log_message(f"Sleeping for {check_interval} seconds...")
        
        # Sleep until next check
        # time.sleep pauses execution for the specified seconds
        time.sleep(check_interval)


# ============================================================
# SCRIPT ENTRY POINT
# ============================================================

# This is Python's standard way of checking if this file is being
# run directly (not imported as a module)
# 
# When you run: python youtube_to_bluesky.py
#   __name__ is set to "__main__", so main() is called
# 
# When you import: import youtube_to_bluesky
#   __name__ is set to "youtube_to_bluesky", so main() is NOT called
if __name__ == "__main__":
    main()
