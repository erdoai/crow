CREATE TABLE scheduled_jobs (
    id TEXT PRIMARY KEY,
    agent_name TEXT NOT NULL,
    input TEXT NOT NULL,
    conversation_id TEXT REFERENCES conversations(id),
    user_id TEXT,
    cron TEXT,
    run_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    created_by_job_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_scheduled_jobs_due ON scheduled_jobs (run_at) WHERE status = 'active';
