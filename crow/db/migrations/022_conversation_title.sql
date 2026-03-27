-- Auto-generated conversation titles
ALTER TABLE conversations
    ADD COLUMN IF NOT EXISTS title TEXT;
