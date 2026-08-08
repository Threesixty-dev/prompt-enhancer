"""Ordered SQLite migrations added after the original Phase 1 schema."""

from __future__ import annotations


MIGRATION_2 = r"""
CREATE TABLE IF NOT EXISTS task_candidates (
    candidate_id TEXT PRIMARY KEY
        CHECK(length(candidate_id) = 64 AND candidate_id NOT GLOB '*[^0-9a-f]*'),
    project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    discovery_version TEXT NOT NULL
        CHECK(length(discovery_version) BETWEEN 1 AND 128),
    input_fingerprint TEXT NOT NULL
        CHECK(length(input_fingerprint) = 64 AND input_fingerprint NOT GLOB '*[^0-9a-f]*'),
    confidence REAL CHECK(confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
    observed_count INTEGER NOT NULL CHECK(observed_count >= 0),
    eligible_count INTEGER NOT NULL CHECK(eligible_count >= 0),
    coverage REAL NOT NULL CHECK(coverage >= 0 AND coverage <= 1),
    created_at TEXT NOT NULL,
    CHECK(observed_count <= eligible_count)
);
CREATE INDEX IF NOT EXISTS task_candidates_project_idx
    ON task_candidates(project_id, created_at DESC);

CREATE TABLE IF NOT EXISTS task_candidate_sessions (
    candidate_id TEXT NOT NULL
        REFERENCES task_candidates(candidate_id) ON DELETE CASCADE,
    session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    ordinal INTEGER NOT NULL CHECK(ordinal >= 0),
    PRIMARY KEY(candidate_id, session_id),
    UNIQUE(candidate_id, ordinal)
);
CREATE INDEX IF NOT EXISTS task_candidate_sessions_session_idx
    ON task_candidate_sessions(session_id);

CREATE TABLE IF NOT EXISTS task_candidate_signals (
    candidate_id TEXT NOT NULL
        REFERENCES task_candidates(candidate_id) ON DELETE CASCADE,
    ordinal INTEGER NOT NULL CHECK(ordinal >= 0),
    signal_key TEXT NOT NULL CHECK(length(signal_key) BETWEEN 1 AND 128),
    signal_version INTEGER NOT NULL CHECK(signal_version >= 1),
    direction TEXT NOT NULL
        CHECK(direction IN ('supports_link', 'supports_boundary', 'unknown')),
    confidence REAL CHECK(confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
    weight REAL NOT NULL CHECK(weight > 0),
    evidence_code TEXT NOT NULL CHECK(length(evidence_code) BETWEEN 1 AND 64),
    observed_count INTEGER NOT NULL CHECK(observed_count >= 0),
    eligible_count INTEGER NOT NULL CHECK(eligible_count >= 0),
    coverage REAL NOT NULL CHECK(coverage >= 0 AND coverage <= 1),
    numeric_evidence REAL,
    evidence_unit TEXT CHECK(evidence_unit IS NULL OR length(evidence_unit) BETWEEN 1 AND 128),
    PRIMARY KEY(candidate_id, ordinal),
    CHECK(observed_count <= eligible_count),
    CHECK((numeric_evidence IS NULL) = (evidence_unit IS NULL)),
    CHECK(
        (direction = 'unknown' AND confidence IS NULL)
        OR (direction <> 'unknown' AND confidence IS NOT NULL)
    )
);

CREATE TABLE IF NOT EXISTS task_candidate_signal_sessions (
    candidate_id TEXT NOT NULL,
    signal_ordinal INTEGER NOT NULL,
    session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    ordinal INTEGER NOT NULL CHECK(ordinal >= 0),
    PRIMARY KEY(candidate_id, signal_ordinal, session_id),
    UNIQUE(candidate_id, signal_ordinal, ordinal),
    FOREIGN KEY(candidate_id, signal_ordinal)
        REFERENCES task_candidate_signals(candidate_id, ordinal) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS tasks (
    task_id TEXT PRIMARY KEY
        CHECK(length(task_id) = 64 AND task_id NOT GLOB '*[^0-9a-f]*'),
    project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS tasks_project_idx ON tasks(project_id, created_at DESC);

CREATE TABLE IF NOT EXISTS task_revisions (
    task_id TEXT NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE,
    revision INTEGER NOT NULL CHECK(revision >= 1),
    task_type TEXT NOT NULL CHECK(length(task_type) BETWEEN 1 AND 64),
    lifecycle_state TEXT NOT NULL CHECK(length(lifecycle_state) BETWEEN 1 AND 64),
    input_fingerprint TEXT NOT NULL
        CHECK(length(input_fingerprint) = 64 AND input_fingerprint NOT GLOB '*[^0-9a-f]*'),
    created_at TEXT NOT NULL,
    PRIMARY KEY(task_id, revision)
);

CREATE TABLE IF NOT EXISTS task_revision_sessions (
    task_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    ordinal INTEGER NOT NULL CHECK(ordinal >= 0),
    PRIMARY KEY(task_id, revision, session_id),
    UNIQUE(task_id, revision, ordinal),
    FOREIGN KEY(task_id, revision)
        REFERENCES task_revisions(task_id, revision) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS task_revision_sessions_session_idx
    ON task_revision_sessions(session_id);

CREATE TABLE IF NOT EXISTS task_decisions (
    decision_id TEXT PRIMARY KEY
        CHECK(length(decision_id) = 64 AND decision_id NOT GLOB '*[^0-9a-f]*'),
    action TEXT NOT NULL CHECK(action IN ('accept', 'reject', 'merge', 'split')),
    decision_schema_version TEXT NOT NULL
        CHECK(length(decision_schema_version) BETWEEN 1 AND 128),
    decision_code TEXT
        CHECK(decision_code IS NULL OR length(decision_code) BETWEEN 1 AND 64),
    decided_at TEXT NOT NULL,
    CHECK((action = 'reject') = (decision_code IS NOT NULL))
);

CREATE TABLE IF NOT EXISTS task_decision_candidates (
    decision_id TEXT NOT NULL REFERENCES task_decisions(decision_id) ON DELETE CASCADE,
    candidate_id TEXT NOT NULL REFERENCES task_candidates(candidate_id) ON DELETE CASCADE,
    ordinal INTEGER NOT NULL CHECK(ordinal >= 0),
    PRIMARY KEY(decision_id, candidate_id),
    UNIQUE(decision_id, ordinal),
    UNIQUE(candidate_id)
);

CREATE TABLE IF NOT EXISTS task_decision_revisions (
    decision_id TEXT NOT NULL REFERENCES task_decisions(decision_id) ON DELETE CASCADE,
    task_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('input', 'output')),
    ordinal INTEGER NOT NULL CHECK(ordinal >= 0),
    PRIMARY KEY(decision_id, task_id, revision, role),
    UNIQUE(decision_id, role, ordinal),
    FOREIGN KEY(task_id, revision)
        REFERENCES task_revisions(task_id, revision) ON DELETE CASCADE
);
CREATE UNIQUE INDEX IF NOT EXISTS task_decision_output_revision_unique
    ON task_decision_revisions(task_id, revision) WHERE role = 'output';

CREATE TABLE IF NOT EXISTS analysis_runs (
    run_id TEXT PRIMARY KEY
        CHECK(length(run_id) = 64 AND run_id NOT GLOB '*[^0-9a-f]*'),
    task_id TEXT NOT NULL,
    task_revision INTEGER NOT NULL,
    metric_pack_key TEXT NOT NULL CHECK(length(metric_pack_key) BETWEEN 1 AND 128),
    metric_pack_version INTEGER NOT NULL CHECK(metric_pack_version >= 1),
    data_tier TEXT NOT NULL CHECK(length(data_tier) BETWEEN 1 AND 64),
    input_fingerprint TEXT NOT NULL
        CHECK(length(input_fingerprint) = 64 AND input_fingerprint NOT GLOB '*[^0-9a-f]*'),
    metric_engine_version TEXT NOT NULL
        CHECK(length(metric_engine_version) BETWEEN 1 AND 128),
    redactor_version TEXT NOT NULL CHECK(length(redactor_version) BETWEEN 1 AND 128),
    schema_version INTEGER NOT NULL CHECK(schema_version >= 1),
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL CHECK(status IN ('running', 'completed', 'failed')),
    failure_code TEXT CHECK(failure_code IS NULL OR length(failure_code) BETWEEN 1 AND 64),
    FOREIGN KEY(task_id, task_revision)
        REFERENCES task_revisions(task_id, revision) ON DELETE CASCADE,
    CHECK(
        (status = 'running' AND finished_at IS NULL AND failure_code IS NULL)
        OR (status = 'completed' AND finished_at IS NOT NULL AND failure_code IS NULL)
        OR (status = 'failed' AND finished_at IS NOT NULL AND failure_code IS NOT NULL)
    )
);
CREATE INDEX IF NOT EXISTS analysis_runs_task_idx
    ON analysis_runs(task_id, task_revision, started_at DESC);

CREATE TABLE IF NOT EXISTS analysis_results (
    run_id TEXT NOT NULL REFERENCES analysis_runs(run_id) ON DELETE CASCADE,
    key TEXT NOT NULL,
    version INTEGER NOT NULL,
    value_state TEXT NOT NULL
        CHECK(value_state IN ('known', 'unknown', 'not_applicable', 'abstained', 'execution_error')),
    numeric_value REAL,
    text_value TEXT CHECK(
        text_value IS NULL OR (
            length(text_value) BETWEEN 1 AND 64
            AND text_value NOT GLOB '*[^a-z0-9._-]*'
        )
    ),
    unit TEXT NOT NULL CHECK(length(unit) BETWEEN 1 AND 128),
    source TEXT NOT NULL CHECK(length(source) BETWEEN 1 AND 64),
    observed_count INTEGER NOT NULL CHECK(observed_count >= 0),
    eligible_count INTEGER NOT NULL CHECK(eligible_count >= 0),
    coverage REAL NOT NULL CHECK(coverage >= 0 AND coverage <= 1),
    confidence REAL CHECK(confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
    calculator_version TEXT NOT NULL CHECK(length(calculator_version) BETWEEN 1 AND 128),
    model_id TEXT,
    model_revision TEXT,
    tokenizer_id TEXT,
    prompt_version TEXT,
    rubric_version TEXT,
    error_code TEXT CHECK(error_code IS NULL OR length(error_code) BETWEEN 1 AND 64),
    computed_at TEXT NOT NULL,
    PRIMARY KEY(run_id, key, version),
    FOREIGN KEY(key, version) REFERENCES metric_definitions(key, version),
    CHECK(NOT (numeric_value IS NOT NULL AND text_value IS NOT NULL)),
    CHECK(observed_count <= eligible_count),
    CHECK(
        (value_state = 'known' AND (numeric_value IS NOT NULL OR text_value IS NOT NULL) AND error_code IS NULL)
        OR (value_state IN ('unknown', 'not_applicable', 'abstained')
            AND numeric_value IS NULL AND text_value IS NULL AND error_code IS NULL)
        OR (value_state = 'execution_error'
            AND numeric_value IS NULL AND text_value IS NULL AND error_code IS NOT NULL)
    )
);
CREATE INDEX IF NOT EXISTS analysis_results_run_idx ON analysis_results(run_id);

CREATE TABLE IF NOT EXISTS analysis_result_evidence (
    run_id TEXT NOT NULL,
    key TEXT NOT NULL,
    version INTEGER NOT NULL,
    event_id TEXT NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
    ordinal INTEGER NOT NULL CHECK(ordinal >= 0),
    PRIMARY KEY(run_id, key, version, event_id),
    UNIQUE(run_id, key, version, ordinal),
    FOREIGN KEY(run_id, key, version)
        REFERENCES analysis_results(run_id, key, version) ON DELETE CASCADE
);

CREATE TRIGGER IF NOT EXISTS task_candidates_no_update
BEFORE UPDATE ON task_candidates
BEGIN
    SELECT RAISE(ABORT, 'task candidates are immutable');
END;

CREATE TRIGGER IF NOT EXISTS task_candidate_signals_no_update
BEFORE UPDATE ON task_candidate_signals
BEGIN
    SELECT RAISE(ABORT, 'task candidate signals are immutable');
END;

CREATE TRIGGER IF NOT EXISTS task_revisions_no_update
BEFORE UPDATE ON task_revisions
BEGIN
    SELECT RAISE(ABORT, 'task revisions are immutable');
END;

CREATE TRIGGER IF NOT EXISTS task_decisions_no_update
BEFORE UPDATE ON task_decisions
BEGIN
    SELECT RAISE(ABORT, 'task decisions are immutable');
END;

CREATE TRIGGER IF NOT EXISTS analysis_runs_terminal_transition_only
BEFORE UPDATE ON analysis_runs
WHEN OLD.status <> 'running'
    OR NEW.status NOT IN ('completed', 'failed')
    OR NEW.run_id IS NOT OLD.run_id
    OR NEW.task_id IS NOT OLD.task_id
    OR NEW.task_revision IS NOT OLD.task_revision
    OR NEW.metric_pack_key IS NOT OLD.metric_pack_key
    OR NEW.metric_pack_version IS NOT OLD.metric_pack_version
    OR NEW.data_tier IS NOT OLD.data_tier
    OR NEW.input_fingerprint IS NOT OLD.input_fingerprint
    OR NEW.metric_engine_version IS NOT OLD.metric_engine_version
    OR NEW.redactor_version IS NOT OLD.redactor_version
    OR NEW.schema_version IS NOT OLD.schema_version
    OR NEW.started_at IS NOT OLD.started_at
    OR NEW.finished_at IS NULL
BEGIN
    SELECT RAISE(ABORT, 'analysis run transition is invalid');
END;

CREATE TRIGGER IF NOT EXISTS analysis_results_no_update
BEFORE UPDATE ON analysis_results
BEGIN
    SELECT RAISE(ABORT, 'analysis results are immutable');
END;
"""


