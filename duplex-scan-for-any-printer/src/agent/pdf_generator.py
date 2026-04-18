from __future__ import annotations

from typing import List, Tuple, Optional, Dict
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from PIL import Image, ImageOps, ImageEnhance
import tempfile
import os
import io

from .layout_engine import quadrant_bounds, fit_within, fit_1to1, anchor_position, layout_items_by_orientation

# Fast PDF generation with PyMuPDF
try:
    import fitz  # PyMuPDF
    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False


def _new_canvas(path: str, page_size: Tuple[int, int]) -> canvas.Canvas:
    c = canvas.Canvas(path, pagesize=page_size)
    c._doc.compression = 1  # Enable compression for PDF structure only
    return c


def _get_image_reader(img: Image.Image, cache: Dict[int, ImageReader] = None) -> ImageReader:
    """Get cached ImageReader or create new one.
    
    Args:
        img: PIL Image
        cache: Optional cache dictionary (pass same dict for multiple calls)
    
    Returns:
        ImageReader object
    """
    img_id = id(img)
    if cache is not None and img_id in cache:
        return cache[img_id]
    
    # Create ImageReader with optimized settings
    # For JPEG images, don't re-encode to avoid quality loss and speed up
    ir = ImageReader(img)
    
    if cache is not None:
        cache[img_id] = ir
    
    return ir


def _optimize_for_pdf(img: Image.Image, target_dpi: int = 150) -> Image.Image:
    """Optimize image for PDF generation.
    
    Args:
        img: PIL Image
        target_dpi: Target DPI for print (default 150 is good balance)
    
    Returns:
        Optimized PIL Image
    """
    # Convert RGBA to RGB (remove alpha channel)
    if img.mode == 'RGBA':
        rgb = Image.new('RGB', img.size, (255, 255, 255))
        rgb.paste(img, mask=img.split()[3])  # Use alpha as mask
        img = rgb
    elif img.mode not in ('RGB', 'L'):
        img = img.convert('RGB')
    
    # Downscale if resolution is too high
    # A4 at 150 DPI = ~1240x1754 pixels
    # Most scanners do 300+ DPI, so we can safely downscale to 150-200 DPI
    max_dimension = 2000  # Equivalent to ~200 DPI on A4
    w, h = img.size
    if w > max_dimension or h > max_dimension:
        scale = max_dimension / max(w, h)
        new_w = int(w * scale)
        new_h = int(h * scale)
        img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
    
    return img


def _to_monochrome(img: Image.Image) -> Image.Image:
    """Convert to grayscale optimized for laser B/W printing.
    
    Modern approach (2025):
    - Simple grayscale conversion with smart auto-levels
    - Laser printers have excellent halftoning - let them handle it
    - Fast, reliable, works for all document types
    
    The key insight: Modern laser printers are MUCH better at handling
    grayscale than we are at pre-processing. Just give them clean grayscale.
    """
    # Convert to grayscale
    gray = img.convert("L")
    
    # Simple auto-contrast to use full dynamic range
    # This removes faint bleed-through by stretching contrast
    gray = ImageOps.autocontrast(gray, cutoff=1)
    
    # Optional: slight sharpening for text clarity
    gray = ImageEnhance.Sharpness(gray).enhance(1.2)
    
    return gray


def save_pdf_from_images_interleaved(pairs: List[Tuple[Image.Image, Image.Image]], output_path: str, page_size: Tuple[int, int] = A4):
    """Render interleaved pages: for each pair (front, back) emit two pages.
    Optimized for speed by downscaling high-res images.
    """
    c = _new_canvas(output_path, page_size)
    W, H = page_size
    cache = {}  # Cache ImageReader objects
    
    for front, back in pairs:
        for img in (front, back):
            # Optimize image before processing
            img_optimized = _optimize_for_pdf(img)
            ir = _get_image_reader(img_optimized, cache)
            iw, ih = img_optimized.size
            # Fit full-page with margin
            margin = 10
            tw = W - 2 * margin
            th = H - 2 * margin
            scale = min(tw / float(iw), th / float(ih)) if iw and ih else 1.0
            dw = int(iw * scale)
            dh = int(ih * scale)
            dx = margin + (tw - dw) // 2
            dy = margin + (th - dh) // 2
            c.drawImage(ir, dx, dy, width=dw, height=dh, preserveAspectRatio=True, mask='auto')
            c.showPage()
    c.save()


