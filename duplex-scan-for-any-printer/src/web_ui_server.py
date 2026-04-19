"""
Web UI Server for Scan Editor
FastAPI backend serving REST API and static files
"""
from __future__ import annotations

import base64
import io
import json
import mimetypes
import os
import re
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Optional

import cv2
import fitz  # PyMuPDF
import httpx
import numpy as np
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image
from pydantic import BaseModel

# Try to import pyvips for faster, low-memory image resizing when available
try:
    import pyvips
    HAS_PYVIPS = True
except Exception:
    HAS_PYVIPS = False


# Some OS/distro configs map .ts to Qt Linguist MIME type which breaks module
# workers under strict browser MIME checking. Override to correct type.
mimetypes.add_type("application/javascript", ".ts")

# Configuration
# Auto-detect environment: Docker vs Local
def get_scan_dir():
    """Get scan output directory based on environment"""
    # Check if running in Docker
    if os.path.exists("/share/scan_out"):
        return "/share/scan_out"
    
    # Local development - relative to project root
    project_root = Path(__file__).parent.parent
    local_scan_dir = project_root / "scan_out"
    local_scan_dir.mkdir(exist_ok=True)
    return str(local_scan_dir)

def get_scan_inbox_dir():
    """Get scan inbox directory based on environment"""
    # Check if running in Docker
    if os.path.exists("/share/scan_inbox"):
        return "/share/scan_inbox"
    
    # Local development - relative to project root
    project_root = Path(__file__).parent.parent
    local_scan_inbox = project_root / "scan_inbox"
    local_scan_inbox.mkdir(exist_ok=True)
    return str(local_scan_inbox)

SCAN_OUT_DIR = os.getenv("SCAN_OUTPUT_DIR", get_scan_dir())
SCAN_INBOX_DIR = os.getenv("SCAN_INBOX_DIR", get_scan_inbox_dir())
WEB_UI_PORT = int(os.getenv("WEB_UI_PORT", "8099"))
# Internal agent API URL (scan agent exposes session/channel state here)
AGENT_API_URL = os.getenv("AGENT_API_URL", "http://127.0.0.1:8098")
# Always operate in low-resource mode by default to support low-power devices (Raspberry Pi, etc.)
# We'll cap background thumbnail workers to a small number and use memory-efficient resizing.
DEFAULT_MAX_WORKERS = 2

# Fix broken SSL_CERT_FILE env var (may be set by another venv/project).
# httpx creates an SSL context at client init time even for plain http:// calls,
# so an invalid SSL_CERT_FILE raises FileNotFoundError before any request is made.
_ssl_cert = os.environ.get("SSL_CERT_FILE", "")
if _ssl_cert and not os.path.exists(_ssl_cert):
    try:
        import certifi
        os.environ["SSL_CERT_FILE"] = certifi.where()
    except ImportError:
        del os.environ["SSL_CERT_FILE"]


def _local_client() -> httpx.AsyncClient:
    """Return an httpx client suitable for localhost-only calls.

    Using verify=False is safe here because all traffic stays on the loopback
    interface (127.0.0.1) and never leaves the machine.
    """
    return httpx.AsyncClient(verify=False)

app = FastAPI(title="Scan Editor API", version="1.0.0")

# Ensure package imports like `agent.*` work when running under uvicorn from project root.
# The `agent` package lives in the same `src/` directory as this file, so add that
# directory to `sys.path` early.
_src_dir = str(Path(__file__).resolve().parent)
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

# Startup info
print(f"🚀 Scan Editor starting. pyvips available: {HAS_PYVIPS}. Platform: {os.name}/{os.sys.platform}")
if HAS_PYVIPS:
    print("💡 pyvips will be used for fast, low-memory thumbnail generation where possible.")
else:
    print("ℹ️  pyvips not available — falling back to Pillow (PIL). For best performance, install libvips and pyvips.")

# CORS: dev server needs localhost:5173; production runs same-origin via HA Ingress
_cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Accept"],
)

# Models
class CropBox(BaseModel):
    x: float
    y: float
    w: float
    h: float

class PageEdit(BaseModel):
    page: int
    crop: Optional[CropBox] = None
    rotate: Optional[int] = None
    brightness: Optional[float] = None
    contrast: Optional[float] = None

class EditRequest(BaseModel):
    filename: str
    pages: List[PageEdit]
    preview_width: int = 800

class CropFromMetadataRequest(BaseModel):
    project_id: str
    image_index: int
    bbox: List[CropBox]
    rotation: Optional[float] = None
    brightness: Optional[float] = None
    contrast: Optional[float] = None

class ProjectMetadata(BaseModel):
    """Project metadata for scan editing"""
    project_id: str
    original_pdf: str
    created: int
    updated: int
    images: List[Dict]  # List of image metadata
    layout: Optional[Dict] = None  # Layout settings

def _calculateDPI(imWidth: int, imHeight: int) -> int:
    # Determine scan DPI:
    # Prefer embedded metadata (if present), else infer from A4 size and snap to standard DPI.
    # A4 physical size: 8.27" × 11.69"; DPI ≈ pixels / inches
    scan_w_inch = 8.27
    scan_h_inch = 11.69
    dpi_w = imWidth / scan_w_inch
    dpi_h = imHeight / scan_h_inch
    inferred_dpi = (dpi_w + dpi_h) / 2.0  # Average DPI

    # Snap to nearest common scanner DPI to avoid odd values
    common_dpi = [75, 100, 150, 200, 300, 600, 1200]
    scan_dpi = min(common_dpi, key=lambda v: abs(v - inferred_dpi))
    return scan_dpi


_PROJECT_ID_RE = re.compile(r'^[\w\-]+$')


def _validate_project_id(project_id: str) -> None:
    """Raise HTTP 400 if project_id contains characters that could enable traversal."""
    if not _PROJECT_ID_RE.match(project_id):
        raise HTTPException(status_code=400, detail="Invalid project_id")


def _safe_path(base_dir: str, *parts: str) -> str:
    """Join path parts and verify the result stays within base_dir. Raises HTTP 400 on traversal."""
    joined = os.path.join(base_dir, *parts)
    resolved = os.path.realpath(joined)
    base_resolved = os.path.realpath(base_dir)
    if not resolved.startswith(base_resolved + os.sep) and resolved != base_resolved:
        raise HTTPException(status_code=400, detail="Invalid path")
    return resolved


def _safe_500(e: Exception, context: str = "Operation failed") -> HTTPException:
    """Log the real error server-side; return a generic message to the client."""
    print(f"ERROR [{context}]: {e}")
    import traceback
    traceback.print_exc()
    return HTTPException(status_code=500, detail=context)

# API Endpoints

@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "ok", "service": "scan-editor"}


@app.get("/api/bot/status")
async def bot_status():
    """Get notification channel statuses from the scan agent."""
    agent_reachable = False
    try:
        async with _local_client() as client:
            resp = await client.get(f"{AGENT_API_URL}/api/channels/status", timeout=2.0)
            channels = resp.json().get("channels", {})
            agent_reachable = True
    except Exception:
        channels = {}

    telegram = channels.get("telegram", {})

    if not agent_reachable:
        default_message = "Agent not reachable"
    elif not telegram:
        default_message = "Telegram not configured"
    elif not telegram.get("enabled", False):
        # Agent reported the channel — check if it's configured but disabled
        configured = telegram.get("configured", bool(telegram.get("bot_token")))
        default_message = "Telegram disabled" if configured else "Telegram not configured"
    else:
        default_message = "Bot stopped"

    return JSONResponse({
        "enabled": telegram.get("enabled", False),
        "connected": telegram.get("connected", False),
        "pending_sessions": 1 if telegram.get("pending_session", False) else 0,
        "authorized_users": telegram.get("authorized_users", 0),
        "message": telegram.get("message", default_message),
        "channels": channels,
    })


