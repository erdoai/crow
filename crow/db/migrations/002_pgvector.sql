-- Add pgvector embedding column if the extension is available.
-- This migration is safe to skip — crow works without it (keyword search only).
CREATE EXTENSION IF NOT EXISTS vector;

ALTER TABLE knowledge ADD COLUMN IF NOT EXISTS embedding vector(1536);

CREATE INDEX IF NOT EXISTS idx_knowledge_embedding
    ON knowledge USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);
