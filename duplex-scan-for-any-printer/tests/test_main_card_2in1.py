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

# Collect images for card_2in1
scan_dir = Path("scan_inbox/card_2in1")
images = sorted(scan_dir.glob("*.jpg"))

if not images:
    print("❌ No images found in scan_inbox/card_2in1/")
    sys.exit(1)

print(f"📁 Found {len(images)} images in card_2in1 folder\n")

# Ensure even count (pairing)
if len(images) % 2 != 0:
    print(f"⚠️  Odd number of images ({len(images)}). Dropping last to keep pairs.")
    images = images[:-1]

if len(images) < 2:
    print("❌ Need at least 2 images for card_2in_1 test")
    sys.exit(1)

# Build session
session = Session(
    id="test_card_2in1",
    mode="card_2in1",
    images=[str(p) for p in images]
)

# Process using main logic
print("🔄 Processing with main.py logic (card_2in1 mode)...\n")
process_session(cfg, session)

print("\n✅ Done! Check scan_out/ for output PDF (paired 2-in-1)")
