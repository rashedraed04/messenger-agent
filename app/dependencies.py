"""
FastAPI dependency injection providers.

Centralises all injectable dependencies so routes stay thin.
"""

from supabase import Client

from app.config import Settings, get_settings
from app.db.client import get_supabase_client


def get_db() -> Client:
    """Provide the Supabase service-role client as a FastAPI dependency."""
    return get_supabase_client()


def get_config() -> Settings:
    """Provide the application settings as a FastAPI dependency."""
    return get_settings()
