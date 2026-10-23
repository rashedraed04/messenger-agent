"""
Health check endpoint.

Performs a lightweight Supabase DB query to:
1. Confirm the application is running.
2. Keep the Supabase free-tier database active (prevents 7-day inactivity pause).

This endpoint is called by:
- Render's health check (healthCheckPath in render.yaml)
- The cron-job.org keep-awake job every 14 minutes (also stops Render's free
  instance from spinning down)
- External uptime monitors (GET or HEAD)
"""

import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from supabase import Client

from app.dependencies import get_db

router = APIRouter(tags=["health"])

# Answer quickly even if Supabase hangs; the client's own timeout is minutes long
DB_PING_TIMEOUT_SECONDS = 5


def _ping_db(db: Client) -> None:
    db.table("stores").select("id").limit(1).execute()


@router.get("/health")
@router.head("/health", include_in_schema=False)
async def health_check(db: Client = Depends(get_db)) -> dict:
    """
    Return application health status.

    Always answers 200 so a database hiccup never makes Render restart the
    web service; the `database` field reports whether the ping got through.
    """
    try:
        # Lightweight query — just need any round-trip to prevent auto-pause
        await asyncio.wait_for(asyncio.to_thread(_ping_db, db), DB_PING_TIMEOUT_SECONDS)
        db_status = "connected"
    except asyncio.TimeoutError:
        db_status = "error: timeout"
    except Exception as exc:
        db_status = f"error: {type(exc).__name__}"

    return {
        "status": "healthy" if db_status == "connected" else "degraded",
        "database": db_status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
