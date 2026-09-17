-- Run once on the DCM Unity Catalog schema.
-- Adds landing-zone notification filters to user preferences.

-- Target environment — the only two lines to change. The monitoring schema is
-- environment-specific: `ba_data_connect_monitoring__d` for dev,
-- `ba_data_connect_monitoring__p` for prod.
USE CATALOG it;
USE SCHEMA ba_data_connect_monitoring__d;

ALTER TABLE dcm_user_notification_preferences
ADD COLUMN notification_lz_ids ARRAY<STRING>;
