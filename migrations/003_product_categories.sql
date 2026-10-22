-- =============================================================================
-- 003 — Product categories managed from the dashboard
-- =============================================================================
-- products.category stays a TEXT column holding the category name, so existing
-- rows, the AI prompt builder and the public API keep working unchanged.
-- This table is the admin-managed list of allowed categories and controls
-- which ones appear as filters on the public storefront.
-- =============================================================================

CREATE TABLE IF NOT EXISTS product_categories (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    store_id        UUID NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
    name_ar         TEXT NOT NULL CHECK (length(btrim(name_ar)) > 0),
    sort_order      INTEGER NOT NULL DEFAULT 0,
    show_in_filter  BOOLEAN NOT NULL DEFAULT true,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_product_categories_store_name UNIQUE (store_id, name_ar)
);

ALTER TABLE product_categories ENABLE ROW LEVEL SECURITY;

CREATE INDEX IF NOT EXISTS idx_product_categories_store_id ON product_categories(store_id);
CREATE INDEX IF NOT EXISTS idx_products_store_category ON products(store_id, category);

DROP TRIGGER IF EXISTS trg_product_categories_updated_at ON product_categories;
CREATE TRIGGER trg_product_categories_updated_at
    BEFORE UPDATE ON product_categories
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Restricted to authenticated store members (service role bypasses RLS)
DROP POLICY IF EXISTS product_categories_member_access ON product_categories;
CREATE POLICY product_categories_member_access ON product_categories
    FOR ALL TO authenticated
    USING (public.is_store_member(store_id))
    WITH CHECK (public.is_store_member(store_id));

-- Seed the default categories for every store
INSERT INTO product_categories (store_id, name_ar, sort_order)
SELECT s.id, d.name_ar, d.sort_order
FROM stores s
CROSS JOIN (VALUES ('رجالي', 1), ('نسائي', 2), ('للجنسين', 3), ('شرقي', 4)) AS d(name_ar, sort_order)
ON CONFLICT (store_id, name_ar) DO NOTHING;

-- Keep any category already used by existing products
INSERT INTO product_categories (store_id, name_ar, sort_order)
SELECT DISTINCT p.store_id, btrim(p.category), 100
FROM products p
WHERE p.category IS NOT NULL AND btrim(p.category) <> ''
ON CONFLICT (store_id, name_ar) DO NOTHING;
