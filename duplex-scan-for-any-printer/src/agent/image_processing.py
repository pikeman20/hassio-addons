from __future__ import annotations

from typing import Tuple, Optional, Callable
from PIL import Image, ImageDraw
import numpy as np
import cv2
import os
import time
import deskew
from withoutbg import OpenSourceModel

import gc

from agent import logger

# Global model cache for background removal
# Strategy: Load on demand, unload after batch to free RAM (~500MB-1GB)
# Trade-off: +1s per batch vs 750MB RAM saved 24/7 - worth it for 24/7 agent
_BG_REMOVAL_MODEL = None

def _get_bg_removal_model():
    """Get or initialize the background removal model (lazy load pattern).
    
    Model is loaded on first use and unloaded after each batch to save RAM.
    For 24/7 agent, saving 750MB RAM is more valuable than 1s speedup.
    """
    global _BG_REMOVAL_MODEL
    if _BG_REMOVAL_MODEL is None:
        _checkpoint_paths = [
            "./checkpoints/depth_anything_v2_vits_slim.onnx",
            "./checkpoints/isnet_uint8.onnx",
            "./checkpoints/focus_matting_1.0.0.onnx",
            "./checkpoints/focus_refiner_1.0.0.onnx",
        ]
        _total_mb = sum(os.path.getsize(p) for p in _checkpoint_paths if os.path.exists(p)) / 1024 / 1024
        logger.info(f"🔄 Loading background removal model ({_total_mb:.0f} MB)...")
        load_start = time.time()
        _BG_REMOVAL_MODEL = OpenSourceModel(
            depth_model_path=_checkpoint_paths[0],
            isnet_model_path=_checkpoint_paths[1],
            matting_model_path=_checkpoint_paths[2],
            refiner_model_path=_checkpoint_paths[3],
        )
        load_time = time.time() - load_start
        logger.info(f"✅ Model loaded successfully in {load_time:.2f}s")
    return _BG_REMOVAL_MODEL

def _unload_bg_removal_model():
    """Unload the background removal model to free memory (~500MB-1GB).
    
    Called automatically after each batch processing to keep RAM low.
    """
    global _BG_REMOVAL_MODEL
    if _BG_REMOVAL_MODEL is not None:
        logger.info("🗑️  Unloading background removal model to free RAM...")
        _BG_REMOVAL_MODEL = None
        gc.collect()

def _remove_background_rmbg(model, img: Image.Image) -> Image.Image:
    """Run background removal on an image using the given model.

    Args:
        model: Background removal model instance (from _get_bg_removal_model).
        img: Input PIL Image.

    Returns:
        PIL Image in RGBA mode with alpha channel representing the foreground mask.
    """
    return model.remove_background(img)


def load_image(path: str) -> Image.Image:
    """Load image from path with error logging."""
    try:
        img = Image.open(path)
        logger.debug(f"Loaded image: {os.path.basename(path)} ({img.size[0]}x{img.size[1]} {img.mode})")
        return img
    except Exception as e:
        logger.error(f"Failed to load image {os.path.basename(path)}: {str(e)}", exc_info=True)
        raise

def rotate_180(img: Image.Image) -> Image.Image:
    return img.rotate(180, expand=True)


def is_landscape(img: Image.Image) -> bool:
    return img.width >= img.height


