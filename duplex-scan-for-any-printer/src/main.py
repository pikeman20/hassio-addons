from __future__ import annotations

import argparse
import os
import sys
import signal
import time
import threading
import queue
import numpy as np
import cv2
import re
from typing import List, Tuple
from PIL import Image

from agent.config import Config
from agent.session_manager import SessionManager, Session
from agent.image_processing import (
    load_image,
    rotate_180,
    batch_correct_orientation,
    deskew_image,
    _unload_bg_removal_model,
    crop_document_v2
)
from agent.pdf_generator import (
    save_pdf_from_images_interleaved,
    save_pdf_card_2in1_grid,
    save_pdf_from_images_interleaved_fast,
    save_pdf_from_images_interleaved_mono_fast,
    save_pdf_scan_document_fast,
    save_pdf_scan_document_mono_fast,
    save_pdf_card_2in1_grid_fast,
    save_pdf_card_2in1_grid_mono_fast
)
from agent.print_dispatcher import print_pdf_duplex, print_pdf_monochrome
from agent.ftp_watcher import FTPWatcher
from agent.layout_engine import (
    determine_document_span,
    layout_documents_smart,
    layout_items_by_orientation
)
from agent.metadata_generator import (
    generate_scan_duplex_metadata,
    generate_scan_document_metadata,
    generate_card_2in1_metadata
)
from agent import logger
from agent.error_handler import (safe_execute, retry_on_failure, handle_session_error,
                                 handle_image_processing_error, handle_pdf_generation_error,
                                 handle_printer_error, check_disk_space,
                                 ImageProcessingError, PDFGenerationError, PrinterError)
from agent.config_validator import validate_config
from agent.resource_monitor import ResourceMonitor, schedule_periodic_cleanup
from agent.telegram_bot import TelegramBot
from agent.notification_manager import NotificationManager
from agent import agent_api

def process_session(cfg: Config, s: Session, notification_manager=None):
    """Process a confirmed session with error handling."""
    session_start = time.time()
    
    # Set logging context for this session
    logger.set_session_context(s.id, s.mode)
    
    success = False
    out_pdf = None
    try:
        logger.info("="*80)
        logger.info(f"Session processing started: {s.id} (mode: {s.mode})")
        logger.info("="*80)
        
        # Check disk space before processing (require 100MB free)
        check_disk_space(cfg.output_dir, required_mb=100)
        # Prepare project directory and move source images into project's own storage
        try:
            project_dir = os.path.join(cfg.output_dir, s.id)
            images_dir = os.path.join(project_dir, 'images')
            os.makedirs(images_dir, exist_ok=True)

            moved_paths = []
            import shutil
            for idx, p in enumerate(s.images):
                try:
                    if not os.path.exists(p):
                        logger.warning(f"Source image missing when preparing project: {p}")
                        continue
                    base = os.path.basename(p)
                    # Ensure unique filename in project images folder
                    target_name = base
                    if os.path.exists(os.path.join(images_dir, target_name)):
                        name, ext = os.path.splitext(base)
                        target_name = f"{name}_{idx}{ext}"
                    target_path = os.path.join(images_dir, target_name)
                    shutil.move(p, target_path)
                    moved_paths.append(target_path)
                except Exception as e:
                    logger.warning(f"Failed to move {p} to project folder: {e}")

            # Replace session images list with moved paths (if any moved), otherwise keep originals
            if moved_paths:
                s.images = moved_paths

        except Exception as e:
            logger.warning(f"Failed to prepare project storage for session {s.id}: {e}")

        out_pdf = _process_session_inner(cfg, s, session_start)
        success = True
        
    except Exception as e:
        handle_session_error(s.id, s.mode, e)
        logger.error(f"❌ Session processing failed: {s.id}")
    finally:
        logger.clear_session_context()
        if notification_manager is not None:
            notification_manager.notify_session_processed(
                s.id, s.mode, success, pdf_path=out_pdf
            )


