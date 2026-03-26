-- Default job mode for agents: 'chat' or 'background'
ALTER TABLE agent_defs ADD COLUMN IF NOT EXISTS mode TEXT NOT NULL DEFAULT 'chat';
