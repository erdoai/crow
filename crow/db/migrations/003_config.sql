-- Agent definitions (loaded from crow.yml)
CREATE TABLE agent_defs (
    name TEXT PRIMARY KEY,
    description TEXT NOT NULL,
    prompt_template TEXT NOT NULL,
    tools TEXT[] DEFAULT '{}',
    mcp_servers TEXT[] DEFAULT '{}',
    knowledge_areas TEXT[] DEFAULT '{}',
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- MCP server configs (loaded from crow.yml)
CREATE TABLE mcp_servers (
    name TEXT PRIMARY KEY,
    url TEXT NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
