"""
FastAPI application entry point for the FDD pipeline.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes import datasets, fdd, graphs, health, historian

app = FastAPI(
    title="Open-FDD Pipeline API",
    description="CSV Ingestion, Validation, Semantic Role Mapping, and Dataset Management API.",
    version="0.1.0",
)

# Enable CORS (configurable via CORS_ORIGINS environment variable)
cors_env = os.getenv("CORS_ORIGINS")
if cors_env:
    allow_origins = [origin.strip() for origin in cors_env.split(",") if origin.strip()]
else:
    allow_origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount API routes
app.include_router(health.router, prefix="/api")
app.include_router(datasets.router, prefix="/api")
app.include_router(historian.router, prefix="/api")
app.include_router(fdd.router, prefix="/api")
app.include_router(graphs.router, prefix="/api")

# Mount production frontend build if available
frontend_dist = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")
