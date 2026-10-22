-- =============================================================================
-- 007: Tell scheduled nightly reports apart from manual "send now" reports
-- =============================================================================
-- Only a successful scheduled (22:00) send blocks a repeat for that day, so
-- pressing "send today's report now" in the dashboard during the day no
-- longer stops the nightly report from going out.
-- =============================================================================

ALTER TABLE report_history ADD COLUMN IF NOT EXISTS is_scheduled BOOLEAN NOT NULL DEFAULT false;
