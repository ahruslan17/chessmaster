"""Health check endpoint for container orchestration."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    """Simple health check for Docker/load balancers. Returns 200 when API is ready."""
    return {"status": "ok"}
