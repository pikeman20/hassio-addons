from __future__ import annotations

from typing import Tuple, List
from PIL import Image


def quadrant_bounds(page_width: int, page_height: int, q: Tuple[int, int]) -> Tuple[int, int, int, int]:
    """Return (x, y, w, h) in points for the given quadrant.
    Quadrants: (0,0)=top-left, (0,1)=top-right, (1,0)=bottom-left, (1,1)=bottom-right.
    Coordinate system: reportlab has origin at bottom-left.
    """
    half_w = page_width // 2
    half_h = page_height // 2
    r, c = q
    # Convert to reportlab coordinates
    if r == 0 and c == 0:
        # top-left
        x = 0
        y = half_h
    elif r == 0 and c == 1:
        # top-right
        x = half_w
        y = half_h
    elif r == 1 and c == 0:
        # bottom-left
        x = 0
        y = 0
    else:
        # bottom-right
        x = half_w
        y = 0
    return (x, y, half_w, half_h)


def fit_within(w: int, h: int, target_w: int, target_h: int, margin: int) -> Tuple[int, int]:
    tw = max(0, target_w - 2 * margin)
    th = max(0, target_h - 2 * margin)
    scale = min(tw / float(w), th / float(h)) if w and h else 1.0
    return (int(w * scale), int(h * scale))


def fit_1to1(w: int, h: int, target_w: int, target_h: int, margin: int, dpi: int = 300) -> Tuple[int, int]:
    """Fit image at physical 1:1 scale (no upscaling).
    
    Converts pixels to points at given DPI (default 300 for scanner).
    - 1 inch = 72 points
    - At 300 DPI: 1 inch = 300 pixels
    - So: points = pixels * 72 / 300
    
    For card_2in1 and scan_document: preserve actual physical size.
    """
    tw = max(0, target_w - 2 * margin)
    th = max(0, target_h - 2 * margin)
    
    # Convert pixels to points at scanner DPI
    w_pt = int(w * 72.0 / dpi)
    h_pt = int(h * 72.0 / dpi)
    
    # Clamp if exceeds target (downscale only, never upscale)
    if w_pt > tw or h_pt > th:
        scale = min(tw / float(w_pt), th / float(h_pt))
        return (int(w_pt * scale), int(h_pt * scale))
    
    # Return physical size in points
    return (w_pt, h_pt)


def can_fit_in_quadrant(img_w: int, img_h: int, quadrant_w: int, quadrant_h: int, margin: int, dpi: int = 300) -> bool:
    """Check if image fits in quadrant at 1:1 physical scale.
    
    Returns True if image can fit within quadrant bounds (with margin).
    """
    target_w = max(0, quadrant_w - 2 * margin)
    target_h = max(0, quadrant_h - 2 * margin)
    
    # Convert image pixels to points at scanner DPI
    img_w_pt = int(img_w * 72.0 / dpi)
    img_h_pt = int(img_h * 72.0 / dpi)
    
    return img_w_pt <= target_w and img_h_pt <= target_h


def determine_document_span(img_w: int, img_h: int, page_w: int, page_h: int, margin: int, dpi: int = 300) -> str:
    """Determine how many grid cells a document spans at 1:1 physical scale.
    
    Returns:
        "single": Fits in 1 quadrant (2x2 grid)
        "half_horizontal": Fits in 1x2 (top or bottom half)
        "half_vertical": Fits in 2x1 (left or right half)
        "full": Full page (no scale, may overflow if too large)
    """
    half_w = page_w // 2
    half_h = page_h // 2
    
    # Convert image pixels to points at scanner DPI (1:1 physical scale)
    img_w_pt = int(img_w * 72.0 / dpi)
    img_h_pt = int(img_h * 72.0 / dpi)
    
    # Check if fits in 1 quadrant (2x2 grid)
    if can_fit_in_quadrant(img_w, img_h, half_w, half_h, margin, dpi):
        return "single"
    
    # Check if fits in horizontal half (1x2 grid: full width, half height)
    full_w_avail = max(0, page_w - 2 * margin)
    half_h_avail = max(0, half_h - 2 * margin)
    
    if img_w_pt <= full_w_avail and img_h_pt <= half_h_avail:
        return "half_horizontal"
    
    # Check if fits in vertical half (2x1 grid: half width, full height)
    half_w_avail = max(0, half_w - 2 * margin)
    full_h_avail = max(0, page_h - 2 * margin)
    
    if img_w_pt <= half_w_avail and img_h_pt <= full_h_avail:
        return "half_vertical"
    
    # Full page (1:1 scale, no scaling even if overflow)
    return "full"