def _process_session_inner(cfg: Config, s: Session, session_start: float):
    """Inner session processing logic (extracted for error handling)."""
    
    mode = s.mode
    out_dir = cfg.output_dir
    os.makedirs(out_dir, exist_ok=True)
    base_name = f"{s.id}.pdf"
    out_path = os.path.join(out_dir, base_name)

    # Strictly order files by group prefix and creation time
    def strict_order_paths(paths: List[str]) -> List[str]:
        """Order files deterministically:
        - Group by prefix pattern: '<prefix>_<id>' where optional trailing '_<index>' indicates order within a group
        - Within each group: sort by index (no index treated as 1)
        - Across groups: sort by earliest creation time (fallback to mtime), then by group key lexicographically
        """
        groups: dict[str, list[tuple[int, float, str]]] = {}
        time_cache: dict[str, float] = {}

        for p in paths:
            name = os.path.splitext(os.path.basename(p))[0]
            # Pattern: base has at least one '_<digits>' and optional trailing '_<digits>' as item index
            m = re.match(r"^(.*?_\d+)(?:_(\d+))?$", name)
            if m:
                gkey = m.group(1)
                idx = int(m.group(2)) if m.group(2) is not None else 1
            else:
                # Fallback: use full stem as group, index 1
                gkey = name
                idx = 1
            # File time: prefer ctime, fallback to mtime
            try:
                t = os.path.getctime(p)
            except Exception:
                try:
                    t = os.path.getmtime(p)
                except Exception:
                    t = 0.0
            time_cache[p] = t
            groups.setdefault(gkey, []).append((idx, t, p))

        # Compute group time as earliest file time in the group
        ordered_group_keys = sorted(
            groups.keys(),
            key=lambda g: (
                min((t for _, t, _ in groups[g]), default=0.0),
                g,
            ),
        )

        ordered_paths: List[str] = []
        for g in ordered_group_keys:
            items = sorted(groups[g], key=lambda it: it[0])
            ordered_paths.extend([p for _, _, p in items])
        return ordered_paths

    load_start = time.time()
    ordered_paths = strict_order_paths(s.images)
    print(f"[TIMING] File ordering: {time.time() - load_start:.3f}s ({len(s.images)} files)")

    # Load all images in strict order and keep path+img together
    from typing import NamedTuple
    class ImageItem(NamedTuple):
        path: str
        img: Image.Image
    
    load_images_start = time.time()
    ordered_items: List[ImageItem] = []
    for p in ordered_paths:
        img = safe_execute(
            load_image, p,
            default=None,
            error_msg=f"Failed to load image: {os.path.basename(p)}"
        )
        if img is not None:
            ordered_items.append(ImageItem(p, img))
        else:
            handle_image_processing_error(os.path.basename(p), "load", Exception("Load failed"))
    
    if not ordered_items:
        raise ImageProcessingError("No valid images to process", "session", "load_all")
    
    print(f"[TIMING] Loading {len(ordered_items)} images: {time.time() - load_images_start:.3f}s")
    
    # For backward compatibility where needed
    imgs = [item.img for item in ordered_items]

    # TEST PRINT MODE: Simple direct print without processing
    if mode == cfg.subdirs.get("test_print") or mode == "test_print":
        logger.info(f"🖨️  Test Print Mode: Printing {len(ordered_items)} images directly")
        
        # Convert images to simple PDF
        # save_pdf_from_images_simple is imported at module top
        
        test_pdf_path = out_path.replace('.pdf', '_test.pdf')
        
        # Simple PDF generation (no interleaving, no processing)
        pdf_start = time.time()
        try:
            # Use PIL Images directly
            pil_images = []
            for item in ordered_items:
                # Convert numpy array to PIL Image if needed
                if isinstance(item.img, np.ndarray):
                    img_pil = Image.fromarray(cv2.cvtColor(item.img, cv2.COLOR_BGR2RGB))
                else:
                    img_pil = item.img
                pil_images.append(img_pil)
            
            # Save as simple PDF
            if pil_images:
                pil_images[0].save(
                    test_pdf_path,
                    save_all=True,
                    append_images=pil_images[1:] if len(pil_images) > 1 else [],
                    resolution=300.0,
                    quality=95
                )
                logger.info(f"✅ Test PDF created: {test_pdf_path} ({len(pil_images)} pages)")
            else:
                raise PDFGenerationError("No images to convert to PDF", "test_print")
                
        except Exception as e:
            handle_pdf_generation_error(s.id, "test_print", e)
            raise
        
        print(f"[TIMING] PDF generation: {time.time() - pdf_start:.3f}s")
        
        # Auto-print if printer configured
        if cfg.printer.enabled:
            printer_ip = cfg.printer.ip.strip() if hasattr(cfg.printer, 'ip') and cfg.printer.ip else None
            printer_name = cfg.printer.name.strip() if cfg.printer.name else None
            
            print_start = time.time()
            try:
                print_pdf_monochrome(
                    test_pdf_path,
                    duplex=False,
                    printer_name=printer_name,
                    printer_ip=printer_ip
                )
                logger.info(f"✅ Test print job sent successfully")
            except Exception as e:
                handle_printer_error(s.id, "test_print", e)
                logger.warning(f"⚠️  Test print failed: {str(e)}")
            
            print(f"[TIMING] Printing: {time.time() - print_start:.3f}s")
        else:
            logger.info(f"ℹ️  Printer not enabled - PDF saved to {test_pdf_path}")
        
        return

    if mode == cfg.subdirs.get("scan_duplex") or mode == "scan_duplex":
        processing_start = time.time()
        # Batch-aware orientation correction with timestamps
        rotation_angles = batch_correct_orientation(imgs, [item.path for item in ordered_items])
        print(f"[TIMING] Orientation detection: {time.time() - processing_start:.3f}s")
        
        print("\n📋 Processing images:")
        print("-" * 90)
        
        # Apply rotations and deskew
        rotate_start = time.time()
        corrected_items = []
        rotation_info = []  # Store (rotation_angle, deskew_angle) for each image
        for i, (item, angle) in enumerate(zip(ordered_items, rotation_angles)):
            img = item.img
            filename = os.path.basename(item.path)
            log_parts = [f"  [{i+1:2d}] {filename:40s}"]
            
            # Step 1: Rotate 180° if needed
            if angle == 180:
                img = rotate_180(img)
                log_parts.append("→ rotate 180°")
            else:
                log_parts.append("→ no rotation")
            
            # Step 2: Deskew (straighten small angles)
            img, deskew_angle = deskew_image(filename, img)
            
            print(" ".join(log_parts))
            corrected_items.append(ImageItem(item.path, img))
            rotation_info.append((angle, deskew_angle))
        
        print("-" * 90)
        print(f"[TIMING] Rotation & deskew: {time.time() - rotate_start:.3f}s")
        
        print("-" * 90)
        
        # Split into fronts/backs and pair
        n = len(corrected_items)
        half = n // 2
        front_items = corrected_items[:half]
        back_items = corrected_items[half:half + half]
        
        # Reverse backs order (duplex scanning convention)
        print(f"\n🔄 Reversing backs order: back[{len(back_items)-1}]...back[0]")
        back_items = back_items[::-1]
        
        print(f"📄 Creating {len(front_items)} page pairs:")
        for i, (f_item, b_item) in enumerate(zip(front_items, back_items)):
            f_name = os.path.basename(f_item.path)
            b_name = os.path.basename(b_item.path)
            print(f"  Page {i+1}: Front {f_name:30s} + Back {b_name}")
        
        pairs = list(zip([item.img for item in front_items], [item.img for item in back_items]))
        
        # Fast PDF generation with PyMuPDF (memory buffers)
        # fast pdf generators imported at module top
        
        print("\n📊 PDF Generation Speed Test:")
        print("-" * 90)
        
        # Color PDF with fast method
        pdf_start = time.time()
        time_fast_color = save_pdf_from_images_interleaved_fast(pairs, out_path)
        print(f"✅ [FAST] Color PDF (PyMuPDF):     {time_fast_color:.3f}s")
        
        # Monochrome PDF for better laser B/W output
        out_path_mono = os.path.join(out_dir, f"{s.id}_mono.pdf")
        
        mono_pdf_start = time.time()
        time_fast_mono = save_pdf_from_images_interleaved_mono_fast(pairs, out_path_mono)
        print(f"✅ [FAST] Mono PDF (PyMuPDF):      {time_fast_mono:.3f}s")
        
        print("-" * 90)
        print(f"💡 Total PDF generation time:       {time_fast_color + time_fast_mono:.3f}s")
        print("-" * 90)

        # Generate duplex metadata: interleave front/back items to match PDF page order.
        # PDF pages are: [front[0], back[reversed_0], front[1], back[reversed_1], ...]
        # rotation_info[i] corresponds to corrected_items[i] (sequential order).
        # back_items[j] was originally corrected_items[half + (half-1-j)] before reversal.
        try:
            interleaved_items = []
            interleaved_rotation = []
            for i in range(half):
                # Front side: corrected index = i
                interleaved_items.append((front_items[i].path, front_items[i].img))
                interleaved_rotation.append(rotation_info[i])
                # Back side (already reversed): original index = half + (half-1-i)
                back_orig_idx = half + (half - 1 - i)
                interleaved_items.append((back_items[i].path, back_items[i].img))
                interleaved_rotation.append(rotation_info[back_orig_idx])
            generate_scan_duplex_metadata(s.id, interleaved_items, interleaved_rotation, out_dir)
        except Exception as e:
            print(f"⚠️  Duplex metadata generation failed: {e}")
        
        # Confirm-and-print: only print if print_requested flag is True
        if s.print_requested and not getattr(cfg, "test_mode", False):
            print("\n🖨️  Printing monochrome (duplex)...")
            try:
                printer_name = cfg.printer.name.strip() if cfg.printer.name else None
                printer_ip = cfg.printer.ip.strip() if hasattr(cfg.printer, 'ip') and cfg.printer.ip else None
                print_pdf_monochrome(out_path_mono, duplex=True, printer_name=printer_name, printer_ip=printer_ip)
                logger.info("✅ Print job submitted successfully")
            except Exception as e:
                handle_printer_error(out_path_mono, cfg.printer.name or cfg.printer.ip or "default", e)
                logger.warning("⚠️  Printing failed, but PDF saved successfully")

    elif mode == cfg.subdirs.get("copy_duplex") or mode == "copy_duplex":
        processing_start = time.time()
        # Batch-aware orientation correction with timestamps
        rotation_angles = batch_correct_orientation(imgs, [item.path for item in ordered_items])
        print(f"[TIMING] Orientation detection: {time.time() - processing_start:.3f}s")
        
        print("\n📋 Processing images:")
        print("-" * 90)
        
        # Apply rotations and deskew
        rotate_start = time.time()
        corrected_items = []
        rotation_info = []  # Store (rotation_angle, deskew_angle) for each image
        for i, (item, angle) in enumerate(zip(ordered_items, rotation_angles)):
            img = item.img
            filename = os.path.basename(item.path)
            log_parts = [f"  [{i+1:2d}] {filename:40s}"]
            
            # Step 1: Rotate 180° if needed
            if angle == 180:
                img = rotate_180(img)
                log_parts.append("→ rotate 180°")
            else:
                log_parts.append("→ no rotation")
            
            # Step 2: Deskew (straighten small angles)
            img, deskew_angle = deskew_image(filename, img)
            
            print(" ".join(log_parts))
            corrected_items.append(ImageItem(item.path, img))
            rotation_info.append((angle, deskew_angle))
        
        print("-" * 90)
        print(f"[TIMING] Rotation & deskew: {time.time() - rotate_start:.3f}s")
        
        print("-" * 90)
        
        # Split into fronts/backs and pair
        n = len(corrected_items)
        half = n // 2
        front_items = corrected_items[:half]
        back_items = corrected_items[half:half + half]
        
        # Reverse backs order (duplex scanning convention)
        print(f"\n🔄 Reversing backs order: back[{len(back_items)-1}]...back[0]")
        back_items = back_items[::-1]
        
        print(f"📄 Creating {len(front_items)} page pairs:")
        for i, (f_item, b_item) in enumerate(zip(front_items, back_items)):
            f_name = os.path.basename(f_item.path)
            b_name = os.path.basename(b_item.path)
            print(f"  Page {i+1}: Front {f_name:30s} + Back {b_name}")
        
        pairs = list(zip([item.img for item in front_items], [item.img for item in back_items]))
        
        pdf_start = time.time()
        save_pdf_from_images_interleaved(pairs, out_path)
        print(f"[TIMING] PDF generation: {time.time() - pdf_start:.3f}s")
        
        # In test mode, do not send to printer
        if not getattr(cfg, "test_mode", False):
            print("\n🖨️  Sending to printer...")
            try:
                printer_name = cfg.printer.name.strip() if cfg.printer.name else None
                printer_ip = cfg.printer.ip.strip() if hasattr(cfg.printer, 'ip') and cfg.printer.ip else None
                print_pdf_duplex(out_path, printer_name=printer_name, printer_ip=printer_ip)
                logger.info("✅ Print job submitted successfully")
            except Exception as e:
                handle_printer_error(out_path, cfg.printer.name or cfg.printer.ip or "default", e)
                logger.warning("⚠️  Printing failed, but PDF saved successfully")

    elif mode == cfg.subdirs.get("scan_document") or mode == "scan_document":
        processing_start = time.time()
        
        # Import the new background removal based cropping
        # crop_document_v2 imported at module top
        
        def crop_document(img: Image.Image) -> List[Tuple[Image.Image, Tuple[int, int, int, int]]]:
            """Document detection and crop using background removal (v2).
            
            Uses withoutbg library for robust background removal, then detects
            largest foreground object with adaptive alpha threshold.
            
            Returns list with a single (crop, bbox) tuple.
            """
            try:
                # Use crop_document_v2 - now returns both cropped image AND bbox
                cropped, bbox = crop_document_v2(
                    img,
                    processing_width=300,  # Reduced for speed - still accurate for bbox
                    img_name=img_name
                )
                
                # Check if cropping was successful
                if cropped.size == img.size:
                    # No crop detected, return empty list to signal skip
                    return []
                
                # bbox is already in (x, y, w, h) format from crop_document_v2
                return [(cropped, bbox)]
                
            except Exception as e:
                print(f"⚠️  crop_document_v2 failed: {e}, returning original image")
                # Fallback: return original as-is
                original_width, original_height = img.size
                return [(img, (0, 0, original_width, original_height))]

        # Process each image sequentially (model is cached, but not thread-safe)
        # Store: (span, position, image, scan_dpi, rotation_angle, deskew_angle, original_filename)
        doc_items: List[Tuple[str, Tuple[int, int], Image.Image, float, int, float, str]] = []
        
        crop_start = time.time()
        for item in ordered_items:
            img_path = item.path
            img_name = os.path.basename(img_path)
            im = item.img

            im, deskew_angle = deskew_image(img_name, im)
            rotation_angle = 0  # scan_document mode doesn't use batch rotation
            
            
            # Determine scan DPI:
            # Prefer embedded metadata (if present), else infer from A4 size and snap to standard DPI.
            # A4 physical size: 8.27" × 11.69"; DPI ≈ pixels / inches
            mdpi = None
            info = getattr(im, "info", {})
            if isinstance(info, dict) and "dpi" in info:
                d = info["dpi"]
                if isinstance(d, tuple) and len(d) >= 2:
                    try:
                        mdpi = (float(d[0]) + float(d[1])) / 2.0
                    except Exception:
                        mdpi = None
                elif isinstance(d, (int, float)):
                    mdpi = float(d)

            # Fallback: infer from image dimensions vs A4
            scan_w_inch = 8.27
            scan_h_inch = 11.69
            dpi_w = im.width / scan_w_inch
            dpi_h = im.height / scan_h_inch
            inferred_dpi = (dpi_w + dpi_h) / 2.0  # Average DPI

            raw_dpi = mdpi if mdpi is not None else inferred_dpi
            # Snap to nearest common scanner DPI to avoid odd values
            common_dpi = [75, 100, 150, 200, 300, 600, 1200]
            scan_dpi = min(common_dpi, key=lambda v: abs(v - raw_dpi))

            # Log details for transparency
            if mdpi is not None:
                print(f"  Scan DPI(meta): {mdpi:.1f} → using {scan_dpi} (pixels {im.width}×{im.height})")
            else:
                print(f"  Scan DPI(infer): {inferred_dpi:.1f} → using {scan_dpi} (pixels {im.width}×{im.height})")
                
            documents = crop_document(im)  # Now returns list of (cropped, bbox)
            
            if not documents:
                # No documents detected, skip this image
                print(f"⚠️ No document detected in {img_name}, skipping")
                continue
            
            print(f"✓ Detected {len(documents)} document(s) in {img_name}")
            
            # Process all detected documents in this image
            for cropped, bbox in documents:
                bbox_x, bbox_y, bbox_w, bbox_h = bbox
                
                # Determine how many grid cells this document spans
                span = determine_document_span(
                    cropped.width, cropped.height,
                    cfg.a4_page.width_pt, cfg.a4_page.height_pt,
                    cfg.margin_pt, scan_dpi
                )
                
                # Store bbox from crop_document for metadata
                # Format: (span, bbox, cropped_img, dpi, rotation, deskew, source_path)
                doc_items.append((span, bbox, cropped, scan_dpi, rotation_angle, deskew_angle, img_path))
        
        print(f"[TIMING] Document detection & cropping: {time.time() - crop_start:.3f}s")
        
        if not doc_items:
            print("⚠️ scan_document: No documents detected")
        else:
            # Use smart layout to group documents into pages
            layout_start = time.time()
            pages = layout_documents_smart(
                doc_items,
                cfg.a4_page.width_pt,
                cfg.a4_page.height_pt,
                cfg.margin_pt,
            )
            print(f"[TIMING] Layout computation: {time.time() - layout_start:.3f}s")

            # Generate metadata for web UI editing
            try:
                generate_scan_document_metadata(s.id, doc_items, pages, out_dir)
            except Exception as e:
                print(f"⚠️  Metadata generation failed: {e}")

            # Prepare monochrome PDF path
            out_path_mono = os.path.join(out_dir, f"{s.id}_mono.pdf")
            
            # Fast PDF generation with PyMuPDF
            # save_pdf_scan_document_* imported at module top
            
            print("\n📊 PDF Generation Speed Test:")
            print("-" * 90)
            
            # Color PDF
            pdf_start = time.time()
            time_fast_color = save_pdf_scan_document_fast(
                pages,
                out_path,
                page_size=(cfg.a4_page.width_pt, cfg.a4_page.height_pt),
                margin=cfg.margin_pt,
            )
            print(f"✅ [FAST] Color PDF (PyMuPDF):     {time_fast_color:.3f}s")
            
            # Monochrome PDF
            mono_pdf_start = time.time()
            time_fast_mono = save_pdf_scan_document_mono_fast(
                pages,
                out_path_mono,
                page_size=(cfg.a4_page.width_pt, cfg.a4_page.height_pt),
                margin=cfg.margin_pt,
            )
            print(f"✅ [FAST] Mono PDF (PyMuPDF):      {time_fast_mono:.3f}s")
            
            print("-" * 90)
            print(f"💡 Total PDF generation time:       {time_fast_color + time_fast_mono:.3f}s")
            print("-" * 90)
            print(
                f"✅ scan_document: {len(doc_items)} documents in {len(pages)} pages → {out_path}"
            )
            # Confirm-and-print: only print if print_requested flag is True
            if s.print_requested and not getattr(cfg, "test_mode", False):
                print("\n🖨️  Printing monochrome...")
                try:
                    printer_name = cfg.printer.name.strip() if cfg.printer.name else None
                    printer_ip = cfg.printer.ip.strip() if hasattr(cfg.printer, 'ip') and cfg.printer.ip else None
                    print_pdf_monochrome(out_path_mono, duplex=False, printer_name=printer_name, printer_ip=printer_ip)
                    logger.info("✅ Print job submitted successfully")
                except Exception as e:
                    handle_printer_error(out_path_mono, cfg.printer.name or cfg.printer.ip or "default", e)
                    logger.warning("⚠️  Printing failed, but PDF saved successfully")

    elif mode == cfg.subdirs.get("card_2in1") or mode == "card_2in1":
        # Import the new background removal based cropping (same as scan_document)
        # crop_document_v2 imported at module top
        
        def crop_card(img: Image.Image, img_name: str) -> Tuple[Image.Image, float]:
            """Card detection using background removal (v2).
            
            Uses same approach as scan_document for consistency and speed:
            1. Deskew the image
            2. Remove background using withoutbg
            3. Detect largest foreground object (the card)
            4. Return tight crop and deskew angle
            """
            # Deskew first
            img, deskew_angle = deskew_image(img_name, img)
            try:
                # Use crop_document_v2 - now returns both cropped image AND bbox
                cropped, bbox = crop_document_v2(
                    img,
                    processing_width=200,  # Fast processing, sufficient for cards
                    img_name=img_name
                )
                return cropped, deskew_angle
            except Exception as e:
                print(f"⚠️  crop_document_v2 failed for {img_name}: {e}, returning original")
                return img, deskew_angle

        # Crop each image to its card region first
        crop_start = time.time()
        crop_results = [crop_card(item.img, os.path.basename(item.path)) for item in ordered_items]
        cropped = [img for img, _ in crop_results]
        deskew_angles = [angle for _, angle in crop_results]
        print(f"[TIMING] Card detection & cropping: {time.time() - crop_start:.3f}s ({len(cropped)} cards)")

        # Generate metadata for web UI editing
        try:
            # Note: We don't have pages layout yet, will be computed inside PDF generator
            # For now, save basic metadata
            pages_layout = layout_items_by_orientation(cropped)
            # Pass original source filenames (which were moved into project images directory)
            source_filenames = [os.path.basename(item.path) for item in ordered_items]
            generate_card_2in1_metadata(s.id, cropped, pages_layout, deskew_angles, out_dir, source_filenames)
        except Exception as e:
            print(f"⚠️  Metadata generation failed: {e}")

        # Fast PDF generation with PyMuPDF (imported at module top)
        
        print("\n📊 PDF Generation Speed Test:")
        print("-" * 90)
        
        # Color PDF
        pdf_start = time.time()
        time_fast_color = save_pdf_card_2in1_grid_fast(
            cropped,
            out_path,
            page_size=(cfg.a4_page.width_pt, cfg.a4_page.height_pt),
            margin=cfg.margin_pt,
        )
        print(f"✅ [FAST] Color PDF (PyMuPDF):     {time_fast_color:.3f}s")
        
        # Prepare monochrome PDF
        out_path_mono = os.path.join(out_dir, f"{s.id}_mono.pdf")
        
        mono_pdf_start = time.time()
        time_fast_mono = save_pdf_card_2in1_grid_mono_fast(
            cropped,
            out_path_mono,
            page_size=(cfg.a4_page.width_pt, cfg.a4_page.height_pt),
            margin=cfg.margin_pt,
        )
        print(f"✅ [FAST] Mono PDF (PyMuPDF):      {time_fast_mono:.3f}s")
        
        print("-" * 90)
        print(f"💡 Total PDF generation time:       {time_fast_color + time_fast_mono:.3f}s")
        print("-" * 90)
        
        # Confirm-and-print: only print if print_requested flag is True
        if s.print_requested and not getattr(cfg, "test_mode", False):
            print("\n🖨️  Printing monochrome...")
            try:
                printer_name = cfg.printer.name.strip() if cfg.printer.name else None
                printer_ip = cfg.printer.ip.strip() if hasattr(cfg.printer, 'ip') and cfg.printer.ip else None
                print_pdf_monochrome(out_path_mono, duplex=False, printer_name=printer_name, printer_ip=printer_ip)
                logger.info("✅ Print job submitted successfully")
            except Exception as e:
                handle_printer_error(out_path_mono, cfg.printer.name or cfg.printer.ip or "default", e)
                logger.warning("⚠️  Printing failed, but PDF saved successfully")

    else:
        # Unknown mode: do nothing
        return None

    # Unload background removal model to free RAM (~750MB saved)
    # Applies to both scan_document and card_2in1 modes
    # Trade-off: +1s load time vs 750MB RAM - worth it for 24/7 agent
    if mode in (cfg.subdirs.get("scan_document"), "scan_document", 
                cfg.subdirs.get("card_2in1"), "card_2in1"):
        _unload_bg_removal_model()
    
    # Print total session processing time
    total_time = time.time() - session_start
    print(f"\n[TIMING] {'='*70}")
    print(f"[TIMING] Total session processing time: {total_time:.3f}s")
    print(f"[TIMING] {'='*70}\n")

    # Skip deletion in test mode
    if cfg.delete_inbox_files_after_process and not getattr(cfg, "test_mode", False):
        deleted_count = 0
        failed_count = 0
        for p in s.images:
            try:
                if os.path.exists(p):
                    os.remove(p)
                    deleted_count += 1
            except Exception as e:
                failed_count += 1
                logger.warning(f"⚠️  Failed to delete {os.path.basename(p)}: {str(e)}")
        
        if deleted_count > 0:
            logger.info(f"🗑️  Cleaned up {deleted_count} processed files")
        if failed_count > 0:
            logger.warning(f"⚠️  Failed to delete {failed_count} files (may need manual cleanup)")

    return out_path  # Color PDF path for notification delivery


