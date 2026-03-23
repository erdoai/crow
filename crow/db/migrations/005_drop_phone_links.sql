-- Remove phone_links table (iMessage gateway replaced by iOS app)

DROP INDEX IF EXISTS idx_phone_links_phone;
DROP TABLE IF EXISTS phone_links;
