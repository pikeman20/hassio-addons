#!/usr/bin/env python3
"""
Test main.py logic with scan_duplex mode
"""
import sys
from pathlib import Path
from datetime import datetime

#Check if current dir is project root or project_root/tests
current_dir = Path(__file__).parent.resolve()
project_root = current_dir.parent if current_dir.name == "tests" else current_dir
sys.path.insert(0, str(project_root / "src"))
#Resolve imports for src files

from agent.config import Config
from agent.session_manager import Session

# Load config
cfg = Config.load("config.yaml")

# Create mock session with scan_duplex mode
scan_dir = Path("scan_inbox/scan_duplex")
images = sorted(scan_dir.glob("*.jpg"))

if not images:
    print("❌ No images found in scan_inbox/scan_duplex/")
    sys.exit(1)

print(f"📁 Found {len(images)} images in scan_duplex folder\n")

# Create session
session = Session(
    id="test_scan_duplex",
    mode="scan_duplex",
    images=[str(p) for p in images]
)

# Process using main logic
print("🔄 Processing with main.py logic (scan_duplex mode)...\n")

from main import process_session
process_session(cfg, session)

print(f"\n✅ Done! Check scan_out/ for output PDF")
