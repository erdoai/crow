-- State channel: key/value store for real-time operational state (per-user)
CREATE TABLE IF NOT EXISTS state (
    key        TEXT NOT NULL,
    user_id    TEXT NOT NULL DEFAULT '',
    data       JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (key, user_id)
);