class ScanAgent:
    def __init__(self, cfg: Config):
        self.cfg = cfg

        # Build notification channels (Telegram + any future channels)
        channels = []
        bot = TelegramBot.from_config(cfg)
        if bot:
            bot.set_session_callback(self._handle_telegram_command)
            channels.append(bot)
        self.notification_manager = NotificationManager(channels)

        # Session manager with callbacks for processing and notifications
        self.sessions = SessionManager(
            cfg.session_timeout_seconds,
            on_confirm=lambda s: process_session(cfg, s, self.notification_manager),
            on_reject=self._on_session_rejected,
            on_state_change=self._on_session_state_change,
        )
        self.watcher = FTPWatcher(cfg.inbox_base, cfg.subdirs, self._on_new_file)

        # Async processing with priority queues
        # Priority queue: (priority, timestamp, data)
        # Priority 0 = signals (confirm/reject), Priority 1 = images
        self.event_queue = queue.PriorityQueue()
        self.event_counter = 0  # For stable sorting
        self.worker_thread = threading.Thread(target=self._process_events, daemon=True)
        self.running = False

        # Wire internal agent API so the web UI and other processes can reach us
        agent_api.init(self.sessions, self.notification_manager, self._handle_telegram_command)

    def _on_session_rejected(self, session: Session) -> None:
        """Called by SessionManager when a session is rejected or times out.

        Fires notify_session_action so all channels (e.g. Telegram) remove
        pending-confirmation UI regardless of what triggered the rejection.
        """
        logger.info(f"Session rejected/timed-out: {session.id} (mode: {session.mode})")
        self.notification_manager.notify_session_action(confirmed=False, action_by="timeout")

    def _on_session_state_change(self, session: Session, old_state: str, new_state: str) -> None:
        """Broadcast session state changes to all notification channels."""
        if new_state == "WAIT_CONFIRM":
            session_info = {
                "id": session.id,
                "mode": session.mode,
                "state": new_state,
                "image_count": len(session.images),
            }
            self.notification_manager.notify_session_ready(session_info)
            logger.info(f"Session {session.id} ready for confirmation (mode: {session.mode})")

    def _handle_telegram_command(self, confirm: bool, print_requested: bool) -> None:
        """Handle commands from Telegram bot."""
        session_to_process = None
        is_confirm = confirm
        request_print = print_requested

        # Find session to process (outside of lock for callback)
        with self.sessions._lock:
            latest_session = None
            for mode, s in self.sessions._by_mode.items():
                if s.state == "WAIT_CONFIRM":
                    if latest_session is None or s.last_activity > latest_session.last_activity:
                        latest_session = s

            if latest_session:
                # Update session state while holding lock
                if confirm:
                    latest_session.state = "CONFIRMED"
                    latest_session.print_requested = print_requested
                else:
                    latest_session.state = "REJECTED"

                # Mark session for processing and clean up tracking
                session_to_process = latest_session
                # Clean up tracking references (but keep session object for callback)
                del self.sessions._by_mode[latest_session.mode]
                for mode, sus in list(self.sessions._suspended_by_mode.items()):
                    try:
                        self.sessions._cleanup_session_files(sus)
                    except Exception:
                        pass
                    del self.sessions._suspended_by_mode[mode]

        # Process session outside of lock to avoid blocking
        if session_to_process:
            if confirm:
                logger.info(f"Session confirmed: {session_to_process.id}")
                # Notify all channels to remove pending-confirmation UI (e.g. Telegram buttons).
                # When the action came from Telegram, _do_confirm already snapshot+cleared the
                # tracked messages, so this becomes a safe no-op for that channel.
                self.notification_manager.notify_session_action(True, action_by="Web UI")
                self.sessions.on_confirm_cb(session_to_process)
            else:
                logger.info(f"Session rejected: {session_to_process.id}")
                self.notification_manager.notify_session_action(False, action_by="Web UI")
                self.sessions._cleanup_session_files(session_to_process)
                self.sessions.on_reject_cb(session_to_process)
        else:
            if confirm:
                logger.warning("Telegram confirm command received but no session in WAIT_CONFIRM state")
            else:
                logger.warning("Telegram reject command received but no session in WAIT_CONFIRM state")


    def _on_new_file(self, mode_folder_name: str, path: str):
        """Queue event for async processing (non-blocking)"""
        print(f"[ScanAgent] Queuing file event: {path} in folder: {mode_folder_name}")
        
        # Determine priority: signals get priority 0, images get priority 1
        if mode_folder_name in ("confirm", "confirm_print", "reject"):
            priority = 0  # High priority
            print(f"[ScanAgent] HIGH PRIORITY signal: {mode_folder_name}")
        else:
            priority = 1  # Normal priority
        
        # Put with priority and counter for stable ordering
        self.event_queue.put((priority, self.event_counter, mode_folder_name, path))
        self.event_counter += 1
    
    def _process_events(self):
        """Worker thread: process queued events asynchronously with priority"""
        print("[ScanAgent] Worker thread started")
        while self.running:
            try:
                # Wait for event with timeout to check running flag
                # PriorityQueue returns (priority, counter, mode_folder_name, path)
                priority, counter, mode_folder_name, path = self.event_queue.get(timeout=0.5)
                print(f"[ScanAgent] Processing event (priority={priority}): {path} in folder: {mode_folder_name}")
                
                # Map folder name to logical keys
                key_for = {v: k for k, v in self.cfg.subdirs.items()}
                key = key_for.get(mode_folder_name, mode_folder_name)
                print(f"[ScanAgent] Mapped to key: {key}")
                
                if key in ("confirm", "confirm_print", "reject"):
                    print(f"[ScanAgent] Signal file detected: {key}")
                    if key == "confirm":
                        # Confirm only: scan PDF without printing
                        print("[ScanAgent] Confirming session (no print)")
                        self.sessions.confirm_latest(print_requested=False)
                    elif key == "confirm_print":
                        # Confirm + print: scan PDF and send to printer
                        print("[ScanAgent] Confirming session (with print)")
                        self.sessions.confirm_latest(print_requested=True)
                    else:  # reject
                        print("[ScanAgent] Rejecting session")
                        self.sessions.reject_latest()
                    # Delete the signal file to keep server light
                    try:
                        if os.path.exists(path):
                            os.remove(path)
                            print(f"[ScanAgent] Deleted signal file: {path}")
                    except Exception as e:
                        print(f"[ScanAgent] Failed to delete signal file: {e}")
                else:
                    print(f"[ScanAgent] Adding image to session: {key}")
                    self.sessions.add_image(key, path)
                    # Hint that user navigated to confirm soon
                    self.sessions.hint_wait_confirm(key)
                
                self.event_queue.task_done()
                
            except queue.Empty:
                # Timeout - continue loop to check running flag
                continue
            except Exception as e:
                print(f"[ScanAgent] Error processing event: {e}")
                import traceback
                traceback.print_exc()
        
        print("[ScanAgent] Worker thread stopped")

    def start(self):
        self.running = True
        self.worker_thread.start()
        self.watcher.start()

        # Start all notification channels (Telegram, future channels, etc.)
        self.notification_manager.start_all()

        # Start internal agent API so web UI and other processes can reach us
        agent_api.start_in_thread()

        print("[ScanAgent] Started (async mode)")

    def stop(self):
        print("[ScanAgent] Stopping...")
        self.running = False
        self.watcher.stop()
        self.notification_manager.stop_all()
        self.worker_thread.join(timeout=5)
        print("[ScanAgent] Stopped")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config.local.yaml")
    args = ap.parse_args()
    
    # Initialize logger first
    logger.info("+" + "-"*78 + "+")
    logger.info("|" + " "*25 + "SCAN AGENT STARTING" + " "*34 + "|")
    logger.info("+" + "-"*78 + "+")
    
    # Load and validate configuration
    logger.info(f"📄 Loading configuration from: {args.config}")
    try:
        cfg = Config.load(args.config)
        logger.info("✅ Configuration loaded successfully")
    except Exception as e:
        logger.critical(f"❌ Failed to load configuration: {str(e)}", exc_info=True)
        sys.exit(1)
    
    # Validate configuration and system requirements
    try:
        validate_config(cfg)
    except Exception as e:
        logger.critical(f"❌ Configuration validation failed: {str(e)}")
        sys.exit(1)
    
    # Initialize resource monitor
    resource_monitor = ResourceMonitor(
        output_dir=cfg.output_dir,
        inbox_dir=cfg.inbox_base,
        retention_days=7,
        min_disk_mb=500,
        min_memory_mb=500
    )
    
    # Check initial resource status
    logger.info("📊 Checking system resources...")
    resource_monitor.report_status()
    
    # Schedule periodic cleanup (every 24 hours)
    if not getattr(cfg, "test_mode", False):
        schedule_periodic_cleanup(resource_monitor, interval_hours=24, dry_run=False)
    else:
        logger.info("⚠️  Test mode: Periodic cleanup disabled")
    
    # Initialize scan agent
    agent = ScanAgent(cfg)

    def _sigterm(*_):
        agent.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, _sigterm)
    signal.signal(signal.SIGTERM, _sigterm)

    agent.start()
    print("Scan Agent running. Watching:")
    for k, v in cfg.subdirs.items():
        print(f" - {k}: {os.path.join(cfg.inbox_base, v)}")
    
    # Block forever (signal.pause() doesn't work on Windows)
    try:
        while True:
            time.sleep(100)
    except KeyboardInterrupt:
        print("\n🛑 Shutting down...")
        agent.stop()


if __name__ == "__main__":
    main()
