-- Device tokens for push notifications (APNs, FCM)
CREATE TABLE IF NOT EXISTS device_tokens (
    id TEXT PRIMARY KEY,
    user_id TEXT REFERENCES users(id) ON DELETE CASCADE,
    token TEXT NOT NULL,
    platform TEXT NOT NULL DEFAULT 'apns',  -- 'apns' or 'fcm'
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_device_tokens_token ON device_tokens (token);
CREATE INDEX IF NOT EXISTS idx_device_tokens_user ON device_tokens (user_id);
