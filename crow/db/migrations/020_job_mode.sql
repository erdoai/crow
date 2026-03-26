-- Job mode: 'chat' (default, blocks thread) or 'background' (silent, notifies on completion)
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS mode TEXT NOT NULL DEFAULT 'chat';