def save_pdf_from_images_interleaved_mono(pairs: List[Tuple[Image.Image, Image.Image]], output_path: str, page_size: Tuple[int, int] = A4):
    """Interleaved pages but convert images to monochrome for printing.
    Optimized with downscaling before monochrome conversion.
    """
    c = _new_canvas(output_path, page_size)
    W, H = page_size
    cache = {}
    for front, back in pairs:
        for img in (front, back):
            # Optimize first to reduce processing time
            img_optimized = _optimize_for_pdf(img)
            m = _to_monochrome(img_optimized)
            ir = _get_image_reader(m, cache)
            iw, ih = m.size
            margin = 10
            tw = W - 2 * margin
            th = H - 2 * margin
            scale = min(tw / float(iw), th / float(ih)) if iw and ih else 1.0
            dw = int(iw * scale)
            dh = int(ih * scale)
            dx = margin + (tw - dw) // 2
            dy = margin + (th - dh) // 2
            c.drawImage(ir, dx, dy, width=dw, height=dh, preserveAspectRatio=True, mask='auto')
            c.showPage()
    c.save()


def save_pdf_card_2in1_grid(images: List[Image.Image], output_path: str, page_size: Tuple[int, int] = A4, margin: int = 10):
    """Layout cards using generic orientation-based grid (up to 4 per page).
    
    Uses layout_items_by_orientation for intelligent 2×2 grid filling.
    No scaling - keeps 1:1 size. Optimized with downscaling for speed.
    """
    # Optimize images first to reduce processing time
    images_optimized = [_optimize_for_pdf(img) for img in images]
    pages = layout_items_by_orientation(images_optimized)
    if not pages:
        return
    
    c = _new_canvas(output_path, page_size)
    W, H = page_size
    cache = {}  # Cache ImageReader objects
    
    for page_items in pages:
        _render_doc_page(c, page_items, W, H, margin, cache)
    
    c.save()


def save_pdf_card_2in1_grid_mono(images: List[Image.Image], output_path: str, page_size: Tuple[int, int] = A4, margin: int = 10):
    """Monochrome variant of card 2-in-1 grid PDF. Optimized with downscaling."""
    # Optimize images first
    images_optimized = [_optimize_for_pdf(img) for img in images]
    pages = layout_items_by_orientation(images_optimized)
    if not pages:
        return
    c = _new_canvas(output_path, page_size)
    W, H = page_size
    cache = {}
    for page_items in pages:
        # convert images to monochrome before rendering
        mono_items = []
        for q, img in page_items:
            mono_items.append((q, _to_monochrome(img)))
        _render_doc_page(c, mono_items, W, H, margin, cache)
    c.save()


