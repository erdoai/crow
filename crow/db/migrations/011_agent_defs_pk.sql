-- Fix agent_defs PK to allow same name for different users.
-- Must drop the agent_shares FK first (it references the old PK).
ALTER TABLE agent_shares DROP CONSTRAINT IF EXISTS agent_shares_agent_name_fkey;
ALTER TABLE agent_defs DROP CONSTRAINT IF EXISTS agent_defs_pkey;
ALTER TABLE agent_defs ADD COLUMN IF NOT EXISTS id SERIAL;
ALTER TABLE agent_defs ADD PRIMARY KEY (id);
CREATE UNIQUE INDEX IF NOT EXISTS agent_defs_name_user
    ON agent_defs (name, user_id) WHERE user_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS agent_defs_name_global
    ON agent_defs (name) WHERE user_id IS NULL;
