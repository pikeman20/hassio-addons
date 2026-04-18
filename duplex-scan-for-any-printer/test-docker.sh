#!/usr/bin/env bash
# Test addon locally with Docker (mimics HAOS environment)

set -e

echo "================================"
echo "Scan Agent - Local Docker Test"
echo "================================"
echo ""

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "ERROR: Docker is not running"
    exit 1
fi

# Build image
echo "Building Docker image..."
docker build \
    --build-arg BUILD_FROM=ghcr.io/home-assistant/amd64-base:latest \
    -t scan-agent:test \
    .

echo ""
echo "Image built successfully!"
echo ""

# Create test directories
echo "Creating test directories..."
mkdir -p test_share/scan_inbox/{scan_duplex,copy_duplex,scan_document,card_2in1,confirm,confirm_print,reject}
mkdir -p test_share/scan_out
mkdir -p test_data/checkpoints

echo "Directories created:"
echo "  test_share/scan_inbox  - FTP upload target"
echo "  test_share/scan_out    - PDF output"
echo "  test_data/checkpoints  - ONNX models"
echo ""

# Create test options.json
echo "Creating test configuration..."
cat > test_data/options.json << 'EOF'
{
  "log_level": "info",
  "ftp": {
    "username": "",
    "password": ""
  },
  "scan_modes": {
    "scan_duplex": {
      "enabled": true,
      "auto_print": false,
      "duplex": true
    },
    "scan_document": {
      "enabled": true,
      "auto_print": false
    },
    "copy_duplex": {
      "enabled": true,
      "auto_print": false,
      "duplex": true
    },
    "card_2in1": {
      "enabled": true,
      "auto_print": false
    }
  },
  "printer": {
    "name": "",
    "enabled": false
  },
  "image_processing": {
    "enable_background_removal": true,
    "enable_depth_anything": true,
    "max_workers": 2
  },
  "retention_days": 7
}
EOF

echo "Configuration created: test_data/options.json"
echo ""

# Get local IP
if command -v ip > /dev/null 2>&1; then
    LOCAL_IP=$(ip route get 8.8.8.8 | awk '{print $7; exit}')
elif command -v ipconfig > /dev/null 2>&1; then
    LOCAL_IP=$(ipconfig | grep "IPv4" | head -1 | awk '{print $NF}')
else
    LOCAL_IP="localhost"
fi

# Run container
echo "Starting container..."
docker run --rm -it \
    --name scan-agent-test \
    -v "$(pwd)/test_share:/share" \
    -v "$(pwd)/test_data:/data" \
    -p 2121:2121 \
    -p 30000-30009:30000-30009 \
    -e LOG_LEVEL=INFO \
    scan-agent:test

echo ""
echo "Container stopped. Cleaning up..."
