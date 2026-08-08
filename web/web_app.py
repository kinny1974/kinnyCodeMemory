#!/usr/bin/env python3
"""
KinnyCode Memory System - Web UI Application
=============================================
Web interface for managing projects, searching documents,
and configuring the server.

Usage:
    python web_app.py [--port PORT] [--host HOST]
"""

import os
import sys
import json
import shutil
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import httpx
import uvicorn

# ═══════════════════════════════════════════════════════════════════════
#  Configuration
# ═══════════════════════════════════════════════════════════════════════

MEMORY_SERVER_URL = os.getenv("KINNYCODE_SERVER_URL", "http://127.0.0.1:8007")
UPLOAD_DIR = Path(__file__).parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

# ═══════════════════════════════════════════════════════════════════════
#  FastAPI App
# ═══════════════════════════════════════════════════════════════════════

app = FastAPI(title="KinnyCode Web UI", version="1.0.0")

# Static files and templates
static_dir = Path(__file__).parent / "static"
templates_dir = Path(__file__).parent / "templates"

app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
templates = Jinja2Templates(directory=str(templates_dir))


# ═══════════════════════════════════════════════════════════════════════
#  Helper Functions
# ═══════════════════════════════════════════════════════════════════════


async def proxy_request(
    method: str,
    endpoint: str,
    data: Optional[dict] = None,
    files: Optional[dict] = None
) -> dict:
    """Proxy request to memory server."""
    url = f"{MEMORY_SERVER_URL}{endpoint}"

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            if method == "GET":
                resp = await client.get(url, params=data)
            elif method == "POST":
                if files:
                    resp = await client.post(url, files=files, data=data)
                else:
                    resp = await client.post(url, json=data)
            elif method == "DELETE":
                resp = await client.delete(url, params=data)
            else:
                raise ValueError(f"Unsupported method: {method}")

            resp.raise_for_status()
            return resp.json()

    except httpx.ConnectError:
        raise HTTPException(
            status_code=503,
            detail="No se pudo conectar al servidor de memoria. "
                   "Asegúrate de que esté ejecutándose en "
                   f"{MEMORY_SERVER_URL}"
        )
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=e.response.status_code,
            detail=str(e)
        )


# ═══════════════════════════════════════════════════════════════════════
#  Routes - Pages
# ═══════════════════════════════════════════════════════════════════════


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Home page - Dashboard."""
    return templates.TemplateResponse("dashboard.html", {"request": request})


@app.get("/projects", response_class=HTMLResponse)
async def projects_page(request: Request):
    """Projects management page."""
    return templates.TemplateResponse("projects.html", {"request": request})


@app.get("/search", response_class=HTMLResponse)
async def search_page(request: Request):
    """Search page."""
    return templates.TemplateResponse("search.html", {"request": request})


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    """Settings page."""
    return templates.TemplateResponse("settings.html", {"request": request})


# ═══════════════════════════════════════════════════════════════════════
#  Routes - API
# ═══════════════════════════════════════════════════════════════════════


@app.get("/api/health")
async def api_health():
    """Check memory server health."""
    return await proxy_request("GET", "/health")


@app.get("/api/metrics")
async def api_metrics():
    """Get server metrics."""
    return await proxy_request("GET", "/metrics")


@app.get("/api/projects")
async def api_projects():
    """List all projects."""
    return await proxy_request("GET", "/list-projects")


@app.get("/api/projects/{project_id}/info")
async def api_project_info(project_id: str):
    """Get project info."""
    return await proxy_request(
        "POST", "/project-info", {"project_id": project_id}
    )


@app.get("/api/projects/{project_id}/documents")
async def api_project_documents(project_id: str):
    """List documents in project."""
    return await proxy_request(
        "GET", "/list-documents", {"project_id": project_id}
    )


@app.post("/api/search")
async def api_search(
    query: str = Form(...),
    project_id: str = Form(...),
    top_k: int = Form(5)
):
    """Search documents."""
    return await proxy_request(
        "POST", "/search-documents",
        {"query": query, "project_id": project_id, "top_k": top_k}
    )


@app.post("/api/rag")
async def api_rag(
    prompt: str = Form(...),
    project_id: str = Form(...),
    top_k: int = Form(5)
):
    """Get RAG context."""
    return await proxy_request(
        "POST", "/retrieve-context",
        {"prompt": prompt, "project_id": project_id, "top_k": top_k}
    )


@app.post("/api/upload")
async def api_upload(
    file: UploadFile = File(...),
    project_id: str = Form(...)
):
    """Upload and index a document."""
    # Save file temporarily
    upload_path = UPLOAD_DIR / file.filename
    with open(upload_path, "wb") as f:
        content = await file.read()
        f.write(content)

    try:
        # Index the file
        result = await proxy_request(
            "POST", "/index-document",
            {"file_path": str(upload_path), "project_id": project_id}
        )
        return result
    finally:
        # Clean up
        upload_path.unlink(missing_ok=True)


@app.delete("/api/projects/{project_id}")
async def api_delete_project(project_id: str):
    """Delete a project."""
    return await proxy_request(
        "POST", "/clear-project", {"project_id": project_id}
    )


# ═══════════════════════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════════════════════


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="KinnyCode Web UI")
    parser.add_argument("--port", type=int, default=19090)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--server", default=MEMORY_SERVER_URL,
                        help="Memory server URL")
    args = parser.parse_args()

    MEMORY_SERVER_URL = args.server

    print(f"\n  KinnyCode Web UI")
    print(f"  http://{args.host}:{args.port}")
    print(f"  Server: {MEMORY_SERVER_URL}\n")

    uvicorn.run(app, host=args.host, port=args.port)