def save_pdf_scan_document(pages: List[List[Tuple[str, Tuple[int, int], Image.Image, float]]], 
                           output_path: str, 
                           page_size: Tuple[int, int] = A4,
                           margin: int = 10):
    """Render documents with smart grid layout using actual scan DPI.
    
    Args:
        pages: List of pages from layout_documents_smart()
            Each page is list of (span, (draw_x, draw_y), image, scan_dpi)
            span: "single", "half_horizontal", "half_vertical", "full"
            (draw_x, draw_y): Draw position in points
            image: Cropped document image
            scan_dpi: Actual DPI of scanned image
        output_path: Output PDF path
        page_size: Page size (default A4)
        margin: Page margin in points
    """
    if not pages:
        return
    
    c = _new_canvas(output_path, page_size)
    cache = {}  # Cache ImageReader objects
    W, H = page_size
    
    # Render all pages
    for page_items in pages:
        for span, (draw_x, draw_y), img, scan_dpi in page_items:
            # Optimize image before processing
            orig_w, orig_h = img.size
            img_optimized = _optimize_for_pdf(img)
            iw, ih = img_optimized.size
            
            # Adjust DPI based on optimization scaling to maintain physical size
            # If image was downscaled, adjust DPI proportionally
            scale_ratio = iw / float(orig_w) if orig_w > 0 else 1.0
            adjusted_dpi = scan_dpi * scale_ratio
            
            # Convert pixels to points using adjusted DPI
            # This maintains physical size from original scan
            img_w_pt = iw * 72.0 / adjusted_dpi
            img_h_pt = ih * 72.0 / adjusted_dpi
            
            # Determine available space based on span
            if span == "single":
                # Quarter page (2x2 grid)
                available_w = W // 2 - 2 * margin
                available_h = H // 2 - 2 * margin
            elif span == "half_horizontal":
                # Half page horizontally (full width, half height)
                available_w = W - 2 * margin
                available_h = H // 2 - 2 * margin
            elif span == "half_vertical":
                # Half page vertically (half width, full height)
                available_w = W // 2 - 2 * margin
                available_h = H - 2 * margin
            else:  # "full"
                # Full page
                available_w = W - 2 * margin
                available_h = H - 2 * margin
            
            # Scale down if image exceeds available space (never scale up)
            if img_w_pt > available_w or img_h_pt > available_h:
                scale = min(available_w / img_w_pt, available_h / img_h_pt)
                img_w_pt *= scale
                img_h_pt *= scale
            
            # Center the image within available space
            # For half_horizontal: center horizontally
            # For half_vertical: center vertically
            # For single/full: center both directions
            final_x = draw_x
            final_y = draw_y
            
            if span == "half_horizontal":
                # Center horizontally within full width
                final_x = (W - img_w_pt) / 2.0
            elif span == "half_vertical":
                # Center vertically within full height
                final_y = (H - img_h_pt) / 2.0
            elif span == "single":
                # Center within quadrant
                quad_w = W // 2
                quad_h = H // 2
                # Determine which quadrant based on draw_x, draw_y
                if draw_x < W // 2:  # Left column
                    final_x = draw_x + (quad_w - 2*margin - img_w_pt) / 2.0
                else:  # Right column
                    final_x = draw_x + (quad_w - 2*margin - img_w_pt) / 2.0
                if draw_y >= H // 2:  # Top row
                    final_y = draw_y + (quad_h - 2*margin - img_h_pt) / 2.0
                else:  # Bottom row
                    final_y = draw_y + (quad_h - 2*margin - img_h_pt) / 2.0
            else:  # "full"
                # Center on full page
                final_x = (W - img_w_pt) / 2.0
                final_y = (H - img_h_pt) / 2.0
            
            # Draw at centered position
            ir = _get_image_reader(img_optimized, cache)
            c.drawImage(ir, final_x, final_y, 
                       width=img_w_pt, height=img_h_pt, 
                       preserveAspectRatio=True, mask='auto')
        c.showPage()
    
    c.save()


def save_pdf_scan_document_mono(pages: List[List[Tuple[str, Tuple[int, int], Image.Image, float]]], 
                                output_path: str, 
                                page_size: Tuple[int, int] = A4,
                                margin: int = 10):
    """Render documents in monochrome for laser printing using actual scan DPI."""
    if not pages:
        return
    c = _new_canvas(output_path, page_size)
    cache = {}
    W, H = page_size
    
    for page_items in pages:
        for span, (draw_x, draw_y), img, scan_dpi in page_items:
            # Optimize before monochrome conversion
            orig_w, orig_h = img.size
            img_optimized = _optimize_for_pdf(img)
            m = _to_monochrome(img_optimized)
            iw, ih = m.size
            
            # Adjust DPI based on optimization scaling to maintain physical size
            scale_ratio = iw / float(orig_w) if orig_w > 0 else 1.0
            adjusted_dpi = scan_dpi * scale_ratio
            
            # Convert pixels to points using adjusted DPI
            img_w_pt = iw * 72.0 / adjusted_dpi
            img_h_pt = ih * 72.0 / adjusted_dpi
            
            # Determine available space based on span
            if span == "single":
                # Quarter page (2x2 grid)
                available_w = W // 2 - 2 * margin
                available_h = H // 2 - 2 * margin
            elif span == "half_horizontal":
                # Half page horizontally (full width, half height)
                available_w = W - 2 * margin
                available_h = H // 2 - 2 * margin
            elif span == "half_vertical":
                # Half page vertically (half width, full height)
                available_w = W // 2 - 2 * margin
                available_h = H - 2 * margin
            else:  # "full"
                # Full page
                available_w = W - 2 * margin
                available_h = H - 2 * margin
            
            # Scale down if image exceeds available space (never scale up)
            if img_w_pt > available_w or img_h_pt > available_h:
                scale = min(available_w / img_w_pt, available_h / img_h_pt)
                img_w_pt *= scale
                img_h_pt *= scale
            
            # Center the image within available space (same logic as color version)
            final_x = draw_x
            final_y = draw_y
            
            if span == "half_horizontal":
                # Center horizontally within full width
                final_x = (W - img_w_pt) / 2.0
            elif span == "half_vertical":
                # Center vertically within full height
                final_y = (H - img_h_pt) / 2.0
            elif span == "single":
                # Center within quadrant
                quad_w = W // 2
                quad_h = H // 2
                if draw_x < W // 2:  # Left column
                    final_x = draw_x + (quad_w - 2*margin - img_w_pt) / 2.0
                else:  # Right column
                    final_x = draw_x + (quad_w - 2*margin - img_w_pt) / 2.0
                if draw_y >= H // 2:  # Top row
                    final_y = draw_y + (quad_h - 2*margin - img_h_pt) / 2.0
                else:  # Bottom row
                    final_y = draw_y + (quad_h - 2*margin - img_h_pt) / 2.0
            else:  # "full"
                # Center on full page
                final_x = (W - img_w_pt) / 2.0
                final_y = (H - img_h_pt) / 2.0
            
            ir = _get_image_reader(m, cache)
            c.drawImage(ir, final_x, final_y, 
                        width=img_w_pt, height=img_h_pt, 
                        preserveAspectRatio=True, mask='auto')
        c.showPage()
    c.save()


