CREATE TABLE run_stages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    stage TEXT NOT NULL,
    created TEXT NOT NULL
);
CREATE INDEX run_stages_run ON run_stages(run_id,id);
