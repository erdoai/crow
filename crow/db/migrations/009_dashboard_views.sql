-- Dashboard views: DB-stored custom dashboard files (uploaded via API/CLI)
CREATE TABLE IF NOT EXISTS dashboard_views (
    name       TEXT PRIMARY KEY,
    label      TEXT NOT NULL,
    files      JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
