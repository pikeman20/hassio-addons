#!/usr/bin/env python3
"""
Test main.py logic with card_2in1 mode
- Reads images from scan_inbox/card_2in1/
- Pairs images in order (2 per page)
- Respects test_mode (no deletions when true)
"""
import sys
from pathlib import Path

# Resolve project root so we can import from src/
current_dir = Path(__file__).parent.resolve()
project_root = current_dir.parent if current_dir.name == "tests" else current_dir
sys.path.insert(0, str(project_root / "src"))

from agent.config import Config
from agent.session_manager import Session
from main import process_session

# Load config
cfg = Config.load("config.yaml")

# Collect images for scan_document
scan_dir = Path("scan_inbox/scan_document")
images = sorted(scan_dir.glob("*.jpg"))

if not images:
    print("❌ No images found in scan_inbox/scan_document/")
    sys.exit(1)

print(f"📁 Found {len(images)} images in scan_document/\n")

# Ensure even count (pairing)
if len(images) % 2 != 0:
    print(f"⚠️  Odd number of images ({len(images)}). Dropping last to keep pairs.")
    images = images[:-1]

if len(images) < 2:
    print("❌ Need at least 2 images for scan_document test")
    sys.exit(1)

# Build session
session = Session(
    id="test_scan_document",
    mode="scan_document",
    images=[str(p) for p in images]
)

# Process using main logic
print("🔄 Processing with main.py logic (scan_document mode)...\n")
process_session(cfg, session)

print("\n✅ Done! Check scan_out/ for output PDF (scan_document mode)")