"""
Image Transformation Service

Applies metadata transformations to images:
- Rotation (from orientation detection)
- Deskew (from skew detection)
- Brightness adjustment
- Contrast adjustment
- Cropping (from bbox)

Used by PDF generation to apply editor changes to final output.
"""

from PIL import Image, ImageEnhance
import numpy as np
from typing import Dict, Tuple, Optional
import os
import math


def apply_brightness_contrast(img: Image.Image, brightness: int, contrast: int) -> Image.Image:
    """
    Apply brightness and contrast adjustments to PIL Image.
    
    Args:
        img: PIL Image
        brightness: Brightness adjustment (-100 to +100)
        contrast: Contrast adjustment (-100 to +100)
    
    Returns:
        Adjusted PIL Image
    """
    # Convert brightness from -100/+100 to PIL factor
    # PIL uses 1.0 as neutral, <1 darker, >1 brighter
    # -100 → 0.0 (black), 0 → 1.0 (original), +100 → 2.0 (double brightness)
    brightness_factor = 1.0 + (brightness / 100.0)
    brightness_factor = max(0.0, min(2.0, brightness_factor))
    
    # Convert contrast from -100/+100 to PIL factor
    # Similar scale: 0 → gray, 1.0 → original, 2.0 → double contrast
    contrast_factor = 1.0 + (contrast / 100.0)
    contrast_factor = max(0.0, min(2.0, contrast_factor))
    
    # Apply brightness
    if brightness != 0:
        enhancer = ImageEnhance.Brightness(img)
        img = enhancer.enhance(brightness_factor)
    
    # Apply contrast
    if contrast != 0:
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(contrast_factor)
    
    return img


def apply_rotation(img: Image.Image, angle: float, expand: bool = True) -> Image.Image:
    """
    Rotate image by specified angle.
    
    Args:
        img: PIL Image
        angle: Rotation angle in degrees (positive = counter-clockwise)
        expand: If True, expand canvas to fit rotated image
    
    Returns:
        Rotated PIL Image
    """
    if angle == 0:
        return img
    
    # Get background color from corners (for filling)
    try:
        # Sample corner pixels
        corners = [
            img.getpixel((0, 0)),
            img.getpixel((img.width - 1, 0)),
            img.getpixel((0, img.height - 1)),
            img.getpixel((img.width - 1, img.height - 1))
        ]
        
        # Average corner colors
        if isinstance(corners[0], tuple):
            bg_color = tuple(int(sum(c[i] for c in corners) / len(corners)) for i in range(len(corners[0])))
        else:
            bg_color = int(sum(corners) / len(corners))
    except:
        bg_color = 255 if img.mode == 'L' else (255, 255, 255)
    
    # Rotate
    rotated = img.rotate(
        angle,
        resample=Image.Resampling.BICUBIC,
        expand=expand,
        fillcolor=bg_color
    )
    
    return rotated


def apply_crop(img: Image.Image, bbox: Dict[str, int]) -> Image.Image:
    """
    Crop image to specified bounding box.
    
    Args:
        img: PIL Image
        bbox: Dict with keys 'x', 'y', 'width', 'height'
    
    Returns:
        Cropped PIL Image
    """
    x = bbox.get('x', 0)
    y = bbox.get('y', 0)
    width = bbox.get('width', img.width)
    height = bbox.get('height', img.height)
    
    # Clamp to image bounds
    x = max(0, min(x, img.width))
    y = max(0, min(y, img.height))
    width = max(1, min(width, img.width - x))
    height = max(1, min(height, img.height - y))
    
    # Crop (PIL uses left, top, right, bottom)
    cropped = img.crop((x, y, x + width, y + height))
    
    return cropped


def apply_metadata_transforms(
    img_path: str,
    metadata: Dict,
    apply_bbox_crop: bool = True,
    target_dpi: Optional[int] = None
) -> Image.Image:
    """
    Apply all transformations from metadata to image.
    
    Transformation order:
    1. Load original image
    2. Apply rotation (orientation correction)
    3. Apply deskew (tilt correction)
    4. Apply brightness/contrast
    5. Apply bbox crop (if enabled)
    
    Args:
        img_path: Path to original image
        metadata: Image metadata dict with transformation parameters
        apply_bbox_crop: Whether to apply bbox cropping
        target_dpi: Target DPI for output (None = keep original)
    
    Returns:
        Transformed PIL Image ready for PDF generation
    """
    # If OpenCV is available prefer the fast cv2 implementation
    try:
        import cv2
        # Use the fast cv2 implementation
        return apply_metadata_transforms_fast_cv2(img_path, metadata, apply_bbox_crop, target_dpi)
    except Exception:
        # Fall back to PIL implementation below
        pass

    # Load original image (PIL fallback)
    if not os.path.exists(img_path):
        raise FileNotFoundError(f"Image not found: {img_path}")

    img = Image.open(img_path)
    
    # Store original DPI
    original_dpi = img.info.get('dpi', (300, 300))
    if isinstance(original_dpi, (int, float)):
        original_dpi = (original_dpi, original_dpi)
    
    # 1. Apply rotation (batch orientation correction)
    rotation = metadata.get('rotation', 0)
    if rotation != 0:
        img = apply_rotation(img, rotation, expand=True)
    
    # 2. Apply deskew (individual tilt correction)
    deskew_angle = metadata.get('deskew_angle', 0.0)
    if abs(deskew_angle) > 0.1:  # Only if significant
        img = apply_rotation(img, deskew_angle, expand=False)
    
    # 3. Apply brightness/contrast (editor adjustments)
    brightness = metadata.get('brightness', 0)
    contrast = metadata.get('contrast', 0)
    if brightness != 0 or contrast != 0:
        img = apply_brightness_contrast(img, brightness, contrast)
    
    # 4. Apply bbox crop (document boundary)
    if apply_bbox_crop and 'bbox' in metadata:
        bbox = metadata['bbox']
        img = apply_crop(img, bbox)
    
    # 5. Adjust DPI if needed
    if target_dpi:
        img.info['dpi'] = (target_dpi, target_dpi)
    else:
        img.info['dpi'] = original_dpi
    
    return img