def _get_occupied_regions(span: str, draw_x: int, draw_y: int, W: int, H: int) -> List[str]:
    """Determine which quadrants/regions a document occupies.
    
    Returns list of region identifiers: "tl", "tr", "bl", "br", "top", "bottom", "left", "right", "full"
    """
    half_w = W // 2
    half_h = H // 2
    
    if span == "single":
        # Determine quadrant from draw position
        if draw_x < half_w and draw_y >= half_h:
            return ["tl"]  # top-left
        elif draw_x >= half_w and draw_y >= half_h:
            return ["tr"]  # top-right
        elif draw_x < half_w and draw_y < half_h:
            return ["bl"]  # bottom-left
        else:
            return ["br"]  # bottom-right
    elif span == "half_horizontal":
        # Top or bottom half
        if draw_y >= half_h:
            return ["top", "tl", "tr"]
        else:
            return ["bottom", "bl", "br"]
    elif span == "half_vertical":
        # Left or right half
        if draw_x < half_w:
            return ["left", "tl", "bl"]
        else:
            return ["right", "tr", "br"]
    else:  # span == "full"
        return ["full", "top", "bottom", "left", "right", "tl", "tr", "bl", "br"]


def _render_doc_page(c: canvas.Canvas, slots, W: int, H: int, margin: int, cache: Dict[int, ImageReader] = None):
    if cache is None:
        cache = {}
    for q, img in slots:
        bx, by, bw, bh = quadrant_bounds(W, H, q)
        iw, ih = img.size
        # Use 1:1 scale for cards/documents (no scaling)
        dw, dh = fit_1to1(iw, ih, bw, bh, margin)
        dx, dy = anchor_position(q, bx, by, bw, bh, dw, dh, margin)
        ir = _get_image_reader(img, cache)
        c.drawImage(ir, dx, dy, width=dw, height=dh, preserveAspectRatio=True, mask='auto')
    c.showPage()


def save_pdf_card_pairs(
    pairs: List[Tuple[Image.Image, Image.Image]],
    output_path: str,
    page_size: Tuple[int, int] = A4,
    margin: int = 10,
    gutter: int = 0,
    labels: Optional[List[Tuple[Optional[str], Optional[str]]]] = None,
):
    """Each pair -> one page; layout left-right if both landscape, else top-bottom.
    - gutter: spacing between left-right or top-bottom panels (pt)
    - labels: optional list of (label_a, label_b) to draw in small font near each image
    """
    c = _new_canvas(output_path, page_size)
    W, H = page_size
    cache = {}  # Cache ImageReader objects
    
    for page_index, (a, b) in enumerate(pairs):
        a_land = a.width >= a.height
        b_land = b.width >= b.height
        if a_land and b_land:
            # Left-right split
            bw = (W - gutter) // 2
            left_box = (0, 0, bw, H)
            right_box = (bw + gutter, 0, bw, H)
            la = labels[page_index][0] if labels and page_index < len(labels) else None
            lb = labels[page_index][1] if labels and page_index < len(labels) else None
            _draw_in_box(c, a, left_box, margin, la, cache)
            _draw_in_box(c, b, right_box, margin, lb, cache)
        else:
            # Top-bottom split
            bh = (H - gutter) // 2
            bottom_box = (0, 0, W, bh)
            top_box = (0, bh + gutter, W, bh)
            la = labels[page_index][0] if labels and page_index < len(labels) else None
            lb = labels[page_index][1] if labels and page_index < len(labels) else None
            _draw_in_box(c, a, top_box, margin, la, cache)
            _draw_in_box(c, b, bottom_box, margin, lb, cache)
        c.showPage()
    c.save()


