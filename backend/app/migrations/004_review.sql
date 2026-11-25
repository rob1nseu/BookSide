CREATE TABLE attachments(id TEXT PRIMARY KEY, space_id TEXT NOT NULL REFERENCES spaces(id) ON DELETE CASCADE, target TEXT NOT NULL, mime TEXT NOT NULL, content BLOB NOT NULL, created TEXT NOT NULL);
ALTER TABLE attachments ADD COLUMN transcription TEXT;
ALTER TABLE attempts ADD COLUMN attachment_id TEXT REFERENCES attachments(id);
CREATE TABLE review_maps(id TEXT PRIMARY KEY, space_id TEXT NOT NULL REFERENCES spaces(id) ON DELETE CASCADE, root_id TEXT NOT NULL REFERENCES chapters(id) ON DELETE CASCADE, payload TEXT NOT NULL, created TEXT NOT NULL, UNIQUE(space_id,root_id));
CREATE TABLE review_sessions(id TEXT PRIMARY KEY, space_id TEXT NOT NULL REFERENCES spaces(id) ON DELETE CASCADE, map_id TEXT NOT NULL REFERENCES review_maps(id) ON DELETE CASCADE, questions TEXT NOT NULL, position INTEGER NOT NULL DEFAULT 0, attempts TEXT NOT NULL DEFAULT '[]', assisted TEXT NOT NULL DEFAULT '[]', status TEXT NOT NULL DEFAULT 'active', created TEXT NOT NULL);
CREATE INDEX review_session_space ON review_sessions(space_id,created);
