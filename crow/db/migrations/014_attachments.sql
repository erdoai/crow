-- File attachments on messages (CVs, cover letters, images, etc.)
CREATE TABLE attachments (
    id TEXT PRIMARY KEY,
    message_id TEXT REFERENCES messages(id),
    job_id TEXT,
    filename TEXT NOT NULL,
    content_type TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    data TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_attachments_message ON attachments(message_id);
CREATE INDEX idx_attachments_job ON attachments(job_id) WHERE job_id IS NOT NULL;
