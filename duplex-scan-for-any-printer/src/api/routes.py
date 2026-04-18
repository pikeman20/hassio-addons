"""
FastAPI routes for image editor web interface

Endpoints:
- GET /api/projects - List all scan sessions
- GET /api/projects/{project_id}/metadata - Get metadata for editing
- PUT /api/projects/{project_id}/metadata - Save edited metadata
- POST /api/projects/{project_id}/generate - Generate PDF with SSE progress
"""

from fastapi import APIRouter, HTTPException, Path, Body
from fastapi.responses import JSONResponse
from typing import Dict, List, Any, Optional
import os
import json
import glob
from pathlib import Path as PathLib
from datetime import datetime

router = APIRouter(prefix="/api")

# Configuration
SCAN_OUT_DIR = "scan_out"
SCAN_INBOX_DIR = "scan_inbox"


@router.get("/projects")
async def list_projects():
    """
    List all scan projects (sessions) with metadata.
    
    Returns list of projects with:
    - id: project identifier (metadata filename without .json)
    - name: human-readable name
    - image_count: number of images
    - created_at: timestamp
    - thumbnail: path to first image (for preview)
    """
    try:
        projects = []
        
        # Find all metadata JSON files in scan_out
        metadata_files = glob.glob(os.path.join(SCAN_OUT_DIR, "*.json"))
        
        for metadata_path in metadata_files:
            try:
                # Read metadata
                with open(metadata_path, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
                
                # Extract project info
                project_id = os.path.splitext(os.path.basename(metadata_path))[0]
                
                # Get file stats
                stat = os.stat(metadata_path)
                created_at = datetime.fromtimestamp(stat.st_ctime).isoformat()
                
                # Get thumbnail (first image)
                thumbnail = None
                if metadata.get('images') and len(metadata['images']) > 0:
                    first_image = metadata['images'][0]
                    thumbnail = first_image.get('path', '')
                
                projects.append({
                    'id': project_id,
                    'name': project_id.replace('_', ' ').title(),
                    'image_count': len(metadata.get('images', [])),
                    'created_at': created_at,
                    'thumbnail': thumbnail,
                    'mode': metadata.get('mode', 'unknown')
                })
            
            except Exception as e:
                print(f"Error reading project {metadata_path}: {e}")
                continue
        
        # Sort by creation time (newest first)
        projects.sort(key=lambda x: x['created_at'], reverse=True)
        
        return JSONResponse(content={
            'projects': projects,
            'total': len(projects)
        })
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list projects: {str(e)}")


@router.get("/projects/{project_id}/metadata")
async def get_project_metadata(
    project_id: str = Path(..., description="Project ID (metadata filename without .json)")
):
    """
    Get metadata for a specific project.
    
    Returns:
    - session_id: project identifier
    - mode: scan mode (scan_document, scan_duplex, etc.)
    - images: list of image metadata with transformations
    - pdf_paths: generated PDF paths (if any)
    """
    try:
        # Build path to metadata file
        metadata_path = os.path.join(SCAN_OUT_DIR, f"{project_id}.json")
        
        if not os.path.exists(metadata_path):
            raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")
        
        # Read metadata
        with open(metadata_path, 'r', encoding='utf-8') as f:
            metadata = json.load(f)
        
        # Add default values for brightness/contrast if not present
        for image in metadata.get('images', []):
            if 'brightness' not in image:
                image['brightness'] = 0
            if 'contrast' not in image:
                image['contrast'] = 0
        
        return JSONResponse(content=metadata)
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load metadata: {str(e)}")


@router.put("/projects/{project_id}/metadata")
async def update_project_metadata(
    project_id: str = Path(..., description="Project ID"),
    metadata: Dict[str, Any] = Body(..., description="Updated metadata")
):
    """
    Save edited metadata (rotation, brightness, contrast, bbox adjustments).
    
    Request body should contain complete metadata object with:
    - images: array of image objects with updated transformations
    - session_id: project identifier
    - mode: scan mode
    """
    try:
        # Build path to metadata file
        metadata_path = os.path.join(SCAN_OUT_DIR, f"{project_id}.json")
        
        if not os.path.exists(metadata_path):
            raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")
        
        # Validate metadata structure
        if 'images' not in metadata:
            raise HTTPException(status_code=400, detail="Metadata must contain 'images' array")
        
        # Backup original metadata
        backup_path = metadata_path + '.backup'
        if os.path.exists(metadata_path):
            import shutil
            shutil.copy2(metadata_path, backup_path)

        # Preserve created timestamp if present, and set updated
        now_ts = int(datetime.utcnow().timestamp())
        try:
            if os.path.exists(metadata_path):
                with open(metadata_path, 'r', encoding='utf-8') as f:
                    try:
                        existing = json.load(f)
                        if isinstance(existing, dict) and 'created' in existing:
                            metadata['created'] = int(existing.get('created') or now_ts)
                    except Exception:
                        pass

            metadata['updated'] = now_ts

            # Atomic write
            tmp_path = metadata_path + '.tmp'
            with open(tmp_path, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, metadata_path)

            return JSONResponse(content={
                'success': True,
                'message': 'Metadata saved successfully',
                'project_id': project_id,
                'backup_path': backup_path,
                'updated': now_ts
            })
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to save metadata: {str(e)}")
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save metadata: {str(e)}")


@router.get("/projects/{project_id}/images/{image_id}")
async def get_image_file(
    project_id: str = Path(..., description="Project ID"),
    image_id: str = Path(..., description="Image ID")
):
    """
    Get image file for display in editor.
    
    This endpoint serves the actual image files referenced in metadata.
    """
    try:
        # Get metadata to find image path
        metadata_path = os.path.join(SCAN_OUT_DIR, f"{project_id}.json")
        
        if not os.path.exists(metadata_path):
            raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")
        
        with open(metadata_path, 'r', encoding='utf-8') as f:
            metadata = json.load(f)
        
        # Find image by ID
        image = next((img for img in metadata.get('images', []) if img.get('id') == image_id), None)
        
        if not image:
            raise HTTPException(status_code=404, detail=f"Image '{image_id}' not found")
        
        # Get image path
        image_path = image.get('path')
        if not image_path or not os.path.exists(image_path):
            raise HTTPException(status_code=404, detail=f"Image file not found: {image_path}")
        
        # Return file
        from fastapi.responses import FileResponse
        return FileResponse(image_path)
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to serve image: {str(e)}")


@router.delete("/projects/{project_id}")
async def delete_project(
    project_id: str = Path(..., description="Project ID to delete")
):
    """
    Delete a project and its metadata.
    
    Note: This does NOT delete the original scanned images, only the metadata.
    """
    try:
        metadata_path = os.path.join(SCAN_OUT_DIR, f"{project_id}.json")
        
        if not os.path.exists(metadata_path):
            raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")
        
        # Delete metadata file
        os.remove(metadata_path)
        
        # Delete backup if exists
        backup_path = metadata_path + '.backup'
        if os.path.exists(backup_path):
            os.remove(backup_path)
        
        # Delete generated PDFs if exist
        pdf_color = os.path.join(SCAN_OUT_DIR, f"{project_id}_color.pdf")
        pdf_mono = os.path.join(SCAN_OUT_DIR, f"{project_id}_mono.pdf")
        
        if os.path.exists(pdf_color):
            os.remove(pdf_color)
        if os.path.exists(pdf_mono):
            os.remove(pdf_mono)
        
        return JSONResponse(content={
            'success': True,
            'message': f"Project '{project_id}' deleted successfully"
        })
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete project: {str(e)}")


@router.get("/projects/{project_id}/generate")
async def generate_pdf(
    project_id: str = Path(..., description="Project ID"),
    quality: str = 'medium',
    paper_size: str = 'a4_fit',
    filename: Optional[str] = None
):
    """
    Generate PDF with Server-Sent Events for progress tracking.
    
    Progress stages:
    - 0-20%: Loading metadata and images
    - 20-50%: Applying transformations
    - 50-90%: Rendering PDF pages
    - 90-100%: Saving and compressing PDF
    
    Request body:
    - quality: 'low' (150 DPI), 'medium' (200 DPI), 'high' (300 DPI)
    - paper_size: 'a4_fit' (fit to A4), 'a4_ratio' (maintain aspect ratio), 'original' (keep original size)
    - filename: Optional custom filename
    
    Response: text/event-stream with JSON events
    """
    from fastapi.responses import StreamingResponse
    import asyncio
    from ..agent.transform_service import apply_metadata_transforms
    from ..agent.pdf_generator import save_pdf_scan_document_fast, save_pdf_scan_document_mono_fast
    from ..agent.layout_engine import layout_documents_smart
    from reportlab.lib.pagesizes import A4
    
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
            
            transformed_items = []
            for i, img_meta in enumerate(images):
                # Progress: 20% + (i / total * 30%)
                progress = 20 + int((i / len(images)) * 30)
                yield f"data: {json.dumps({'progress': progress, 'stage': 'transform', 'message': f'Transforming image {i+1}/{len(images)}...'})}\n\n"
                await asyncio.sleep(0.05)
                
                try:
                    # Apply all transformations
                    img_path = img_meta.get('path')
                    if not img_path or not os.path.exists(img_path):
                        continue
                    
                    transformed_img = apply_metadata_transforms(
                        img_path,
                        img_meta,
                        apply_bbox_crop=True,
                        target_dpi=target_dpi
                    )
                    
                    # Build doc_item: (span, pos, img, dpi, rotation, deskew, filename)
                    # For PDF generation, we use simplified structure
                    span = 'single'  # Assume single-page items
                    pos = (0, 0)  # Position will be determined by layout engine
                    
                    transformed_items.append((span, pos, transformed_img, target_dpi))
                
                except Exception as e:
                    yield f"data: {json.dumps({'warning': f'Failed to transform image {i+1}: {str(e)}'})}\n\n"
                    continue
            
            if not transformed_items:
                yield f"data: {json.dumps({'error': 'No images could be transformed'})}\n\n"
                return
            
            yield f"data: {json.dumps({'progress': 50, 'stage': 'transform', 'message': f'Transformed {len(transformed_items)} images'})}\n\n"
            await asyncio.sleep(0.1)
            
            # Stage 3: Render PDF (50-90%)
            yield f"data: {json.dumps({'progress': 50, 'stage': 'render', 'message': 'Laying out pages...'})}\n\n"
            await asyncio.sleep(0.1)
            
            # Layout documents using the same smart layout as the main agent
            # transformed_items is a list of tuples: (span, pos, img, dpi)
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
            
            # Get file sizes
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
