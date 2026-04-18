#!/usr/bin/env python3
"""
Standalone test for background removal (RMBG-2.0 model).

Loads images from scan_inbox/card_2in1 - Copy/ (or any folder with images),
runs crop_document_v2 which uses the RMBG model, and saves:
  - The RGBA mask result
  - The cropped output
to scan_out/test_bg_remover/
"""
import sys
from pathlib import Path

# Resolve project root so we can import from src/
current_dir = Path(__file__).parent.resolve()
project_root = current_dir.parent if current_dir.name == "tests" else current_dir
sys.path.insert(0, str(project_root / "src"))

from PIL import Image
from agent.image_processing import (
    _get_bg_removal_model,
    _remove_background_rmbg,
    crop_document_v2,
)
from agent import logger

# ─── Config ────────────────────────────────────────────────────────────────────
INPUT_DIRS = [
    Path("scan_inbox/card_2in1 - Copy"),
    Path("scan_inbox/card_2in1"),
    Path("scan_inbox/confirm"),
]
OUTPUT_DIR = Path("scan_out/test_bg_remover")
MAX_IMAGES = 6  # Limit to keep test fast
# ────────────────────────────────────────────────────────────────────────────────


def find_images():
    images = []
    for d in INPUT_DIRS:
        if d.exists():
            found = sorted(d.glob("*.jpg")) + sorted(d.glob("*.png"))
            images.extend(found[:MAX_IMAGES])
            if len(images) >= MAX_IMAGES:
                break
    return images[:MAX_IMAGES]


def test_raw_rmbg(img: Image.Image, name: str, out_dir: Path):
    """Test the raw RMBG model — saves RGBA mask output."""
    model = _get_bg_removal_model()
    rgba = _remove_background_rmbg(model, img)

    out_path = out_dir / f"{name}_rmbg_rgba.png"
    rgba.save(out_path)
    logger.info(f"  ✅ Raw RMBG output → {out_path}")

    # Also save just the alpha mask for easy inspection
    alpha = rgba.split()[3]
    mask_path = out_dir / f"{name}_rmbg_mask.png"
    alpha.save(mask_path)
    logger.info(f"  ✅ Alpha mask       → {mask_path}")


def test_crop_document_v2(img: Image.Image, name: str, out_dir: Path):
    """Test the full crop_document_v2 pipeline."""
    cropped, bbox = crop_document_v2(img, debug=True, img_name=name)

    out_path = out_dir / f"{name}_cropped.jpg"
    cropped.convert("RGB").save(out_path, quality=95)
    logger.info(f"  ✅ Cropped output  → {out_path}  bbox={bbox}")


def main():
    images = find_images()
    if not images:
        print("❌ No images found. Put JPG/PNG files in scan_inbox/card_2in1 - Copy/")
        sys.exit(1)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"📁 Testing {len(images)} image(s) → output in {OUTPUT_DIR}/\n")

    for img_path in images:
        name = img_path.stem
        print(f"🖼️  Processing: {img_path.name}")
        img = Image.open(img_path)

        print("  1️⃣  Raw RMBG model output:")
        test_raw_rmbg(img, name, OUTPUT_DIR)

        print("  2️⃣  Full crop_document_v2 pipeline:")
        test_crop_document_v2(img, name, OUTPUT_DIR)
        print()

    print(f"✅ Done! Check {OUTPUT_DIR}/ for results")


if __name__ == "__main__":
    main()