def _draw_in_box(c: canvas.Canvas, img: Image.Image, box, margin: int, label: Optional[str] = None, cache: Dict[int, ImageReader] = None):
    if cache is None:
        cache = {}
    bx, by, bw, bh = box
    iw, ih = img.size
    # Fit within box respecting margin
    dw, dh = fit_within(iw, ih, bw, bh, margin)
    
    # Top-align to save paper (instead of center)
    dx = bx + margin
    dy = by + bh - margin - dh  # Anchor at top of box
    
    ir = _get_image_reader(img, cache)
    c.drawImage(ir, dx, dy, width=dw, height=dh, preserveAspectRatio=True, mask='auto')
    if label:
        try:
            c.setFont("Helvetica", 8)
        except Exception:
            pass
        # Place label just below the image if space, else at bottom-left of box
        label_y = dy - 10
        if label_y < by + 2:
            label_y = by + 2
        c.drawString(dx, label_y, str(label))


# ============================================================================
# FAST PDF GENERATION USING PyMuPDF (5-20x faster with memory buffers)
# ============================================================================

def save_pdf_from_images_interleaved_fast(pairs: List[Tuple[Image.Image, Image.Image]], 
                                         output_path: str, 
                                         page_size: Tuple[int, int] = A4) -> float:
    """Fast interleaved PDF generation using PyMuPDF with memory buffers.
    
    Uses PyMuPDF (fitz) with C++ backend and in-memory image handling,
    making it 5-20x faster than ReportLab.
    
    Returns: Time taken in seconds
    """
    import time
    start = time.time()
    
    if not HAS_PYMUPDF:
        # Fallback to ReportLab
        save_pdf_from_images_interleaved(pairs, output_path, page_size)
        return time.time() - start
    
    try:
        doc = fitz.open()
        W, H = page_size
        margin = 10
        
        for front, back in pairs:
            for img in (front, back):
                # Optimize image
                img_optimized = _optimize_for_pdf(img)
                
                # Convert to RGB if needed
                if img_optimized.mode != 'RGB':
                    img_optimized = img_optimized.convert('RGB')
                
                # Save to memory buffer (no disk I/O!)
                img_bytes = io.BytesIO()
                img_optimized.save(img_bytes, 'JPEG', quality=90, optimize=True)
                img_bytes.seek(0)
                
                # Create page and fit image with margin
                page = doc.new_page(width=W, height=H)
                iw, ih = img_optimized.size
                
                # Calculate fitted size
                tw = W - 2 * margin
                th = H - 2 * margin
                scale = min(tw / float(iw), th / float(ih)) if iw and ih else 1.0
                dw = iw * scale
                dh = ih * scale
                
                # Center image
                dx = margin + (tw - dw) / 2
                dy = margin + (th - dh) / 2
                
                # Insert image from memory
                rect = fitz.Rect(dx, dy, dx + dw, dy + dh)
                page.insert_image(rect, stream=img_bytes.getvalue(), keep_proportion=True)
        
        # Save PDF with optimization
        doc.save(output_path, garbage=4, deflate=True, clean=True)
        doc.close()
        
    except Exception as e:
        print(f"⚠️  PyMuPDF failed: {e}, falling back to ReportLab")
        save_pdf_from_images_interleaved(pairs, output_path, page_size)
    
    return time.time() - start


