-- =============================================================================
-- 005: Drop per-governorate delivery zones
-- =============================================================================
-- Delivery is handled by an external delivery company at one flat fee, stored
-- in store_settings under the key 'delivery_fee_jod' and edited from the
-- dashboard settings page. Orders keep their governorate and delivery_fee_jod
-- columns, so no order data is lost.
-- =============================================================================

ALTER TABLE orders DROP CONSTRAINT IF EXISTS orders_delivery_zone_id_fkey;
ALTER TABLE orders DROP COLUMN IF EXISTS delivery_zone_id;

DROP TABLE IF EXISTS delivery_zones;