def detect_orientation_angle(img: Image.Image) -> int:
    """
    Ultra-lightweight SOTA orientation detection optimized for Raspberry Pi.
    
    Strategy:
    1. Downsample to 600px width (10x faster, same accuracy)
    2. Text block detection using morphology (no ML needed)
    3. Mass centroid analysis - text weight distribution
    4. Projection profile periodicity via autocorrelation
    
    Returns: rotation angle needed (0, 90, 180, 270)
    For document duplex: focus on 0° vs 180° detection
    """
    # Step 1: Smart downsample - preserve aspect ratio, target ~600px width
    target_width = 600
    if img.width > target_width:
        scale = target_width / float(img.width)
        new_size = (int(img.width * scale), int(img.height * scale))
        img_small = img.resize(new_size, Image.Resampling.LANCZOS)
    else:
        img_small = img
    
    rgb = np.array(img_small.convert("RGB"))
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    h, w = gray.shape
    
    # Step 2: Adaptive thresholding for robust text extraction
    binary = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                                    cv2.THRESH_BINARY_INV, 21, 10)
    
    # Step 3: Morphological operations to extract text blocks
    # Horizontal kernel to connect text in lines
    kernel_h = cv2.getStructuringElement(cv2.MORPH_RECT, (25, 1))
    dilated_h = cv2.dilate(binary, kernel_h, iterations=1)
    
    # Vertical kernel to connect lines into blocks
    kernel_v = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 5))
    text_blocks = cv2.dilate(dilated_h, kernel_v, iterations=1)
    
    # Step 4: Mass centroid analysis - where is the "weight" of content?
    moments = cv2.moments(text_blocks)
    if moments['m00'] > 0:
        cx = moments['m10'] / moments['m00']
        cy = moments['m01'] / moments['m00']
        
        # Normalized centroid position
        cx_norm = cx / w
        cy_norm = cy / h
    else:
        cx_norm = 0.5
        cy_norm = 0.5
    
    # Step 5: Projection profile analysis with autocorrelation
    h_projection = np.sum(text_blocks, axis=1).astype(float)
    v_projection = np.sum(text_blocks, axis=0).astype(float)
    
    # Normalize
    h_projection = h_projection / (np.max(h_projection) + 1e-6)
    v_projection = v_projection / (np.max(v_projection) + 1e-6)
    
    # Calculate variance and periodicity
    h_variance = np.var(h_projection)
    v_variance = np.var(v_projection)
    
    # Autocorrelation to detect text line periodicity
    h_autocorr = np.correlate(h_projection, h_projection, mode='same')
    h_periodicity = np.std(h_autocorr)
    
    # Step 6: Top-heavy vs bottom-heavy analysis
    top_third = text_blocks[:h//3, :]
    middle_third = text_blocks[h//3:2*h//3, :]
    bottom_third = text_blocks[2*h//3:, :]
    
    top_density = np.sum(top_third > 0) / top_third.size
    middle_density = np.sum(middle_third > 0) / middle_third.size
    bottom_density = np.sum(bottom_third > 0) / bottom_third.size
    
    # Step 7: Corner detection - logos/stamps often at specific corners
    corner_size = min(h//4, w//4)
    top_left = text_blocks[:corner_size, :corner_size]
    top_right = text_blocks[:corner_size, -corner_size:]
    bottom_left = text_blocks[-corner_size:, :corner_size]
    bottom_right = text_blocks[-corner_size:, -corner_size:]
    
    tl_density = np.sum(top_left > 0) / top_left.size
    tr_density = np.sum(top_right > 0) / top_right.size
    bl_density = np.sum(bottom_left > 0) / bottom_left.size
    br_density = np.sum(bottom_right > 0) / bottom_right.size
    
    top_corners = tl_density + tr_density
    bottom_corners = bl_density + br_density
    
    # Decision logic for 0° vs 180° (most common for duplex)
    # Documents typically have:
    # - Header at top (higher density in top third)
    # - More whitespace at bottom
    # - Centroid slightly above center
    # - Logos/stamps in top corners more common than bottom
    
    score_upright = 0.0
    score_inverted = 0.0
    
    # Centroid position vote (strongest signal)
    if cy_norm < 0.45:  # Content center well above middle
        score_upright += 3.0
    elif cy_norm > 0.55:  # Content center well below middle
        score_inverted += 3.0
    elif cy_norm < 0.48:
        score_upright += 1.5
    elif cy_norm > 0.52:
        score_inverted += 1.5
    
    # Density distribution vote
    density_ratio = top_density / (bottom_density + 1e-6)
    if density_ratio > 1.2:
        score_upright += 2.0
    elif density_ratio < 0.83:  # 1/1.2
        score_inverted += 2.0
    
    # Corner density vote (logos, headers)
    if top_corners > bottom_corners * 1.1:
        score_upright += 1.0
    elif bottom_corners > top_corners * 1.1:
        score_inverted += 1.0
    
    # Periodicity vote (text lines create regular patterns)
    if h_variance > v_variance * 1.2:
        # Strong horizontal structure = correct orientation
        score_upright += 1.0
    
    # Middle density check (text usually concentrated in middle)
    if middle_density > max(top_density, bottom_density) * 1.05:
        score_upright += 0.5
    
    # Final decision with confidence threshold
    if abs(score_inverted - score_upright) < 0.5:
        # Too close to call - default to upright (safer choice)
        return 0
    elif score_inverted > score_upright:
        return 180
    else:
        return 0


def detect_orientation_osd(img: Image.Image) -> Tuple[int, float]:
    """
    Detect orientation using Tesseract OSD (Orientation & Script Detection).
    Returns (angle, confidence) where angle in {0, 90, 180, 270}.
    If Tesseract/pytesseract is unavailable, returns (None, 0.0).
    """
    try:
        import pytesseract
        # Convert to RGB for pytesseract
        img_rgb = img.convert("RGB")
        osd = pytesseract.image_to_osd(img_rgb)
        # Typical output contains lines like:
        # "Rotate: 180\nOrientation confidence: 12.34\n..."
        angle_val = None
        conf_val = 0.0
        for line in osd.splitlines():
            if line.lower().startswith("rotate:"):
                try:
                    angle_val = int(line.split(":")[1].strip())
                except:
                    angle_val = None
            elif "orientation" in line.lower() and "confidence" in line.lower():
                try:
                    conf_val = float(line.split(":")[1].strip())
                except:
                    conf_val = 0.0
        # Normalize confidence to [0, 1] (heuristic: divide by 15)
        conf_norm = max(0.0, min(conf_val / 15.0, 1.0))
        if angle_val in (0, 90, 180, 270):
            return angle_val, conf_norm
        return None, 0.0
    except Exception:
        # pytesseract not installed or tesseract binary missing
        return None, 0.0

def detect_orientation_with_confidence(img: Image.Image) -> Tuple[int, float]:
    """
    Detect orientation and return confidence score.
    Returns: (angle, confidence) where confidence in [0, 1]
    """
    # Reuse the same logic but expose scores
    target_width = 600
    if img.width > target_width:
        scale = target_width / float(img.width)
        new_size = (int(img.width * scale), int(img.height * scale))
        img_small = img.resize(new_size, Image.Resampling.LANCZOS)
    else:
        img_small = img
    
    rgb = np.array(img_small.convert("RGB"))
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    h, w = gray.shape
    
    binary = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                                    cv2.THRESH_BINARY_INV, 21, 10)
    
    kernel_h = cv2.getStructuringElement(cv2.MORPH_RECT, (25, 1))
    dilated_h = cv2.dilate(binary, kernel_h, iterations=1)
    
    kernel_v = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 5))
    text_blocks = cv2.dilate(dilated_h, kernel_v, iterations=1)
    
    moments = cv2.moments(text_blocks)
    if moments['m00'] > 0:
        cx = moments['m10'] / moments['m00']
        cy = moments['m01'] / moments['m00']
        cx_norm = cx / w
        cy_norm = cy / h
    else:
        cx_norm = 0.5
        cy_norm = 0.5
    
    h_projection = np.sum(text_blocks, axis=1).astype(float)
    v_projection = np.sum(text_blocks, axis=0).astype(float)
    
    h_projection = h_projection / (np.max(h_projection) + 1e-6)
    v_projection = v_projection / (np.max(v_projection) + 1e-6)
    
    h_variance = np.var(h_projection)
    v_variance = np.var(v_projection)
    
    top_third = text_blocks[:h//3, :]
    middle_third = text_blocks[h//3:2*h//3, :]
    bottom_third = text_blocks[2*h//3:, :]
    
    top_density = np.sum(top_third > 0) / top_third.size
    middle_density = np.sum(middle_third > 0) / middle_third.size
    bottom_density = np.sum(bottom_third > 0) / bottom_third.size
    
    # Check if content is sparse (cards, small documents on white background)
    overall_density = np.sum(text_blocks > 0) / text_blocks.size
    is_sparse = overall_density < 0.15  # Less than 15% coverage
    
    # Check if content is uniform (like repeated text pattern)
    density_variance = np.var([top_density, middle_density, bottom_density])
    is_uniform = density_variance < 0.01  # Very similar densities across thirds
    
    corner_size = min(h//4, w//4)
    top_left = text_blocks[:corner_size, :corner_size]
    top_right = text_blocks[:corner_size, -corner_size:]
    bottom_left = text_blocks[-corner_size:, :corner_size]
    bottom_right = text_blocks[-corner_size:, -corner_size:]
    
    tl_density = np.sum(top_left > 0) / top_left.size
    tr_density = np.sum(top_right > 0) / top_right.size
    bl_density = np.sum(bottom_left > 0) / bottom_left.size
    br_density = np.sum(bottom_right > 0) / bottom_right.size
    
    top_corners = tl_density + tr_density
    bottom_corners = bl_density + br_density
    
    score_upright = 0.0
    score_inverted = 0.0
    
    # Edge case 1: Sparse content (cards/small docs) - invert logic
    if is_sparse:
        # For sparse content, if items are at top → likely inverted (should be at bottom after scan)
        # This handles cards placed at scanner top edge
        if cy_norm < 0.4:
            score_inverted += 3.0  # Inverted: content should be lower
        elif cy_norm > 0.6:
            score_upright += 3.0
    # Edge case 2: Uniform content (repeated text) - rely on corners more
    elif is_uniform:
        # Can't trust density distribution, focus on corners and centroid only
        if cy_norm < 0.45:
            score_upright += 2.0
        elif cy_norm > 0.55:
            score_inverted += 2.0
    else:
        # Normal case: full-page document
        # Centroid position vote (strongest signal) - MORE AGGRESSIVE
        if cy_norm < 0.42:  # Content center well above middle
            score_upright += 4.0
        elif cy_norm > 0.58:  # Content center well below middle
            score_inverted += 4.0
        elif cy_norm < 0.47:
            score_upright += 2.0
        elif cy_norm > 0.53:
            score_inverted += 2.0
    
    # Density distribution vote - MORE SENSITIVE (skip for sparse/uniform)
    if not is_sparse and not is_uniform:
        density_ratio = top_density / (bottom_density + 1e-6)
        if density_ratio > 1.15:
            score_upright += 2.5
        elif density_ratio < 0.87:  # 1/1.15
            score_inverted += 2.5
        elif density_ratio > 1.05:
            score_upright += 1.0
        elif density_ratio < 0.95:
            score_inverted += 1.0
    
    # Corner density vote (logos, headers) - STRONGER weight
    corner_ratio = top_corners / (bottom_corners + 1e-6)
    if corner_ratio > 1.2:
        score_upright += 2.0
    elif corner_ratio < 0.83:
        score_inverted += 2.0
    
    # Periodicity vote (text lines create regular patterns)
    if h_variance > v_variance * 1.2:
        # Strong horizontal structure = correct orientation
        score_upright += 1.0
    
    # Middle density check (text usually concentrated in middle)
    if not is_sparse and middle_density > max(top_density, bottom_density) * 1.05:
        score_upright += 0.5
    
    # Calculate confidence based on score difference
    total_score = score_upright + score_inverted
    if total_score < 0.1:
        confidence = 0.0
    else:
        diff = abs(score_inverted - score_upright)
        confidence = min(1.0, diff / 8.0)  # Normalize to [0, 1], higher denominator = stricter
    
    if score_inverted > score_upright:
        return (180, confidence)
    else:
        return (0, confidence)


def batch_correct_orientation(images: list[Image.Image], image_paths: list[str] = None) -> list[int]:
    """
    Smart batch orientation correction for duplex scanning.
    
    In duplex mode:
    - First batch (by time) = fronts (pages 1,3,5,7...)
    - Second batch (by time) = backs (pages 2,4,6,8...)
    
    If odd count: fronts get larger portion (user more careful with fronts)
    
    Args:
        images: List of PIL images
        image_paths: Optional list of file paths (for timestamp detection)
    
    Returns: list of rotation angles (0 or 180) for each image
    """
    n = len(images)
    if n == 0:
        return []
    
    logger.info(f"📊 Starting batch orientation detection for {n} images...")
    start_time = time.time()
    
    # Sort by creation time if paths provided
    if image_paths and len(image_paths) == n:
        # Get creation times
        file_times = []
        for path in image_paths:
            try:
                ctime = os.path.getctime(path)
                file_times.append((path, ctime))
            except:
                file_times.append((path, 0))
        
        # Sort by time
        file_times.sort(key=lambda x: x[1])
        sorted_paths = [p for p, _ in file_times]
        
        # Reorder images to match sorted paths
        path_to_idx = {p: i for i, p in enumerate(image_paths)}
        sorted_indices = [path_to_idx[p] for p in sorted_paths]
        images = [images[i] for i in sorted_indices]
        image_paths = sorted_paths
        
        print(f"📅 Images sorted by creation time:")
        for i, (path, time_val) in enumerate(file_times):
            from datetime import datetime
            dt = datetime.fromtimestamp(time_val)
            batch = "FRONTS" if i < (n + 1) // 2 else "BACKS"
            print(f"   {i+1}. {os.path.basename(path):40s} {dt.strftime('%H:%M:%S')} [{batch}]")
        
        # Keep mapping to restore original order later
        restore_indices = sorted_indices
    
    # WARNING: Odd number of images suggests missing page
    if n % 2 != 0:
        print(f"⚠️  WARNING: Odd number of images ({n}). Expected even count for duplex scanning.")
        print(f"   Assuming front batch is larger (user more careful with fronts).")
    
    # Phase 1: Individual detection with confidence
    detections = []
    for img in images:
        angle, confidence = detect_orientation_with_confidence(img)
        detections.append((angle, confidence))
    
    # Phase 2: Split into fronts and backs
    # Smart split: if odd, fronts get the extra image (scanned first, less likely to miss)
    import math
    # For 7 images: fronts=4 (ceil), backs=3 (floor)
    fronts_count = math.ceil(n / 2.0)
    backs_count = n - fronts_count
    
    fronts = detections[:fronts_count]
    backs = detections[fronts_count:]
    
    print(f"   Fronts: {fronts_count} images (indices 0-{fronts_count-1})")
    print(f"   Backs:  {backs_count} images (indices {fronts_count}-{n-1})")
    
    # Phase 3: Intelligent majority vote per batch with confidence weighting
    def smart_majority_vote(batch, batch_name="batch"):
        """
        Smart voting that considers:
        1. Confidence-weighted votes (high conf votes count more)
        2. Pattern analysis (if many images lean one way, weak signals follow)
        3. Total evidence accumulation
        """
        if not batch:
            return 0
        
        # Separate by confidence levels
        high_conf = [(a, c) for a, c in batch if c >= 0.55]
        medium_conf = [(a, c) for a, c in batch if 0.35 <= c < 0.55]
        low_conf = [(a, c) for a, c in batch if c < 0.35]
        
        # Calculate weighted scores
        score_0 = 0.0
        score_180 = 0.0
        
        # High confidence votes: full weight
        for angle, conf in high_conf:
            if angle == 0:
                score_0 += conf
            else:
                score_180 += conf
        
        # Medium confidence votes: half weight
        for angle, conf in medium_conf:
            if angle == 0:
                score_0 += conf * 0.5
            else:
                score_180 += conf * 0.5
        
        # Low confidence votes: follow the trend if clear
        if score_0 > score_180 * 1.3:
            # Clear trend toward 0°
            for angle, conf in low_conf:
                score_0 += 0.2
        elif score_180 > score_0 * 1.3:
            # Clear trend toward 180°
            for angle, conf in low_conf:
                score_180 += 0.2
        else:
            # Unclear trend - count low conf votes at low weight
            for angle, conf in low_conf:
                if angle == 0:
                    score_0 += conf * 0.3
                else:
                    score_180 += conf * 0.3
        
        # Decision with hysteresis - prefer 180° if close (safer for duplex backs)
        if score_180 >= score_0 * 0.9:  # Within 10% → choose 180°
            return 180
        else:
            return 0
    
    majority_front = smart_majority_vote(fronts, "fronts")
    majority_back = smart_majority_vote(backs, "backs")
    
    # Phase 4: Apply batch consistency correction
    corrected = []
    
    for i, (angle, conf) in enumerate(detections):
        if i < fronts_count:
            # Front batch
            if conf < 0.35:  # Low confidence - trust majority
                corrected.append(majority_front)
            elif conf < 0.60:  # Medium confidence - strengthen batch override
                # If conflicts with majority, override to majority
                if angle != majority_front:
                    corrected.append(majority_front)
                else:
                    corrected.append(angle)
            else:
                # High confidence - trust individual detection
                corrected.append(angle)
        else:
            # Back batch
            if conf < 0.35:
                corrected.append(majority_back)
            elif conf < 0.60:  # Medium confidence - strengthen batch override
                # If conflicts with majority, override to majority
                if angle != majority_back:
                    corrected.append(majority_back)
                else:
                    corrected.append(angle)
            else:
                corrected.append(angle)
    
    # Restore original order if we sorted by time
    try:
        restore_indices
        corrected_orig = [None] * n
        for sorted_pos, orig_idx in enumerate(restore_indices):
            corrected_orig[orig_idx] = corrected[sorted_pos]
        
        elapsed = time.time() - start_time
        rotated_count = sum(1 for a in corrected_orig if a == 180)
        logger.info(
            f"✅ Batch orientation complete: {n} images in {elapsed:.2f}s, "
            f"{rotated_count} need 180° rotation (fronts: {majority_front}°, backs: {majority_back}°)"
        )
        
        return corrected_orig
    except NameError:
        elapsed = time.time() - start_time
        rotated_count = sum(1 for a in corrected if a == 180)
        logger.info(
            f"✅ Batch orientation complete: {n} images in {elapsed:.2f}s, "
            f"{rotated_count} need 180° rotation (fronts: {majority_front}°, backs: {majority_back}°)"
        )
        
        return corrected


def should_rotate_180(img: Image.Image) -> bool:
    """
    Determine if image needs 180° rotation using SOTA methods.
    """
    angle = detect_orientation_angle(img)
    return angle == 180


def auto_rotate_to_upright(img: Image.Image) -> Image.Image:
    """
    Automatically rotate image to correct orientation.
    """
    angle = detect_orientation_angle(img)
    if angle == 0:
        return img
    elif angle == 90:
        return img.rotate(-90, expand=True)
    elif angle == 180:
        return img.rotate(180, expand=True)
    elif angle == 270:
        return img.rotate(90, expand=True)
    return img

def is_near_white(rgb, min_brightness=200, max_color_diff=15):
    r, g, b = rgb
    brightness = (r + g + b) / 3
    color_diff = max(abs(r-g), abs(r-b), abs(g-b))
    return brightness >= min_brightness and color_diff <= max_color_diff

def estimate_bg_from_corners(img, patch=20):
    arr = np.array(img)
    h, w, _ = arr.shape

    corners = [
        arr[0:patch, 0:patch],
        arr[0:patch, w-patch:w],
        arr[h-patch:h, 0:patch],
        arr[h-patch:h, w-patch:w],
    ]

    valid_colors = []

    for c in corners:
        avg = tuple(np.mean(c.reshape(-1,3), axis=0))
        if is_near_white(avg):
            valid_colors.append(avg)

    if not valid_colors:
        return None  # fallback needed

    return tuple(np.median(valid_colors, axis=0).astype(int))



def get_robust_bg(pixels):
    # Lấy các pixel nằm trong khoảng "an toàn"
    p25 = np.percentile(pixels, 25, axis=0)
    p75 = np.percentile(pixels, 75, axis=0)
    
    # Lọc những pixel nằm giữa p25 và p75
    mask = np.all((pixels >= p25) & (pixels <= p75), axis=1)
    safe_pixels = pixels[mask]
    
    # Trả về trung bình của vùng an toàn này
    return np.mean(safe_pixels, axis=0).astype(int)

def rotate_with_auto_fill(image_path, angle, pad_size=20):
    # 1. Mở ảnh
    img = Image.open(image_path).convert("RGB")
    img_array = np.array(img)

    # 2. Lấy mẫu màu nền từ 4 cạnh (mỗi cạnh lấy pad_size pixel)
    # Chúng ta lấy median để tránh các vết ố hoặc chữ sát viền làm sai màu
    top_edge = img_array[:pad_size, :, :]
    bottom_edge = img_array[-pad_size:, :, :]
    left_edge = img_array[:, :pad_size, :]
    right_edge = img_array[:, -pad_size:, :]

    all_edge_pixels = np.concatenate([
        top_edge.reshape(-1, 3), 
        bottom_edge.reshape(-1, 3), 
        left_edge.reshape(-1, 3), 
        right_edge.reshape(-1, 3)
    ])

    bg_color = get_robust_bg(all_edge_pixels)
    rotated_img = img.rotate(
        angle, 
        expand=True,      # Để không bị mất góc ảnh
        resample=Image.BICUBIC, 
        fillcolor=tuple(bg_color)
    )

    return rotated_img

def deskew_image(fileName: str, img: Image.Image) -> Tuple[Image.Image, float]:
    """
    Correct skew/tilt in scanned document.
    
    Args:
        fileName: Path to image file (for logging)
        img: PIL Image to deskew
    
    Returns:
        Deskewed PIL Image
    
    Memory optimization for Android box:
    - Downsample before processing (saves RAM)
    - Delete temp arrays immediately after use
    - Auto-detect blank pages and skip processing
    """
    # Downsample for speed (600px width uses ~1MB RAM vs ~10MB for 2000px)
    target_width = 600
    if img.width > target_width:
        scale = target_width / float(img.width)
        new_size = (int(img.width * scale), int(img.height * scale))
        img_small = img.resize(new_size, Image.Resampling.LANCZOS)
    else:
        img_small = img
    
    converted = np.array(img_small)

    # Blank page detection (auto-skip if detected)
    gray = cv2.cvtColor(converted, cv2.COLOR_RGB2GRAY)
    h, w = gray.shape
    mean_intensity = np.mean(gray)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    content_density = np.sum(binary > 0) / (h * w)
    
    # Free memory immediately
    del gray, binary
    
    if mean_intensity > 240 and content_density < 0.02:
        print(f"Deskewing '{os.path.basename(fileName)}': blank page, skipping.")
        del converted, img_small
        # Return a consistent tuple: (image, deskew_angle)
        return img, 0.0

    # Get background color from edges (use downsampled image to save RAM)
    pad_size = 20
    
    # Sample edges efficiently
    top_edge = converted[:pad_size, :, :]
    bottom_edge = converted[-pad_size:, :, :]
    left_edge = converted[:, :pad_size, :]
    right_edge = converted[:, -pad_size:, :]
    
    all_edge_pixels = np.concatenate([
        top_edge.reshape(-1, 3), 
        bottom_edge.reshape(-1, 3), 
        left_edge.reshape(-1, 3), 
        right_edge.reshape(-1, 3)
    ])
    
    bg_color = get_robust_bg(all_edge_pixels)
    
    # Free edge arrays immediately
    del top_edge, bottom_edge, left_edge, right_edge, all_edge_pixels

    # Detect skew angle
    angle = deskew.determine_skew(converted, min_angle=-15, max_angle=15, min_deviation=0.2, num_peaks=15)
    if angle is None:
        angle = 0.0
    
    # Free converted array
    del converted, img_small
    
    
    print(f"Deskewing '{os.path.basename(fileName)}': angle = {angle:.2f}°")
    
    rotated_img = img.rotate(angle, resample=Image.Resampling.BICUBIC, expand=False, fillcolor=tuple(bg_color))
    return rotated_img, angle

def crop_document_v2(img: Image.Image, processing_width: int = 800, debug: bool = True, img_name: str = None) -> Tuple[Image.Image, Tuple[int, int, int, int]]:
    """
    Crop document using background removal approach (v2).
    
    Strategy:
    1. Resize image down to speed up processing
    2. Remove background using withoutbg library
    3. Find bounding box of foreground (non-transparent pixels)
    4. Scale coordinates back to original image
    5. Crop original image (tight crop, no margin)
    
    Args:
        img: Input PIL Image
        processing_width: Width to resize for processing (default 800px)
        debug: If True, save intermediate images to debug/ folder
        img_name: Optional image filename to use as debug prefix (basename without extension)
    
    Returns:
        Tuple of (cropped PIL Image, bbox as (x, y, w, h))
    """
    original_width, original_height = img.size
    # Step 1: Resize down for faster processing
    if img.width > processing_width:
        scale = processing_width / float(img.width)
        new_size = (int(img.width * scale), int(img.height * scale))
        img_small = img.resize(new_size, Image.Resampling.LANCZOS)
    else:
        img_small = img
        scale = 1.0

    converted = np.array(img_small)
    pad_size = 20
    # Sample edges efficiently
    top_edge = converted[:pad_size, :, :]
    bottom_edge = converted[-pad_size:, :, :]
    left_edge = converted[:, :pad_size, :]
    right_edge = converted[:, -pad_size:, :]
    
    all_edge_pixels = np.concatenate([
        top_edge.reshape(-1, 3), 
        bottom_edge.reshape(-1, 3), 
        left_edge.reshape(-1, 3), 
        right_edge.reshape(-1, 3)
    ])
    
    bg_color = get_robust_bg(all_edge_pixels)
    
    # Step 2: Remove background
    try:
        # Get cached model (loaded once, reused for all images)
        model = _get_bg_removal_model()

        result_rgba = model.remove_background(img_small)  # Returns PIL Image with alpha channel
        
        # Step 3: Find bounding box from alpha channel
        # Convert to numpy array and get alpha channel
        rgba_array = np.array(result_rgba)
        if rgba_array.shape[2] == 4:  # Has alpha channel
            # Get raw alpha channel (don't zero out pixels yet)
            alpha = rgba_array[:, :, 3]
        else:
            # Fallback: if no alpha, assume all non-white is foreground
            gray = cv2.cvtColor(rgba_array[:, :, :3], cv2.COLOR_RGB2GRAY)
            _, alpha = cv2.threshold(gray, 250, 255, cv2.THRESH_BINARY_INV)
        
        # CRITICAL FIX: Hybrid approach - both remove definite BG and boost definite document
        # Case A: Model leaves white fog → identify and force alpha=0
        # Case B: Model ghosts document → identify and boost alpha=255
        # Case C: Uncertain → keep original alpha → let threshold decide
        
        rgb_pixels = rgba_array[:, :, :3]  # Get RGB channels (HxWx3)
        
        # Calculate color metrics
        bg_dist = np.linalg.norm(rgb_pixels - bg_color, axis=-1)  # Distance from bgcolor
        brightness = np.mean(rgb_pixels, axis=-1)  # Brightness (0-255)
        rgb_min = np.min(rgb_pixels, axis=-1)
        rgb_max = np.max(rgb_pixels, axis=-1)
        saturation = np.where(rgb_max > 0, (rgb_max - rgb_min) / rgb_max, 0)  # Saturation (0-1)
        
        # Strategy 1: BLACKLIST - Force remove definite background
        # Very strict criteria (all must be true):
        is_very_close_bg = bg_dist < 20  # Almost identical to bgcolor (stricter)
        is_very_bright = brightness > 230  # Very very white (stricter)
        is_very_desaturated = saturation < 0.03  # Pure grayscale (stricter)
        is_low_alpha = alpha < 80  # Model marked as very transparent (stricter)
        
        is_definite_background = is_very_close_bg & is_very_bright & is_very_desaturated & is_low_alpha
        
        # Strategy 2: WHITELIST - Force boost definite document
        # Use ONLY clear indicators, NO medium alpha check (too risky for fog)
        is_dark = brightness < 165  # Text, dark content (slightly relaxed)
        is_saturated = saturation > 0.12  # Colored content (tightened - avoid pastels near fog)
        is_far_from_bg = bg_dist > 70  # Very clearly different from background (tightened)
        
        # NEW: Spatial context - boost pixels NEAR document CORE (shadows, watermarks)
        # Strategy: Erode first to get core, then dilate to find proximity zone
        temp_doc_mask = (is_dark | is_saturated | is_far_from_bg).astype(np.uint8)
        
        # Step 1: Erode to get document core (remove edges/noise)
        kernel_erode = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        doc_core_mask = cv2.erode(temp_doc_mask, kernel_erode, iterations=1)
        
        # Step 2: Dilate core to create proximity zone (catch nearby content)
        kernel_dilate = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11))
        doc_proximity_mask = cv2.dilate(doc_core_mask, kernel_dilate, iterations=1)
        
        # Protect pixels in proximity zone - distinguish SHADOW vs DOCUMENT GHOST
        # Shadow characteristics: low saturation, gradual brightness change, similar to background
        # Document ghost: distinct color/texture, sharp edges, clearly different from background
        is_near_core = (doc_proximity_mask > 0) & (alpha > 70) & (alpha < 200)  # Near core, medium alpha
        
        # CRITICAL: Much stricter criteria to avoid boosting shadows
        # Must have CLEAR document characteristics, not just "not fog"
        is_clearly_document = (
            (saturation > 0.15) |  # Strong color (not gray shadow) - tightened from 0.12
            (bg_dist > 85) |       # Very different from background - tightened from 70
            ((brightness < 140) & (alpha > 120))  # Dark + decent alpha (text/content, not shadow gradient)
        )
        is_document_ghost = is_near_core & is_clearly_document
        
        # Combine: original definite + ONLY clear document ghosts (no shadows)
        is_definite_document = ((is_dark | is_saturated | is_far_from_bg | is_document_ghost) & (alpha > 30))  # Has some alpha
        
        # Apply hybrid logic:
        # 1. Definite background → alpha=0
        # 2. Definite document → alpha=255
        # 3. Uncertain → keep original alpha
        alpha_processed = np.where(is_definite_background, 0, alpha)  # Remove BG first
        alpha_processed = np.where(is_definite_document, 255, alpha_processed)  # Boost document
        alpha_processed = alpha_processed.astype(np.uint8)
        
        # For safeguard: protect all document pixels
        protected_mask = is_definite_document.astype(np.uint8)
        
        if debug:
            bg_removed = np.sum(is_definite_background)
            doc_boosted = np.sum(is_definite_document)
            uncertain = np.sum(~is_definite_background & ~is_definite_document)
            print(f"   Hybrid stats: BG_removed={bg_removed}, Doc_boosted={doc_boosted}, Uncertain={uncertain}")
            # Save protected mask for inspection

        # Use processed alpha for all subsequent processing
        alpha = alpha_processed
        # For safeguard: keep protected document pixels
        recovered_mask = protected_mask

        # Build a clean foreground mask using multi-stage intelligent filtering
        # Problem: Background removal models have various failure modes:
        #   1. Gradient halos around edges (alpha 50-200 instead of 0/255)
        #   2. Multiple foreground objects (document + hand/shadow)
        #   3. Noisy alpha with scattered mid-values
        # Solution: Multi-stage pipeline with spatial intelligence
        try:
            h_alpha, w_alpha = alpha.shape
            alpha_nonzero = alpha[alpha > 10]
            
            if len(alpha_nonzero) < 100:
                alpha_threshold = 80
                mask = (alpha > alpha_threshold).astype(np.uint8) * 255
            else:
                # Stage 1: Initial threshold using adaptive method
                # Try multiple methods and pick the one with best validation score
                candidate_thresholds = []
                
                # Method 1: Otsu (good for bimodal)
                try:
                    from skimage.filters import threshold_otsu
                    t1 = threshold_otsu(alpha_nonzero)
                    if 30 < t1 < 220:
                        candidate_thresholds.append(('otsu', int(t1)))
                except:
                    pass
                
                # Method 2: High percentile (good for documents with halo)
                t2 = int(np.percentile(alpha_nonzero, 70))
                candidate_thresholds.append(('p70', max(50, min(200, t2))))
                
                # Method 3: Mean of top 30% (robust to outliers)
                sorted_alpha = np.sort(alpha_nonzero)
                top_30_start = int(len(sorted_alpha) * 0.7)
                t3 = int(np.mean(sorted_alpha[top_30_start:])) - 40  # Offset to catch edges
                candidate_thresholds.append(('top30', max(40, min(180, t3))))
                
                # Evaluate each threshold by foreground ratio (expect 5-60% for documents)
                best_threshold = 80
                best_score = float('inf')
                
                for method, thresh in candidate_thresholds:
                    test_mask = (alpha > thresh).astype(np.uint8) * 255
                    fg_ratio = np.sum(test_mask > 0) / test_mask.size
                    
                    # Penalize if too small (<3%) or too large (>70%)
                    if fg_ratio < 0.03:
                        penalty = (0.03 - fg_ratio) * 100
                    elif fg_ratio > 0.70:
                        penalty = (fg_ratio - 0.70) * 50
                    else:
                        penalty = 0
                    
                    # Prefer mid-range thresholds (60-150) for stability
                    if thresh < 60:
                        penalty += (60 - thresh) * 0.2
                    elif thresh > 150:
                        penalty += (thresh - 150) * 0.2
                    
                    if penalty < best_score:
                        best_score = penalty
                        best_threshold = thresh
                        best_method = method
                
                alpha_threshold = best_threshold
                mask = (alpha > alpha_threshold).astype(np.uint8) * 255
                
                # CRITICAL: Clean up fog/uncertain pixels BEFORE safeguard
                # Fog has medium alpha (100-200) but wasn't boosted to 255
                # Remove pixels that are: high alpha BUT NOT boosted (likely fog/shadow)
                is_fog_candidate = (alpha > 100) & (alpha < 255)  # Medium alpha, not boosted
                is_bright_fog = (brightness > 200) & (saturation < 0.05) & (bg_dist < 50)  # Fog characteristics
                should_remove_fog = is_fog_candidate & is_bright_fog
                mask = np.where(should_remove_fog, 0, mask).astype(np.uint8)
                
                # SAFEGUARD: Protect pixels that were boosted to 255 (confirmed document)
                is_boosted_document = (alpha == 255)
                mask = np.where(is_boosted_document, 255, mask).astype(np.uint8)
                
                if debug:
                    fg_ratio = np.sum(mask > 0) / mask.size
                    safeguard_count = np.sum(is_boosted_document)
                    fog_removed_count = np.sum(should_remove_fog)
                    print(f"   ✓ Threshold: {alpha_threshold} ({best_method}), fg ratio: {fg_ratio:.1%}")
                    print(f"   ✓ Fog removed: {fog_removed_count} pixels")
                    print(f"   ✓ Safeguard: forced {safeguard_count} boosted pixels into mask")
                
                # Stage 2: Spatial filtering - keep only the most "document-like" component
                # Documents are typically: rectangular, centered, medium-large size
                num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(mask, connectivity=8)
                
                if num_labels > 2:  # More than just background + 1 object
                    # Score each component by "document-likeness"
                    component_scores = []
                    
                    for i in range(1, num_labels):  # Skip label 0 (background)
                        area = stats[i, cv2.CC_STAT_AREA]
                        x = stats[i, cv2.CC_STAT_LEFT]
                        y = stats[i, cv2.CC_STAT_TOP]
                        w = stats[i, cv2.CC_STAT_WIDTH]
                        h = stats[i, cv2.CC_STAT_HEIGHT]
                        cx, cy = centroids[i]
                        
                        # Skip tiny components (noise)
                        if area < h_alpha * w_alpha * 0.005:  # <0.5% of image
                            continue
                        
                        # Calculate document-likeness score (higher = more likely document)
                        score = 0
                        
                        # Factor 1: Size (prefer medium-large, 5-60% of image)
                        size_ratio = area / (h_alpha * w_alpha)
                        if 0.05 < size_ratio < 0.60:
                            score += 100 * size_ratio
                        elif size_ratio >= 0.60:
                            score += 30  # Penalize too large
                        
                        # Factor 2: Aspect ratio (documents are typically 1.4-1.7 for cards, 1.3-1.5 for A4)
                        aspect = max(w, h) / max(min(w, h), 1)
                        if 1.2 < aspect < 2.0:
                            score += 30
                        
                        # Factor 3: Rectangularity (area / bounding_box_area)
                        rectangularity = area / (w * h) if w * h > 0 else 0
                        if rectangularity > 0.7:  # Documents are ~rectangular
                            score += 40 * rectangularity
                        
                        # Factor 4: Position (prefer centered objects)
                        center_dist_x = abs(cx - w_alpha / 2) / w_alpha
                        center_dist_y = abs(cy - h_alpha / 2) / h_alpha
                        center_score = (1 - center_dist_x) * 20 + (1 - center_dist_y) * 20
                        score += center_score
                        
                        # Factor 5: Not touching image borders (documents are usually cropped)
                        # Edges touching borders might be hands/shadows
                        border_margin = 5
                        touches_border = (x < border_margin or y < border_margin or 
                                        x + w > w_alpha - border_margin or 
                                        y + h > h_alpha - border_margin)
                        if not touches_border:
                            score += 25
                        
                        component_scores.append((i, score, area))
                    
                    if len(component_scores) > 0:
                        # Keep only top scoring component (most document-like)
                        component_scores.sort(key=lambda x: x[1], reverse=True)
                        best_component_idx = component_scores[0][0]
                        
                        # Create new mask with only the best component
                        mask_filtered = (labels == best_component_idx).astype(np.uint8) * 255
                        
                        if debug:
                            print(f"   ✓ Filtered {num_labels-1} components, kept best (score: {component_scores[0][1]:.1f})")
                            if len(component_scores) > 1:
                                print(f"      Rejected: {[(f'comp{i}', f'{s:.0f}') for i, s, _ in component_scores[1:3]]}")
                        
                        mask = mask_filtered
                
        except Exception as e:
            print(f"Warning: Adaptive threshold failed ({e}), using fallback")
            import traceback
            traceback.print_exc()
            # Simple fallback: use fixed threshold
            # Note: alpha already recovered above, so this is safe
            alpha_threshold = 80
            mask = (alpha > alpha_threshold).astype(np.uint8) * 255
                

        # Morphology to fill small holes and connect fragmented regions
        h_s, w_s = mask.shape
        # Kernel size relative to image size - moderate to balance detail vs robustness
        # Use 1.5% of image dimension (balanced approach)
        k = max(3, min(11, int(min(h_s, w_s) * 0.015)))
        kernel = np.ones((k, k), np.uint8)
        
        # Simplified morphology - just close operation (no dilation)
        # This fills internal gaps without expanding boundaries excessively
        mask_closed = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)

        # Connected components: find and merge foreground objects
        num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(mask_closed, connectivity=8)

        if num_labels <= 1:
            # Fallback to simple row/col projection if no components found
            rows = np.any(mask_closed > 0, axis=1)
            cols = np.any(mask_closed > 0, axis=0)
            if not rows.any() or not cols.any():
                print("crop_document_v2: No foreground detected, returning original image")
                return img
            y_min, y_max = np.where(rows)[0][[0, -1]]
            x_min, x_max = np.where(cols)[0][[0, -1]]
        else:
            # Strategy: Use convex hull of ALL significant components (not just largest)
            # This prevents missing document parts that got fragmented
            
            # Find all components with reasonable size (>0.5% of image)
            areas = stats[1:, cv2.CC_STAT_AREA]
            min_area = h_s * w_s * 0.005  # 0.5% threshold
            significant_indices = [i+1 for i, area in enumerate(areas) if area > min_area]
            
            if not significant_indices:
                # No significant components - use projection fallback
                rows = np.any(mask_closed > 0, axis=1)
                cols = np.any(mask_closed > 0, axis=0)
                if not rows.any() or not cols.any():
                    print("crop_document_v2: No foreground detected, returning original image")
                    return img
                y_min, y_max = np.where(rows)[0][[0, -1]]
                x_min, x_max = np.where(cols)[0][[0, -1]]
            else:
                # Collect all points from significant components
                all_points = []
                for idx in significant_indices:
                    component_mask = (labels == idx).astype(np.uint8) * 255
                    contours, _ = cv2.findContours(component_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                    for contour in contours:
                        all_points.extend(contour.reshape(-1, 2))
                
                if len(all_points) > 0:
                    # Compute convex hull of all points (tightest enclosing polygon)
                    all_points = np.array(all_points)
                    hull = cv2.convexHull(all_points)
                    
                    # Get bounding box of convex hull
                    x_min = int(np.min(hull[:, 0, 0]))
                    y_min = int(np.min(hull[:, 0, 1]))
                    x_max = int(np.max(hull[:, 0, 0]))
                    y_max = int(np.max(hull[:, 0, 1]))
                else:
                    # Fallback if no contours found
                    rows = np.any(mask_closed > 0, axis=1)
                    cols = np.any(mask_closed > 0, axis=0)
                    y_min, y_max = np.where(rows)[0][[0, -1]]
                    x_min, x_max = np.where(cols)[0][[0, -1]]
        
        # Step 4: Scale coordinates back to original image with safety margin
        scale_x = original_width / img_small.width
        scale_y = original_height / img_small.height
        
        x_min_orig = int(x_min * scale_x)
        x_max_orig = int(x_max * scale_x)
        y_min_orig = int(y_min * scale_y)
        y_max_orig = int(y_max * scale_y)
        
        # Add 0.5% margin on all sides to prevent edge cutting (balanced approach)
        # Smaller margin to avoid oversized bbox, but still prevents "lẹm"
        margin_x = int(original_width * 0.005)
        margin_y = int(original_height * 0.005)
        
        x_min_orig = max(0, x_min_orig - margin_x)
        y_min_orig = max(0, y_min_orig - margin_y)
        x_max_orig = min(original_width, x_max_orig + margin_x)
        y_max_orig = min(original_height, y_max_orig + margin_y)
        
        # Step 5: Crop original image
        cropped = img.crop((x_min_orig, y_min_orig, x_max_orig, y_max_orig))
        
        # Calculate bbox in original image coordinates (x, y, w, h)
        bbox = (x_min_orig, y_min_orig, x_max_orig - x_min_orig, y_max_orig - y_min_orig)
        
        if debug:
            # Draw bounding box on original image for visualization
            img_with_box = img.copy()
            draw = ImageDraw.Draw(img_with_box)
            draw.rectangle([(x_min_orig, y_min_orig), (x_max_orig, y_max_orig)], outline="red", width=5)
            print(f"🐛 Crop coordinates: ({x_min_orig}, {y_min_orig}) to ({x_max_orig}, {y_max_orig})")
            print(f"🐛 Bbox (x,y,w,h): {bbox}")
        
        print(f"crop_document_v2: Cropped from {original_width}x{original_height} to {cropped.width}x{cropped.height}")
        return cropped, bbox
        
    except Exception as e:
        print(f"crop_document_v2: Error during background removal: {e}")
        print("Returning original image")
        return img, (0, 0, img.width, img.height)
