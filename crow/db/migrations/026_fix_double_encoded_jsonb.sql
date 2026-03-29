-- Fix double-encoded JSONB content in messages.
-- Rows where content is a JSON string that contains a JSON array
-- (e.g. '"[{\"type\":\"text\",...}]"') need to be unwrapped to a native array.
UPDATE messages
SET content = (content #>> '{}')::jsonb
WHERE jsonb_typeof(content) = 'string'
  AND (content #>> '{}') ~ '^\s*\[';
