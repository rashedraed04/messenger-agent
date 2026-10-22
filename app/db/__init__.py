"""
Supabase client singleton.

Creates a single Supabase client using the service_role key for server-side
operations. The service_role key bypasses RLS — it must NEVER be exposed to
the client/browser.
"""

from functools import lru_cache

from supabase import Client, ClientOptions, create_client

from app.config import get_settings


@lru_cache
def get_supabase_client() -> Client:
    """
    Return a cached Supabase client using the service_role key.

    This client has full database access (bypasses RLS) and is used
    exclusively on the server side for dashboard admin operations and
    webhook processing.
    """
    settings = get_settings()
    client: Client = create_client(
        settings.supabase_url,
        settings.supabase_service_role_key,
    )
    return client


def get_supabase_anon_client() -> Client:
    """
    Return a Supabase client using the anon key.

    Used for Supabase Auth flows (login, password/email changes) where RLS
    and auth policies should apply. A fresh client per call keeps one admin's
    session from leaking into another request; auto-refresh is off so no
    background refresh timer outlives the request.
    """
    settings = get_settings()
    client: Client = create_client(
        settings.supabase_url,
        settings.supabase_anon_key,
        options=ClientOptions(auto_refresh_token=False, persist_session=False),
    )
    return client