@app.get("/api/bot/info")
async def bot_info():
    """Return Telegram registered chats / notify_chat_ids for the settings UI."""
    try:
        async with _local_client() as client:
            resp = await client.get(f"{AGENT_API_URL}/api/channels/telegram/info", timeout=2.0)
            return JSONResponse(resp.json())
    except Exception:
        return JSONResponse({"registered_chats": {}, "notify_chat_ids": []})


@app.get("/api/session/status")
async def session_status():
    """Get current session status from the scan agent."""
    try:
        async with _local_client() as client:
            resp = await client.get(f"{AGENT_API_URL}/api/session/current", timeout=2.0)
            data = resp.json()
    except Exception:
        return JSONResponse({
            "current_session_id": None,
            "state": "COLLECTING",
            "mode": "unknown",
            "image_count": 0,
            "timeout_seconds": 300,
            "message": "Agent not reachable",
        })

    session = data.get("session")
    if not session:
        return JSONResponse({
            "current_session_id": None,
            "state": "COLLECTING",
            "mode": "unknown",
            "image_count": 0,
            "timeout_seconds": 300,
            "message": "No active session",
        })

    return JSONResponse({
        "current_session_id": session.get("id"),
        "state": session.get("state", "COLLECTING"),
        "mode": session.get("mode", "unknown"),
        "image_count": session.get("image_count", 0),
        "timeout_seconds": 300,
        "message": f"Session {session.get('id')} — {session.get('state')}",
    })


@app.post("/api/session/confirm")
async def session_confirm_proxy(print_requested: bool = False):
    """Forward confirm command to scan agent."""
    try:
        async with _local_client() as client:
            resp = await client.post(
                f"{AGENT_API_URL}/api/session/confirm",
                params={"print_requested": print_requested},
                timeout=5.0,
            )
            return JSONResponse(resp.json(), status_code=resp.status_code)
    except Exception as e:
        return JSONResponse({"ok": False, "message": str(e)}, status_code=503)


@app.post("/api/session/reject")
async def session_reject_proxy():
    """Forward reject command to scan agent."""
    try:
        async with _local_client() as client:
            resp = await client.post(f"{AGENT_API_URL}/api/session/reject", timeout=5.0)
            return JSONResponse(resp.json(), status_code=resp.status_code)
    except Exception as e:
        return JSONResponse({"ok": False, "message": str(e)}, status_code=503)


@app.get("/api/activity")
async def list_activity():
    """Lightweight list of recent processed scan sessions (no thumbnail generation)."""
    if not os.path.exists(SCAN_OUT_DIR):
        return {"items": []}

    items = []
    for filename in sorted(os.listdir(SCAN_OUT_DIR), reverse=True):
        # Only color PDFs (skip _mono.pdf)
        if not filename.endswith(".pdf") or filename.endswith("_mono.pdf"):
            continue
        filepath = os.path.join(SCAN_OUT_DIR, filename)
        if not os.path.isfile(filepath):
            continue
        stat = os.stat(filepath)
        base_name = os.path.splitext(filename)[0]

        # Try to load lightweight metadata from companion JSON
        md_path = os.path.join(SCAN_OUT_DIR, f"{base_name}.json")
        pages = None
        md_created = None
        if os.path.exists(md_path):
            try:
                with open(md_path, "r", encoding="utf-8") as f:
                    md = json.load(f)
                    pages = md.get("pages") or md.get("page_count")
                    md_created = md.get("created")
            except Exception:
                pass

        mode = "unknown"
        if "scan_document" in filename:
            mode = "scan_document"
        elif "card" in filename or "2in1" in filename:
            mode = "card_2in1"
        elif "duplex" in filename or "copy" in filename:
            mode = "scan_duplex"

        items.append({
            "id": base_name,
            "filename": filename,
            "mode": mode,
            "pages": pages,
            "size_mb": round(stat.st_size / 1024 / 1024, 2),
            "created": int(md_created) if md_created else int(stat.st_ctime),
        })

    return {"items": items[:20]}  # cap at 20 most recent


@app.get("/api/projects")
async def list_projects():
    """List all PDF projects (generated scans) with metadata"""
    if not os.path.exists(SCAN_OUT_DIR):
        return {"projects": []}
    
    projects = []
    for filename in sorted(os.listdir(SCAN_OUT_DIR), reverse=True):
        if filename.endswith('.pdf') and not filename.endswith('_mono.pdf'):
            filepath = os.path.join(SCAN_OUT_DIR, filename)
            stat = os.stat(filepath)
            
            # Get PDF info
            try:
                doc = fitz.open(filepath)
                pages_count = len(doc)
                
                # Get first page as thumbnail
                first_page = doc[0]
                pix = first_page.get_pixmap(dpi=72)
                thumb_bytes = pix.tobytes("png")
                thumb_b64 = base64.b64encode(thumb_bytes).decode()
                
                doc.close()
                
                # Check for metadata file
                base_name = os.path.splitext(filename)[0]
                metadata_path = os.path.join(SCAN_OUT_DIR, f"{base_name}.json")
                has_metadata = os.path.exists(metadata_path)
                md_created = None
                md_updated = None
                if has_metadata:
                    try:
                        with open(metadata_path, 'r', encoding='utf-8') as f:
                            md = json.load(f)
                            md_created = int(md.get('created')) if isinstance(md.get('created'), (int, float, str)) and str(md.get('created')).isdigit() else None
                            md_updated = int(md.get('updated')) if isinstance(md.get('updated'), (int, float, str)) and str(md.get('updated')).isdigit() else None
                    except Exception:
                        md_created = None
                        md_updated = None
                
                # Extract mode from filename (test_scan_document, test_card_2in1, etc)
                mode = "unknown"
                if "scan_document" in filename:
                    mode = "scan_document"
                elif "card" in filename or "2in1" in filename:
                    mode = "card_2in1"
                elif "duplex" in filename:
                    mode = "scan_duplex"
                
                projects.append({
                    "id": base_name,
                    "filename": filename,
                    "mode": mode,
                    "pages": pages_count,
                    "size": stat.st_size,
                    "size_mb": round(stat.st_size / 1024 / 1024, 2),
                    "created": int(md_created) if md_created is not None else int(stat.st_ctime),
                    "updated": int(md_updated) if md_updated is not None else int(stat.st_mtime),
                    "has_metadata": has_metadata,
                    "thumbnail": f"data:image/png;base64,{thumb_b64}"
                })
            except Exception as e:
                print(f"Error processing {filename}: {e}")
                continue
    
    return {"projects": projects}


@app.get("/api/projects/{project_id}/images")
async def get_project_images(project_id: str):
    """Extract all images from PDF project"""
    _validate_project_id(project_id)
    pdf_path = _safe_path(SCAN_OUT_DIR, f"{project_id}.pdf")
    if not os.path.exists(pdf_path):
        raise HTTPException(status_code=404, detail="Project not found")
    
    try:
        doc = fitz.open(pdf_path)
        images = []
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            
            # Get page as image
            pix = page.get_pixmap(dpi=150)
            img_bytes = pix.tobytes("png")
            img_b64 = base64.b64encode(img_bytes).decode()
            
            # Try to detect individual images on page (for scan_document mode)
            # For now, treat each page as one image
            images.append({
                "id": f"img_{page_num}",
                "page": page_num,
                "width": int(page.rect.width),
                "height": int(page.rect.height),
                "thumbnail": f"data:image/png;base64,{img_b64}",
                "url": f"/api/scan/{project_id}.pdf/page/{page_num}?size=medium"
            })
        
        doc.close()
        return {"images": images}
        
    except Exception as e:
        raise _safe_500(e, "Failed to extract project images")


