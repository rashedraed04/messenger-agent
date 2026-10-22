-- =============================================================================
-- 004 — Admin-managed product types (متجر التقوى: Hajj & Umrah goods and gifts)
-- =============================================================================
-- A product type decides which fields the product form asks for (size label
-- and unit, what the detail tags are called) and which illustration the
-- storefront draws when the product has no photo.
-- products.product_type stays a TEXT column holding the type name, the same
-- way products.category works, so existing queries keep working unchanged.
-- =============================================================================

CREATE TABLE IF NOT EXISTS product_types (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    store_id        UUID NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
    name_ar         TEXT NOT NULL CHECK (length(btrim(name_ar)) > 0),
    visual          TEXT NOT NULL DEFAULT 'gift',
    size_label      TEXT,           -- NULL = this type has no size field
    size_unit       TEXT,           -- e.g. 'مل', 'سم'; NULL = free text size
    details_label   TEXT NOT NULL DEFAULT 'المميزات',
    show_in_filter  BOOLEAN NOT NULL DEFAULT true,
    sort_order      INTEGER NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_product_types_store_name UNIQUE (store_id, name_ar)
);

ALTER TABLE product_types ENABLE ROW LEVEL SECURITY;

CREATE INDEX IF NOT EXISTS idx_product_types_store_id ON product_types(store_id);

ALTER TABLE products ADD COLUMN IF NOT EXISTS product_type TEXT;
CREATE INDEX IF NOT EXISTS idx_products_store_type ON products(store_id, product_type);

DROP TRIGGER IF EXISTS trg_product_types_updated_at ON product_types;
CREATE TRIGGER trg_product_types_updated_at
    BEFORE UPDATE ON product_types
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Restricted to authenticated store members (service role bypasses RLS)
DROP POLICY IF EXISTS product_types_member_access ON product_types;
CREATE POLICY product_types_member_access ON product_types
    FOR ALL TO authenticated
    USING (public.is_store_member(store_id))
    WITH CHECK (public.is_store_member(store_id));

-- Starter types for every store (all editable / removable from the dashboard)
INSERT INTO product_types (store_id, name_ar, visual, size_label, size_unit, details_label, sort_order)
SELECT s.id, d.name_ar, d.visual, d.size_label, d.size_unit, d.details_label, d.sort_order
FROM stores s
CROSS JOIN (VALUES
    ('عطور ومسك',            'bottle',  'الحجم',           'مل',   'النوتات العطرية', 1),
    ('سجاد صلاة',            'rug',     'المقاس',          'سم',   'المميزات',        2),
    ('مسابح',                'beads',   'عدد الحبات',      'حبة',  'المميزات',        3),
    ('مصاحف وكتب',           'book',    'الحجم',           'سم',   'المميزات',        4),
    ('ملابس إحرام وعبايات',  'garment', 'المقاس',          NULL,   'المميزات',        5),
    ('تمور وماء زمزم',       'dates',   'الوزن / الحجم',   NULL,   'المميزات',        6),
    ('هدايا ومجموعات',       'gift',    NULL,              NULL,   'المحتويات',       7)
) AS d(name_ar, visual, size_label, size_unit, details_label, sort_order)
ON CONFLICT (store_id, name_ar) DO NOTHING;

-- Existing catalog rows are perfumes (sized in ml)
UPDATE products
SET product_type = 'عطور ومسك'
WHERE product_type IS NULL AND size_ml IS NOT NULL AND btrim(size_ml) <> '';

-- Store identity: متجر التقوى
UPDATE stores SET name = 'متجر التقوى' WHERE name = 'متجر العطور الأردني';

UPDATE store_settings
SET setting_value = 'متجر التقوى متخصص ببضائع وهدايا الحج والعمرة في الأردن: عطور ومسك، سجاد صلاة، مسابح، مصاحف، ملابس إحرام، تمور وماء زمزم، وهدايا مجهزة للحجاج والمعتمرين، مع توصيل لجميع المحافظات والدفع عند الاستلام.'
WHERE setting_key = 'store_description'
  AND setting_value LIKE '%العطور%';
