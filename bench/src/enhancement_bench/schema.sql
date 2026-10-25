PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS core_images (
  core_version TEXT NOT NULL, variant TEXT NOT NULL CHECK(variant IN ('default','models')),
  image TEXT NOT NULL, receipt TEXT, registered REAL NOT NULL,
  PRIMARY KEY(core_version, variant)
);
CREATE TABLE IF NOT EXISTS definitions (
  stable_id TEXT NOT NULL, revision TEXT NOT NULL, generation INTEGER NOT NULL,
  spec_hash TEXT NOT NULL, body TEXT NOT NULL, image TEXT NOT NULL,
  auto_run INTEGER NOT NULL, created REAL NOT NULL,
  PRIMARY KEY(stable_id, revision), UNIQUE(stable_id, generation)
);
CREATE TABLE IF NOT EXISTS core_artifacts (
  core_version TEXT NOT NULL, variant TEXT NOT NULL, image TEXT NOT NULL,
  receipt TEXT NOT NULL, registered REAL NOT NULL,
  PRIMARY KEY(core_version, variant, image)
);
CREATE TRIGGER IF NOT EXISTS immutable_core_artifact BEFORE UPDATE ON core_artifacts
BEGIN SELECT RAISE(ABORT, 'immutable_core_artifact'); END;
CREATE TABLE IF NOT EXISTS runs (
  id TEXT PRIMARY KEY, correlation_id TEXT NOT NULL UNIQUE,
  stable_id TEXT NOT NULL, revision TEXT NOT NULL, generation INTEGER NOT NULL,
  origin TEXT NOT NULL CHECK(origin IN ('gitops','ui')),
  request_key TEXT NOT NULL UNIQUE, request_hash TEXT NOT NULL,
  retry_of TEXT REFERENCES runs(id), effective TEXT NOT NULL, image TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('queued','running','succeeded','failed','cancelled','interrupted','superseded')),
  assertion_outcome TEXT NOT NULL DEFAULT 'unknown',
  cancel_requested INTEGER NOT NULL DEFAULT 0, cleanup_pending INTEGER NOT NULL DEFAULT 0,
  reconciliation_required INTEGER NOT NULL DEFAULT 0,
  container_name TEXT, error_code TEXT, created REAL NOT NULL, started REAL, finished REAL,
  FOREIGN KEY(stable_id,revision) REFERENCES definitions(stable_id,revision)
);
CREATE UNIQUE INDEX IF NOT EXISTS one_auto_revision ON runs(stable_id,revision) WHERE origin='gitops';
CREATE UNIQUE INDEX IF NOT EXISTS one_active_run ON runs((1)) WHERE status='running';
CREATE TABLE IF NOT EXISTS attempts (
  id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(id),
  unit_id TEXT NOT NULL, subject_id TEXT NOT NULL, position INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'queued', request TEXT, result TEXT,
  progress TEXT, error_code TEXT, started REAL, finished REAL,
  UNIQUE(run_id,unit_id,subject_id)
);
CREATE TABLE IF NOT EXISTS events (
  sequence INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL REFERENCES runs(id),
  attempt_id TEXT, state TEXT NOT NULL, code TEXT, created REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS reconciliations (
  run_id TEXT PRIMARY KEY REFERENCES runs(id), evidence_reference TEXT NOT NULL, created REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS cleanup_checks (
  run_id TEXT PRIMARY KEY REFERENCES runs(id), attempts INTEGER NOT NULL,
  checked_at REAL, next_check REAL, error_code TEXT,
  state TEXT NOT NULL CHECK(state IN ('pending','checking','failed','confirmed'))
);
CREATE TRIGGER IF NOT EXISTS immutable_definition BEFORE UPDATE ON definitions
BEGIN SELECT RAISE(ABORT, 'immutable_definition'); END;
CREATE TRIGGER IF NOT EXISTS immutable_run_settings BEFORE UPDATE OF
  effective,image,stable_id,revision,generation,request_key,request_hash,correlation_id ON runs
BEGIN SELECT RAISE(ABORT, 'immutable_run_settings'); END;
