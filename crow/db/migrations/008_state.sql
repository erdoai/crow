-- State channel: key/value store for real-time operational state
CREATE TABLE IF NOT EXISTS state (
    key        TEXT PRIMARY KEY,
    data       JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
