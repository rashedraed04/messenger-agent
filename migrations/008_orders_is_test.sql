-- =============================================================================
-- 008: Flag orders placed from the dashboard bot simulator
-- =============================================================================
-- Simulator chats use a messenger_psid starting with 'sim_'. Their orders are
-- kept for testing but must never reach the courier list in the daily
-- Telegram report.
-- =============================================================================

ALTER TABLE orders ADD COLUMN IF NOT EXISTS is_test BOOLEAN NOT NULL DEFAULT false;

UPDATE orders o SET is_test = true
FROM conversations c
WHERE o.conversation_id = c.id AND c.messenger_psid LIKE 'sim\_%';