def apply_metadata_transforms_fast_cv2(
    img_path: str,
    metadata: Dict,
    apply_bbox_crop: bool = True,
    target_dpi: Optional[int] = None
) -> Image.Image:
    """
    Fast implementation of apply_metadata_transforms using OpenCV.
    Performs rotation, deskew, crop, brightness/contrast using cv2 (C-optimized).
    Returns a PIL.Image for compatibility with existing code.
    """
    try:
        import cv2
    except Exception:
        raise

    if not os.path.exists(img_path):
        raise FileNotFoundError(f"Image not found: {img_path}")

    # Load image robustly (support Windows unicode paths)
    try:
        if os.name == 'nt':
            arr = np.fromfile(img_path, dtype=np.uint8)
            img_bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        else:
            img_bgr = cv2.imread(img_path, cv2.IMREAD_COLOR)
    except Exception:
        img_bgr = None

    if img_bgr is None:
        raise IOError(f"Failed to load image via OpenCV: {img_path}")

    # Convert BGR -> RGB
    img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)

    def _rotate_cv2(img_np, angle_deg, expand=True, bg_color=(255, 255, 255)):
        if angle_deg == 0:
            return img_np
        h, w = img_np.shape[:2]
        cx, cy = w / 2.0, h / 2.0
        M = cv2.getRotationMatrix2D((cx, cy), angle_deg, 1.0)
        if expand:
            cos = abs(M[0, 0]); sin = abs(M[0, 1])
            nw = int((h * sin) + (w * cos))
            nh = int((h * cos) + (w * sin))
            M[0, 2] += (nw / 2.0) - cx
            M[1, 2] += (nh / 2.0) - cy
            dst = cv2.warpAffine(img_np, M, (nw, nh), flags=cv2.INTER_CUBIC, borderValue=bg_color)
            return dst
        else:
            dst = cv2.warpAffine(img_np, M, (w, h), flags=cv2.INTER_CUBIC, borderValue=bg_color)
            return dst

    def _adjust_brightness_contrast_cv2(img_np, brightness=0, contrast=0):
        # brightness, contrast in -100..100
        if brightness == 0 and contrast == 0:
            return img_np
        beta = float(brightness) * 255.0 / 100.0
        alpha = 1.0 + (float(contrast) / 100.0)
        img_adj = cv2.convertScaleAbs(img_np, alpha=alpha, beta=beta)
        return img_adj

    # 1. Apply rotation (batch orientation)
    rotation = float(metadata.get('rotation', 0) or 0)
    if rotation != 0:
        img_rgb = _rotate_cv2(img_rgb, rotation, expand=True, bg_color=(255, 255, 255))

    # 2. Apply deskew (tilt correction)
    deskew_angle = float(metadata.get('deskew_angle', 0.0) or 0.0)
    if abs(deskew_angle) > 0.1:
        img_rgb = _rotate_cv2(img_rgb, deskew_angle, expand=False, bg_color=(255, 255, 255))

    # 3. Crop by bbox (after rotation/deskew)
    if apply_bbox_crop and 'bbox' in metadata:
        b = metadata['bbox']
        x = int(b.get('x', 0))
        y = int(b.get('y', 0))
        w = int(b.get('w') or b.get('width') or 0)
        h = int(b.get('h') or b.get('height') or 0)
        # clamp
        x = max(0, x); y = max(0, y)
        w = max(1, min(w, img_rgb.shape[1] - x))
        h = max(1, min(h, img_rgb.shape[0] - y))
        img_rgb = img_rgb[y:y+h, x:x+w]

    # 4. Brightness/contrast
    brightness = int(metadata.get('brightness', 0) or 0)
    contrast = int(metadata.get('contrast', 0) or 0)
    if brightness != 0 or contrast != 0:
        img_rgb = _adjust_brightness_contrast_cv2(img_rgb, brightness, contrast)

    # 5. Convert to PIL and set DPI if requested
    img_pil = Image.fromarray(img_rgb)
    if target_dpi:
        img_pil.info['dpi'] = (target_dpi, target_dpi)

    return img_pil


def get_transform_summary(metadata: Dict) -> str:
    """
    Generate human-readable summary of transformations.
    
    Args:
        metadata: Image metadata dict
    
    Returns:
        Summary string like "Rotation: 180°, Deskew: -2.3°, Brightness: +20"
    """
    parts = []
    
    rotation = metadata.get('rotation', 0)
    if rotation != 0:
        parts.append(f"Rotation: {rotation}°")
    
    deskew = metadata.get('deskew_angle', 0.0)
    if abs(deskew) > 0.1:
        parts.append(f"Deskew: {deskew:.1f}°")
    
    brightness = metadata.get('brightness', 0)
    if brightness != 0:
        sign = '+' if brightness > 0 else ''
        parts.append(f"Brightness: {sign}{brightness}")
    
    contrast = metadata.get('contrast', 0)
    if contrast != 0:
        sign = '+' if contrast > 0 else ''
        parts.append(f"Contrast: {sign}{contrast}")
    
    if 'bbox' in metadata:
        bbox = metadata['bbox']
        parts.append(f"Crop: {bbox['width']}x{bbox['height']}")
    
    return ', '.join(parts) if parts else 'No transformations'
