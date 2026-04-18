# Test Scan Agent Addon với Docker (Windows PowerShell)
# Chạy local test trước khi publish lên HAOS

Write-Host "================================" -ForegroundColor Green
Write-Host "Scan Agent - Local Docker Test" -ForegroundColor Green
Write-Host "================================" -ForegroundColor Green
Write-Host ""

# Check Docker
Write-Host "Checking Docker..." -ForegroundColor Yellow
try {
    docker info | Out-Null
    Write-Host "✓ Docker is running" -ForegroundColor Green
} catch {
    Write-Host "✗ Docker is not running. Please start Docker Desktop." -ForegroundColor Red
    exit 1
}

# Build image
Write-Host "`nBuilding Docker image..." -ForegroundColor Yellow
Write-Host "Note: Using HAOS Debian base with Python 3.10 (ghcr.io/home-assistant/amd64-base-debian:latest)" -ForegroundColor Cyan
$CacheBust = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
docker build `
    --build-arg BUILD_FROM=ghcr.io/home-assistant/amd64-base-debian:latest `
    --build-arg CACHE_BUST=$CacheBust `
    -t scan-agent:test `
    .

if ($LASTEXITCODE -ne 0) {
    Write-Host "✗ Build failed" -ForegroundColor Red
    exit 1
}

Write-Host "✓ Image built successfully!" -ForegroundColor Green

# Check existing directories
Write-Host "`nChecking directories..." -ForegroundColor Yellow
if (-not (Test-Path "scan_inbox")) {
    Write-Host "✗ scan_inbox not found. Creating..." -ForegroundColor Yellow
    New-Item -ItemType Directory -Force -Path "scan_inbox" | Out-Null
}
if (-not (Test-Path "scan_out")) {
    Write-Host "✗ scan_out not found. Creating..." -ForegroundColor Yellow
    New-Item -ItemType Directory -Force -Path "scan_out" | Out-Null
}

# Create checkpoints folder for container data
New-Item -ItemType Directory -Force -Path "test_data" | Out-Null

Write-Host "✓ Using existing directories:" -ForegroundColor Green
Write-Host "  ./scan_inbox  - FTP upload target (existing data preserved)"
Write-Host "  ./scan_out    - PDF output"
Write-Host "  ./test_data   - Container data (config.yaml)"

# Verify config.yaml exists (mounted as /data/config.yaml in container)
Write-Host "`nPreparing test configuration..." -ForegroundColor Yellow
if (-not (Test-Path "test_data/config.yaml")) {
    Write-Host "✗ test_data/config.yaml not found!" -ForegroundColor Red
    Write-Host "  Create it based on config.local.template.yaml or check docs." -ForegroundColor Yellow
    exit 1
} else {
    Write-Host "✓ Using test_data/config.yaml" -ForegroundColor Green
}

# Get local IP
$LocalIP = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object {$_.InterfaceAlias -notlike "*Loopback*" -and $_.InterfaceAlias -notlike "*VirtualBox*"} | Select-Object -First 1).IPAddress

Write-Host "`n================================" -ForegroundColor Cyan
Write-Host "Scanner Configuration" -ForegroundColor Cyan
Write-Host "================================" -ForegroundColor Cyan
Write-Host "Configure your Brother scanner:" -ForegroundColor White
Write-Host "  Server IP: $LocalIP" -ForegroundColor Yellow
Write-Host "  Port: 2121" -ForegroundColor Yellow
Write-Host "  Username: anonymous" -ForegroundColor Yellow
Write-Host "  Password: (leave empty)" -ForegroundColor Yellow
Write-Host "  Directory: /scan_duplex" -ForegroundColor Yellow
Write-Host ""
Write-Host "Test FTP connection:" -ForegroundColor White
Write-Host "  ftp $LocalIP 2121" -ForegroundColor Yellow
Write-Host ""
Write-Host "Web UI dashboard:" -ForegroundColor White
Write-Host "  http://${LocalIP}:8099" -ForegroundColor Yellow
Write-Host ""
# Run container
Write-Host "Starting container..." -ForegroundColor Yellow
Write-Host "Press Ctrl+C to stop" -ForegroundColor White
Write-Host ""

# Check if Docker Desktop supports host network (Linux containers on Windows use NAT)
# For printer access, we'll use host network on Linux, or bridge with port mapping on Windows
$OnLinux = $PSVersionTable.Platform -eq 'Unix'

if ($OnLinux) {
    Write-Host "Using host network mode for direct printer access" -ForegroundColor Cyan
    docker run --rm -it `
        --name scan-agent-test `
        --network host `
        -v "${PWD}/scan_inbox:/share/scan_inbox" `
        -v "${PWD}/scan_out:/share/scan_out" `
        -v "${PWD}/test_data:/data" `
        -v "${PWD}/checkpoints:/app/checkpoints:ro" `
        -e SCAN_INBOX_BASE=/share/scan_inbox `
        -e SCAN_OUTPUT_DIR=/share/scan_out `
        -e LOG_LEVEL=INFO `
        scan-agent:test
} else {
    Write-Host "Using bridge network (Windows Docker Desktop)" -ForegroundColor Cyan
    Write-Host "Note: Printer at 192.168.100.60 may not be accessible from container" -ForegroundColor Yellow
    Write-Host "      This is normal in Docker Desktop on Windows" -ForegroundColor Yellow
    Write-Host "      Printer will work when deployed to HAOS" -ForegroundColor Yellow
    Write-Host ""
    docker run --rm -it `
        --name scan-agent-test `
        -v "${PWD}/scan_inbox:/share/scan_inbox" `
        -v "${PWD}/scan_out:/share/scan_out" `
        -v "${PWD}/test_data:/data" `
        -v "${PWD}/checkpoints:/app/checkpoints:ro" `
        -p 2121:2121 `
        -p 8099:8099 `
        -p 30000-30002:30000-30002 `
        -e SCAN_INBOX_BASE=/share/scan_inbox `
        -e SCAN_OUTPUT_DIR=/share/scan_out `
        -e LOG_LEVEL=INFO `
        scan-agent:test
}

Write-Host "`nContainer stopped." -ForegroundColor Yellow
