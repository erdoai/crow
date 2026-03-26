-- Persistent structured key-value store for agents.
-- Scoped per user, keyed by namespace (agent name) + key.
CREATE TABLE IF NOT EXISTS agent_store (
    namespace TEXT NOT NULL,
    key TEXT NOT NULL,
    user_id TEXT NOT NULL DEFAULT '',
    data JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (namespace, key, user_id)
);

CREATE INDEX IF NOT EXISTS idx_agent_store_ns_user
    ON agent_store (namespace, user_id);
