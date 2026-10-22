-- =============================================================================
-- 006: Security hardening (Supabase database linter fixes)
-- =============================================================================
-- 1. update_updated_at_column gets a fixed search_path (lint 0011).
-- 2. is_store_member is only needed by RLS policies for signed-in users, so
--    anonymous visitors may no longer call it via /rest/v1/rpc (lint 0028).
-- 3. rls_auto_enable is an event trigger function and is never called through
--    the API (lints 0028/0029).
-- =============================================================================

ALTER FUNCTION public.update_updated_at_column() SET search_path = public;

REVOKE EXECUTE ON FUNCTION public.is_store_member(uuid) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.is_store_member(uuid) TO authenticated, service_role;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = 'public' AND p.proname = 'rls_auto_enable'
    ) THEN
        REVOKE EXECUTE ON FUNCTION public.rls_auto_enable() FROM PUBLIC, anon, authenticated;
    END IF;
END $$;
