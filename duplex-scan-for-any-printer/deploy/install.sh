#!/bin/bash
# Deployment script for Scan Agent
# Supports Docker and bare metal installation

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
APP_NAME="scan-agent"
APP_DIR="/opt/scan-agent"
USER="scanagent"
VENV_DIR="$APP_DIR/.venv"

echo -e "${GREEN}================================${NC}"
echo -e "${GREEN}Scan Agent Installation Script${NC}"
echo -e "${GREEN}================================${NC}"
echo ""

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   echo -e "${RED}This script must be run as root (sudo)${NC}" 
   exit 1
fi

# Detect OS
if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS=$ID
    VER=$VERSION_ID
else
    echo -e "${RED}Cannot detect OS${NC}"
    exit 1
fi

echo -e "${YELLOW}Detected OS: $OS $VER${NC}"

# Ask deployment mode
echo ""
echo "Select deployment mode:"
echo "1) Docker (recommended for Home Assistant OS)"
echo "2) Bare metal (systemd service)"
read -p "Enter choice [1-2]: " DEPLOY_MODE

if [ "$DEPLOY_MODE" == "1" ]; then
    echo -e "${GREEN}Installing with Docker...${NC}"
    
    # Check if Docker is installed
    if ! command -v docker &> /dev/null; then
        echo -e "${YELLOW}Docker not found. Installing Docker...${NC}"
        
        if [ "$OS" == "ubuntu" ] || [ "$OS" == "debian" ] || [ "$OS" == "raspbian" ]; then
            # Install Docker
            curl -fsSL https://get.docker.com -o get-docker.sh
            sh get-docker.sh
            rm get-docker.sh
            
            # Add current user to docker group
            usermod -aG docker $SUDO_USER
            
            echo -e "${GREEN}Docker installed successfully${NC}"
        else
            echo -e "${RED}Please install Docker manually for your OS${NC}"
            exit 1
        fi
    else
        echo -e "${GREEN}Docker already installed${NC}"
    fi
    
    # Check if Docker Compose is installed
    if ! command -v docker-compose &> /dev/null; then
        echo -e "${YELLOW}Docker Compose not found. Installing...${NC}"
        
        if [ "$OS" == "ubuntu" ] || [ "$OS" == "debian" ] || [ "$OS" == "raspbian" ]; then
            apt-get update
            apt-get install -y docker-compose
            echo -e "${GREEN}Docker Compose installed${NC}"
        else
            echo -e "${YELLOW}Please install Docker Compose manually${NC}"
        fi
    else
        echo -e "${GREEN}Docker Compose already installed${NC}"
    fi
    
    # Create directories
    echo -e "${YELLOW}Creating directories...${NC}"
    mkdir -p scan_inbox/scan_duplex scan_inbox/copy_duplex scan_inbox/scan_document
    mkdir -p scan_inbox/card_2in1 scan_inbox/confirm scan_inbox/confirm_print scan_inbox/reject
    mkdir -p scan_out
    mkdir -p logs
    
    # Set permissions
    chmod 777 scan_inbox scan_out logs
    chmod 777 scan_inbox/*
    
    # Build and start
    echo -e "${YELLOW}Building Docker image...${NC}"
    docker-compose build
    
    echo -e "${YELLOW}Starting services...${NC}"
    docker-compose up -d
    
    echo ""
    echo -e "${GREEN}================================${NC}"
    echo -e "${GREEN}Docker deployment complete!${NC}"
    echo -e "${GREEN}================================${NC}"
    echo ""
    echo "Services running:"
    docker-compose ps
    echo ""
    echo "View logs: docker-compose logs -f scan-agent"
    echo "Stop: docker-compose down"
    echo "Restart: docker-compose restart"
    
elif [ "$DEPLOY_MODE" == "2" ]; then
    echo -e "${GREEN}Installing bare metal with systemd...${NC}"
    
    # Install system dependencies
    echo -e "${YELLOW}Installing system dependencies...${NC}"
    
    if [ "$OS" == "ubuntu" ] || [ "$OS" == "debian" ] || [ "$OS" == "raspbian" ]; then
        apt-get update
        apt-get install -y \
            python3.10 python3.10-venv python3-pip \
            cups cups-client \
            libopencv-dev python3-opencv \
            build-essential gcc g++
    else
        echo -e "${RED}Unsupported OS for bare metal installation${NC}"
        exit 1
    fi
    
    # Create user
    if ! id "$USER" &>/dev/null; then
        echo -e "${YELLOW}Creating user $USER...${NC}"
        useradd -m -s /bin/bash $USER
    else
        echo -e "${GREEN}User $USER already exists${NC}"
    fi
    
    # Create app directory
    echo -e "${YELLOW}Creating application directory...${NC}"
    mkdir -p $APP_DIR
    
    # Copy files
    echo -e "${YELLOW}Copying application files...${NC}"
    cp -r src $APP_DIR/
    cp config.yaml $APP_DIR/
    cp -r checkpoints $APP_DIR/
    cp requirements.txt $APP_DIR/
    
    # Create directories
    mkdir -p /scan_inbox/scan_duplex /scan_inbox/copy_duplex /scan_inbox/scan_document
    mkdir -p /scan_inbox/card_2in1 /scan_inbox/confirm /scan_inbox/confirm_print /scan_inbox/reject
    mkdir -p /scan_out
    mkdir -p /var/log/scan-agent
    
    # Set ownership
    chown -R $USER:$USER $APP_DIR /scan_inbox /scan_out /var/log/scan-agent
    chmod 755 /scan_inbox /scan_out
    
    # Create virtual environment
    echo -e "${YELLOW}Creating Python virtual environment...${NC}"
    sudo -u $USER python3.10 -m venv $VENV_DIR
    
    # Install Python dependencies
    echo -e "${YELLOW}Installing Python dependencies...${NC}"
    sudo -u $USER $VENV_DIR/bin/pip install --upgrade pip
    sudo -u $USER $VENV_DIR/bin/pip install -r $APP_DIR/requirements.txt
    
    # Create systemd service
    echo -e "${YELLOW}Creating systemd service...${NC}"
    cat > /etc/systemd/system/scan-agent.service << EOF
[Unit]
Description=Scan Agent Service
After=network.target cups.service

[Service]
Type=simple
User=$USER
WorkingDirectory=$APP_DIR
Environment="PATH=$VENV_DIR/bin:/usr/local/bin:/usr/bin:/bin"
Environment="PYTHONUNBUFFERED=1"
Environment="SCAN_INBOX_BASE=/scan_inbox"
Environment="SCAN_OUTPUT_DIR=/scan_out"
ExecStart=$VENV_DIR/bin/python -m src.main --config $APP_DIR/config.yaml
Restart=always
RestartSec=10

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=scan-agent

[Install]
WantedBy=multi-user.target
EOF
    
    # Reload systemd
    systemctl daemon-reload
    
    # Enable and start service
    echo -e "${YELLOW}Enabling and starting service...${NC}"
    systemctl enable scan-agent
    systemctl start scan-agent
    
    echo ""
    echo -e "${GREEN}================================${NC}"
    echo -e "${GREEN}Bare metal deployment complete!${NC}"
    echo -e "${GREEN}================================${NC}"
    echo ""
    echo "Service status: systemctl status scan-agent"
    echo "View logs: journalctl -u scan-agent -f"
    echo "Stop: systemctl stop scan-agent"
    echo "Restart: systemctl restart scan-agent"
    
else
    echo -e "${RED}Invalid choice${NC}"
    exit 1
fi

echo ""
echo -e "${GREEN}Installation complete!${NC}"
echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo "1. Configure your Brother scanner FTP settings:"
echo "   - Server: <this-machine-ip>"
echo "   - Port: 2121 (or 21 if using external FTP)"
echo "   - Username: anonymous (or configured user)"
echo "   - Remote directory: /scan_duplex, /scan_document, etc."
echo ""
echo "2. Test the installation:"
echo "   - Scan a test document"
echo "   - Check /scan_out for generated PDF"
echo ""
echo "3. Configure CUPS printer (for printing feature):"
echo "   - Run: ./deploy/setup-cups.sh"
