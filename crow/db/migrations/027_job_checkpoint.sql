-- Intermediate turns for resume, stored on the job instead of polluting
-- the conversation with duplicate messages.
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS checkpoint JSONB DEFAULT '[]'::jsonb;
