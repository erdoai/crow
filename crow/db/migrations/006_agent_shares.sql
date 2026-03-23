-- Share links for agents
CREATE TABLE IF NOT EXISTS agent_shares (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    agent_name TEXT NOT NULL REFERENCES agent_defs(name) ON DELETE CASCADE,
    token TEXT UNIQUE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_agent_shares_token ON agent_shares(token);
CREATE INDEX IF NOT EXISTS idx_agent_shares_agent ON agent_shares(agent_name);
