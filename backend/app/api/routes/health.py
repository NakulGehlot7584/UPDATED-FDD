"""
Health check route.
"""

from __future__ import annotations

from fastapi import APIRouter
from app.api.schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    """
    Return basic service health without inspecting files.
    """
    return HealthResponse(status="ok")