def compute_document_position(bbox_x: int, bbox_y: int, bbox_w: int, bbox_h: int, 
                              scan_w: int, scan_h: int, 
                              img_w: int, img_h: int,
                              page_w: int, page_h: int, 
                              margin: int, span: str, dpi: int = 300) -> Tuple[int, int]:
    """Compute draw position for document based on scanned position.
    NO SCALING - always 1:1 physical size.
    
    Args:
        bbox_x, bbox_y, bbox_w, bbox_h: Bounding box in scan image (before crop)
        scan_w, scan_h: Scan image dimensions
        img_w, img_h: Cropped document dimensions
        page_w, page_h: PDF page dimensions
        margin: Margin in points
        span: Document span type from determine_document_span()
        dpi: Scanner DPI
    
    Returns:
        (draw_x, draw_y): Position for rendering at 1:1 scale
    """
    # Convert cropped image to points (1:1 physical scale)
    img_w_pt = int(img_w * 72.0 / dpi)
    img_h_pt = int(img_h * 72.0 / dpi)
    
    # Compute center of bbox in scan image (normalized 0-1)
    cx_norm = (bbox_x + bbox_w / 2.0) / scan_w
    cy_norm = (bbox_y + bbox_h / 2.0) / scan_h
    
    half_w = page_w // 2
    half_h = page_h // 2
    
    if span == "single":
        # Determine quadrant from center position
        if cx_norm < 0.5 and cy_norm < 0.5:
            # Top-left quadrant [0][0]
            region_x, region_y, region_w, region_h = 0, half_h, half_w, half_h
        elif cx_norm >= 0.5 and cy_norm < 0.5:
            # Top-right quadrant [0][1]
            region_x, region_y, region_w, region_h = half_w, half_h, half_w, half_h
        elif cx_norm < 0.5 and cy_norm >= 0.5:
            # Bottom-left quadrant [1][0]
            region_x, region_y, region_w, region_h = 0, 0, half_w, half_h
        else:
            # Bottom-right quadrant [1][1]
            region_x, region_y, region_w, region_h = half_w, 0, half_w, half_h
        
        # Top-left anchor within quadrant
        draw_x = region_x + margin
        draw_y = region_y + region_h - margin - img_h_pt
        return (draw_x, draw_y)
        
    elif span == "half_horizontal":
        # Determine top or bottom half from cy_norm
        if cy_norm < 0.5:
            # Top half: [0][0] + [0][1]
            region_x, region_y, region_w, region_h = 0, half_h, page_w, half_h
        else:
            # Bottom half: [1][0] + [1][1]
            region_x, region_y, region_w, region_h = 0, 0, page_w, half_h
        
        # Determine x position from cx_norm (preserve left/center/right intent)
        if cx_norm < 0.33:
            # Left-aligned
            draw_x = region_x + margin
        elif cx_norm > 0.67:
            # Right-aligned
            draw_x = region_x + region_w - margin - img_w_pt
        else:
            # Center-aligned
            draw_x = region_x + (region_w - img_w_pt) // 2
        
        draw_y = region_y + region_h - margin - img_h_pt
        return (draw_x, draw_y)
        
    elif span == "half_vertical":
        # Determine left or right half from cx_norm
        if cx_norm < 0.5:
            # Left half: [0][0] + [1][0]
            region_x, region_y, region_w, region_h = 0, 0, half_w, page_h
        else:
            # Right half: [0][1] + [1][1]
            region_x, region_y, region_w, region_h = half_w, 0, half_w, page_h
        
        # Determine y position from cy_norm (preserve top/center/bottom intent)
        if cy_norm < 0.33:
            # Top-aligned
            draw_y = region_y + region_h - margin - img_h_pt
        elif cy_norm > 0.67:
            # Bottom-aligned
            draw_y = region_y + margin
        else:
            # Center-aligned
            draw_y = region_y + (region_h - img_h_pt) // 2
        
        draw_x = region_x + margin
        return (draw_x, draw_y)
        
    else:  # span == "full"
        # Full page - NO SCALING, just center on page
        # Center on page (may overflow if too large, but that's acceptable)
        draw_x = (page_w - img_w_pt) // 2
        draw_y = (page_h - img_h_pt) // 2
        
        return (draw_x, draw_y)