MIGRATION_3 = r"""
ALTER TABLE events ADD COLUMN time_basis TEXT NOT NULL
    DEFAULT 'provider_reported'
    CHECK(time_basis IN ('provider_reported', 'turn_started', 'turn_completed', 'session_started'));

ALTER TABLE usage_records ADD COLUMN counter_kind TEXT NOT NULL
    DEFAULT 'unknown'
    CHECK(counter_kind IN ('delta', 'cumulative', 'unknown'));

ALTER TABLE usage_records ADD COLUMN scope TEXT NOT NULL
    DEFAULT 'unknown'
    CHECK(scope IN ('request', 'turn', 'thread', 'unknown'));
"""


MIGRATION_4 = r"""
ALTER TABLE projects ADD COLUMN display_name TEXT
    CHECK(display_name IS NULL OR length(display_name) BETWEEN 1 AND 120);

ALTER TABLE sessions ADD COLUMN display_name TEXT
    CHECK(display_name IS NULL OR length(display_name) BETWEEN 1 AND 160);
"""

MIGRATION_5 = r"""
CREATE TABLE project_display_labels (
    project_id TEXT PRIMARY KEY REFERENCES projects(project_id) ON DELETE CASCADE,
    provider_value TEXT CHECK(
        provider_value IS NULL OR length(provider_value) BETWEEN 1 AND 120
    ),
    provider_source TEXT CHECK(
        provider_source IS NULL OR provider_source IN (
            'provider_path_basename', 'provider_explicit_title'
        )
    ),
    observation_method TEXT CHECK(
        observation_method IS NULL OR observation_method IN (
            'thread_list_state_db', 'thread_read_summary', 'legacy_v4_import'
        )
    ),
    extractor_version TEXT,
    provider_version TEXT,
    adapter_version TEXT,
    source_schema_version TEXT,
    provider_observed_at TEXT,
    manual_value TEXT CHECK(
        manual_value IS NULL OR length(manual_value) BETWEEN 1 AND 120
    ),
    manual_revision INTEGER NOT NULL DEFAULT 0 CHECK(manual_revision >= 0),
    manual_updated_at TEXT,
    CHECK(
        (provider_value IS NULL AND provider_source IS NULL
            AND observation_method IS NULL AND extractor_version IS NULL
            AND provider_version IS NULL AND adapter_version IS NULL
            AND source_schema_version IS NULL AND provider_observed_at IS NULL)
        OR
        (provider_value IS NOT NULL AND provider_source IS NOT NULL
            AND observation_method IS NOT NULL AND extractor_version IS NOT NULL
            AND provider_version IS NOT NULL AND adapter_version IS NOT NULL
            AND source_schema_version IS NOT NULL AND provider_observed_at IS NOT NULL)
    )
);

CREATE TABLE session_display_labels (
    session_id TEXT PRIMARY KEY REFERENCES sessions(session_id) ON DELETE CASCADE,
    provider_value TEXT CHECK(
        provider_value IS NULL OR length(provider_value) BETWEEN 1 AND 160
    ),
    provider_source TEXT CHECK(
        provider_source IS NULL OR provider_source IN (
            'provider_path_basename', 'provider_explicit_title'
        )
    ),
    observation_method TEXT CHECK(
        observation_method IS NULL OR observation_method IN (
            'thread_list_state_db', 'thread_read_summary', 'legacy_v4_import'
        )
    ),
    extractor_version TEXT,
    provider_version TEXT,
    adapter_version TEXT,
    source_schema_version TEXT,
    provider_observed_at TEXT,
    manual_value TEXT CHECK(
        manual_value IS NULL OR length(manual_value) BETWEEN 1 AND 160
    ),
    manual_revision INTEGER NOT NULL DEFAULT 0 CHECK(manual_revision >= 0),
    manual_updated_at TEXT,
    CHECK(
        (provider_value IS NULL AND provider_source IS NULL
            AND observation_method IS NULL AND extractor_version IS NULL
            AND provider_version IS NULL AND adapter_version IS NULL
            AND source_schema_version IS NULL AND provider_observed_at IS NULL)
        OR
        (provider_value IS NOT NULL AND provider_source IS NOT NULL
            AND observation_method IS NOT NULL AND extractor_version IS NOT NULL
            AND provider_version IS NOT NULL AND adapter_version IS NOT NULL
            AND source_schema_version IS NOT NULL AND provider_observed_at IS NOT NULL)
    )
);

INSERT INTO project_display_labels(
    project_id, provider_value, provider_source, observation_method,
    extractor_version, provider_version, adapter_version,
    source_schema_version, provider_observed_at
)
SELECT project_id, display_name, 'provider_path_basename', 'legacy_v4_import',
       'legacy-v4', 'unknown', 'unknown', 'unknown', created_at
FROM projects
WHERE display_name IS NOT NULL;

INSERT INTO session_display_labels(
    session_id, provider_value, provider_source, observation_method,
    extractor_version, provider_version, adapter_version,
    source_schema_version, provider_observed_at
)
SELECT session_id, display_name, 'provider_explicit_title', 'legacy_v4_import',
       'legacy-v4', provider_version, adapter_version,
       source_schema_version, updated_at
FROM sessions
WHERE display_name IS NOT NULL;

UPDATE projects SET display_name = NULL WHERE display_name IS NOT NULL;
UPDATE sessions SET display_name = NULL WHERE display_name IS NOT NULL;
"""
