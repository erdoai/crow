-- Retry tracking for deploy-resilient job execution.
-- attempt: tracks how many times the reaper has requeued a zombie job (retry cap).
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS attempt INTEGER NOT NULL DEFAULT 0;
