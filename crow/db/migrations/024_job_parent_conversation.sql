-- Background jobs get their own conversation; parent_conversation_id
-- links back to the originating chat thread for post_update / final result.
ALTER TABLE jobs ADD COLUMN parent_conversation_id TEXT REFERENCES conversations(id);
