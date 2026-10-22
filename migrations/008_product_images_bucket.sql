-- =============================================================================
-- 008: Storage bucket for product photos uploaded from the dashboard
-- =============================================================================
-- Public so the storefront and Messenger can show the photos by URL. Only the
-- server (service role) uploads or deletes, so no storage policies are needed.
-- =============================================================================

INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES ('product-images', 'product-images', true, 5242880,
        ARRAY['image/jpeg', 'image/png', 'image/webp'])
ON CONFLICT (id) DO UPDATE SET
    public = EXCLUDED.public,
    file_size_limit = EXCLUDED.file_size_limit,
    allowed_mime_types = EXCLUDED.allowed_mime_types;
