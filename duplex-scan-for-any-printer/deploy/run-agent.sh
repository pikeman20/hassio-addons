#!/bin/bash
# Quick start script for Scan Agent (non-Docker)

set -e

APP_DIR="/opt/scan-agent"
VENV_DIR="$APP_DIR/.venv"
CONFIG_FILE="$APP_DIR/config.yaml"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}Starting Scan Agent...${NC}"

# Check if installed
if [ ! -d "$APP_DIR" ]; then
    echo -e "${RED}Scan Agent not installed. Run deploy/install.sh first${NC}"
    exit 1
fi

# Check if running as scanagent user or root
if [ "$USER" != "scanagent" ] && [ "$EUID" -ne 0 ]; then
    echo -e "${YELLOW}Switching to scanagent user...${NC}"
    sudo -u scanagent $0
    exit 0
fi

# Activate virtual environment
if [ -f "$VENV_DIR/bin/activate" ]; then
    source "$VENV_DIR/bin/activate"
else
    echo -e "${RED}Virtual environment not found${NC}"
    exit 1
fi

# Set environment variables
export PYTHONUNBUFFERED=1
export SCAN_INBOX_BASE=/scan_inbox
export SCAN_OUTPUT_DIR=/scan_out

# Check if config exists
if [ ! -f "$CONFIG_FILE" ]; then
    echo -e "${RED}Config file not found: $CONFIG_FILE${NC}"
    exit 1
fi

# Run the agent
cd "$APP_DIR"
echo -e "${GREEN}Scan Agent started${NC}"
echo -e "${YELLOW}Press Ctrl+C to stop${NC}"
echo ""

python -m src.main --config "$CONFIG_FILE"