def save_pdf_from_images_interleaved_mono_fast(pairs: List[Tuple[Image.Image, Image.Image]], 
                                              output_path: str, 
                                              page_size: Tuple[int, int] = A4) -> float:
    """Fast monochrome interleaved PDF using PyMuPDF with memory buffers.
    
    Returns: Time taken in seconds
    """
    import time
    start = time.time()
    
    if not HAS_PYMUPDF:
        # Fallback to ReportLab
        save_pdf_from_images_interleaved_mono(pairs, output_path, page_size)
        return time.time() - start
    
    try:
        doc = fitz.open()
        W, H = page_size
        margin = 10
        
        for front, back in pairs:
            for img in (front, back):
                # Optimize and convert to monochrome
                img_optimized = _optimize_for_pdf(img)
                img_mono = _to_monochrome(img_optimized)
                
                # Convert to RGB for JPEG
                if img_mono.mode != 'RGB':
                    img_mono = img_mono.convert('RGB')
                
                # Save to memory buffer
                img_bytes = io.BytesIO()
                img_mono.save(img_bytes, 'JPEG', quality=90, optimize=True)
                img_bytes.seek(0)
                
                # Create page and fit image
                page = doc.new_page(width=W, height=H)
                iw, ih = img_mono.size
                
                # Calculate fitted size with margin
                tw = W - 2 * margin
                th = H - 2 * margin
                scale = min(tw / float(iw), th / float(ih)) if iw and ih else 1.0
                dw = iw * scale
                dh = ih * scale
                
                # Center image
                dx = margin + (tw - dw) / 2
                dy = margin + (th - dh) / 2
                
                # Insert image from memory
                rect = fitz.Rect(dx, dy, dx + dw, dy + dh)
                page.insert_image(rect, stream=img_bytes.getvalue(), keep_proportion=True)
        
        # Save PDF with optimization
        doc.save(output_path, garbage=4, deflate=True, clean=True)
        doc.close()
        
    except Exception as e:
        print(f"⚠️  PyMuPDF failed: {e}, falling back to ReportLab")
        save_pdf_from_images_interleaved_mono(pairs, output_path, page_size)
    
    return time.time() - start


# ============================================================================
# FAST PDF GENERATION USING PyMuPDF (5-20x faster for complex layouts)
# ============================================================================

def save_pdf_card_2in1_grid_fast(images: List[Image.Image], 
                                 output_path: str, 
                                 page_size: Tuple[int, int] = A4, 
                                 margin: int = 10) -> float:
    """Fast card 2-in-1 grid using PyMuPDF.
    
    Uses PyMuPDF (fitz) with C++ backend for 5-20x faster PDF generation
    compared to ReportLab while maintaining complex layout capabilities.
    
    Returns: Time taken in seconds
    """
    import time
    start = time.time()
    
    if not HAS_PYMUPDF:
        # Fallback to ReportLab
        save_pdf_card_2in1_grid(images, output_path, page_size, margin)
        return time.time() - start
    
    try:
        # Optimize images first
        images_optimized = [_optimize_for_pdf(img) for img in images]
        pages = layout_items_by_orientation(images_optimized)
        
        if not pages:
            return time.time() - start
        
        # Create PDF with PyMuPDF
        doc = fitz.open()
        W, H = page_size
        
        for page_items in pages:
            # Create new page
            page = doc.new_page(width=W, height=H)
            
            for quadrant, img in page_items:
                # Get quadrant bounds
                qx, qy, qw, qh = quadrant_bounds(quadrant, W, H)
                
                # Convert to RGB if needed
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                
                # Save image to memory buffer (no disk I/O!)
                img_bytes = io.BytesIO()
                img.save(img_bytes, 'JPEG', quality=90, optimize=True)
                img_bytes.seek(0)
                
                # Insert image from memory buffer
                rect = fitz.Rect(qx + margin, qy + margin, 
                                qx + qw - margin, qy + qh - margin)
                page.insert_image(rect, stream=img_bytes.getvalue(), keep_proportion=True)
        
        # Save PDF
        doc.save(output_path, garbage=4, deflate=True, clean=True)
        doc.close()
        
    except Exception as e:
        print(f"⚠️  PyMuPDF failed: {e}, falling back to ReportLab")
        save_pdf_card_2in1_grid(images, output_path, page_size, margin)
    
    return time.time() - start