def anchor_position(q: Tuple[int, int], x: int, y: int, w: int, h: int, img_w: int, img_h: int, margin: int) -> Tuple[int, int]:
    """Anchor image in the quadrant with top-left alignment.
    
    All quadrants anchor from top-left corner to keep images close together.
    Returns (draw_x, draw_y) for reportlab (origin at bottom-left).
    """
    r, c = q
    
    # All positions start from top of their quadrant, left-aligned
    draw_x = x + margin
    draw_y = y + h - margin - img_h  # Top of quadrant
    
    return (draw_x, draw_y)


def layout_documents_smart(doc_items: List[Tuple[str, Tuple[int, int], Image.Image, float]], 
                          page_w: int, page_h: int, margin: int) -> List[List[Tuple[str, Tuple[int, int], Image.Image, float]]]:
    """Tetris-style layout engine - fills documents optimally using quadrant tracking.
    
    Uses "Tetris" placement: tries to fit each document in available space on current page,
    starts new page only if no space available.
    
    Each document type occupies different quadrants:
    - "single": 1 quadrant (tl/tr/bl/br)
    - "half_horizontal": 2 quadrants (top: tl+tr, bottom: bl+br)
    - "half_vertical": 2 quadrants (left: tl+bl, right: tr+br)
    - "full": All 4 quadrants (entire page)
    
    Args:
        doc_items: List of (span, (ignored_pos), cropped_image, scan_dpi, rotation, deskew, filename)
        page_w, page_h: Page dimensions in points
        margin: Margin in points
    
    Returns:
        List of pages, each page is list of doc_items with calculated positions
    """
    if not doc_items:
        return []
    
    pages = []
    current_page = []
    page_num = 1
    
    half_w = page_w // 2
    half_h = page_h // 2
    
    # Track quadrant occupancy for smart "Tetris" placement
    quadrants_occupied = {
        "tl": False,
        "tr": False,
        "bl": False,
        "br": False
    }
    
    def check_and_place(required_quadrants, span_type, img_ref, dpi_ref, get_position_func):
        """Check if required quadrants are available, place if yes, else start new page."""
        nonlocal current_page, page_num, quadrants_occupied
        
        # Check if all required quadrants are available
        all_available = all(not quadrants_occupied[q] for q in required_quadrants)
        
        if not all_available:
            # Start new page
            if current_page:
                pages.append(current_page)
            page_num += 1
            current_page = []
            quadrants_occupied.update({"tl": False, "tr": False, "bl": False, "br": False})
        
        # Place document
        draw_x, draw_y = get_position_func()
        current_page.append((span_type, (draw_x, draw_y), img_ref, dpi_ref))
        
        # Mark quadrants as occupied
        for q in required_quadrants:
            quadrants_occupied[q] = True
    
    # Quadrant base positions (will be centered in PDF rendering)
    quadrant_positions = {
        "tl": (margin, half_h),
        "tr": (half_w + margin, half_h),
        "bl": (margin, 0),
        "br": (half_w + margin, 0)
    }
    
    for doc_idx, item in enumerate(doc_items):
        span, _, img, scan_dpi = item[0], item[1], item[2], item[3]
        
        if span == "single":
            # Try to find first available quadrant: tl, tr, bl, br
            for q in ["tl", "tr", "bl", "br"]:
                if not quadrants_occupied[q]:
                    check_and_place([q], span, img, scan_dpi, lambda pos=quadrant_positions[q]: pos)
                    break
            else:
                # All quadrants occupied - force new page
                check_and_place(["tl"], span, img, scan_dpi, lambda: quadrant_positions["tl"])
            
        elif span == "half_horizontal":
            # Try top half (tl+tr), then bottom half (bl+br)
            if not quadrants_occupied["tl"] and not quadrants_occupied["tr"]:
                check_and_place(["tl", "tr"], span, img, scan_dpi, lambda: (margin, half_h))
            elif not quadrants_occupied["bl"] and not quadrants_occupied["br"]:
                check_and_place(["bl", "br"], span, img, scan_dpi, lambda: (margin, 0))
            else:
                # Both halves occupied - force new page, use top half
                check_and_place(["tl", "tr"], span, img, scan_dpi, lambda: (margin, half_h))
            
        elif span == "half_vertical":
            # Try left half (tl+bl), then right half (tr+br)
            if not quadrants_occupied["tl"] and not quadrants_occupied["bl"]:
                check_and_place(["tl", "bl"], span, img, scan_dpi, lambda: (margin, 0))
            elif not quadrants_occupied["tr"] and not quadrants_occupied["br"]:
                check_and_place(["tr", "br"], span, img, scan_dpi, lambda: (half_w + margin, 0))
            else:
                # Both halves occupied - force new page, use left half
                check_and_place(["tl", "bl"], span, img, scan_dpi, lambda: (margin, 0))
            
        else:  # span == "full"
            # Full page - always start fresh page
            if current_page:
                print(f"  → Full page needs fresh page, saving page {page_num}")
                pages.append(current_page)
                page_num += 1
                current_page = []
                quadrants_occupied.update({"tl": False, "tr": False, "bl": False, "br": False})
            
            print(f"  → Placing full page at ({margin}, {margin})")
            pages.append([(span, (margin, margin), img, scan_dpi)])
            page_num += 1
            current_page = []
            quadrants_occupied.update({"tl": False, "tr": False, "bl": False, "br": False})
    
    # Don't forget last page
    if current_page:
        pages.append(current_page)
    
    return pages


