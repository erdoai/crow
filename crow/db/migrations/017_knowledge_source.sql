ALTER TABLE knowledge RENAME COLUMN source TO source_type;
ALTER TABLE knowledge ADD COLUMN IF NOT EXISTS source_ref TEXT;
ALTER TABLE knowledge ADD COLUMN IF NOT EXISTS source_verified_at TIMESTAMPTZ;
