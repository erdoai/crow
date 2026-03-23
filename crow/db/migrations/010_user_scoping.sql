-- Per-user scoping for dashboards and agents.
-- NULL user_id = instance-level (visible to all).
-- Non-NULL user_id = private to that user.
-- share_token = public access link.

-- Dashboard views: add user scoping
ALTER TABLE dashboard_views ADD COLUMN IF NOT EXISTS user_id TEXT;
ALTER TABLE dashboard_views ADD COLUMN IF NOT EXISTS share_token TEXT UNIQUE;

-- Replace simple PK with unique indexes that handle NULLs correctly
ALTER TABLE dashboard_views DROP CONSTRAINT IF EXISTS dashboard_views_pkey;
ALTER TABLE dashboard_views ADD COLUMN IF NOT EXISTS id SERIAL;
ALTER TABLE dashboard_views ADD PRIMARY KEY (id);
CREATE UNIQUE INDEX IF NOT EXISTS dashboard_views_name_user
    ON dashboard_views (name, user_id) WHERE user_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS dashboard_views_name_global
    ON dashboard_views (name) WHERE user_id IS NULL;

-- Agent defs: add user scoping
ALTER TABLE agent_defs ADD COLUMN IF NOT EXISTS user_id TEXT;
