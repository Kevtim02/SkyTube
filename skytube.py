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
    
    Enable continuous file logging:
        python youtube_to_bluesky.py --log
        python youtube_to_bluesky.py --log --use-api --build-db
    
    Disable API caching (force fresh data):
        python youtube_to_bluesky.py --use-api --no-cache
        python youtube_to_bluesky.py --log --use-api --no-cache
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
import logging         # For structured logging to console and file (built-in)
from logging.handlers import RotatingFileHandler  # For automatic log rotation
import traceback       # For detailed exception tracebacks in logs (built-in)
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
# LOGGING SETUP - File logger for the --log option
# ============================================================

# The file logger instance, initialized to None
# When --log is passed, this gets configured to write to skytube.log
# All log_message/log_error/log_success/log_warning calls will
# also write to this logger when it is active
file_logger = None

# The log file name, placed in the same directory as the running script
LOG_FILE_NAME = "skytube.log"

# Maximum log file size before rotation (10 MB)
MAX_LOG_SIZE_BYTES = 10 * 1024 * 1024


def setup_file_logging():
    """
    Configures the file logger to write continuously to skytube.log.
    
    The log file is created in the same directory the script runs in.
    Uses RotatingFileHandler which automatically clears the log file when
    it reaches MAX_LOG_SIZE_BYTES (10 MB). When the limit is reached,
    the log is cleared and writing continues from the beginning.
    
    Returns:
        A configured logging.Logger instance writing to skytube.log
    """
    # Determine the directory where the script is being run from
    # os.getcwd() gives the current working directory
    log_file_path = os.path.join(os.getcwd(), LOG_FILE_NAME)

    # Create a named logger specific to this application
    # Using a named logger avoids conflicts with other libraries' loggers
    logger = logging.getLogger("skytube")
    logger.setLevel(logging.DEBUG)

    # Avoid adding duplicate handlers if setup is called more than once
    if logger.handlers:
        return logger

    try:
        # Create a rotating file handler that clears the log when it reaches 10 MB
        # backupCount=0 means no backup files are kept - log is simply cleared
        file_handler = RotatingFileHandler(
            log_file_path, 
            maxBytes=MAX_LOG_SIZE_BYTES, 
            backupCount=0, 
            encoding="utf-8"
        )
        file_handler.setLevel(logging.DEBUG)

        # Define the log format to match the console output style
        # Format: [YYYY-MM-DD HH:MM:SS] [LEVEL] Message
        formatter = logging.Formatter(
            fmt="[%(asctime)s] [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        file_handler.setFormatter(formatter)

        # Attach the handler to our logger
        logger.addHandler(file_handler)

        # Log a startup separator so each run is clearly visible in the file
        logger.info("=" * 60)
        logger.info("SKYTUBE FILE LOGGING STARTED")
        logger.info(f"Log file: {log_file_path}")
        logger.info("=" * 60)

    except PermissionError:
        # Handle case where we cannot write to the log directory
        print(f"{Colors.RED}[ERROR] Permission denied: cannot create log file at {log_file_path}{Colors.RESET}")
        print(f"{Colors.YELLOW}Check that you have write permissions to this directory.{Colors.RESET}")
        sys.exit(1)
    except OSError as e:
        # Handle other OS-level file errors (disk full, invalid path, etc.)
        print(f"{Colors.RED}[ERROR] Failed to create log file at {log_file_path}: {e}{Colors.RESET}")
        sys.exit(1)

    return logger


def _write_to_file_log(level, message):
    """
    Writes a message to the file logger if file logging is enabled.
    
    This is an internal helper called by log_message, log_error, etc.
    It maps our color-based log levels to standard logging levels.
    
    Args:
        level: A string indicating the log level ("DEBUG", "INFO", "WARNING", "ERROR", "SUCCESS")
        message: The message string to log
    """
    # Only write if the file logger has been initialized (--log flag was passed)
    if file_logger is None:
        return

    # Map our custom levels to standard logging levels
    # "SUCCESS" is not a standard level, so we log it as INFO with a prefix
    if level == "ERROR":
        file_logger.error(message)
    elif level == "WARNING":
        file_logger.warning(message)
    elif level == "SUCCESS":
        file_logger.info(f"[SUCCESS] {message}")
    elif level == "DEBUG":
        file_logger.debug(message)
    else:
        # Default to INFO for general messages
        file_logger.info(message)


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

# Global variable to track whether to disable caching
# Set by command line argument --no-cache
no_cache = False


# ============================================================
# HELPER FUNCTIONS - Reusable pieces of code
# ============================================================

def log_message(message, color=None):
    """
    Prints a message with a timestamp and optional color.
    Also writes to the log file if --log is enabled.
    
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

    # Write to file log as a general INFO message
    _write_to_file_log("INFO", message)


def log_error(message):
    """
    Prints an error message in red.
    Also writes to the log file at ERROR level if --log is enabled.
    Wrapper around log_message for convenience.
    
    Args:
        message: The error text to print
    """
    log_message(message, Colors.RED)
    # Additionally write at ERROR level to the file log
    # (log_message already writes at INFO, so we overwrite with ERROR)
    # We call _write_to_file_log directly to ensure the ERROR level is used
    _write_to_file_log("ERROR", message)


def log_success(message):
    """
    Prints a success message in green.
    Also writes to the log file at SUCCESS level if --log is enabled.
    Wrapper around log_message for convenience.
    
    Args:
        message: The success text to print
    """
    log_message(message, Colors.GREEN)
    # Write at SUCCESS level to the file log for easy filtering
    _write_to_file_log("SUCCESS", message)


def log_warning(message):
    """
    Prints a warning message in yellow.
    Also writes to the log file at WARNING level if --log is enabled.
    Wrapper around log_message for convenience.
    
    Args:
        message: The warning text to print
    """
    log_message(message, Colors.YELLOW)
    # Write at WARNING level to the file log
    _write_to_file_log("WARNING", message)


def log_debug(message):
    """
    Writes a debug-level message to the log file only (not printed to console).
    Useful for verbose diagnostic info that would clutter the terminal.
    
    Args:
        message: The debug text to write to the log file
    """
    _write_to_file_log("DEBUG", message)


def log_exception(message, exc):
    """
    Logs an error message along with the full exception traceback.
    The traceback is written to the log file for debugging but only
    a summary is printed to the console to keep output clean.
    
    Args:
        message: A human-readable description of what went wrong
        exc: The exception object that was caught
    """
    # Print the summary to console in red
    log_error(f"{message}: {exc}")

    # Write the full traceback to the log file for detailed debugging
    # traceback.format_exc() returns the full stack trace as a string
    tb = traceback.format_exc()
    if tb and tb.strip() != "NoneType: None":
        _write_to_file_log("ERROR", f"Full traceback for '{message}':\n{tb}")


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
        log_debug(f"Example config file written to: {config_path}")
        return True
    except PermissionError:
        # Handle permission errors specifically for a clearer message
        log_error(f"Permission denied: cannot write config file to {config_path}")
        log_debug(f"Check file/directory permissions for: {config_path}")
        return False
    except OSError as e:
        # Handle OS-level errors (disk full, read-only filesystem, etc.)
        log_exception(f"OS error creating config file at {config_path}", e)
        return False
    except Exception as e:
        # Handle any errors (permission denied, disk full, etc.)
        log_exception(f"Failed to create config file at {config_path}", e)
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
        
        log_debug(f"Config file not found at path: {config_path}")

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
            except EOFError:
                # Handle EOF (e.g., piped input ended unexpectedly)
                print()
                log_warning("Input stream ended unexpectedly (EOF)")
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
    log_debug(f"Config file size: {os.path.getsize(config_path)} bytes")

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
            
            # Validate that the parsed config is a dictionary
            # A YAML file could parse to a string or list if malformed
            if not isinstance(user_config, dict):
                log_error(f"Config file has invalid structure (expected key-value pairs, got {type(user_config).__name__})")
                log_debug(f"Parsed config type: {type(user_config)}, value: {repr(user_config)[:200]}")
                return None

            log_debug(f"Config loaded successfully with {len(user_config)} keys: {list(user_config.keys())}")

            # Return the parsed configuration dictionary
            return user_config
    
    # Handle YAML syntax errors (invalid formatting)
    except yaml.YAMLError as e:
        log_error(f"Error parsing YAML config file: {e}")
        # Provide line/column info if available from the YAML parser
        if hasattr(e, 'problem_mark') and e.problem_mark is not None:
            mark = e.problem_mark
            log_error(f"  YAML syntax error at line {mark.line + 1}, column {mark.column + 1}")
        log_debug(f"YAML parsing error details: {repr(e)}")
        return None
    # Handle permission errors specifically
    except PermissionError:
        log_error(f"Permission denied: cannot read config file at {config_path}")
        return None
    # Handle other errors (permission denied, file locked, etc.)
    except Exception as e:
        log_exception(f"Error loading config file", e)
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

    # Validate check_interval_seconds is a positive number if present
    check_interval = config.get("check_interval_seconds")
    if check_interval is not None:
        if not isinstance(check_interval, (int, float)) or check_interval <= 0:
            log_warning(f"Invalid check_interval_seconds value: {check_interval} (must be a positive number, using default 600)")
            log_debug(f"check_interval_seconds type: {type(check_interval).__name__}, value: {repr(check_interval)}")

    # Validate api_max_results is within the acceptable range if present
    max_results = config.get("api_max_results")
    if max_results is not None:
        if not isinstance(max_results, int) or max_results < 1:
            log_warning(f"Invalid api_max_results value: {max_results} (must be a positive integer, using default 15)")
    
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

        log_debug(f"Config validation failed. Missing fields: {missing}")
        
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
    log_debug("Config validation passed for all required fields")
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
        try:
            # Open and read the file
            with open(seen_file, "r") as f:
                # json.load converts JSON text back to Python data
                # We convert the list to a set for faster lookups
                data = json.load(f)

                # Validate that the loaded data is actually a list
                if not isinstance(data, list):
                    log_warning(f"Seen videos file has unexpected format (expected list, got {type(data).__name__}). Starting fresh.")
                    log_debug(f"Unexpected seen_videos data type: {type(data)}, value preview: {repr(data)[:200]}")
                    return set()

                log_debug(f"Loaded {len(data)} seen video IDs from {seen_file}")
                return set(data)

        except json.JSONDecodeError as e:
            # Handle corrupted or invalid JSON in the seen videos file
            log_error(f"Seen videos file is corrupted (invalid JSON): {e}")
            log_debug(f"JSON decode error in {seen_file}: {repr(e)}")

            # Attempt to back up the corrupted file before starting fresh
            backup_path = seen_file + ".corrupt.bak"
            try:
                os.rename(seen_file, backup_path)
                log_warning(f"Corrupted file backed up to: {backup_path}")
            except OSError as rename_err:
                log_warning(f"Could not back up corrupted file: {rename_err}")

            return set()

        except PermissionError:
            # Handle permission errors reading the seen videos file
            log_error(f"Permission denied: cannot read seen videos file at {seen_file}")
            return set()

        except Exception as e:
            # Handle any other unexpected errors reading the file
            log_exception(f"Unexpected error loading seen videos from {seen_file}", e)
            return set()
    else:
        # No file yet - this is a fresh start, return empty set
        log_debug(f"Seen videos file not found at {seen_file}, starting with empty set")
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
    
    try:
        # Open file for writing (creates it if it doesn't exist)
        with open(seen_file, "w") as f:
            # Convert set to list (JSON doesn't support sets)
            # then write it to the file
            json.dump(list(seen_videos), f)
        log_debug(f"Saved {len(seen_videos)} seen video IDs to {seen_file}")

    except PermissionError:
        # Handle permission errors writing the seen videos file
        log_error(f"Permission denied: cannot write seen videos file to {seen_file}")
        log_error("Video tracking may be lost — duplicate posts could occur on next run!")

    except OSError as e:
        # Handle OS-level errors (disk full, read-only filesystem, etc.)
        log_exception(f"OS error writing seen videos file to {seen_file}", e)
        log_error("Video tracking may be lost — duplicate posts could occur on next run!")

    except Exception as e:
        # Handle any other unexpected errors
        log_exception(f"Unexpected error saving seen videos to {seen_file}", e)
        log_error("Video tracking may be lost — duplicate posts could occur on next run!")


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
    log_debug(f"RSS fetch initiated for channel: {channel_id}")
    
    try:
        # Use feedparser to fetch and parse the RSS/Atom feed
        # feedparser handles all the complexity of parsing different feed formats
        feed = feedparser.parse(feed_url)
    except Exception as e:
        # Handle unexpected errors from feedparser (network issues, malformed XML, etc.)
        log_exception("Failed to fetch or parse RSS feed", e)
        return []
    
    # Check if parsing was successful
    # 'bozo' is True if there was a parsing error (feedparser terminology)
    if feed.bozo:
        log_warning(f"Feed parsing issue - {feed.bozo_exception}")
        log_debug(f"Feed bozo exception type: {type(feed.bozo_exception).__name__}")

    # Check if the feed returned any entries at all
    if not feed.entries:
        log_warning("RSS feed returned no entries")
        # Log HTTP status if available (feedparser stores it in feed.status)
        if hasattr(feed, 'status'):
            log_debug(f"RSS feed HTTP status: {feed.status}")
        # Check if the feed itself has a title (indicates the channel was found)
        if hasattr(feed.feed, 'title'):
            log_debug(f"Feed title: {feed.feed.title}")
        else:
            log_warning("Feed has no title — channel ID may be invalid or the channel has no public videos")
        return []

    log_debug(f"RSS feed returned {len(feed.entries)} entries")
    
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
    
    # Validate max_results is a sane value
    if not isinstance(max_results, int) or max_results < 1:
        log_warning(f"Invalid api_max_results: {max_results}. Falling back to default of 15.")
        max_results = 15

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

    # Counter for API pages fetched (useful for debugging pagination issues)
    page_count = 0
    
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

            page_count += 1
            log_debug(f"API request page {page_count}: maxResults={per_page}, pageToken={next_page_token}")

            # Prepare headers and parameters for the API request
            request_headers = {}

            # Add cache-busting if --no-cache flag is enabled
            if no_cache:
                # Add cache-control headers to prevent caching
                request_headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
                request_headers["Pragma"] = "no-cache"
                request_headers["Expires"] = "0"
                # Add a unique timestamp parameter to bust caches
                params["_nocache"] = str(int(time.time()))
                log_debug(f"Cache-busting enabled: added timestamp {params['_nocache']}")

            # Make the API request
            response = requests.get(url, params=params, headers=request_headers, timeout=30)

            log_debug(f"API response status: {response.status_code}, content-length: {len(response.content)}")
            
            # Check for HTTP errors
            if response.status_code == 403:
                log_error("API request forbidden (HTTP 403). Check that:")
                log_error("  1. Your API key is valid")
                log_error("  2. YouTube Data API v3 is enabled in your Google Cloud project")
                log_error("  3. You haven't exceeded your API quota")
                # Try to extract a more specific error message from the response body
                try:
                    error_body = response.json()
                    error_detail = error_body.get("error", {}).get("message", "")
                    if error_detail:
                        log_error(f"  API error detail: {error_detail}")
                    log_debug(f"Full 403 response body: {json.dumps(error_body, indent=2)}")
                except (json.JSONDecodeError, Exception):
                    log_debug(f"Could not parse 403 response body: {response.text[:500]}")
                return all_entries if all_entries else []

            elif response.status_code == 404:
                log_error(f"Playlist not found (HTTP 404). Check that channel ID '{channel_id}' is correct")
                log_debug(f"404 response for playlist: {uploads_playlist_id}")
                return all_entries if all_entries else []

            elif response.status_code == 400:
                # Bad request - often caused by invalid parameters or API key format
                log_error(f"Bad API request (HTTP 400). The request parameters may be invalid.")
                try:
                    error_body = response.json()
                    error_detail = error_body.get("error", {}).get("message", "")
                    if error_detail:
                        log_error(f"  API error detail: {error_detail}")
                    log_debug(f"Full 400 response body: {json.dumps(error_body, indent=2)}")
                except (json.JSONDecodeError, Exception):
                    log_debug(f"Could not parse 400 response body: {response.text[:500]}")
                return all_entries if all_entries else []

            elif response.status_code == 429:
                # Rate limited by the API
                log_warning("YouTube API rate limit hit (HTTP 429). Waiting before retrying...")
                log_debug("Rate limited. Returning partial results if available.")
                return all_entries if all_entries else []
            
            # Raise exception for other unexpected HTTP errors (5xx, etc.)
            try:
                response.raise_for_status()
            except requests.exceptions.HTTPError as http_err:
                log_error(f"YouTube API returned HTTP {response.status_code}")
                log_exception("HTTP error from YouTube API", http_err)
                return all_entries if all_entries else []
            
            # Parse the JSON response
            data = response.json()
            
            # Check for API errors in the response
            if "error" in data:
                error_msg = data["error"].get("message", "Unknown API error")
                error_code = data["error"].get("code", "N/A")
                log_error(f"YouTube API error (code {error_code}): {error_msg}")
                log_debug(f"Full API error response: {json.dumps(data['error'], indent=2)}")
                return all_entries if all_entries else []
            
            # Process items from this page
            items = data.get("items", [])
            
            if not items:
                # No more items available
                log_message("No more videos available from API")
                break
            
            # Track how many items were skipped on this page (missing video ID)
            skipped_count = 0

            # Convert API response to the same format as RSS entries
            for item in items:
                snippet = item.get("snippet", {})
                content_details = item.get("contentDetails", {})
                
                # Get the video ID - try multiple locations
                video_id = content_details.get("videoId") or \
                           snippet.get("resourceId", {}).get("videoId", "")
                
                if not video_id:
                    skipped_count += 1
                    log_debug(f"Skipped API item with no video ID: {json.dumps(item, indent=2)[:300]}")
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

            if skipped_count > 0:
                log_warning(f"Skipped {skipped_count} items with missing video IDs on page {page_count}")
            
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
        log_error("YouTube API request timed out after 30 seconds")
        log_debug("Consider increasing the timeout or checking network connectivity")
        return all_entries if all_entries else []
    except requests.exceptions.ConnectionError as e:
        # Handle network-level connection failures specifically
        log_error("Could not connect to YouTube API — network may be down")
        log_exception("Connection error to YouTube API", e)
        return all_entries if all_entries else []
    except requests.exceptions.RequestException as e:
        log_exception("YouTube API request failed", e)
        return all_entries if all_entries else []
    except json.JSONDecodeError as e:
        log_error(f"Failed to parse YouTube API response as JSON")
        log_exception("JSON decode error from YouTube API", e)
        return all_entries if all_entries else []
    except Exception as e:
        log_exception("Unexpected error fetching from YouTube API", e)
        return all_entries if all_entries else []


def get_videos():
    """
    Fetches videos from YouTube using either RSS or API based on configuration.
    
    This is a wrapper function that delegates to either get_youtube_feed()
    or get_youtube_feed_api() based on the --use-api flag.
    
    Returns:
        A list of video entries from the feed/API, or empty list on error
    """
    log_debug(f"Fetching videos using {'YouTube API' if use_youtube_api else 'RSS feed'}")
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

    # Log whether extraction succeeded or failed
    if video_id:
        log_debug(f"Extracted video ID '{video_id}' from URL: {video_url}")
    else:
        log_debug(f"Could not extract video ID from URL: {video_url}")
    
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

            log_debug(f"Thumbnail response: status={response.status_code}, size={len(response.content)} bytes")
            
            # Check if we got a valid image
            # maxresdefault sometimes returns a small placeholder if not available
            # Valid thumbnails are larger than 1KB
            if len(response.content) > 1000:
                # Upload the image to Bluesky
                # upload_blob returns an object with a 'blob' attribute
                try:
                    upload_response = client.upload_blob(response.content)
                    log_success("Thumbnail uploaded successfully")
                    log_debug(f"Thumbnail blob uploaded, size: {len(response.content)} bytes")
                    # Return the blob reference (used in the embed)
                    return upload_response.blob
                except Exception as upload_err:
                    # Handle Bluesky upload failures separately from download failures
                    log_exception("Failed to upload thumbnail to Bluesky", upload_err)
                    return None
            else:
                # Image was too small — likely a placeholder, try next quality
                log_debug(f"Thumbnail too small ({len(response.content)} bytes), trying next quality")

        except requests.exceptions.Timeout:
            # Thumbnail download timed out, try next quality
            log_warning(f"Thumbnail download timed out for {thumb_url}")
            continue

        except requests.exceptions.ConnectionError as e:
            # Network-level failure downloading thumbnail
            log_warning(f"Connection error downloading thumbnail from {thumb_url}: {e}")
            continue

        except requests.exceptions.HTTPError as e:
            # HTTP error (4xx, 5xx) downloading thumbnail
            log_warning(f"HTTP error downloading thumbnail from {thumb_url}: {e}")
            continue

        except Exception as e:
            # This thumbnail quality failed, try the next one
            log_warning(f"Thumbnail download failed for {thumb_url}: {e}")
            log_debug(f"Thumbnail exception type: {type(e).__name__}")
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

        # ==========================================
        # Validate credentials before attempting login
        # ==========================================
        if not handle:
            log_error("Bluesky handle is empty — cannot post")
            return False
        if not password:
            log_error("Bluesky password is empty — cannot post")
            return False
        
        # Log in to Bluesky account
        log_message(f"Logging in to Bluesky as {handle}...")

        try:
            client.login(handle, password)
            log_debug(f"Bluesky login successful for handle: {handle}")
        except Exception as login_err:
            # Handle authentication failures specifically
            log_error(f"Bluesky login failed for handle '{handle}'")
            log_exception("Bluesky authentication error", login_err)
            # Provide helpful hints based on common login issues
            err_str = str(login_err).lower()
            if "invalid" in err_str or "authentication" in err_str or "unauthorized" in err_str:
                log_error("  Hint: Check your bluesky_handle and bluesky_password in config.yaml")
                log_error("  Hint: Use an App Password from Bluesky settings, not your main password")
            elif "rate" in err_str or "limit" in err_str:
                log_error("  Hint: You may be rate-limited. Wait a few minutes and try again.")
            elif "network" in err_str or "connection" in err_str or "resolve" in err_str:
                log_error("  Hint: Network error. Check your internet connection.")
            return False
        
        # Build the post text using the template from config
        # {title} and {url} are replaced with actual values
        try:
            post_text = post_template.format(title=video_title, url=video_url)
        except KeyError as fmt_err:
            # Handle invalid placeholders in the template (e.g., {nonexistent})
            log_error(f"Invalid placeholder in post_template: {fmt_err}")
            log_error(f"  Template: {post_template}")
            log_error("  Supported placeholders: {title}, {url}")
            # Fall back to a safe default template
            post_text = f"🎬 New video: {video_title}"
            log_warning(f"Using fallback post text: {post_text}")

        log_debug(f"Post text ({len(post_text)} chars): {post_text}")

        # Check Bluesky post length limit (300 characters as of current AT Protocol)
        if len(post_text) > 300:
            log_warning(f"Post text is {len(post_text)} characters (Bluesky limit is 300). It may be truncated or rejected.")
        
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
        else:
            log_debug("Posting without thumbnail (thumbnail upload failed or was skipped)")
        
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
        log_debug("Sending post to Bluesky...")
        client.send_post(text=post_text, embed=embed)
        
        log_success(f"✓ Posted successfully with preview: {video_title}")
        return True

    except requests.exceptions.ConnectionError as e:
        # Handle network connectivity failures when communicating with Bluesky
        log_error("Network error: could not connect to Bluesky servers")
        log_exception("Bluesky connection error", e)
        return False

    except requests.exceptions.Timeout as e:
        # Handle timeout when communicating with Bluesky
        log_error("Request to Bluesky timed out")
        log_exception("Bluesky timeout", e)
        return False
        
    except Exception as e:
        # Something went wrong - log the error
        # Common errors: invalid credentials, rate limiting, network issues
        log_exception(f"Error posting to Bluesky for video '{video_title}'", e)
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
        elif not video_id:
            # Log a warning if a feed entry has no video ID (shouldn't happen normally)
            log_warning(f"  ⚠ Skipped entry with no video ID: {video_title}")
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
    log_debug("Starting check for new videos...")

    # Fetch the latest videos from YouTube (RSS or API based on flag)
    entries = get_videos()
    
    # Check if we got any videos
    if not entries:
        log_warning("No entries found in feed")
        return seen_videos
    
    log_message(f"Found {len(entries)} videos in feed")
    
    # Track how many new videos were found and posted in this check cycle
    new_found = 0
    post_success = 0
    post_failed = 0

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

        # Skip entries with missing critical data
        if not video_id:
            log_warning(f"Skipping entry with no video ID: {video_title}")
            continue
        if not video_url:
            log_warning(f"Skipping entry with no URL: {video_title} (ID: {video_id})")
            continue
        
        # This is a new video - highlight it
        new_found += 1
        log_message(f"New video found: {video_title}", Colors.MAGENTA)
        log_debug(f"New video details — ID: {video_id}, URL: {video_url}, Title: {video_title}")
        
        # Attempt to post to Bluesky
        if post_to_bluesky(video_title, video_url):
            # Success! Add to our database so we don't post again
            post_success += 1
            seen_videos.add(video_id)
            # Save immediately in case the script crashes later
            save_seen_videos(seen_videos)
        else:
            # Posting failed — log but don't add to seen (will retry next cycle)
            post_failed += 1
            log_warning(f"Will retry posting '{video_title}' on next check cycle")
        
        # Wait between posts to avoid rate limiting
        # Bluesky has rate limits on how fast you can post
        time.sleep(2)

    # Log a summary of this check cycle
    if new_found > 0:
        log_message(f"Check cycle summary: {new_found} new, {post_success} posted, {post_failed} failed")
    else:
        log_debug("No new videos found in this check cycle")
    
    # Return the updated set of seen videos
    return seen_videos


def parse_arguments():
    """
    Parses command line arguments.

    Supported arguments:
        --config, -c: Path to the configuration YAML file
        --build-db: Build the database without posting
        --use-api: Use YouTube Data API instead of RSS feed
        --log: Enable continuous file logging to skytube.log
        --no-cache: Disable caching for YouTube API requests

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
  python youtube_to_bluesky.py --log                        # Enable file logging to skytube.log
  python youtube_to_bluesky.py --log --use-api              # File logging with API mode
  python youtube_to_bluesky.py --use-api --no-cache         # Disable API caching (fresh data)
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

    # --log flag: enable continuous file logging to skytube.log
    # When enabled, all log output is also written to a file in the
    # current working directory for persistent record keeping
    parser.add_argument(
        "--log",
        action="store_true",
        help="Enable continuous file logging to skytube.log in the current directory. "
             "All console output is also written to the log file with timestamps and levels."
    )

    # --no-cache flag: disable caching for YouTube API requests
    # This adds cache-busting headers and timestamps to API requests
    # Useful when the API returns stale/cached data
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Disable caching for YouTube API requests by adding cache-control headers "
             "and unique timestamps. Useful when the API returns stale data."
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
    2. Optionally sets up file logging (--log)
    3. Loads and validates configuration
    4. Either builds the database (--build-db) or starts monitoring
    """
    # Declare that we want to modify the global variables
    global config
    global use_youtube_api
    global file_logger
    global no_cache
    
    # Parse command line arguments (--config, --build-db, --use-api, --log, --no-cache)
    args = parse_arguments()
    
    # Set global flags from command line arguments
    use_youtube_api = args.use_api
    no_cache = args.no_cache

    # ==========================================
    # Set up file logging if --log flag was passed
    # ==========================================
    if args.log:
        file_logger = setup_file_logging()
        log_message(f"File logging enabled — writing to {os.path.join(os.getcwd(), LOG_FILE_NAME)}", Colors.BLUE)
    
    # Load configuration from the YAML file
    loaded_config = load_config(args.config)
    
    # If config loading failed or was cancelled, exit with error code
    if loaded_config is None:
        log_debug("Exiting: config loading returned None")
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
    if no_cache:
        log_message("Cache control: DISABLED (--no-cache)", Colors.YELLOW)
    log_message(f"Check interval: {config.get('check_interval_seconds', 600)} seconds")
    if file_logger:
        log_message(f"File logging: ENABLED ({LOG_FILE_NAME})", Colors.BLUE)
    log_message("=" * 50)
    
    # Load any previously seen videos from the database
    seen_videos = load_seen_videos()
    log_message(f"Loaded {len(seen_videos)} previously seen videos")
    
    # Main monitoring loop - runs forever until script is stopped
    while True:
        try:
            # Check for new videos and post them
            seen_videos = check_for_new_videos(seen_videos)

        except KeyboardInterrupt:
            # User pressed Ctrl+C to stop the script — exit gracefully
            log_message("Received keyboard interrupt (Ctrl+C). Shutting down gracefully...", Colors.YELLOW)
            log_debug("Script terminated by user via KeyboardInterrupt")
            break
            
        except Exception as e:
            # Catch any unexpected errors but keep the loop running
            # This prevents the script from crashing on temporary issues
            log_exception("Unexpected error during check cycle", e)
            log_warning("The monitoring loop will continue despite the error above")
        
        # Wait before checking again
        # Get interval from config, default to 600 seconds (10 minutes)
        check_interval = config.get("check_interval_seconds", 600)

        # Validate that the interval is a positive number before sleeping
        if not isinstance(check_interval, (int, float)) or check_interval <= 0:
            log_warning(f"Invalid check_interval_seconds ({check_interval}), using default 600 seconds")
            check_interval = 600

        log_message(f"Sleeping for {check_interval} seconds...")
        
        try:
            # Sleep until next check
            # time.sleep pauses execution for the specified seconds
            time.sleep(check_interval)
        except KeyboardInterrupt:
            # User pressed Ctrl+C during the sleep period — exit gracefully
            log_message("Received keyboard interrupt during sleep. Shutting down gracefully...", Colors.YELLOW)
            log_debug("Script terminated by user during sleep via KeyboardInterrupt")
            break

    # Log final shutdown message
    log_message("Script stopped.", Colors.CYAN)


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