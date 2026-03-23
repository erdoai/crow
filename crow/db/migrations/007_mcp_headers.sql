-- Add headers column to MCP servers for authenticated connections
ALTER TABLE mcp_servers ADD COLUMN IF NOT EXISTS headers JSONB DEFAULT '{}';