def save_pdf_card_2in1_grid_mono_fast(images: List[Image.Image], 
                                      output_path: str, 
                                      page_size: Tuple[int, int] = A4, 
                                      margin: int = 10) -> float:
    """Fast monochrome card 2-in-1 grid using PyMuPDF.
    
    Returns: Time taken in seconds
    """
    import time
    start = time.time()
    
    if not HAS_PYMUPDF:
        # Fallback to ReportLab
        save_pdf_card_2in1_grid_mono(images, output_path, page_size, margin)
        return time.time() - start
    
    try:
        # Optimize and convert to monochrome
        images_optimized = [_to_monochrome(_optimize_for_pdf(img)) for img in images]
        pages = layout_items_by_orientation(images_optimized)
        
        if not pages:
            return time.time() - start
        
        # Create PDF with PyMuPDF
        doc = fitz.open()
        W, H = page_size
        
        for page_items in pages:
            page = doc.new_page(width=W, height=H)
            
            for quadrant, img in page_items:
                qx, qy, qw, qh = quadrant_bounds(quadrant, W, H)
                
                # Convert to RGB if needed
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                
                # Save to memory buffer
                img_bytes = io.BytesIO()
                img.save(img_bytes, 'JPEG', quality=90, optimize=True)
                img_bytes.seek(0)
                
                rect = fitz.Rect(qx + margin, qy + margin,
                                qx + qw - margin, qy + qh - margin)
                page.insert_image(rect, stream=img_bytes.getvalue(), keep_proportion=True)
        
        doc.save(output_path, garbage=4, deflate=True, clean=True)
        doc.close()
        
    except Exception as e:
        print(f"⚠️  PyMuPDF failed: {e}, falling back to ReportLab")
        save_pdf_card_2in1_grid_mono(images, output_path, page_size, margin)
    
    return time.time() - start


def save_pdf_scan_document_fast(pages: List[List[Tuple[str, Tuple[int, int], Image.Image, float]]], 
                                output_path: str, 
                                page_size: Tuple[int, int] = A4,
                                margin: int = 10) -> float:
    """Fast scan document PDF using PyMuPDF with smart layout.
    
    Returns: Time taken in seconds
    """
    import time
    start = time.time()
    
    if not HAS_PYMUPDF or not pages:
        # Fallback to ReportLab
        save_pdf_scan_document(pages, output_path, page_size, margin)
        return time.time() - start
    
    try:
        doc = fitz.open()
        W, H = page_size
        
        for page_items in pages:
            page = doc.new_page(width=W, height=H)
            
            for span, (draw_x, draw_y), img, scan_dpi in page_items:
                # Optimize image
                orig_w, orig_h = img.size
                img_optimized = _optimize_for_pdf(img)
                iw, ih = img_optimized.size
                
                # Adjust DPI based on optimization scaling
                scale_ratio = iw / float(orig_w) if orig_w > 0 else 1.0
                adjusted_dpi = scan_dpi * scale_ratio
                
                # Convert pixels to points
                img_w_pt = iw * 72.0 / adjusted_dpi
                img_h_pt = ih * 72.0 / adjusted_dpi
                
                # Determine available space
                if span == "single":
                    available_w = W // 2 - 2 * margin
                    available_h = H // 2 - 2 * margin
                elif span == "half_horizontal":
                    available_w = W - 2 * margin
                    available_h = H // 2 - 2 * margin
                elif span == "half_vertical":
                    available_w = W // 2 - 2 * margin
                    available_h = H - 2 * margin
                else:  # "full"
                    available_w = W - 2 * margin
                    available_h = H - 2 * margin
                
                # Scale down if needed
                if img_w_pt > available_w or img_h_pt > available_h:
                    scale = min(available_w / img_w_pt, available_h / img_h_pt)
                    img_w_pt *= scale
                    img_h_pt *= scale
                
                # Calculate final position (centered)
                final_x = draw_x
                final_y = draw_y
                
                if span == "half_horizontal":
                    final_x = (W - img_w_pt) / 2.0
                elif span == "half_vertical":
                    final_y = (H - img_h_pt) / 2.0
                elif span == "single":
                    quad_w = W // 2
                    quad_h = H // 2
                    if draw_x < W // 2:
                        final_x = draw_x + (quad_w - 2*margin - img_w_pt) / 2.0
                    else:
                        final_x = draw_x + (quad_w - 2*margin - img_w_pt) / 2.0
                    if draw_y >= H // 2:
                        final_y = draw_y + (quad_h - 2*margin - img_h_pt) / 2.0
                    else:
                        final_y = draw_y + (quad_h - 2*margin - img_h_pt) / 2.0
                else:  # "full"
                    final_x = (W - img_w_pt) / 2.0
                    final_y = (H - img_h_pt) / 2.0
                
                # Save and insert image using memory buffer
                if img_optimized.mode != 'RGB':
                    img_optimized = img_optimized.convert('RGB')
                
                img_bytes = io.BytesIO()
                img_optimized.save(img_bytes, 'JPEG', quality=90, optimize=True)
                img_bytes.seek(0)
                
                # PyMuPDF uses bottom-left origin, ReportLab too, but coordinates differ
                rect = fitz.Rect(final_x, H - final_y - img_h_pt,
                                final_x + img_w_pt, H - final_y)
                page.insert_image(rect, stream=img_bytes.getvalue(), keep_proportion=True)
        
        doc.save(output_path, garbage=4, deflate=True, clean=True)
        doc.close()
        
    except Exception as e:
        print(f"⚠️  PyMuPDF failed: {e}, falling back to ReportLab")
        save_pdf_scan_document(pages, output_path, page_size, margin)
    
    return time.time() - start


