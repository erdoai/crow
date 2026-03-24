-- Sub-agent support: parent relationship, per-agent MCP configs, configurable iterations.
-- parent_agent: NULL = user-facing (shown in UI), non-NULL = sub-agent of that parent (hidden)
-- mcp_configs: inline MCP server configs per-agent (overrides instance-level)
-- max_iterations: override default tool-use loop limit (default 10)

ALTER TABLE agent_defs ADD COLUMN IF NOT EXISTS parent_agent TEXT;
ALTER TABLE agent_defs ADD COLUMN IF NOT EXISTS max_iterations INTEGER;
ALTER TABLE agent_defs ADD COLUMN IF NOT EXISTS mcp_configs JSONB;
