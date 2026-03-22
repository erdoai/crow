CREATE EXTENSION IF NOT EXISTS vector;

-- Conversations (thread per user per gateway)
CREATE TABLE conversations (
    id TEXT PRIMARY KEY,
    gateway TEXT NOT NULL,
    gateway_thread_id TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(gateway, gateway_thread_id)
);

-- Messages within conversations
CREATE TABLE messages (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id),
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    agent_name TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_messages_conversation ON messages(conversation_id, created_at);

-- Jobs (agent execution queue)
CREATE TABLE jobs (
    id TEXT PRIMARY KEY,
    agent_name TEXT NOT NULL,
    conversation_id TEXT REFERENCES conversations(id),
    status TEXT NOT NULL DEFAULT 'pending',
    input TEXT NOT NULL,
    output TEXT,
    worker_id TEXT,
    tokens_used INTEGER DEFAULT 0,
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ
);
CREATE INDEX idx_jobs_status ON jobs(status, created_at);
CREATE INDEX idx_jobs_agent ON jobs(agent_name, created_at DESC);

-- Workers (heartbeat tracking)
CREATE TABLE workers (
    id TEXT PRIMARY KEY,
    name TEXT,
    last_heartbeat TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status TEXT NOT NULL DEFAULT 'idle'
);

-- Knowledge (PARA + pgvector)
CREATE TABLE knowledge (
    id TEXT PRIMARY KEY,
    agent_name TEXT NOT NULL,
    category TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    source TEXT,
    tags TEXT[] DEFAULT '{}',
    embedding vector(1536),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_knowledge_agent_cat ON knowledge(agent_name, category);
CREATE INDEX idx_knowledge_embedding ON knowledge USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- Schema migrations tracking
CREATE TABLE schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
