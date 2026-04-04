-- Personal agent per user: just a name and avatar.
-- Identity, personality, and all context live in the knowledge system.
CREATE TABLE IF NOT EXISTS user_agents (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL UNIQUE REFERENCES users(id),
    agent_name TEXT NOT NULL DEFAULT 'assistant',
    avatar_url TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_user_agents_user ON user_agents(user_id);

-- Pinned knowledge entries are always injected into the system prompt.
-- Use for soul/identity docs, core instructions, etc.
ALTER TABLE knowledge ADD COLUMN IF NOT EXISTS pinned BOOLEAN NOT NULL DEFAULT FALSE;
