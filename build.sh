#!/bin/bash
# SkyTube Build Script
# ====================
# Builds a single binary executable from skytube.py using PyInstaller
# Outputs to release/<version>/ directory and cleans up all temporary files

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"
BUILD_DIR="$SCRIPT_DIR/build"
DIST_DIR="$SCRIPT_DIR/dist"
RELEASE_BASE_DIR="$SCRIPT_DIR/release"
SPEC_FILE="$SCRIPT_DIR/skytube.spec"
VERSION_FILE="$SCRIPT_DIR/VERSION"

# Binary name
BINARY_NAME="skytube"

# Function to clean up on failure
cleanup_on_failure() {
    echo ""
    echo -e "${RED}Cleaning up due to build failure...${NC}"
    rm -rf "$BUILD_DIR"
    rm -rf "$DIST_DIR"
    # Only clean release dir if it was created in this run
    if [ -n "${VERSION:-}" ] && [ -d "$RELEASE_BASE_DIR/$VERSION" ]; then
        rm -rf "$RELEASE_BASE_DIR/$VERSION"
        # Remove release base dir if empty
        if [ -d "$RELEASE_BASE_DIR" ] && [ ! "$(ls -A "$RELEASE_BASE_DIR")" ]; then
            rm -rf "$RELEASE_BASE_DIR"
        fi
    fi
    echo -e "${RED}Cleanup complete.${NC}"
}

# Set trap to call cleanup on error
trap cleanup_on_failure ERR

echo -e "${BLUE}SkyTube Build Script${NC}"
echo "===================="
echo ""

# Read version from VERSION file
echo -e "${BLUE}Reading version from VERSION file...${NC}"
if [ ! -f "$VERSION_FILE" ]; then
    echo -e "${RED}Error: VERSION file not found at $VERSION_FILE${NC}"
    echo "Please create a VERSION file containing the version number (e.g., '1.0.0')"
    exit 1
fi

VERSION=$(cat "$VERSION_FILE" | tr -d '[:space:]')

if [ -z "$VERSION" ]; then
    echo -e "${RED}Error: VERSION file is empty${NC}"
    echo "Please add a version number to the VERSION file (e.g., '1.0.0')"
    exit 1
fi

# Basic version format validation (allows: 1.0.0, 1.0.0-beta, 1.0.0-rc1, etc.)
if ! [[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+([-\.].*)?$ ]]; then
    echo -e "${RED}Error: Invalid version format in VERSION file: '$VERSION'${NC}"
    echo "Version must follow semantic versioning (e.g., 1.0.0, 2.1.0-beta)"
    exit 1
fi

echo -e "${GREEN}Building version: $VERSION${NC}"
echo ""

# Set versioned release directory
RELEASE_DIR="$RELEASE_BASE_DIR/$VERSION"

# Check if virtual environment exists
if [ ! -d "$VENV_DIR" ]; then
    echo -e "${RED}Error: Virtual environment not found at $VENV_DIR${NC}"
    echo "Please create it first: python -m venv .venv"
    exit 1
fi

# Activate virtual environment
echo -e "${BLUE}Activating virtual environment...${NC}"
source "$VENV_DIR/bin/activate"

# Check if pyinstaller is installed
VENV_PYTHON="$VENV_DIR/bin/python"

if ! "$VENV_PYTHON" -c "import PyInstaller" &> /dev/null; then
    echo -e "${YELLOW}PyInstaller not found. Installing...${NC}"
    "$VENV_PYTHON" -m pip install pyinstaller
fi

# Clean up previous builds
echo -e "${BLUE}Cleaning previous builds...${NC}"
rm -rf "$BUILD_DIR"
rm -rf "$DIST_DIR"
rm -rf "$RELEASE_BASE_DIR"

# Create release directory
echo -e "${BLUE}Creating release directory: release/$VERSION/${NC}"
mkdir -p "$RELEASE_DIR"

# Run PyInstaller
echo -e "${BLUE}Building binary with PyInstaller...${NC}"
echo ""

"$VENV_PYTHON" -m PyInstaller \
    --clean \
    --noconfirm \
    --onefile \
    --name "$BINARY_NAME" \
    --distpath "$DIST_DIR" \
    --workpath "$BUILD_DIR" \
    --specpath "$SCRIPT_DIR" \
    "$SCRIPT_DIR/skytube.py"

# Check if build succeeded
if [ ! -f "$DIST_DIR/$BINARY_NAME" ]; then
    echo -e "${RED}Error: Build failed - binary not found${NC}"
    exit 1
fi

# Move binary to release directory
echo -e "${BLUE}Moving binary to release/$VERSION/ directory...${NC}"
mv "$DIST_DIR/$BINARY_NAME" "$RELEASE_DIR/"

# Copy example config to release
echo -e "${BLUE}Copying example files to release/$VERSION/ directory...${NC}"
if [ -f "$SCRIPT_DIR/config_example.yaml" ]; then
    cp "$SCRIPT_DIR/config_example.yaml" "$RELEASE_DIR/"
fi

# Create README for release
echo -e "${BLUE}Creating release README...${NC}"
cat > "$RELEASE_DIR/README.txt" << EOF
SkyTube Binary Release v$VERSION
================================

This folder contains the SkyTube executable binary.

Version: $VERSION
Built: $(date '+%Y-%m-%d %H:%M:%S')

Usage:
------
1. Copy config_example.yaml to config.yaml
2. Edit config.yaml with your credentials
3. Run: ./skytube --config /path/to/config.yaml

Or run without arguments (looks for config.yaml in current directory):
    ./skytube

For more options:
    ./skytube --help

Notes:
------
- The binary is a standalone executable
- No Python installation required
- Configuration and seen videos file are not bundled (edit them separately)
EOF

# Clean up PyInstaller artifacts
echo -e "${BLUE}Cleaning up PyInstaller artifacts...${NC}"
rm -rf "$BUILD_DIR"
rm -rf "$DIST_DIR"
# Keep the spec file for future builds, but remove the backup
rm -f "$SCRIPT_DIR/${BINARY_NAME}.spec.bak"

echo ""
echo -e "${GREEN}Build complete!${NC}"
echo "================="
echo ""
echo "Version: $VERSION"
echo "Binary location: release/$VERSION/$BINARY_NAME"
echo ""
echo "Release contents:"
ls -lh "$RELEASE_DIR/"
echo ""
echo -e "${GREEN}Done!${NC}"
