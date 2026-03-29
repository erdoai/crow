-- Convert messages.content from TEXT to JSONB.
-- Plain text strings become JSON strings, JSON arrays stay as arrays.
ALTER TABLE messages
ALTER COLUMN content TYPE JSONB
USING CASE
    WHEN content ~ '^\s*\[' THEN content::jsonb
    ELSE to_jsonb(content)
END;
