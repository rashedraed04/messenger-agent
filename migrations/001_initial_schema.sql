-- =============================================================================
-- Migration 001: Initial Schema & Row Level Security
-- Messenger Agent — Jordanian Perfume Store
-- =============================================================================
-- This migration creates all 13 core tables, constraints, indexes, triggers,
-- and Row Level Security (RLS) policies for the multi-store perfume sales agent.
--
-- Security Philosophy:
-- 1. All tables enforce store_id multi-tenant isolation.
-- 2. Privileged access (Supabase service_role) is restricted server-side only.
-- 3. Public storefront queries execute via FastAPI server-side repository
--    (ProductRepository.get_public_showcase) to guarantee zero price leakage.
-- 4. No direct 'anon' role SELECT policies exist on products or delivery_zones.
-- 5. Authenticated dashboard access is strictly authorized via store_members table.
--
-- Currency: JOD (Jordanian Dinar) — 3 decimal places (fils).
-- NUMERIC(10,3) is used throughout.
-- =============================================================================

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";


-- ---------------------------------------------------------------------------
-- 1. STORES — Multi-store root table
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS stores (
    id                               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                             TEXT NOT NULL,
    facebook_page_id                 TEXT UNIQUE,
    meta_page_access_token_encrypted TEXT,
    meta_app_secret_encrypted        TEXT,
    gemini_api_key_encrypted         TEXT,
    telegram_bot_token_encrypted     TEXT,
    telegram_chat_id                 TEXT,
    is_active                        BOOLEAN NOT NULL DEFAULT true,
    created_at                       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                       TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE stores ENABLE ROW LEVEL SECURITY;


-- ---------------------------------------------------------------------------
-- 2. STORE_MEMBERS — Authenticated user-to-store authorization mapping
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS store_members (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    store_id   UUID NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
    user_id    UUID NOT NULL, -- references auth.users(id) in Supabase
    role       TEXT NOT NULL DEFAULT 'manager' CHECK (role IN ('owner', 'manager', 'staff')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (store_id, user_id)
);

ALTER TABLE store_members ENABLE ROW LEVEL SECURITY;

CREATE INDEX idx_store_members_user_store ON store_members(user_id, store_id);
CREATE INDEX idx_store_members_store_id ON store_members(store_id);


-- ---------------------------------------------------------------------------
-- 3. PRODUCTS — Perfume catalog per store
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS products (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    store_id        UUID NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
    name_ar         TEXT NOT NULL,
    name_en         TEXT,
    description_ar  TEXT,
    brand           TEXT,
    size_ml         TEXT,
    price_jod       NUMERIC(10,3) NOT NULL CHECK (price_jod >= 0),
    stock_quantity  INTEGER NOT NULL DEFAULT 0 CHECK (stock_quantity >= 0),
    in_stock        BOOLEAN NOT NULL DEFAULT true,
    is_active       BOOLEAN NOT NULL DEFAULT true,
    image_url       TEXT,
    category        TEXT,
    tags            TEXT,
    sort_order      INTEGER NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_products_store_name UNIQUE (store_id, name_ar)
);

ALTER TABLE products ENABLE ROW LEVEL SECURITY;

CREATE INDEX idx_products_store_active
    ON products(store_id)
    WHERE is_active = true AND in_stock = true;

CREATE INDEX idx_products_store_id ON products(store_id);


-- ---------------------------------------------------------------------------
-- 4. DELIVERY_ZONES — Governorates with delivery fees
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS delivery_zones (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    store_id         UUID NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
    governorate_ar   TEXT NOT NULL,
    governorate_en   TEXT,
    delivery_fee_jod NUMERIC(10,3) NOT NULL DEFAULT 0 CHECK (delivery_fee_jod >= 0),
    estimated_days   INTEGER NOT NULL DEFAULT 1 CHECK (estimated_days >= 1),
    is_active        BOOLEAN NOT NULL DEFAULT true,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE delivery_zones ENABLE ROW LEVEL SECURITY;

CREATE INDEX idx_delivery_zones_store_id ON delivery_zones(store_id);


-- ---------------------------------------------------------------------------
-- 5. CUSTOMERS — Customer profiles per store
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS customers (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    store_id         UUID NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
    messenger_psid   TEXT NOT NULL,
    name             TEXT,
    phone_normalized TEXT, -- 10-digit Jordanian format: 07XXXXXXXX
    governorate      TEXT,
    address_detail   TEXT,
    total_orders     INTEGER NOT NULL DEFAULT 0 CHECK (total_orders >= 0),
    first_contact_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_contact_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE customers ENABLE ROW LEVEL SECURITY;

CREATE UNIQUE INDEX idx_customers_store_psid
    ON customers(store_id, messenger_psid);


-- ---------------------------------------------------------------------------
-- 6. CONVERSATIONS — Active chat sessions
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS conversations (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    store_id         UUID NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
    customer_id      UUID REFERENCES customers(id) ON DELETE SET NULL,
    messenger_psid   TEXT NOT NULL,
    state            TEXT NOT NULL DEFAULT 'DISCOVERY',
    collected_slots  JSONB NOT NULL DEFAULT '{}',
    current_order_id UUID, -- Foreign key added below after orders table
    is_human_handoff BOOLEAN NOT NULL DEFAULT false,
    handoff_reason   TEXT,
    last_message_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE conversations ENABLE ROW LEVEL SECURITY;

CREATE INDEX idx_conversations_store_psid
    ON conversations(store_id, messenger_psid);

CREATE INDEX idx_conversations_store_state
    ON conversations(store_id, state);


-- ---------------------------------------------------------------------------
-- 7. ORDERS — Customer orders per store
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS orders (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    store_id            UUID NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
    customer_id         UUID REFERENCES customers(id) ON DELETE SET NULL,
    conversation_id     UUID REFERENCES conversations(id) ON DELETE SET NULL,
    order_number        TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'PENDING'
                        CHECK (status IN ('PENDING', 'AWAITING_CONFIRMATION', 'CONFIRMED', 'DELIVERED', 'CANCELLED')),
    customer_name       TEXT,
    customer_phone      TEXT,
    governorate         TEXT,
    address_detail      TEXT,
    delivery_zone_id    UUID REFERENCES delivery_zones(id) ON DELETE SET NULL,
    subtotal_jod        NUMERIC(10,3) NOT NULL DEFAULT 0 CHECK (subtotal_jod >= 0),
    delivery_fee_jod    NUMERIC(10,3) NOT NULL DEFAULT 0 CHECK (delivery_fee_jod >= 0),
    total_jod           NUMERIC(10,3) NOT NULL DEFAULT 0 CHECK (total_jod >= 0),
    notes               TEXT,
    cancellation_reason TEXT,
    confirmed_at        TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE orders ENABLE ROW LEVEL SECURITY;

CREATE INDEX idx_orders_store_status ON orders(store_id, status);

CREATE INDEX idx_orders_confirmed_date
    ON orders(store_id, confirmed_at)
    WHERE status = 'CONFIRMED';

CREATE UNIQUE INDEX idx_orders_store_number ON orders(store_id, order_number);

-- Circular reference resolution: conversations.current_order_id -> orders.id
ALTER TABLE conversations
    ADD CONSTRAINT fk_conversations_current_order
    FOREIGN KEY (current_order_id) REFERENCES orders(id) ON DELETE SET NULL;


-- ---------------------------------------------------------------------------
-- 8. ORDER_ITEMS — Frozen line items per order
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS order_items (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id              UUID NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    product_id            UUID REFERENCES products(id) ON DELETE SET NULL,
    product_name_snapshot TEXT NOT NULL,
    unit_price_snapshot   NUMERIC(10,3) NOT NULL CHECK (unit_price_snapshot >= 0),
    quantity              INTEGER NOT NULL CHECK (quantity > 0),
    line_total_jod        NUMERIC(10,3) NOT NULL CHECK (line_total_jod >= 0)
);

ALTER TABLE order_items ENABLE ROW LEVEL SECURITY;

CREATE INDEX idx_order_items_order_id ON order_items(order_id);


-- ---------------------------------------------------------------------------
-- 9. MESSAGES — Full conversation history
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS messages (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    direction       TEXT NOT NULL CHECK (direction IN ('inbound', 'outbound')),
    content         TEXT NOT NULL,
    message_type    TEXT NOT NULL DEFAULT 'text',
    ai_metadata     JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE messages ENABLE ROW LEVEL SECURITY;

CREATE INDEX idx_messages_conversation_id ON messages(conversation_id);
CREATE INDEX idx_messages_created_at ON messages(conversation_id, created_at);


-- ---------------------------------------------------------------------------
-- 10. FAQS — Frequently asked questions & store policies
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS faqs (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    store_id    UUID NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
    question_ar TEXT NOT NULL,
    answer_ar   TEXT NOT NULL,
    is_active   BOOLEAN NOT NULL DEFAULT true,
    sort_order  INTEGER NOT NULL DEFAULT 0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE faqs ENABLE ROW LEVEL SECURITY;

CREATE INDEX idx_faqs_store_id ON faqs(store_id);


-- ---------------------------------------------------------------------------
-- 11. STORE_SETTINGS — Key-value configuration per store
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS store_settings (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    store_id      UUID NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
    setting_key   TEXT NOT NULL,
    setting_value TEXT,
    setting_type  TEXT NOT NULL DEFAULT 'text',
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE store_settings ENABLE ROW LEVEL SECURITY;

CREATE UNIQUE INDEX idx_settings_store_key
    ON store_settings(store_id, setting_key);


-- ---------------------------------------------------------------------------
-- 12. NOTIFICATION_SETTINGS — Telegram & channel alert preferences
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS notification_settings (
    id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    store_id               UUID NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
    channel                TEXT NOT NULL DEFAULT 'telegram' CHECK (channel IN ('telegram', 'email', 'sms')),
    recipient_chat_id      TEXT,
    daily_report_enabled   BOOLEAN NOT NULL DEFAULT true,
    daily_report_time      TIME NOT NULL DEFAULT '21:00:00',
    alert_on_new_order     BOOLEAN NOT NULL DEFAULT true,
    alert_on_human_handoff BOOLEAN NOT NULL DEFAULT true,
    alert_on_low_stock     BOOLEAN NOT NULL DEFAULT true,
    low_stock_threshold    INTEGER NOT NULL DEFAULT 5 CHECK (low_stock_threshold >= 0),
    created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (store_id, channel)
);

ALTER TABLE notification_settings ENABLE ROW LEVEL SECURITY;

CREATE INDEX idx_notification_settings_store ON notification_settings(store_id);


-- ---------------------------------------------------------------------------
-- 13. PROCESSED_WEBHOOK_EVENTS — Idempotency for Meta webhook events
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS processed_webhook_events (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    store_id    UUID NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
    event_mid   TEXT NOT NULL,
    event_type  TEXT,
    received_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE processed_webhook_events ENABLE ROW LEVEL SECURITY;

CREATE UNIQUE INDEX idx_webhook_events_store_mid
    ON processed_webhook_events(store_id, event_mid);


-- ---------------------------------------------------------------------------
-- 14. REPORT_HISTORY — Daily Telegram report logs
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS report_history (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    store_id          UUID NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
    report_date       DATE NOT NULL,
    report_content    TEXT,
    sent_successfully BOOLEAN NOT NULL DEFAULT false,
    error_message     TEXT,
    sent_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE report_history ENABLE ROW LEVEL SECURITY;

CREATE UNIQUE INDEX idx_report_store_date
    ON report_history(store_id, report_date);


-- =============================================================================
-- TRIGGERS: Automated updated_at timestamps
-- =============================================================================
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_stores_updated_at
    BEFORE UPDATE ON stores
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trg_store_members_updated_at
    BEFORE UPDATE ON store_members
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trg_products_updated_at
    BEFORE UPDATE ON products
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trg_orders_updated_at
    BEFORE UPDATE ON orders
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trg_store_settings_updated_at
    BEFORE UPDATE ON store_settings
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trg_notification_settings_updated_at
    BEFORE UPDATE ON notification_settings
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();


-- =============================================================================
-- ROW LEVEL SECURITY (RLS) HELPER & POLICIES
-- =============================================================================
-- Per Supabase performance best practices:
-- 1. Helper is SECURITY DEFINER with set search_path = public.
-- 2. Checks cached auth.uid() via subquery: (SELECT auth.uid()).
-- 3. All member lookups hit indexed (user_id, store_id).
-- 4. CRITICAL SECURITY: NO anon access to products or delivery_zones. All public
--    storefront requests execute server-side through ProductRepository.get_public_showcase.
-- =============================================================================

CREATE OR REPLACE FUNCTION public.is_store_member(target_store_id UUID)
RETURNS BOOLEAN
LANGUAGE sql
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT EXISTS (
    SELECT 1 FROM public.store_members
    WHERE store_id = target_store_id
      AND user_id = (SELECT auth.uid())
  );
$$;

-- 1. STORES
CREATE POLICY stores_member_select ON stores
    FOR SELECT TO authenticated
    USING (public.is_store_member(id));

CREATE POLICY stores_member_update ON stores
    FOR UPDATE TO authenticated
    USING (public.is_store_member(id));

-- 2. STORE_MEMBERS
CREATE POLICY store_members_self_select ON store_members
    FOR SELECT TO authenticated
    USING (user_id = (SELECT auth.uid()) OR public.is_store_member(store_id));

CREATE POLICY store_members_manage ON store_members
    FOR ALL TO authenticated
    USING (public.is_store_member(store_id));

-- 3. PRODUCTS (Restricted to authenticated store members only — NEVER anon)
CREATE POLICY products_member_access ON products
    FOR ALL TO authenticated
    USING (public.is_store_member(store_id))
    WITH CHECK (public.is_store_member(store_id));

-- 4. DELIVERY_ZONES (Restricted to authenticated store members only — NEVER anon)
CREATE POLICY delivery_zones_member_access ON delivery_zones
    FOR ALL TO authenticated
    USING (public.is_store_member(store_id))
    WITH CHECK (public.is_store_member(store_id));

-- 5. CUSTOMERS
CREATE POLICY customers_member_access ON customers
    FOR ALL TO authenticated
    USING (public.is_store_member(store_id))
    WITH CHECK (public.is_store_member(store_id));

-- 6. CONVERSATIONS
CREATE POLICY conversations_member_access ON conversations
    FOR ALL TO authenticated
    USING (public.is_store_member(store_id))
    WITH CHECK (public.is_store_member(store_id));

-- 7. ORDERS
CREATE POLICY orders_member_access ON orders
    FOR ALL TO authenticated
    USING (public.is_store_member(store_id))
    WITH CHECK (public.is_store_member(store_id));

-- 8. ORDER_ITEMS
CREATE POLICY order_items_member_access ON order_items
    FOR ALL TO authenticated
    USING (EXISTS (
        SELECT 1 FROM orders o
        WHERE o.id = order_items.order_id
          AND public.is_store_member(o.store_id)
    ))
    WITH CHECK (EXISTS (
        SELECT 1 FROM orders o
        WHERE o.id = order_items.order_id
          AND public.is_store_member(o.store_id)
    ));

-- 9. MESSAGES
CREATE POLICY messages_member_access ON messages
    FOR ALL TO authenticated
    USING (EXISTS (
        SELECT 1 FROM conversations c
        WHERE c.id = messages.conversation_id
          AND public.is_store_member(c.store_id)
    ))
    WITH CHECK (EXISTS (
        SELECT 1 FROM conversations c
        WHERE c.id = messages.conversation_id
          AND public.is_store_member(c.store_id)
    ));

-- 10. FAQS
CREATE POLICY faqs_member_access ON faqs
    FOR ALL TO authenticated
    USING (public.is_store_member(store_id))
    WITH CHECK (public.is_store_member(store_id));

-- 11. STORE_SETTINGS
CREATE POLICY store_settings_member_access ON store_settings
    FOR ALL TO authenticated
    USING (public.is_store_member(store_id))
    WITH CHECK (public.is_store_member(store_id));

-- 12. NOTIFICATION_SETTINGS
CREATE POLICY notification_settings_member_access ON notification_settings
    FOR ALL TO authenticated
    USING (public.is_store_member(store_id))
    WITH CHECK (public.is_store_member(store_id));

-- 13. PROCESSED_WEBHOOK_EVENTS
CREATE POLICY processed_webhook_events_member_access ON processed_webhook_events
    FOR ALL TO authenticated
    USING (public.is_store_member(store_id))
    WITH CHECK (public.is_store_member(store_id));

-- 14. REPORT_HISTORY
CREATE POLICY report_history_member_access ON report_history
    FOR ALL TO authenticated
    USING (public.is_store_member(store_id))
    WITH CHECK (public.is_store_member(store_id));


-- ---------------------------------------------------------------------------
-- 15. DEFAULT PERMISSIONS AND ROLE GRANTS
-- ---------------------------------------------------------------------------
GRANT USAGE ON SCHEMA public TO postgres, anon, authenticated, service_role;

GRANT ALL ON ALL TABLES IN SCHEMA public TO postgres, service_role;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO postgres, service_role;
GRANT ALL ON ALL ROUTINES IN SCHEMA public TO postgres, service_role;

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO authenticated;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO authenticated;

ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO postgres, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO postgres, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON ROUTINES TO postgres, service_role;

ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO authenticated;