def layout_items_by_orientation(images: List[Image.Image]) -> List[List[Tuple[Tuple[int, int], Image.Image]]]:
    """Generic layout engine for card_2in1 and scan_document.
    
    Groups images by orientation (landscape vs portrait) and fills grid 2×2.
    - Landscape images: fill horizontally first [0][0], [0][1], [1][0], [1][1]
    - Portrait images: fill vertically first [0][0], [1][0], [0][1], [1][1]
    
    Returns: List of pages, each page has up to 4 (quadrant, image) tuples.
    """
    if not images:
        return []
    
    pages = []
    
    # Group consecutive images by same orientation
    groups = []
    current_group = []
    current_is_landscape = None
    
    for img in images:
        is_landscape = img.width >= img.height
        
        if current_is_landscape is None:
            current_is_landscape = is_landscape
            current_group.append(img)
        elif is_landscape == current_is_landscape:
            current_group.append(img)
        else:
            # Orientation changed - start new group
            if current_group:
                groups.append((current_is_landscape, current_group))
            current_group = [img]
            current_is_landscape = is_landscape
    
    # Don't forget last group
    if current_group:
        groups.append((current_is_landscape, current_group))
    
    # Process each group
    for is_landscape, group_imgs in groups:
        if is_landscape:
            # Landscape: fill horizontally [0][0], [0][1], [1][0], [1][1]
            quadrant_order = [(0, 0), (0, 1), (1, 0), (1, 1)]
        else:
            # Portrait: fill vertically [0][0], [1][0], [0][1], [1][1]
            quadrant_order = [(0, 0), (1, 0), (0, 1), (1, 1)]
        
        # Fill pages with up to 4 images each
        for i in range(0, len(group_imgs), 4):
            page_imgs = group_imgs[i:i+4]
            page_items = []
            
            for idx, img in enumerate(page_imgs):
                quadrant = quadrant_order[idx]
                page_items.append((quadrant, img))
            
            pages.append(page_items)
    
    return pages
