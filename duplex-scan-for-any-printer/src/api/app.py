"""
FastAPI Application Setup

Initializes the web API server for image editor interface.
Provides CORS, static file serving, and API route registration.

Usage:
    uvicorn src.api.app:app --reload --host 0.0.0.0 --port 8000
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os

from .routes import router

# Create FastAPI application
app = FastAPI(
    title="Document Scanner API",
    description="Backend API for web-based document image editor",
    version="1.0.0"
)

# Configure CORS - allow frontend to access API
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",  # Vite dev server
        "http://localhost:3000",  # Alternative frontend port
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],  # Allow all HTTP methods
    allow_headers=["*"],  # Allow all headers
)

# Register API routes
app.include_router(router)

# Serve static files (images from scan_out and scan_inbox)
if os.path.exists("scan_out"):
    app.mount("/static/scan_out", StaticFiles(directory="scan_out"), name="scan_out")

if os.path.exists("scan_inbox"):
    app.mount("/static/scan_inbox", StaticFiles(directory="scan_inbox"), name="scan_inbox")

# Serve frontend build (if exists)
if os.path.exists("frontend/dist"):
    app.mount("/assets", StaticFiles(directory="frontend/dist/assets"), name="assets")
    
    @app.get("/")
    async def serve_frontend():
        """Serve frontend index.html"""
        return FileResponse("frontend/dist/index.html")
    
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """Serve SPA routes - fallback to index.html"""
        file_path = f"frontend/dist/{full_path}"
        if os.path.exists(file_path) and os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse("frontend/dist/index.html")


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "Document Scanner API",
        "version": "1.0.0"
    }


# Run with: uvicorn src.api.app:app --reload --host 0.0.0.0 --port 8000
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "src.api.app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
