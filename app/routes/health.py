"""
Health check endpoint.

Performs a lightweight Supabase DB query to:
1. Confirm the application is running.
2. Keep the Supabase free-tier database active (prevents 7-day inactivity pause).

This endpoint is called by:
- Cloud Run readiness/liveness probes
- The Cloud Scheduler daily report job (which also keeps the DB alive)
- External uptime monitors
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from supabase import Client

from app.dependencies import get_db

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check(db: Client = Depends(get_db)) -> dict:
    """
    Return application health status.

    Executes a trivial DB query (SELECT 1 from stores LIMIT 1) to keep
    the Supabase free-tier database awake and confirm connectivity.
    """
    db_status = "unknown"
    try:
        # Lightweight query — just need any round-trip to prevent auto-pause
        db.table("stores").select("id").limit(1).execute()
        db_status = "connected"
    except Exception as exc:
        db_status = f"error: {type(exc).__name__}"

    return {
        "status": "healthy" if db_status == "connected" else "degraded",
        "database": db_status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