@app.get("/api/projects/{project_id}/metadata")
async def get_project_metadata(project_id: str):
    """Get project metadata from pipeline-generated JSON"""
    _validate_project_id(project_id)
    metadata_path = _safe_path(SCAN_OUT_DIR, f"{project_id}.json")

    if not os.path.exists(metadata_path):
        raise HTTPException(status_code=404, detail="Metadata not found")

    try:
        with open(metadata_path, 'r', encoding='utf-8') as f:
            metadata = json.load(f)
    except Exception as e:
        raise _safe_500(e, "Failed to load project metadata")

    # Metadata now stores simple filenames (no paths)
    # Frontend will use /api/images/{project_id}/{filename} to access
    if 'images' in metadata:
        for img in metadata['images']:
            # Ensure default values
            img.setdefault('brightness', 1.0)
            img.setdefault('contrast', 1.0)
            img.setdefault('rotation', 0)
            img.setdefault('deskew_angle', 0.0)

    return metadata


@app.get("/api/projects/{project_id}/output")
async def get_project_output(project_id: str):
    """Return list of output image filenames for a project.

    Behavior:
    - If `scan_out/{project_id}/images/` exists and contains images, return those filenames.
    - Otherwise, if a PDF exists (preferred: `{project_id}_color.pdf`, then `{project_id}.pdf`, then edited PDF), extract pages to that images folder and return filenames.
    - If nothing is available, return an empty `images` list.
    """
    _validate_project_id(project_id)
    try:
        project_images_dir = _safe_path(SCAN_OUT_DIR, project_id, 'images')

        # If images directory exists and has image files, return them
        if os.path.isdir(project_images_dir):
            files = sorted([f for f in os.listdir(project_images_dir) if os.path.isfile(os.path.join(project_images_dir, f))])
            images = [f for f in files if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
            if images:
                return {"images": images}

        # No pre-extracted images — try to find a PDF to extract pages from
        pdf_candidates = [
            _safe_path(SCAN_OUT_DIR, f"{project_id}_color.pdf"),
            _safe_path(SCAN_OUT_DIR, f"{project_id}.pdf"),
            _safe_path(SCAN_OUT_DIR, f"{project_id}_edited.pdf"),
        ]

        for pdf_path in pdf_candidates:
            if os.path.exists(pdf_path):
                # Ensure images dir exists
                os.makedirs(project_images_dir, exist_ok=True)
                try:
                    doc = fitz.open(pdf_path)
                    out_files = []
                    for i, page in enumerate(doc):
                        pix = page.get_pixmap(dpi=150)
                        outname = f"page_{i}.jpg"
                        outpath = os.path.join(project_images_dir, outname)
                        # Save page image (atomic write)
                        tmp_out = outpath + '.tmp'
                        try:
                            pix.save(tmp_out)
                            try:
                                os.replace(tmp_out, outpath)
                            except Exception:
                                os.rename(tmp_out, outpath)
                        except Exception:
                            # Fallback: write bytes directly
                            with open(outpath, 'wb') as w:
                                w.write(pix.tobytes('jpg'))

                        out_files.append(outname)
                    doc.close()
                    return {"images": out_files}
                except Exception as e:
                    raise HTTPException(status_code=500, detail=f"Failed to extract PDF pages: {e}")

        # Nothing found
        return {"images": []}

    except HTTPException:
        raise
    except Exception as e:
        raise _safe_500(e, "Failed to get project output")


@app.get("/api/images/{filename}")
async def get_project_image(filename: str, project_id: str, size: str = "medium", request: Request = None):
    """Serve image with smart resizing and caching
    
    Strategy:
    - Original images stay in scan_inbox (300-600 DPI, several MB each)
    - Generate thumbnails on-demand with disk caching
    - Cache in scan_out/.thumbnails/{size}/{filename}
    
    Sizes:
    - thumbnail: 200px width (for grid view)
    - medium: 800px width (for editor preview)
    - large: 1600px width (for detail view)
    - original: Full resolution (fallback)
    
    Security:
    - Validates project_id exists
    - Prevents directory traversal
    - Only serves files referenced in project metadata
    
    Performance:
    - Disk cache for generated thumbnails
    - ETags for browser caching
    - Progressive JPEG for faster loading
    
    Args:
        filename: Image filename
        project_id: Project ID
        size: Image size (thumbnail/medium/large/original)
    """
    # Security: Prevent directory traversal
    if '..' in filename or filename.startswith('/') or '\\' in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    # Security: Validate project_id
    _validate_project_id(project_id)

    # Security: Validate project exists and get source path
    project_json = _safe_path(SCAN_OUT_DIR, f"{project_id}.json")
    if not os.path.exists(project_json):
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Load metadata to get source_path
    try:
        with open(project_json, 'r') as f:
            metadata = json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to load metadata")
    
    # Find image in metadata
    img_meta = next((img for img in metadata.get('images', []) 
                    if img.get('filename') == filename or img.get('source_file') == filename), None)

    if not img_meta:
        raise HTTPException(status_code=404, detail=f"Image not in project: {filename}")

    # Only serve images from the project's `images` folder under SCAN_OUT_DIR
    project_images_dir = _safe_path(SCAN_OUT_DIR, project_id, 'images')

    # Build expected path
    source_path = _safe_path(project_images_dir, filename)

    if not os.path.exists(source_path):
        raise HTTPException(status_code=404, detail=f"Source image not found for: {filename}")
    
    # Security: Check file size of original (limit 50MB)
    source_size = os.path.getsize(source_path)
    if source_size > 50 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Source file too large")
    
    # Size configuration
    size_config = {
        'thumbnail': 200,
        'medium': 800,
        'large': 1600,
        'original': None
    }
    
    target_width = size_config.get(size)
    if target_width is None and size != 'original':
        raise HTTPException(status_code=400, detail="Invalid size parameter")
    
    # Original size: serve source file directly
    if size == 'original':
        file_stat = os.stat(source_path)
        etag = f'"{file_stat.st_mtime}-{file_stat.st_size}"'
        last_modified = time.strftime('%a, %d %b %Y %H:%M:%S GMT', time.gmtime(file_stat.st_mtime))
        
        # Check If-None-Match
        if request and request.headers.get('if-none-match') == etag:
            return JSONResponse(status_code=304, content=None)
        
        return FileResponse(
            source_path,
            media_type="image/jpeg",
            headers={
                'ETag': etag,
                'Last-Modified': last_modified,
                'Cache-Control': 'public, max-age=31536000, immutable',
            }
        )
    
    # Thumbnail: check cache first
    cache_dir = os.path.join(SCAN_OUT_DIR, '.thumbnails', size)
    os.makedirs(cache_dir, exist_ok=True)
    
    cache_path = os.path.join(cache_dir, filename)
    
    # Generate thumbnail if not cached or source is newer
    source_mtime = os.path.getmtime(source_path)
    needs_generate = True
    
    if os.path.exists(cache_path):
        cache_mtime = os.path.getmtime(cache_path)
        if cache_mtime >= source_mtime:
            needs_generate = False
    
    if needs_generate:
        try:
            # Generate thumbnail using PIL with efficient settings and atomic write
            from PIL import Image as PILImage

            # Prefer pyvips if available for speed + low memory
            # Skip pyvips for files marked as problematic
            no_pyvips_marker = cache_path + '.no_pyvips'
            if HAS_PYVIPS and not os.path.exists(no_pyvips_marker):
                try:
                    # pyvips: use the class helper to get a JPEG buffer directly
                    try:
                        # Safer pyvips path: open file with sequential access and produce a resized image
                        # This avoids pyvips returning unexpected types from convenience helpers.
                        img = pyvips.Image.new_from_file(source_path, access='sequential')
                        # Use thumbnail_image which preserves aspect ratio and is memory-efficient
                        img_thumb = img.thumbnail_image(int(target_width))

                        # Convert to JPEG buffer
                        buf = img_thumb.write_to_buffer('.jpg')

                        # Normalize buffer to bytes if necessary
                        if isinstance(buf, memoryview):
                            buf = bytes(buf)
                        elif isinstance(buf, bytearray):
                            buf = bytes(buf)
                        elif isinstance(buf, str):
                            try:
                                buf = buf.encode('latin-1')
                            except Exception:
                                buf = buf.encode('utf-8', errors='ignore')

                        tmp_cache = cache_path + '.tmp'
                        with open(tmp_cache, 'wb') as out_f:
                            out_f.write(buf)
                        try:
                            os.replace(tmp_cache, cache_path)
                        except Exception:
                            os.rename(tmp_cache, cache_path)
                    except Exception as e:
                        # If pyvips failed for this file, mark it so we skip it next time
                        try:
                            open(no_pyvips_marker, 'w').close()
                        except Exception:
                            pass
                        # propagate to outer handler which logs and falls back to PIL
                        raise
                except Exception as e:
                    print(f"⚠️  pyvips thumbnail failed for {filename}: {type(e).__name__}: {repr(e)}")
                    try:
                        print('pyvips version:', getattr(pyvips, '__version__', 'unknown'))
                    except Exception:
                        pass
                    # show traceback
                    traceback.print_exc()
                    # show buf info if available
                    try:
                        if 'buf' in locals():
                            b = locals().get('buf')
                            print('pyvips buf type:', type(b))
                            try:
                                if isinstance(b, (bytes, bytearray, memoryview)):
                                    print('pyvips buf len:', len(b))
                                    print('pyvips buf head:', bytes(b)[:64])
                                elif isinstance(b, str):
                                    print('pyvips buf (str) len:', len(b))
                                    print('pyvips buf head (repr):', repr(b[:64]))
                                else:
                                    print('pyvips buf repr:', repr(b)[:128])
                            except Exception:
                                pass
                    except Exception:
                        pass
                    # fallback to PIL
                    with PILImage.open(source_path) as img:
                        img_copy = img.copy()
                        img_copy.thumbnail((target_width, target_width * 3), PILImage.Resampling.LANCZOS)
                        tmp_cache = cache_path + '.tmp'
                        img_copy.save(tmp_cache, 'JPEG', quality=78)
                        try:
                            os.replace(tmp_cache, cache_path)
                        except Exception:
                            os.rename(tmp_cache, cache_path)
            else:
                with PILImage.open(source_path) as img:
                    # Use in-place thumbnail to be memory efficient (low RAM)
                    img_copy = img.copy()
                    img_copy.thumbnail((target_width, int(target_width * 3)), PILImage.Resampling.LANCZOS)
                    tmp_cache = cache_path + '.tmp'
                    img_copy.save(tmp_cache, 'JPEG', quality=80)
                    try:
                        os.replace(tmp_cache, cache_path)
                    except Exception:
                        os.rename(tmp_cache, cache_path)

            # Small log for debug
            try:
                print(f"🖼️  Generated {size} thumbnail: {filename} ({source_size // 1024}KB → {os.path.getsize(cache_path) // 1024}KB)")
            except Exception:
                pass

        except Exception as e:
            print(f"⚠️  Thumbnail generation failed for {filename}: {e}")
            # Fallback to original
            cache_path = source_path
    
    # Serve cached thumbnail
    file_stat = os.stat(cache_path)
    etag = f'"{file_stat.st_mtime}-{file_stat.st_size}-{size}"'
    last_modified = time.strftime('%a, %d %b %Y %H:%M:%S GMT', time.gmtime(file_stat.st_mtime))
    
    # Check If-None-Match
    if request and request.headers.get('if-none-match') == etag:
        return JSONResponse(status_code=304, content=None)
    
    return FileResponse(
        cache_path,
        media_type="image/jpeg",
        headers={
            'ETag': etag,
            'Last-Modified': last_modified,
            'Cache-Control': 'public, max-age=31536000, immutable',
        }
    )


@app.post("/api/projects/{project_id}/precache_thumbnails")
async def precache_thumbnails(project_id: str, request: Request):
    """Pre-generate thumbnails for a project (background worker using thread pool).

    Expects optional JSON body: { "sizes": ["thumbnail","medium","large"] }
    Returns a summary of generated/cached/missing files.
    """
    try:
        body = await request.json()
    except Exception:
        body = {}

    size_list = body.get('sizes') if isinstance(body.get('sizes'), list) else ['thumbnail', 'medium', 'large']

    metadata_path = os.path.join(SCAN_OUT_DIR, f"{project_id}.json")
    if not os.path.exists(metadata_path):
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        with open(metadata_path, 'r', encoding='utf-8') as f:
            metadata = json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read metadata: {e}")

    images = [img.get('filename') or img.get('source_file') for img in metadata.get('images', []) if img.get('filename') or img.get('source_file')]
    if not images:
        return {"status": "no_images"}

    # Worker to generate one thumbnail
    def generate_one(fname, sz):
        try:
            project_images_dir = os.path.join(SCAN_OUT_DIR, project_id, 'images')
            source_path = os.path.join(project_images_dir, fname)
            if not os.path.exists(source_path):
                return (fname, sz, 'missing')

            cache_dir = os.path.join(SCAN_OUT_DIR, '.thumbnails', sz)
            os.makedirs(cache_dir, exist_ok=True)
            cache_path = os.path.join(cache_dir, fname)

            try:
                source_mtime = os.path.getmtime(source_path)
                if os.path.exists(cache_path) and os.path.getmtime(cache_path) >= source_mtime:
                    return (fname, sz, 'cached')
            except Exception:
                pass

            # Prefer pyvips when available, unless file marked to skip
            cache_no_pyvips = os.path.join(SCAN_OUT_DIR, '.thumbnails', sz, fname + '.no_pyvips')
            if HAS_PYVIPS and not os.path.exists(cache_no_pyvips):
                try:
                    w = {'thumbnail':200,'medium':800,'large':1600}.get(sz,800)
                    # Safer: open with sequential access and thumbnail_image
                    img = pyvips.Image.new_from_file(source_path, access='sequential')
                    img_thumb = img.thumbnail_image(int(w))
                    buf = img_thumb.write_to_buffer('.jpg')
                    if isinstance(buf, memoryview):
                        buf = bytes(buf)
                    elif isinstance(buf, bytearray):
                        buf = bytes(buf)
                    elif isinstance(buf, str):
                        try:
                            buf = buf.encode('latin-1')
                        except Exception:
                            buf = buf.encode('utf-8', errors='ignore')
                    tmp_cache = os.path.join(SCAN_OUT_DIR, '.thumbnails', sz, fname + '.tmp')
                    with open(tmp_cache, 'wb') as out_f:
                        out_f.write(buf)
                    try:
                        os.replace(tmp_cache, os.path.join(SCAN_OUT_DIR, '.thumbnails', sz, fname))
                    except Exception:
                        os.rename(tmp_cache, os.path.join(SCAN_OUT_DIR, '.thumbnails', sz, fname))
                    return (fname, sz, 'generated')
                except Exception:
                    # mark file to skip pyvips for future runs
                    try:
                        open(cache_no_pyvips, 'w').close()
                    except Exception:
                        pass
                    # fallback to PIL below
                    pass

            # PIL fallback
            from PIL import Image as PILImage
            with PILImage.open(source_path) as img:
                aspect_ratio = img.height / img.width
                target_width = {'thumbnail':200,'medium':800,'large':1600}.get(sz,800)
                new_width = target_width
                new_height = int(target_width * aspect_ratio)
                img_resized = img.resize((new_width, new_height), PILImage.Resampling.LANCZOS)
                tmp_cache = os.path.join(SCAN_OUT_DIR, '.thumbnails', sz, fname + '.tmp')
                img_resized.save(tmp_cache, 'JPEG', quality=80)
                try:
                    os.replace(tmp_cache, os.path.join(SCAN_OUT_DIR, '.thumbnails', sz, fname))
                except Exception:
                    os.rename(tmp_cache, os.path.join(SCAN_OUT_DIR, '.thumbnails', sz, fname))
            return (fname, sz, 'generated')

        except Exception as e:
            return (fname, sz, f'error:{str(e)[:200]}')

    # Limit parallelism on low-resource devices like Raspberry Pi
    # Always limit parallelism to a small number to avoid high CPU/RAM usage on embedded devices
    max_workers = DEFAULT_MAX_WORKERS
    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = [ex.submit(generate_one, fname, sz) for fname in images for sz in size_list]
        for fut in as_completed(futures):
            try:
                results.append(fut.result())
            except Exception as e:
                results.append(('unknown', 'unknown', f'error:{str(e)[:200]}'))

    summary = {}
    for fname, sz, status in results:
        summary.setdefault(status, 0)
        summary[status] += 1

    return {"status": "done", "summary": summary}


@app.put("/api/projects/{project_id}/metadata")
async def update_project_metadata(project_id: str, request: Request):
    """Merge client-provided edits into existing project metadata.

    The server does not blindly trust the client. It accepts a limited
    set of editable fields per-image and merges them into the on-disk
    metadata file. This prevents the client from overwriting server-
    managed fields like `created`, `original_pdf`, etc.
    """
    metadata_path = os.path.join(SCAN_OUT_DIR, f"{project_id}.json")

    try:
        payload = await request.json()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {e}")

    # Only accept 'images' edits from client
    incoming_images = payload.get('images') if isinstance(payload, dict) else None
    if incoming_images is None:
        raise HTTPException(status_code=400, detail="Request must include 'images' list")

    # Load existing metadata if present, otherwise initialize a minimal structure
    if os.path.exists(metadata_path):
        try:
            with open(metadata_path, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to read existing metadata: {e}")
    else:
        metadata = {
            'project_id': project_id,
            'original_pdf': f"{project_id}.pdf",
            'created': int(time.time()),
            'updated': int(time.time()),
            'images': [],
            'layout': None
        }

    # Ensure images list exists
    metadata.setdefault('images', [])

    # Helper to normalize bbox entries
    def sanitize_bbox(b):
        # Accept either single bbox object or list of bbox objects
        if b is None:
            return None
        def valid_box(box):
            try:
                x = float(box.get('x'))
                y = float(box.get('y'))
                w = float(box.get('w'))
                h = float(box.get('h'))
                return {'x': x, 'y': y, 'w': w, 'h': h}
            except Exception:
                return None

        if isinstance(b, list):
            out = [valid_box(bb) for bb in b]
            return [o for o in out if o is not None]
        elif isinstance(b, dict):
            vb = valid_box(b)
            return vb
        else:
            return None

    # Index existing images by id and filename for quick lookup
    id_index = {img.get('id'): img for img in metadata['images'] if 'id' in img}
    fn_index = {img.get('filename'): img for img in metadata['images'] if 'filename' in img}

    updated_ids = []
    now_ts = int(time.time())

    # Allowed fields client may update per image
    allowed_fields = {'rotation', 'deskew_angle', 'brightness', 'contrast', 'bbox'}

    for inc in incoming_images:
        if not isinstance(inc, dict):
            continue

        img_id = inc.get('id')
        filename = inc.get('filename')

        target = None
        if img_id and img_id in id_index:
            target = id_index[img_id]
        elif filename and filename in fn_index:
            target = fn_index[filename]

        # If target not found, create a new minimal image entry and append
        if target is None:
            target = {
                'id': img_id or f"img_{len(metadata['images'])}",
                'filename': filename or '',
                'page': inc.get('page'),
                'width': inc.get('width'),
                'height': inc.get('height'),
                'rotation': 0,
                'deskew_angle': 0.0,
                'brightness': 1.0,
                'contrast': 1.0,
                'bbox': None
            }
            metadata['images'].append(target)
            # update indexes
            id_index[target.get('id')] = target
            if target.get('filename'):
                fn_index[target.get('filename')] = target

        # Merge allowed fields
        for k, v in inc.items():
            if k in allowed_fields:
                if k == 'bbox':
                    sanitized = sanitize_bbox(v)
                    target['bbox'] = sanitized
                elif k in ('brightness', 'contrast'):
                    try:
                        target[k] = float(v)
                    except Exception:
                        pass
                elif k in ('rotation', 'deskew_angle'):
                    try:
                        target[k] = float(v)
                    except Exception:
                        pass

        updated_ids.append(target.get('id'))

    # Update the updated timestamp and write back safely
    metadata['updated'] = now_ts

    try:
        tmp_path = metadata_path + '.tmp'
        with open(tmp_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, metadata_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to write metadata: {e}")

    return {"status": "success", "updated": now_ts, "updated_images": updated_ids}


@app.get("/api/scans")
async def list_scans():
    """List all PDF files in scan_out directory"""
    if not os.path.exists(SCAN_OUT_DIR):
        return {"scans": []}
    
    scans = []
    for filename in sorted(os.listdir(SCAN_OUT_DIR), reverse=True):
        if filename.endswith('.pdf'):
            filepath = os.path.join(SCAN_OUT_DIR, filename)
            stat = os.stat(filepath)
            
            # Get PDF info
            try:
                doc = fitz.open(filepath)
                pages = len(doc)
                doc.close()
            except:
                pages = 0
            
            scans.append({
                "filename": filename,
                "path": filepath,
                "size": stat.st_size,
                "size_mb": round(stat.st_size / 1024 / 1024, 2),
                "created": int(stat.st_ctime),
                "pages": pages
            })
    
    return {"scans": scans}


@app.get("/api/scan/{filename}/info")
async def get_scan_info(filename: str):
    """Get PDF metadata"""
    filepath = _safe_path(SCAN_OUT_DIR, filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="File not found")
    
    try:
        doc = fitz.open(filepath)
        
        # Get first page dimensions
        page = doc[0]
        width = int(page.rect.width)
        height = int(page.rect.height)
        
        info = {
            "filename": filename,
            "pages": len(doc),
            "width": width,
            "height": height,
            "metadata": doc.metadata
        }
        
        doc.close()
        return info
    except Exception as e:
        raise _safe_500(e, "Failed to get scan info")
async def get_page_image(filename: str, page_num: int, size: str = "medium"):
    """
    Extract page as image with specified size
    size: small (400px), medium (800px), large (1200px)
    """
    filepath = _safe_path(SCAN_OUT_DIR, filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="File not found")
    
    try:
        doc = fitz.open(filepath)
        
        if page_num < 0 or page_num >= len(doc):
            raise HTTPException(status_code=400, detail="Invalid page number")
        
        page = doc[page_num]
        
        # Determine DPI based on size
        if size == "small":
            dpi = 72  # ~400px width for A4
        elif size == "large":
            dpi = 200  # ~1600px width
        else:  # medium
            dpi = 150  # ~1200px width
        
        # Render page as image
        pix = page.get_pixmap(dpi=dpi)
        img_data = pix.tobytes("png")
        
        doc.close()
        
        return StreamingResponse(
            io.BytesIO(img_data),
            media_type="image/png",
            headers={"Cache-Control": "max-age=3600"}
        )
    except HTTPException:
        raise
    except Exception as e:
        raise _safe_500(e, "Failed to render page")


@app.get("/api/scan/{filename}/pages")
async def get_all_pages(filename: str, size: str = "small"):
    """Get all pages as base64 images (for thumbnail gallery)"""
    filepath = _safe_path(SCAN_OUT_DIR, filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="File not found")
    
    try:
        doc = fitz.open(filepath)
        pages = []
        
        dpi = 72 if size == "small" else 100
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            pix = page.get_pixmap(dpi=dpi)
            img_data = pix.tobytes("png")
            b64 = base64.b64encode(img_data).decode()
            
            pages.append({
                "page": page_num,
                "image": f"data:image/png;base64,{b64}",
                "width": pix.width,
                "height": pix.height
            })
        
        doc.close()
        return {"pages": pages}
    except Exception as e:
        raise _safe_500(e, "Failed to get pages")


@app.post("/api/edit")
async def apply_edits(request: EditRequest):
    """Apply edits to PDF and generate new file"""
    filepath = _safe_path(SCAN_OUT_DIR, request.filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="File not found")
    
    try:
        # Extract images from PDF
        doc = fitz.open(filepath)
        
        # Get original dimensions from first page
        first_page = doc[0]
        original_width = int(first_page.rect.width)
        
        # Calculate scale factor
        scale = original_width / request.preview_width
        
        # Process each page
        processed_images = []
        
        for page_edit in request.pages:
            page = doc[page_edit.page]
            
            # Render at high DPI for quality
            pix = page.get_pixmap(dpi=300)
            img_array = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
            
            # Convert to BGR for OpenCV
            if pix.n == 4:  # RGBA
                img = cv2.cvtColor(img_array, cv2.COLOR_RGBA2BGR)
            else:  # RGB
                img = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
            
            # Apply crop if specified
            if page_edit.crop:
                crop = page_edit.crop
                # Scale coordinates to original resolution
                x = int(crop.x * scale * (300/72))  # Adjust for DPI
                y = int(crop.y * scale * (300/72))
                w = int(crop.w * scale * (300/72))
                h = int(crop.h * scale * (300/72))
                
                # Ensure bounds
                x = max(0, min(x, img.shape[1]))
                y = max(0, min(y, img.shape[0]))
                w = min(w, img.shape[1] - x)
                h = min(h, img.shape[0] - y)
                
                img = img[y:y+h, x:x+w]
            
            # Apply rotation if specified
            if page_edit.rotate:
                if page_edit.rotate == 90:
                    img = cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
                elif page_edit.rotate == 180:
                    img = cv2.rotate(img, cv2.ROTATE_180)
                elif page_edit.rotate == 270:
                    img = cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)
            
            # Apply brightness/contrast if specified
            if page_edit.brightness or page_edit.contrast:
                alpha = page_edit.contrast or 1.0
                beta = int((page_edit.brightness or 1.0 - 1.0) * 100)
                img = cv2.convertScaleAbs(img, alpha=alpha, beta=beta)
            
            processed_images.append(img)
        
        doc.close()
        
        # Generate new PDF
        base_name = os.path.splitext(request.filename)[0]
        output_filename = f"{base_name}_edited.pdf"
        output_path = os.path.join(SCAN_OUT_DIR, output_filename)
        
        # Convert images to PIL and save as PDF
        pil_images = []
        for img in processed_images:
            img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            pil_img = Image.fromarray(img_rgb)
            pil_images.append(pil_img)
        
        if pil_images:
            pil_images[0].save(
                output_path,
                save_all=True,
                append_images=pil_images[1:] if len(pil_images) > 1 else [],
                resolution=300.0,
                quality=95
            )
        
        # Save metadata for bbox info and include created/updated timestamps
        now_ts = int(time.time())
        metadata = {
            "original_file": request.filename,
            "pages": [
                {
                    "page": edit.page,
                    "crop": edit.crop.dict() if edit.crop else None,
                    "rotate": edit.rotate,
                    "brightness": edit.brightness,
                    "contrast": edit.contrast
                }
                for edit in request.pages
            ],
            "preview_width": request.preview_width,
            "timestamp": now_ts,
            # created: preserve if existing metadata exists, otherwise set now
            "created": now_ts,
            "updated": now_ts
        }

        metadata_path = os.path.join(SCAN_OUT_DIR, f"{base_name}_edited.json")
        try:
            if os.path.exists(metadata_path):
                with open(metadata_path, 'r', encoding='utf-8') as f:
                    try:
                        existing = json.load(f)
                        if isinstance(existing, dict) and 'created' in existing:
                            metadata['created'] = int(existing.get('created') or now_ts)
                    except Exception:
                        pass

            tmp_meta = metadata_path + '.tmp'
            with open(tmp_meta, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)
            os.replace(tmp_meta, metadata_path)
        except Exception as e:
            print(f"Failed to write edited metadata for {base_name}: {e}")
        
        return {
            "status": "success",
            "file": output_filename,
            "pages_processed": len(processed_images),
            "metadata_saved": True
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise _safe_500(e, "Failed to apply edits")


@app.get("/api/scan/{filename}/metadata")
async def get_scan_metadata(filename: str):
    """Get metadata for edited scan (bbox info, etc)"""
    # Remove .pdf extension and add .json
    base_name = os.path.splitext(filename)[0]
    metadata_path = _safe_path(SCAN_OUT_DIR, f"{base_name}.json")
    
    if not os.path.exists(metadata_path):
        return {"has_metadata": False}
    
    try:
        with open(metadata_path, 'r') as f:
            metadata = json.load(f)
        return {
            "has_metadata": True,
            **metadata
        }
    except Exception as e:
        raise _safe_500(e, "Failed to load scan metadata")


@app.get("/api/download/{filename}")
async def download_file(filename: str):
    """Download PDF file"""
    filepath = _safe_path(SCAN_OUT_DIR, filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="File not found")
    
    return FileResponse(
        filepath,
        media_type="application/pdf",
        filename=filename
    )


@app.delete("/api/scan/{filename}")
async def delete_scan(filename: str):
    """Delete PDF file"""
    filepath = _safe_path(SCAN_OUT_DIR, filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="File not found")
    
    try:
        os.remove(filepath)
        return {"status": "deleted", "filename": filename}
    except Exception as e:
        raise _safe_500(e, "Failed to delete scan")


@app.delete("/api/projects/{project_id}")
async def delete_project(project_id: str):
    """Delete a project completely: color PDF, mono PDF, JSON metadata, and images subfolder."""
    import shutil
    import re

    # Reject path traversal attempts
    if not re.match(r'^[\w\-]+$', project_id):
        raise HTTPException(status_code=400, detail="Invalid project_id")

    deleted = []
    errors = []

    # Files associated with the project
    candidates = [
        os.path.join(SCAN_OUT_DIR, f"{project_id}.pdf"),
        os.path.join(SCAN_OUT_DIR, f"{project_id}_mono.pdf"),
        os.path.join(SCAN_OUT_DIR, f"{project_id}_color.pdf"),
        os.path.join(SCAN_OUT_DIR, f"{project_id}_edited.pdf"),
        os.path.join(SCAN_OUT_DIR, f"{project_id}.json"),
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                os.remove(path)
                deleted.append(os.path.basename(path))
            except Exception as e:
                errors.append(f"{os.path.basename(path)}: {e}")

    # Project subfolder (images, thumbnails, etc.)
    project_dir = os.path.join(SCAN_OUT_DIR, project_id)
    if os.path.isdir(project_dir):
        try:
            shutil.rmtree(project_dir)
            deleted.append(f"{project_id}/")
        except Exception as e:
            errors.append(f"{project_id}/: {e}")

    if not deleted and not errors:
        raise HTTPException(status_code=404, detail="Project not found")

    if errors:
        raise HTTPException(status_code=500, detail="; ".join(errors))

    return {"status": "deleted", "project_id": project_id, "deleted": deleted}


@app.get("/api/projects/{project_id}/generate")
async def generate_pdf_with_progress(
    project_id: str,
    quality: str = 'medium',
    paper_size: str = 'a4_fit',
    filename: Optional[str] = None
):
    """
    Generate PDF from metadata with Server-Sent Events for real-time progress.
    
    Expects JSON body with:
    - quality: 'low' (150 DPI), 'medium' (200 DPI), 'high' (300 DPI)
    - paper_size: 'a4_fit', 'a4_ratio', 'original'
    - filename: Optional custom filename
    
    Returns SSE stream with progress updates.
    """
    import asyncio
    from agent.transform_service import apply_metadata_transforms
    from agent.pdf_generator import save_pdf_scan_document_fast, save_pdf_scan_document_mono_fast
    from agent.layout_engine import layout_items_by_orientation
    from reportlab.lib.pagesizes import A4
    
    # Query params (EventSource / GET) provide: quality, paper_size, filename
    # Values are passed via the function parameters (defaults above)
    
    async def generate():
        try:
            # Stage 1: Load metadata (0-20%)
            yield f"data: {json.dumps({'progress': 0, 'stage': 'loading', 'message': 'Loading project metadata...'})}\n\n"
            await asyncio.sleep(0.1)
            
            metadata_path = os.path.join(SCAN_OUT_DIR, f"{project_id}.json")
            if not os.path.exists(metadata_path):
                yield f"data: {json.dumps({'error': f'Project {project_id} not found'})}\n\n"
                return
            
            with open(metadata_path, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
            
            images = metadata.get('images', [])
            if not images:
                yield f"data: {json.dumps({'error': 'No images in project'})}\n\n"
                return
            
            yield f"data: {json.dumps({'progress': 10, 'stage': 'loading', 'message': f'Loaded {len(images)} images'})}\n\n"
            await asyncio.sleep(0.1)
            
            # Determine DPI based on quality
            dpi_map = {'low': 150, 'medium': 200, 'high': 300}
            target_dpi = dpi_map.get(quality, 200)
            
            # Stage 2: Apply transformations (20-50%)
            yield f"data: {json.dumps({'progress': 20, 'stage': 'transform', 'message': 'Applying image transformations...'})}\n\n"
            await asyncio.sleep(0.1)
            
            # Parallelize heavy image transforms in a small thread pool (PIL/OpenCV release GIL)
            transformed_items = []
            project_images_dir = os.path.join(SCAN_OUT_DIR, project_id, 'images')
            loop = asyncio.get_event_loop()
            from concurrent.futures import ThreadPoolExecutor
            from agent.layout_engine import determine_document_span

            max_workers = min(DEFAULT_MAX_WORKERS, max(1, len(images)))
            executor = ThreadPoolExecutor(max_workers=max_workers)

            # Prepare asyncio tasks: each task returns (idx, img_meta, fname, transformed_img)
            tasks = []
            def _transform_worker(img_path, img_meta, target_dpi, idx, fname):
                # Runs in ThreadPoolExecutor
                transformed = apply_metadata_transforms(img_path, img_meta, True, target_dpi)
                return (idx, img_meta, fname, transformed)

            for i, img_meta in enumerate(images):
                fname = img_meta.get('filename') or img_meta.get('source_file') or img_meta.get('source_path')
                if not fname:
                    yield f"data: {json.dumps({'warning': f'No filename in metadata for image index {i}'})}\n\n"
                    continue

                img_path = os.path.join(project_images_dir, fname)
                if not os.path.exists(img_path):
                    img_path = os.path.join(SCAN_OUT_DIR, fname)
                if not os.path.exists(img_path):
                    yield f"data: {json.dumps({'warning': f'Image not found: {fname}'})}\n\n"
                    continue

                # schedule transform on the dedicated ThreadPoolExecutor
                raw_task = loop.run_in_executor(
                    executor,
                    _transform_worker,
                    img_path,
                    img_meta,
                    target_dpi,
                    i,
                    fname
                )
                tasks.append(asyncio.ensure_future(raw_task))

            total = len(tasks)
            if total == 0:
                yield f"data: {json.dumps({'error': 'No images could be transformed'})}\n\n"
                executor.shutdown(wait=False)
                return

            completed = 0
            # Use asyncio.as_completed to await asyncio Futures as they finish
            for fut in asyncio.as_completed(tasks):
                try:
                    idx, img_meta, fname, transformed_img = await fut

                    # Determine span using scan_dpi from metadata (fallback to target_dpi)
                    scan_dpi = int(img_meta.get('scan_dpi') or target_dpi)
                    span = determine_document_span(
                        transformed_img.width,
                        transformed_img.height,
                        int(A4[0]),
                        int(A4[1]),
                        10,
                        dpi=scan_dpi
                    )

                    pos = (0, 0)
                    transformed_items.append((span, pos, transformed_img, scan_dpi))

                except Exception as e:
                    # Since the worker returns metadata on success, if we get here we may not have idx/fname
                    try:
                        # Attempt to extract info from exception if present
                        yield f"data: {json.dumps({'warning': f'Failed to transform an image: {str(e)}'})}\n\n"
                    except Exception:
                        yield f"data: {json.dumps({'warning': 'Failed to transform an image'})}\n\n"

                completed += 1
                progress = 20 + int((completed / total) * 30)
                yield f"data: {json.dumps({'progress': progress, 'stage': 'transform', 'message': f'Transformed {completed}/{total} images'})}\n\n"

            executor.shutdown(wait=False)
            
            if not transformed_items:
                yield f"data: {json.dumps({'error': 'No images could be transformed'})}\n\n"
                return
            
            yield f"data: {json.dumps({'progress': 50, 'stage': 'transform', 'message': f'Transformed {len(transformed_items)} images'})}\n\n"
            await asyncio.sleep(0.1)
            
            # Stage 3: Render PDF (50-90%)
            yield f"data: {json.dumps({'progress': 50, 'stage': 'render', 'message': 'Laying out pages...'})}\n\n"
            await asyncio.sleep(0.1)
            
            # Layout documents using the same smart layout as `main.py`
            from agent.layout_engine import layout_documents_smart
            pages = layout_documents_smart(transformed_items, int(A4[0]), int(A4[1]), 10)
            
            yield f"data: {json.dumps({'progress': 60, 'stage': 'render', 'message': f'Rendering {len(pages)} pages...'})}\n\n"
            await asyncio.sleep(0.1)
            
            # Determine output filename
            if filename:
                base_filename = filename
            else:
                base_filename = project_id
            
            # Generate color PDF
            output_color = os.path.join(SCAN_OUT_DIR, f"{base_filename}_color.pdf")
            output_mono = os.path.join(SCAN_OUT_DIR, f"{base_filename}_mono.pdf")
            
            yield f"data: {json.dumps({'progress': 70, 'stage': 'render', 'message': 'Generating color PDF...'})}\n\n"
            await asyncio.sleep(0.1)
            
            # Run PDF generation in thread pool (blocking I/O)
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                save_pdf_scan_document_fast,
                pages,
                output_color,
                A4
            )
            
            yield f"data: {json.dumps({'progress': 80, 'stage': 'render', 'message': 'Generating monochrome PDF...'})}\n\n"
            await asyncio.sleep(0.1)
            
            await loop.run_in_executor(
                None,
                save_pdf_scan_document_mono_fast,
                pages,
                output_mono,
                A4
            )
            
            # Stage 4: Save and complete (90-100%)
            yield f"data: {json.dumps({'progress': 90, 'stage': 'save', 'message': 'Finalizing PDF files...'})}\n\n"
            await asyncio.sleep(0.1)
            
            # Get file sizes and provide download URLs
            color_size = os.path.getsize(output_color) if os.path.exists(output_color) else 0
            mono_size = os.path.getsize(output_mono) if os.path.exists(output_mono) else 0
            files_out = []
            if os.path.exists(output_color):
                files_out.append({'path': output_color, 'size': color_size, 'type': 'color', 'url': f'/api/download/{os.path.basename(output_color)}'})
            if os.path.exists(output_mono):
                files_out.append({'path': output_mono, 'size': mono_size, 'type': 'monochrome', 'url': f'/api/download/{os.path.basename(output_mono)}'})

            yield f"data: {json.dumps({'progress': 100, 'stage': 'complete', 'message': 'PDF generation complete!', 'files': files_out})}\n\n"
        
        except Exception as e:
            yield f"data: {json.dumps({'error': f'PDF generation failed: {str(e)}'})}\n\n"
    
    return StreamingResponse(generate(), media_type="text/event-stream")


@app.post("/api/crop-from-metadata")
async def crop_from_metadata(request: CropFromMetadataRequest):
    """Crop image from metadata and new bbox for debugging"""
    print(f"Crop request: project_id={request.project_id}, image_index={request.image_index}, bbox_count={len(request.bbox)}")
    try:
        # Load project metadata
        metadata_path = os.path.join(SCAN_OUT_DIR, f"{request.project_id}.json")
        if not os.path.exists(metadata_path):
            raise HTTPException(status_code=404, detail="Project metadata not found")

        with open(metadata_path, 'r') as f:
            metadata = json.load(f)

        # Sort images by order
        images = sorted(metadata.get('images', []), key=lambda x: x.get('order', 0))

        if request.image_index >= len(images):
            raise HTTPException(status_code=400, detail="Invalid image index")

        image_meta = images[request.image_index]

        # Resolve image filename from metadata: prefer 'filename' or 'source_file', fall back to legacy 'source_path'
        filename = image_meta.get('filename') or image_meta.get('source_file') or image_meta.get('source_path')
        if not filename:
            raise HTTPException(status_code=404, detail="Source filename not found in metadata")

        # Prefer project-local images folder: scan_out/{project_id}/images/{filename}
        project_images_dir = Path(SCAN_OUT_DIR) / request.project_id / 'images'
        full_source_path = project_images_dir / filename

        # Fallbacks: direct file under scan_out or absolute path stored in metadata
        if not full_source_path.exists():
            alt1 = Path(SCAN_OUT_DIR) / filename
            if alt1.exists():
                full_source_path = alt1
            else:
                alt2 = Path(filename)
                if alt2.exists():
                    full_source_path = alt2
                else:
                    raise HTTPException(status_code=404, detail=f"Source image not found: {filename}")

        # Load source image via OpenCV
        img = cv2.imread(str(full_source_path))
        if img is None:
            raise HTTPException(status_code=404, detail=f"Failed to load image: {full_source_path}")

        debug_info = {
            "source_file": image_meta.get('source_file'),
            "source_path": str(full_source_path),
            "original_size": {"width": img.shape[1], "height": img.shape[0]},
            "applied_adjustments": {
                "rotation": request.rotation or 0,
                "brightness": request.brightness or 1.0,
                "contrast": request.contrast or 1.0,
                "deskew_angle": image_meta.get('deskew_angle', 0)
            },
            "bbox_count": len(request.bbox),
            "bboxes": []
        }

        # Apply adjustments
        # Apply rotation
        if request.rotation:
            rotation = request.rotation
            if rotation == 90:
                img = cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
            elif rotation == 180:
                img = cv2.rotate(img, cv2.ROTATE_180)
            elif rotation == 270:
                img = cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)

        # Apply brightness/contrast
        brightness = request.brightness or 1.0
        contrast = request.contrast or 1.0
        if brightness != 1.0 or contrast != 1.0:
            alpha = contrast
            beta = int((brightness - 1.0) * 100)
            img = cv2.convertScaleAbs(img, alpha=alpha, beta=beta)

        # Apply deskew from metadata
        deskew_angle = image_meta.get('deskew_angle', 0)
        if deskew_angle != 0:
            center = (img.shape[1] // 2, img.shape[0] // 2)
            rotation_matrix = cv2.getRotationMatrix2D(center, deskew_angle, 1.0)
            img = cv2.warpAffine(img, rotation_matrix, (img.shape[1], img.shape[0]))

        # Now apply new bbox crops
        cropped_images = []
        for i, bbox in enumerate(request.bbox):
            x, y, w, h = int(bbox.x), int(bbox.y), int(bbox.w), int(bbox.h)

            # Ensure bounds
            x = max(0, min(x, img.shape[1]))
            y = max(0, min(y, img.shape[0]))
            w = min(w, img.shape[1] - x)
            h = min(h, img.shape[0] - y)

            cropped = img[y:y+h, x:x+w]
            cropped_images.append(cropped)

            debug_info["bboxes"].append({
                "index": i,
                "original_bbox": {"x": bbox.x, "y": bbox.y, "w": bbox.w, "h": bbox.h},
                "adjusted_bbox": {"x": x, "y": y, "w": w, "h": h},
                "cropped_size": {"width": cropped.shape[1], "height": cropped.shape[0]}
            })

        
        # If multiple crops, combine them or return first one
        if cropped_images:
            final_img = cropped_images[0]  # For now, return first crop
            debug_info["final_crop_size"] = {"width": final_img.shape[1], "height": final_img.shape[0]}

            # Convert to base64 for preview
            img_rgb = cv2.cvtColor(final_img, cv2.COLOR_BGR2RGB)
            pil_img = Image.fromarray(img_rgb)
            buffer = io.BytesIO()
            pil_img.save(buffer, format='PNG')
            img_base64 = base64.b64encode(buffer.getvalue()).decode()

            return {
                "cropped_url": f"data:image/png;base64,{img_base64}",
                "width": final_img.shape[1],
                "height": final_img.shape[0],
                "debug_info": debug_info
            }
        else:
            return {
                "cropped_url": None,
                "width": 0,
                "height": 0,
                "debug_info": debug_info
            }

    except Exception as e:
        print(f"Crop error: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Crop failed: {str(e)}")


# Serve static files (Vue app)
# Mount after API routes to avoid conflicts
web_ui_dist = Path(__file__).parent.parent / "web_ui" / "dist"
if web_ui_dist.exists():
    app.mount("/", StaticFiles(directory=str(web_ui_dist), html=True), name="static")
else:
    print(f"⚠️  Web UI dist not found at {web_ui_dist}")
    print("💡 Run: cd web_ui && npm run build")


if __name__ == "__main__":
    import uvicorn
    print(f"🚀 Starting Web UI Server...")
    print(f"📁 Scan directory: {SCAN_OUT_DIR}")
    print(f"🌐 Server: http://localhost:{WEB_UI_PORT}")
    print(f"📊 API docs: http://localhost:{WEB_UI_PORT}/docs")
    uvicorn.run(app, host="0.0.0.0", port=WEB_UI_PORT)
