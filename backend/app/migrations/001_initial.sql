CREATE TABLE documents(id TEXT PRIMARY KEY, owner TEXT NOT NULL DEFAULT 'local', name TEXT NOT NULL, hash TEXT NOT NULL UNIQUE, kind TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'uploaded', error TEXT, created TEXT NOT NULL);
CREATE TABLE pages(id TEXT PRIMARY KEY, document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE, number INTEGER NOT NULL, title TEXT NOT NULL, text TEXT NOT NULL, notes TEXT NOT NULL DEFAULT '', warning TEXT NOT NULL DEFAULT '', UNIQUE(document_id,number));
CREATE TABLE spaces(id TEXT PRIMARY KEY, owner TEXT NOT NULL DEFAULT 'local', name TEXT NOT NULL, archived INTEGER NOT NULL DEFAULT 0, current_chapter TEXT, mode TEXT NOT NULL DEFAULT 'learn', return_chapter TEXT, review_queue TEXT NOT NULL DEFAULT '[]', created TEXT NOT NULL);
CREATE TABLE space_documents(space_id TEXT REFERENCES spaces(id) ON DELETE CASCADE, document_id TEXT REFERENCES documents(id), PRIMARY KEY(space_id,document_id));
CREATE TABLE chapters(id TEXT PRIMARY KEY, space_id TEXT NOT NULL REFERENCES spaces(id) ON DELETE CASCADE, document_id TEXT NOT NULL REFERENCES documents(id), title TEXT NOT NULL, start_page INTEGER NOT NULL, end_page INTEGER NOT NULL, position INTEGER NOT NULL, state TEXT NOT NULL DEFAULT '未学习', lesson TEXT, question_index INTEGER NOT NULL DEFAULT 0, hint_used INTEGER NOT NULL DEFAULT 0, revealed INTEGER NOT NULL DEFAULT 0, passed_at TEXT);
CREATE TABLE questions(id TEXT PRIMARY KEY, chapter_id TEXT NOT NULL REFERENCES chapters(id) ON DELETE CASCADE, position INTEGER NOT NULL, payload TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1, UNIQUE(chapter_id,position));
CREATE TABLE attempts(id TEXT PRIMARY KEY, chapter_id TEXT NOT NULL REFERENCES chapters(id) ON DELETE CASCADE, question_id TEXT NOT NULL REFERENCES questions(id) ON DELETE CASCADE, answer TEXT NOT NULL, feedback TEXT NOT NULL, assisted INTEGER NOT NULL DEFAULT 0, disputed INTEGER NOT NULL DEFAULT 0, created TEXT NOT NULL);
CREATE TABLE messages(id TEXT PRIMARY KEY, space_id TEXT REFERENCES spaces(id) ON DELETE CASCADE, thread TEXT NOT NULL, role TEXT NOT NULL, text TEXT NOT NULL, private INTEGER NOT NULL DEFAULT 0, created TEXT NOT NULL);
CREATE TABLE memories(id TEXT PRIMARY KEY, scope TEXT NOT NULL, space_id TEXT REFERENCES spaces(id) ON DELETE CASCADE, text TEXT NOT NULL, source_id TEXT, active INTEGER NOT NULL DEFAULT 1, created TEXT NOT NULL, updated TEXT NOT NULL);
CREATE TABLE summaries(thread TEXT PRIMARY KEY, text TEXT NOT NULL, watermark TEXT, generation INTEGER NOT NULL DEFAULT 0);
CREATE TABLE settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE runs(id TEXT PRIMARY KEY, scope TEXT NOT NULL, space_id TEXT REFERENCES spaces(id) ON DELETE CASCADE, chapter_id TEXT REFERENCES chapters(id) ON DELETE CASCADE, action TEXT NOT NULL, request_key TEXT NOT NULL, status TEXT NOT NULL, result TEXT, error TEXT, partial TEXT NOT NULL DEFAULT '', created TEXT NOT NULL, completed TEXT, elapsed REAL, usage TEXT, UNIQUE(scope,request_key));
CREATE UNIQUE INDEX single_running ON runs(scope) WHERE status='running';
CREATE TABLE jobs(id TEXT PRIMARY KEY, document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE, status TEXT NOT NULL, error TEXT, created TEXT NOT NULL);
CREATE INDEX messages_thread ON messages(thread,created);
CREATE INDEX pages_document ON pages(document_id,number);
CREATE INDEX memory_scope ON memories(scope,space_id,active);
CREATE INDEX attempts_chapter ON attempts(chapter_id,created);