def save_pdf_scan_document_mono_fast(pages: List[List[Tuple[str, Tuple[int, int], Image.Image, float]]],
                                     output_path: str,
                                     page_size: Tuple[int, int] = A4,
                                     margin: int = 10) -> float:
    """Fast monochrome scan document PDF using PyMuPDF.
    
    Returns: Time taken in seconds
    """
    import time
    start = time.time()
    
    if not HAS_PYMUPDF or not pages:
        save_pdf_scan_document_mono(pages, output_path, page_size, margin)
        return time.time() - start
    
    try:
        doc = fitz.open()
        W, H = page_size
        
        for page_items in pages:
            page = doc.new_page(width=W, height=H)
            
            for span, (draw_x, draw_y), img, scan_dpi in page_items:
                # Optimize and convert to monochrome
                orig_w, orig_h = img.size
                img_optimized = _optimize_for_pdf(img)
                img_mono = _to_monochrome(img_optimized)
                iw, ih = img_mono.size
                
                scale_ratio = iw / float(orig_w) if orig_w > 0 else 1.0
                adjusted_dpi = scan_dpi * scale_ratio
                
                img_w_pt = iw * 72.0 / adjusted_dpi
                img_h_pt = ih * 72.0 / adjusted_dpi
                
                # Determine available space
                if span == "single":
                    available_w = W // 2 - 2 * margin
                    available_h = H // 2 - 2 * margin
                elif span == "half_horizontal":
                    available_w = W - 2 * margin
                    available_h = H // 2 - 2 * margin
                elif span == "half_vertical":
                    available_w = W // 2 - 2 * margin
                    available_h = H - 2 * margin
                else:
                    available_w = W - 2 * margin
                    available_h = H - 2 * margin
                
                if img_w_pt > available_w or img_h_pt > available_h:
                    scale = min(available_w / img_w_pt, available_h / img_h_pt)
                    img_w_pt *= scale
                    img_h_pt *= scale
                
                # Calculate position
                final_x = draw_x
                final_y = draw_y
                
                if span == "half_horizontal":
                    final_x = (W - img_w_pt) / 2.0
                elif span == "half_vertical":
                    final_y = (H - img_h_pt) / 2.0
                elif span == "single":
                    quad_w = W // 2
                    quad_h = H // 2
                    if draw_x < W // 2:
                        final_x = draw_x + (quad_w - 2*margin - img_w_pt) / 2.0
                    else:
                        final_x = draw_x + (quad_w - 2*margin - img_w_pt) / 2.0
                    if draw_y >= H // 2:
                        final_y = draw_y + (quad_h - 2*margin - img_h_pt) / 2.0
                    else:
                        final_y = draw_y + (quad_h - 2*margin - img_h_pt) / 2.0
                else:
                    final_x = (W - img_w_pt) / 2.0
                    final_y = (H - img_h_pt) / 2.0
                
                # Insert image using memory buffer
                if img_mono.mode != 'RGB':
                    img_mono = img_mono.convert('RGB')
                
                img_bytes = io.BytesIO()
                img_mono.save(img_bytes, 'JPEG', quality=90, optimize=True)
                img_bytes.seek(0)
                
                rect = fitz.Rect(final_x, H - final_y - img_h_pt,
                                final_x + img_w_pt, H - final_y)
                page.insert_image(rect, stream=img_bytes.getvalue(), keep_proportion=True)
        
        doc.save(output_path, garbage=4, deflate=True, clean=True)
        doc.close()
        
    except Exception as e:
        print(f"⚠️  PyMuPDF failed: {e}, falling back to ReportLab")
        save_pdf_scan_document_mono(pages, output_path, page_size, margin)
    
    return time.time() - start
