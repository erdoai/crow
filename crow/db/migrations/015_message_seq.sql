-- Add a sequence column for deterministic message ordering.
ALTER TABLE messages ADD COLUMN seq SERIAL;
CREATE INDEX idx_messages_seq ON messages(conversation_id, seq);
