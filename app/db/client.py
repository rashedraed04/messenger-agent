"""
Supabase client access module.

Re-exports client factories from the db package for convenient imports:
    from app.db.client import get_supabase_client
"""

from app.db import get_supabase_anon_client, get_supabase_client

__all__ = ["get_supabase_client", "get_supabase_anon_client"]
