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


MIGRATION_6 = r"""
BEGIN IMMEDIATE;

CREATE TABLE metric_results_v6 (
    session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    key TEXT NOT NULL,
    version INTEGER NOT NULL,
    metric_pack_key TEXT NOT NULL CHECK(
        length(metric_pack_key) BETWEEN 1 AND 128
        AND metric_pack_key GLOB '[A-Za-z0-9]*'
        AND metric_pack_key NOT GLOB '*[^A-Za-z0-9._+:/-]*'
    ),
    metric_pack_version INTEGER NOT NULL CHECK(metric_pack_version >= 1),
    numeric_value REAL,
    text_value TEXT,
    unit TEXT NOT NULL,
    source TEXT NOT NULL,
    observed_count INTEGER NOT NULL CHECK(observed_count >= 0),
    eligible_count INTEGER NOT NULL CHECK(eligible_count >= 0),
    coverage REAL NOT NULL CHECK(coverage >= 0 AND coverage <= 1),
    confidence REAL CHECK(confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
    metric_engine_version TEXT NOT NULL,
    redactor_version TEXT NOT NULL,
    model_id TEXT,
    model_revision TEXT,
    tokenizer_id TEXT,
    prompt_version TEXT,
    rubric_version TEXT,
    computed_at TEXT NOT NULL,
    CHECK(NOT (numeric_value IS NOT NULL AND text_value IS NOT NULL)),
    CHECK(observed_count <= eligible_count),
    PRIMARY KEY(session_id, key, version),
    FOREIGN KEY(key, version) REFERENCES metric_definitions(key, version)
);

INSERT INTO metric_results_v6(
    session_id, key, version, metric_pack_key, metric_pack_version,
    numeric_value, text_value, unit, source, observed_count, eligible_count,
    coverage, confidence, metric_engine_version, redactor_version, model_id,
    model_revision, tokenizer_id, prompt_version, rubric_version, computed_at
)
SELECT session_id, key, version, 'legacy.unknown.session', 1,
       numeric_value, text_value, unit, source, observed_count, eligible_count,
       coverage, confidence, metric_engine_version, redactor_version, model_id,
       model_revision, tokenizer_id, prompt_version, rubric_version, computed_at
FROM metric_results;

DROP TABLE metric_results;
ALTER TABLE metric_results_v6 RENAME TO metric_results;
CREATE INDEX metric_results_session_idx ON metric_results(session_id);

COMMIT;
"""


MIGRATION_7 = r"""
BEGIN IMMEDIATE;

CREATE TABLE session_analysis_runs (
    run_id TEXT PRIMARY KEY
        CHECK(length(run_id) = 64 AND run_id NOT GLOB '*[^0-9a-f]*'),
    session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    request_fingerprint TEXT NOT NULL
        CHECK(length(request_fingerprint) = 64 AND request_fingerprint NOT GLOB '*[^0-9a-f]*'),
    input_fingerprint TEXT NOT NULL
        CHECK(length(input_fingerprint) = 64 AND input_fingerprint NOT GLOB '*[^0-9a-f]*'),
    metric_pack_key TEXT NOT NULL CHECK(
        length(metric_pack_key) BETWEEN 1 AND 128
        AND metric_pack_key GLOB '[A-Za-z0-9]*'
        AND metric_pack_key NOT GLOB '*[^A-Za-z0-9._+:/-]*'
    ),
    metric_pack_version INTEGER NOT NULL CHECK(metric_pack_version >= 1),
    data_tier TEXT NOT NULL CHECK(data_tier = 'redacted_content'),
    consent_purpose TEXT NOT NULL CHECK(consent_purpose = 'text_analysis'),
    consent_policy_version TEXT NOT NULL CHECK(
        length(consent_policy_version) BETWEEN 1 AND 128
        AND consent_policy_version GLOB '[A-Za-z0-9]*'
        AND consent_policy_version NOT GLOB '*[^A-Za-z0-9._+:/-]*'
    ),
    provider TEXT NOT NULL CHECK(provider IN ('codex', 'claude_code', 'synthetic')),
    provider_version TEXT NOT NULL CHECK(
        length(provider_version) BETWEEN 1 AND 128
        AND provider_version GLOB '[A-Za-z0-9]*'
        AND provider_version NOT GLOB '*[^A-Za-z0-9._+:/-]*'
    ),
    adapter_version TEXT NOT NULL CHECK(
        length(adapter_version) BETWEEN 1 AND 128
        AND adapter_version GLOB '[A-Za-z0-9]*'
        AND adapter_version NOT GLOB '*[^A-Za-z0-9._+:/-]*'
    ),
    source_schema_version TEXT NOT NULL CHECK(
        length(source_schema_version) BETWEEN 1 AND 128
        AND source_schema_version GLOB '[A-Za-z0-9]*'
        AND source_schema_version NOT GLOB '*[^A-Za-z0-9._+:/-]*'
    ),
    content_schema_version TEXT NOT NULL CHECK(
        length(content_schema_version) BETWEEN 1 AND 128
        AND content_schema_version GLOB '[A-Za-z0-9]*'
        AND content_schema_version NOT GLOB '*[^A-Za-z0-9._+:/-]*'
    ),
    metric_engine_version TEXT NOT NULL CHECK(
        length(metric_engine_version) BETWEEN 1 AND 128
        AND metric_engine_version GLOB '[A-Za-z0-9]*'
        AND metric_engine_version NOT GLOB '*[^A-Za-z0-9._+:/-]*'
    ),
    redactor_version TEXT NOT NULL CHECK(
        length(redactor_version) BETWEEN 1 AND 128
        AND redactor_version GLOB '[A-Za-z0-9]*'
        AND redactor_version NOT GLOB '*[^A-Za-z0-9._+:/-]*'
    ),
    model_plan_fingerprint TEXT NOT NULL CHECK(
        length(model_plan_fingerprint) = 64
        AND model_plan_fingerprint NOT GLOB '*[^0-9a-f]*'
    ),
    schema_version INTEGER NOT NULL CHECK(schema_version >= 1),
    local_only INTEGER NOT NULL CHECK(local_only = 1),
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL CHECK(status IN ('running', 'completed', 'failed')),
    failure_code TEXT CHECK(
        failure_code IS NULL OR (
            length(failure_code) BETWEEN 1 AND 64
            AND failure_code GLOB '[a-z0-9]*'
            AND failure_code NOT GLOB '*[^a-z0-9._-]*'
        )
    ),
    CHECK(
        (status = 'running' AND finished_at IS NULL AND failure_code IS NULL)
        OR (status = 'completed' AND finished_at IS NOT NULL AND failure_code IS NULL)
        OR (status = 'failed' AND finished_at IS NOT NULL AND failure_code IS NOT NULL)
    )
);
CREATE INDEX session_analysis_runs_session_idx
    ON session_analysis_runs(session_id, started_at DESC, run_id);

CREATE TABLE session_analysis_results (
    run_id TEXT NOT NULL REFERENCES session_analysis_runs(run_id) ON DELETE CASCADE,
    key TEXT NOT NULL,
    version INTEGER NOT NULL CHECK(version >= 1),
    metric_schema_version INTEGER NOT NULL CHECK(metric_schema_version >= 1),
    value_state TEXT NOT NULL CHECK(
        value_state IN ('known', 'unknown', 'not_applicable', 'abstained', 'execution_error')
    ),
    numeric_value REAL,
    unit TEXT NOT NULL CHECK(
        length(unit) BETWEEN 1 AND 128
        AND unit GLOB '[A-Za-z0-9]*'
        AND unit NOT GLOB '*[^A-Za-z0-9._+:/-]*'
    ),
    source TEXT NOT NULL CHECK(
        source IN ('provider_reported', 'deterministic', 'human_label', 'estimated')
    ),
    direction TEXT NOT NULL CHECK(direction IN ('higher_is_better', 'lower_is_better')),
    applicability TEXT NOT NULL CHECK(
        applicability IN ('applicable', 'not_applicable', 'unknown')
    ),
    aggregation_method TEXT NOT NULL CHECK(aggregation_method = 'ratio_of_sums'),
    fraction_numerator INTEGER CHECK(fraction_numerator IS NULL OR fraction_numerator >= 0),
    fraction_denominator INTEGER CHECK(fraction_denominator IS NULL OR fraction_denominator >= 1),
    observed_count INTEGER NOT NULL CHECK(observed_count >= 0),
    eligible_count INTEGER NOT NULL CHECK(eligible_count >= 0),
    coverage REAL NOT NULL CHECK(coverage >= 0 AND coverage <= 1),
    confidence REAL CHECK(confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
    evidence_data_tier TEXT NOT NULL CHECK(evidence_data_tier = 'redacted_content'),
    explanation_code TEXT NOT NULL CHECK(
        length(explanation_code) BETWEEN 1 AND 64
        AND explanation_code GLOB '[a-z0-9]*'
        AND explanation_code NOT GLOB '*[^a-z0-9._-]*'
    ),
    error_code TEXT CHECK(
        error_code IS NULL OR (
            length(error_code) BETWEEN 1 AND 64
            AND error_code GLOB '[a-z0-9]*'
            AND error_code NOT GLOB '*[^a-z0-9._-]*'
        )
    ),
    algorithm_id TEXT NOT NULL CHECK(
        length(algorithm_id) BETWEEN 1 AND 128
        AND algorithm_id GLOB '[A-Za-z0-9]*'
        AND algorithm_id NOT GLOB '*[^A-Za-z0-9._+:/-]*'
    ),
    algorithm_version TEXT NOT NULL CHECK(
        length(algorithm_version) BETWEEN 1 AND 128
        AND algorithm_version GLOB '[A-Za-z0-9]*'
        AND algorithm_version NOT GLOB '*[^A-Za-z0-9._+:/-]*'
    ),
    model_id TEXT CHECK(model_id IS NULL OR (
        length(model_id) BETWEEN 1 AND 128
        AND model_id GLOB '[A-Za-z0-9]*'
        AND model_id NOT GLOB '*[^A-Za-z0-9._+:/-]*'
    )),
    model_revision TEXT CHECK(model_revision IS NULL OR (
        length(model_revision) BETWEEN 1 AND 128
        AND model_revision GLOB '[A-Za-z0-9]*'
        AND model_revision NOT GLOB '*[^A-Za-z0-9._+:/-]*'
    )),
    model_license TEXT CHECK(model_license IS NULL OR (
        length(model_license) BETWEEN 1 AND 128
        AND model_license GLOB '[A-Za-z0-9]*'
        AND model_license NOT GLOB '*[^A-Za-z0-9._+:/-]*'
    )),
    tokenizer_id TEXT CHECK(tokenizer_id IS NULL OR (
        length(tokenizer_id) BETWEEN 1 AND 128
        AND tokenizer_id GLOB '[A-Za-z0-9]*'
        AND tokenizer_id NOT GLOB '*[^A-Za-z0-9._+:/-]*'
    )),
    prompt_version TEXT CHECK(prompt_version IS NULL OR (
        length(prompt_version) BETWEEN 1 AND 128
        AND prompt_version GLOB '[A-Za-z0-9]*'
        AND prompt_version NOT GLOB '*[^A-Za-z0-9._+:/-]*'
    )),
    rubric_version TEXT CHECK(rubric_version IS NULL OR (
        length(rubric_version) BETWEEN 1 AND 128
        AND rubric_version GLOB '[A-Za-z0-9]*'
        AND rubric_version NOT GLOB '*[^A-Za-z0-9._+:/-]*'
    )),
    computed_at TEXT NOT NULL,
    PRIMARY KEY(run_id, key, version),
    FOREIGN KEY(key, version) REFERENCES metric_definitions(key, version),
    CHECK(observed_count <= eligible_count),
    CHECK(abs(coverage - CASE
        WHEN eligible_count = 0 THEN 0.0
        ELSE CAST(observed_count AS REAL) / eligible_count
    END) <= 0.000000001),
    CHECK((fraction_numerator IS NULL) = (fraction_denominator IS NULL)),
    CHECK(fraction_numerator IS NULL OR fraction_numerator <= fraction_denominator),
    CHECK(
        (value_state = 'known' AND numeric_value IS NOT NULL
            AND fraction_numerator IS NOT NULL AND applicability = 'applicable'
            AND error_code IS NULL)
        OR
        (value_state IN ('unknown', 'abstained') AND numeric_value IS NULL
            AND fraction_numerator IS NULL AND applicability <> 'not_applicable'
            AND confidence IS NULL AND error_code IS NULL)
        OR
        (value_state = 'not_applicable' AND numeric_value IS NULL
            AND fraction_numerator IS NULL AND applicability = 'not_applicable'
            AND confidence IS NULL AND error_code IS NULL)
        OR
        (value_state = 'execution_error' AND numeric_value IS NULL
            AND fraction_numerator IS NULL AND applicability <> 'not_applicable'
            AND confidence IS NULL AND error_code IS NOT NULL)
    ),
    CHECK(
        numeric_value IS NULL OR abs(
            numeric_value - CAST(fraction_numerator AS REAL) / fraction_denominator
        ) <= 0.000000001
    ),
    CHECK(
        (model_id IS NULL AND model_revision IS NULL AND model_license IS NULL
            AND tokenizer_id IS NULL AND prompt_version IS NULL)
        OR
        (model_id IS NOT NULL AND model_revision IS NOT NULL AND model_license IS NOT NULL
            AND tokenizer_id IS NOT NULL)
    )
);
CREATE INDEX session_analysis_results_run_idx
    ON session_analysis_results(run_id, key, version);

CREATE TABLE session_analysis_result_evidence (
    run_id TEXT NOT NULL,
    key TEXT NOT NULL,
    version INTEGER NOT NULL,
    message_id TEXT NOT NULL CHECK(
        length(message_id) = 64 AND message_id NOT GLOB '*[^0-9a-f]*'
    ),
    origin TEXT NOT NULL CHECK(origin IN ('direct', 'inherited')),
    ordinal INTEGER NOT NULL CHECK(ordinal >= 0),
    PRIMARY KEY(run_id, key, version, message_id),
    UNIQUE(run_id, key, version, ordinal),
    FOREIGN KEY(run_id, key, version)
        REFERENCES session_analysis_results(run_id, key, version) ON DELETE CASCADE
);

CREATE TRIGGER session_analysis_runs_terminal_transition_only
BEFORE UPDATE ON session_analysis_runs
WHEN OLD.status <> 'running'
    OR NEW.status NOT IN ('completed', 'failed')
    OR NEW.run_id IS NOT OLD.run_id
    OR NEW.session_id IS NOT OLD.session_id
    OR NEW.request_fingerprint IS NOT OLD.request_fingerprint
    OR NEW.input_fingerprint IS NOT OLD.input_fingerprint
    OR NEW.metric_pack_key IS NOT OLD.metric_pack_key
    OR NEW.metric_pack_version IS NOT OLD.metric_pack_version
    OR NEW.data_tier IS NOT OLD.data_tier
    OR NEW.consent_purpose IS NOT OLD.consent_purpose
    OR NEW.consent_policy_version IS NOT OLD.consent_policy_version
    OR NEW.provider IS NOT OLD.provider
    OR NEW.provider_version IS NOT OLD.provider_version
    OR NEW.adapter_version IS NOT OLD.adapter_version
    OR NEW.source_schema_version IS NOT OLD.source_schema_version
    OR NEW.content_schema_version IS NOT OLD.content_schema_version
    OR NEW.metric_engine_version IS NOT OLD.metric_engine_version
    OR NEW.redactor_version IS NOT OLD.redactor_version
    OR NEW.model_plan_fingerprint IS NOT OLD.model_plan_fingerprint
    OR NEW.schema_version IS NOT OLD.schema_version
    OR NEW.local_only IS NOT OLD.local_only
    OR NEW.started_at IS NOT OLD.started_at
    OR NEW.finished_at IS NULL
    OR (NEW.status = 'completed' AND NOT EXISTS (
        SELECT 1 FROM session_analysis_results WHERE run_id = OLD.run_id
    ))
    OR (NEW.status = 'failed' AND EXISTS (
        SELECT 1 FROM session_analysis_results WHERE run_id = OLD.run_id
    ))
BEGIN
    SELECT RAISE(ABORT, 'session analysis run transition is invalid');
END;

CREATE TRIGGER session_analysis_results_running_insert_only
BEFORE INSERT ON session_analysis_results
WHEN COALESCE(
    (SELECT status FROM session_analysis_runs WHERE run_id = NEW.run_id), ''
) <> 'running'
BEGIN
    SELECT RAISE(ABORT, 'session analysis results require a running run');
END;

CREATE TRIGGER session_analysis_results_no_update
BEFORE UPDATE ON session_analysis_results
BEGIN
    SELECT RAISE(ABORT, 'session analysis results are immutable');
END;

CREATE TRIGGER session_analysis_results_privacy_delete_only
BEFORE DELETE ON session_analysis_results
WHEN EXISTS (
    SELECT 1 FROM session_analysis_runs WHERE run_id = OLD.run_id
)
BEGIN
    SELECT RAISE(ABORT, 'session analysis results require parent privacy deletion');
END;

CREATE TRIGGER session_analysis_result_evidence_running_insert_only
BEFORE INSERT ON session_analysis_result_evidence
WHEN COALESCE(
    (SELECT status FROM session_analysis_runs WHERE run_id = NEW.run_id), ''
) <> 'running'
BEGIN
    SELECT RAISE(ABORT, 'session analysis evidence requires a running run');
END;

CREATE TRIGGER session_analysis_result_evidence_no_update
BEFORE UPDATE ON session_analysis_result_evidence
BEGIN
    SELECT RAISE(ABORT, 'session analysis evidence is immutable');
END;

CREATE TRIGGER session_analysis_result_evidence_privacy_delete_only
BEFORE DELETE ON session_analysis_result_evidence
WHEN EXISTS (
    SELECT 1 FROM session_analysis_results
    WHERE run_id = OLD.run_id AND key = OLD.key AND version = OLD.version
)
BEGIN
    SELECT RAISE(ABORT, 'session analysis evidence requires parent privacy deletion');
END;

COMMIT;
"""


MIGRATION_8 = r"""
BEGIN IMMEDIATE;

ALTER TABLE session_analysis_runs
ADD COLUMN analysis_profile_key TEXT NOT NULL DEFAULT 'legacy.explicit-profile'
    CHECK(
        length(analysis_profile_key) BETWEEN 1 AND 128
        AND analysis_profile_key GLOB '[A-Za-z0-9]*'
        AND analysis_profile_key NOT GLOB '*[^A-Za-z0-9._+:/-]*'
    );

ALTER TABLE session_analysis_runs
ADD COLUMN analysis_profile_version INTEGER NOT NULL DEFAULT 1
    CHECK(analysis_profile_version >= 1);

DROP TRIGGER session_analysis_runs_terminal_transition_only;
CREATE TRIGGER session_analysis_runs_terminal_transition_only
BEFORE UPDATE ON session_analysis_runs
WHEN OLD.status <> 'running'
    OR NEW.status NOT IN ('completed', 'failed')
    OR NEW.run_id IS NOT OLD.run_id
    OR NEW.session_id IS NOT OLD.session_id
    OR NEW.request_fingerprint IS NOT OLD.request_fingerprint
    OR NEW.input_fingerprint IS NOT OLD.input_fingerprint
    OR NEW.analysis_profile_key IS NOT OLD.analysis_profile_key
    OR NEW.analysis_profile_version IS NOT OLD.analysis_profile_version
    OR NEW.metric_pack_key IS NOT OLD.metric_pack_key
    OR NEW.metric_pack_version IS NOT OLD.metric_pack_version
    OR NEW.data_tier IS NOT OLD.data_tier
    OR NEW.consent_purpose IS NOT OLD.consent_purpose
    OR NEW.consent_policy_version IS NOT OLD.consent_policy_version
    OR NEW.provider IS NOT OLD.provider
    OR NEW.provider_version IS NOT OLD.provider_version
    OR NEW.adapter_version IS NOT OLD.adapter_version
    OR NEW.source_schema_version IS NOT OLD.source_schema_version
    OR NEW.content_schema_version IS NOT OLD.content_schema_version
    OR NEW.metric_engine_version IS NOT OLD.metric_engine_version
    OR NEW.redactor_version IS NOT OLD.redactor_version
    OR NEW.model_plan_fingerprint IS NOT OLD.model_plan_fingerprint
    OR NEW.schema_version IS NOT OLD.schema_version
    OR NEW.local_only IS NOT OLD.local_only
    OR NEW.started_at IS NOT OLD.started_at
    OR NEW.finished_at IS NULL
    OR (NEW.status = 'completed' AND NOT EXISTS (
        SELECT 1 FROM session_analysis_results WHERE run_id = OLD.run_id
    ))
    OR (NEW.status = 'failed' AND EXISTS (
        SELECT 1 FROM session_analysis_results WHERE run_id = OLD.run_id
    ))
BEGIN
    SELECT RAISE(ABORT, 'session analysis run transition is invalid');
END;

COMMIT;
"""


MIGRATION_9 = r"""
BEGIN IMMEDIATE;

CREATE TABLE session_analysis_result_signals (
    run_id TEXT NOT NULL,
    key TEXT NOT NULL,
    version INTEGER NOT NULL,
    code TEXT NOT NULL CHECK(
        length(code) BETWEEN 1 AND 64
        AND code GLOB '[a-z0-9]*'
        AND code NOT GLOB '*[^a-z0-9._-]*'
    ),
    status TEXT NOT NULL CHECK(
        status IN ('detected', 'missing', 'counted', 'unknown')
    ),
    signal_count INTEGER CHECK(
        signal_count IS NULL OR signal_count BETWEEN 0 AND 10000000
    ),
    ordinal INTEGER NOT NULL CHECK(ordinal >= 0),
    PRIMARY KEY(run_id, key, version, code),
    UNIQUE(run_id, key, version, ordinal),
    FOREIGN KEY(run_id, key, version)
        REFERENCES session_analysis_results(run_id, key, version) ON DELETE CASCADE,
    CHECK(
        (status = 'detected' AND signal_count = 1)
        OR (status = 'missing' AND signal_count = 0)
        OR (status = 'counted' AND signal_count IS NOT NULL)
        OR (status = 'unknown' AND signal_count IS NULL)
    )
);

CREATE TRIGGER session_analysis_result_signals_running_insert_only
BEFORE INSERT ON session_analysis_result_signals
WHEN COALESCE(
    (SELECT status FROM session_analysis_runs WHERE run_id = NEW.run_id), ''
) <> 'running'
BEGIN
    SELECT RAISE(ABORT, 'session analysis signals require a running run');
END;

CREATE TRIGGER session_analysis_result_signals_no_update
BEFORE UPDATE ON session_analysis_result_signals
BEGIN
    SELECT RAISE(ABORT, 'session analysis signals are immutable');
END;

CREATE TRIGGER session_analysis_result_signals_privacy_delete_only
BEFORE DELETE ON session_analysis_result_signals
WHEN EXISTS (
    SELECT 1 FROM session_analysis_results
    WHERE run_id = OLD.run_id AND key = OLD.key AND version = OLD.version
)
BEGIN
    SELECT RAISE(ABORT, 'session analysis signals require parent privacy deletion');
END;

COMMIT;
"""


MIGRATION_10 = r"""
BEGIN IMMEDIATE;

CREATE TABLE session_model_link_runs (
    run_id TEXT PRIMARY KEY CHECK(length(run_id) = 64),
    session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    request_fingerprint TEXT NOT NULL CHECK(length(request_fingerprint) = 64),
    input_fingerprint TEXT NOT NULL CHECK(length(input_fingerprint) = 64),
    experiment_key TEXT NOT NULL CHECK(
        length(experiment_key) BETWEEN 1 AND 128
        AND experiment_key GLOB '[A-Za-z0-9]*'
        AND experiment_key NOT GLOB '*[^A-Za-z0-9._+:/-]*'
    ),
    experiment_version INTEGER NOT NULL CHECK(experiment_version >= 1),
    provider TEXT NOT NULL CHECK(provider IN ('codex', 'claude_code', 'synthetic')),
    provider_version TEXT NOT NULL,
    adapter_version TEXT NOT NULL,
    source_schema_version TEXT NOT NULL,
    content_schema_version TEXT NOT NULL,
    redactor_version TEXT NOT NULL,
    consent_policy_version TEXT NOT NULL,
    resolved_device TEXT NOT NULL CHECK(resolved_device IN ('cpu', 'cuda', 'mps')),
    qwen_model_key TEXT NOT NULL,
    qwen_repository_id TEXT NOT NULL,
    qwen_revision TEXT NOT NULL CHECK(length(qwen_revision) = 40),
    qwen_license TEXT NOT NULL,
    qwen_tokenizer_id TEXT NOT NULL,
    qwen_backend_key TEXT NOT NULL,
    bge_model_key TEXT NOT NULL,
    bge_repository_id TEXT NOT NULL,
    bge_revision TEXT NOT NULL CHECK(length(bge_revision) = 40),
    bge_license TEXT NOT NULL,
    bge_tokenizer_id TEXT NOT NULL,
    bge_backend_key TEXT NOT NULL,
    query_count INTEGER NOT NULL CHECK(query_count BETWEEN 1 AND 8),
    link_count INTEGER NOT NULL CHECK(link_count BETWEEN 1 AND 16),
    agreement_count INTEGER NOT NULL CHECK(
        agreement_count BETWEEN 0 AND query_count
    ),
    started_at TEXT NOT NULL,
    finished_at TEXT NOT NULL,
    local_only INTEGER NOT NULL CHECK(local_only = 1),
    UNIQUE(session_id, request_fingerprint)
);

CREATE INDEX session_model_link_runs_latest_idx
    ON session_model_link_runs(session_id, finished_at DESC, run_id DESC);

CREATE TABLE session_model_links (
    run_id TEXT NOT NULL REFERENCES session_model_link_runs(run_id) ON DELETE CASCADE,
    link_id TEXT NOT NULL CHECK(length(link_id) = 64),
    query_message_id TEXT NOT NULL CHECK(length(query_message_id) = 64),
    candidate_message_id TEXT NOT NULL CHECK(length(candidate_message_id) = 64),
    query_sequence INTEGER NOT NULL CHECK(query_sequence >= 0),
    candidate_sequence INTEGER NOT NULL CHECK(candidate_sequence > query_sequence),
    candidate_kind TEXT NOT NULL CHECK(candidate_kind IN ('response', 'plan')),
    qwen_score REAL NOT NULL CHECK(qwen_score BETWEEN -1.000001 AND 1.000001),
    qwen_rank INTEGER NOT NULL CHECK(qwen_rank BETWEEN 1 AND 8),
    bge_score REAL NOT NULL CHECK(bge_score BETWEEN -100000 AND 100000),
    bge_rank INTEGER NOT NULL CHECK(bge_rank BETWEEN 1 AND 8),
    recommended_by TEXT NOT NULL CHECK(recommended_by IN ('qwen', 'bge', 'both')),
    PRIMARY KEY(run_id, link_id),
    UNIQUE(run_id, query_message_id, candidate_message_id)
);

CREATE TABLE session_model_link_annotations (
    run_id TEXT NOT NULL,
    link_id TEXT NOT NULL,
    revision INTEGER NOT NULL CHECK(revision >= 1),
    label TEXT NOT NULL CHECK(label IN ('relevant', 'incorrect', 'unsure')),
    annotated_at TEXT NOT NULL,
    PRIMARY KEY(run_id, link_id, revision),
    FOREIGN KEY(run_id, link_id)
        REFERENCES session_model_links(run_id, link_id) ON DELETE CASCADE
);

CREATE TRIGGER session_model_link_runs_no_update
BEFORE UPDATE ON session_model_link_runs
BEGIN
    SELECT RAISE(ABORT, 'session model-link runs are immutable');
END;

CREATE TRIGGER session_model_links_no_update
BEFORE UPDATE ON session_model_links
BEGIN
    SELECT RAISE(ABORT, 'session model links are immutable');
END;

CREATE TRIGGER session_model_links_privacy_delete_only
BEFORE DELETE ON session_model_links
WHEN EXISTS (
    SELECT 1 FROM session_model_link_runs WHERE run_id = OLD.run_id
)
BEGIN
    SELECT RAISE(ABORT, 'session model links require parent privacy deletion');
END;

CREATE TRIGGER session_model_link_annotations_no_update
BEFORE UPDATE ON session_model_link_annotations
BEGIN
    SELECT RAISE(ABORT, 'session model-link annotations are append-only');
END;

CREATE TRIGGER session_model_link_annotations_privacy_delete_only
BEFORE DELETE ON session_model_link_annotations
WHEN EXISTS (
    SELECT 1 FROM session_model_links
    WHERE run_id = OLD.run_id AND link_id = OLD.link_id
)
BEGIN
    SELECT RAISE(ABORT, 'session model-link annotations require parent privacy deletion');
END;

COMMIT;
"""


MIGRATION_11 = r"""
BEGIN IMMEDIATE;

CREATE TABLE analysis_jobs (
    job_id TEXT PRIMARY KEY
        CHECK(length(job_id) = 64 AND job_id NOT GLOB '*[^0-9a-f]*'),
    dedupe_key TEXT NOT NULL UNIQUE
        CHECK(length(dedupe_key) = 64 AND dedupe_key NOT GLOB '*[^0-9a-f]*'),
    kind TEXT NOT NULL CHECK(kind IN ('session_quality', 'synthetic_validation')),
    provider TEXT NOT NULL CHECK(provider IN ('codex', 'claude_code', 'synthetic')),
    project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    input_fingerprint TEXT NOT NULL CHECK(
        length(input_fingerprint) = 64
        AND input_fingerprint NOT GLOB '*[^0-9a-f]*'
    ),
    provenance_fingerprint TEXT NOT NULL CHECK(
        length(provenance_fingerprint) = 64
        AND provenance_fingerprint NOT GLOB '*[^0-9a-f]*'
    ),
    estimator_plan_version TEXT NOT NULL CHECK(
        length(estimator_plan_version) BETWEEN 1 AND 128
        AND estimator_plan_version GLOB '[A-Za-z0-9]*'
        AND estimator_plan_version NOT GLOB '*[^A-Za-z0-9._+:/-]*'
    ),
    redactor_version TEXT NOT NULL CHECK(
        length(redactor_version) BETWEEN 1 AND 128
        AND redactor_version GLOB '[A-Za-z0-9]*'
        AND redactor_version NOT GLOB '*[^A-Za-z0-9._+:/-]*'
    ),
    provider_schema_version TEXT NOT NULL CHECK(
        length(provider_schema_version) BETWEEN 1 AND 128
        AND provider_schema_version GLOB '[A-Za-z0-9]*'
        AND provider_schema_version NOT GLOB '*[^A-Za-z0-9._+:/-]*'
    ),
    automation_grant_id TEXT CHECK(
        automation_grant_id IS NULL OR (
            length(automation_grant_id) = 64
            AND automation_grant_id NOT GLOB '*[^0-9a-f]*'
        )
    ),
    local_only INTEGER NOT NULL CHECK(local_only = 1),
    state TEXT NOT NULL CHECK(state IN (
        'queued', 'preprocessing', 'stage_n', 'awaiting_approval',
        'completed', 'partial', 'failed', 'cancelled', 'superseded'
    )),
    stage_number INTEGER CHECK(stage_number BETWEEN 1 AND 32),
    progress_completed INTEGER NOT NULL CHECK(
        progress_completed BETWEEN 0 AND 1000000
    ),
    progress_total INTEGER NOT NULL CHECK(progress_total BETWEEN 1 AND 1000000),
    attempt_count INTEGER NOT NULL CHECK(attempt_count BETWEEN 0 AND 5),
    max_attempts INTEGER NOT NULL CHECK(max_attempts BETWEEN 1 AND 5),
    available_at TEXT NOT NULL,
    cancel_requested INTEGER NOT NULL CHECK(cancel_requested IN (0, 1)),
    lease_owner TEXT CHECK(
        lease_owner IS NULL OR (
            length(lease_owner) = 64 AND lease_owner NOT GLOB '*[^0-9a-f]*'
        )
    ),
    lease_token TEXT CHECK(
        lease_token IS NULL OR (
            length(lease_token) = 64 AND lease_token NOT GLOB '*[^0-9a-f]*'
        )
    ),
    lease_expires_at TEXT,
    last_error_code TEXT CHECK(
        last_error_code IS NULL OR (
            length(last_error_code) BETWEEN 1 AND 128
            AND last_error_code GLOB '[A-Za-z0-9]*'
            AND last_error_code NOT GLOB '*[^A-Za-z0-9._+:/-]*'
        )
    ),
    terminal_reason_code TEXT CHECK(
        terminal_reason_code IS NULL OR (
            length(terminal_reason_code) BETWEEN 1 AND 128
            AND terminal_reason_code GLOB '[A-Za-z0-9]*'
            AND terminal_reason_code NOT GLOB '*[^A-Za-z0-9._+:/-]*'
        )
    ),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    terminal_at TEXT,
    CHECK(attempt_count <= max_attempts),
    CHECK(progress_completed <= progress_total),
    CHECK((state = 'stage_n') = (stage_number IS NOT NULL)),
    CHECK(
        (state IN ('preprocessing', 'stage_n')
            AND lease_owner IS NOT NULL
            AND lease_token IS NOT NULL
            AND lease_expires_at IS NOT NULL)
        OR
        (state NOT IN ('preprocessing', 'stage_n')
            AND lease_owner IS NULL
            AND lease_token IS NULL
            AND lease_expires_at IS NULL)
    ),
    CHECK(
        (state IN ('completed', 'partial', 'failed', 'cancelled', 'superseded')
            AND terminal_at IS NOT NULL AND terminal_reason_code IS NOT NULL)
        OR
        (state NOT IN ('completed', 'partial', 'failed', 'cancelled', 'superseded')
            AND terminal_at IS NULL AND terminal_reason_code IS NULL)
    )
);

CREATE INDEX analysis_jobs_claim_idx
    ON analysis_jobs(state, available_at, created_at, job_id);
CREATE INDEX analysis_jobs_session_idx
    ON analysis_jobs(session_id, created_at DESC, job_id DESC);
CREATE INDEX analysis_jobs_grant_idx
    ON analysis_jobs(automation_grant_id, state, created_at)
    WHERE automation_grant_id IS NOT NULL;
CREATE INDEX analysis_jobs_lease_idx
    ON analysis_jobs(state, lease_expires_at)
    WHERE state IN ('preprocessing', 'stage_n');

CREATE TABLE analysis_job_metrics (
    job_id TEXT NOT NULL REFERENCES analysis_jobs(job_id) ON DELETE CASCADE,
    metric_key TEXT NOT NULL CHECK(
        length(metric_key) BETWEEN 1 AND 128
        AND metric_key GLOB '[A-Za-z0-9]*'
        AND metric_key NOT GLOB '*[^A-Za-z0-9._+:/-]*'
    ),
    ordinal INTEGER NOT NULL CHECK(ordinal BETWEEN 0 AND 99),
    PRIMARY KEY(job_id, metric_key),
    UNIQUE(job_id, ordinal)
);

CREATE TRIGGER analysis_jobs_identity_immutable
BEFORE UPDATE ON analysis_jobs
WHEN NEW.job_id IS NOT OLD.job_id
    OR NEW.dedupe_key IS NOT OLD.dedupe_key
    OR NEW.kind IS NOT OLD.kind
    OR NEW.provider IS NOT OLD.provider
    OR NEW.project_id IS NOT OLD.project_id
    OR NEW.session_id IS NOT OLD.session_id
    OR NEW.input_fingerprint IS NOT OLD.input_fingerprint
    OR NEW.provenance_fingerprint IS NOT OLD.provenance_fingerprint
    OR NEW.estimator_plan_version IS NOT OLD.estimator_plan_version
    OR NEW.redactor_version IS NOT OLD.redactor_version
    OR NEW.provider_schema_version IS NOT OLD.provider_schema_version
    OR NEW.automation_grant_id IS NOT OLD.automation_grant_id
    OR NEW.local_only IS NOT OLD.local_only
    OR NEW.max_attempts IS NOT OLD.max_attempts
    OR NEW.created_at IS NOT OLD.created_at
BEGIN
    SELECT RAISE(ABORT, 'analysis job identity is immutable');
END;

CREATE TRIGGER analysis_jobs_closed_transitions
BEFORE UPDATE ON analysis_jobs
WHEN NEW.state <> OLD.state AND NOT (
    (OLD.state = 'queued' AND NEW.state IN (
        'preprocessing', 'cancelled', 'superseded'
    ))
    OR (OLD.state = 'preprocessing' AND NEW.state IN (
        'queued', 'stage_n', 'awaiting_approval', 'completed', 'partial',
        'failed', 'cancelled', 'superseded'
    ))
    OR (OLD.state = 'stage_n' AND NEW.state IN (
        'queued', 'awaiting_approval', 'completed', 'partial', 'failed',
        'cancelled', 'superseded'
    ))
    OR (OLD.state = 'awaiting_approval' AND NEW.state IN (
        'queued', 'failed', 'cancelled', 'superseded'
    ))
)
BEGIN
    SELECT RAISE(ABORT, 'analysis job state transition is invalid');
END;

CREATE TRIGGER analysis_jobs_terminal_immutable
BEFORE UPDATE ON analysis_jobs
WHEN OLD.state IN ('completed', 'partial', 'failed', 'cancelled', 'superseded')
BEGIN
    SELECT RAISE(ABORT, 'terminal analysis jobs are immutable');
END;

CREATE TRIGGER analysis_job_metrics_no_update
BEFORE UPDATE ON analysis_job_metrics
BEGIN
    SELECT RAISE(ABORT, 'analysis job metric selections are immutable');
END;

COMMIT;
"""


MIGRATION_12 = r"""
BEGIN IMMEDIATE;

CREATE TABLE automation_grants (
    grant_id TEXT PRIMARY KEY
        CHECK(length(grant_id) = 64 AND grant_id NOT GLOB '*[^0-9a-f]*'),
    revision INTEGER NOT NULL CHECK(revision >= 1),
    provider TEXT NOT NULL CHECK(provider IN ('codex', 'claude_code', 'synthetic')),
    project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    newest_session_limit INTEGER NOT NULL CHECK(newest_session_limit BETWEEN 1 AND 100),
    check_interval_seconds INTEGER NOT NULL CHECK(
        check_interval_seconds BETWEEN 60 AND 86400
    ),
    route TEXT NOT NULL CHECK(route IN ('fast', 'balanced', 'deep')),
    max_gpu_workers INTEGER NOT NULL CHECK(max_gpu_workers = 1),
    max_cpu_workers INTEGER NOT NULL CHECK(max_cpu_workers BETWEEN 1 AND 4),
    pause_on_battery INTEGER NOT NULL CHECK(pause_on_battery IN (0, 1)),
    maximum_session_seconds INTEGER NOT NULL CHECK(
        maximum_session_seconds BETWEEN 60 AND 14400
    ),
    local_only INTEGER NOT NULL CHECK(local_only = 1),
    remote_requires_fresh_approval INTEGER NOT NULL
        CHECK(remote_requires_fresh_approval = 1),
    state TEXT NOT NULL CHECK(state IN ('active', 'revoked', 'expired')),
    created_at TEXT NOT NULL,
    renewed_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    next_check_at TEXT NOT NULL,
    last_checked_at TEXT,
    revoked_at TEXT,
    last_error_code TEXT CHECK(
        last_error_code IS NULL OR (
            length(last_error_code) BETWEEN 1 AND 128
            AND last_error_code GLOB '[A-Za-z0-9]*'
            AND last_error_code NOT GLOB '*[^A-Za-z0-9._+:/-]*'
        )
    ),
    CHECK((state = 'revoked') = (revoked_at IS NOT NULL))
);

CREATE INDEX automation_grants_due_idx
    ON automation_grants(state, next_check_at, expires_at, grant_id);
CREATE INDEX automation_grants_provider_idx
    ON automation_grants(provider, state, created_at, grant_id);
CREATE UNIQUE INDEX automation_grants_one_active_project_idx
    ON automation_grants(provider, project_id)
    WHERE state = 'active';

CREATE TABLE automation_grant_metrics (
    grant_id TEXT NOT NULL
        REFERENCES automation_grants(grant_id) ON DELETE CASCADE,
    metric_key TEXT NOT NULL CHECK(
        length(metric_key) BETWEEN 1 AND 128
        AND metric_key GLOB '[A-Za-z0-9]*'
        AND metric_key NOT GLOB '*[^A-Za-z0-9._+:/-]*'
    ),
    ordinal INTEGER NOT NULL CHECK(ordinal BETWEEN 0 AND 99),
    PRIMARY KEY(grant_id, metric_key),
    UNIQUE(grant_id, ordinal)
);

CREATE TRIGGER automation_grants_scope_immutable
BEFORE UPDATE ON automation_grants
WHEN NEW.grant_id IS NOT OLD.grant_id
    OR NEW.provider IS NOT OLD.provider
    OR NEW.project_id IS NOT OLD.project_id
    OR NEW.newest_session_limit IS NOT OLD.newest_session_limit
    OR NEW.check_interval_seconds IS NOT OLD.check_interval_seconds
    OR NEW.route IS NOT OLD.route
    OR NEW.max_gpu_workers IS NOT OLD.max_gpu_workers
    OR NEW.max_cpu_workers IS NOT OLD.max_cpu_workers
    OR NEW.pause_on_battery IS NOT OLD.pause_on_battery
    OR NEW.maximum_session_seconds IS NOT OLD.maximum_session_seconds
    OR NEW.local_only IS NOT OLD.local_only
    OR NEW.remote_requires_fresh_approval IS NOT OLD.remote_requires_fresh_approval
    OR NEW.created_at IS NOT OLD.created_at
BEGIN
    SELECT RAISE(ABORT, 'automation grant scope is immutable');
END;

CREATE TRIGGER automation_grants_closed_transitions
BEFORE UPDATE ON automation_grants
WHEN NEW.state <> OLD.state AND NOT (
    (OLD.state = 'active' AND NEW.state IN ('revoked', 'expired'))
    OR (OLD.state IN ('revoked', 'expired') AND NEW.state = 'active')
)
BEGIN
    SELECT RAISE(ABORT, 'automation grant state transition is invalid');
END;

CREATE TRIGGER automation_grant_metrics_no_update
BEFORE UPDATE ON automation_grant_metrics
BEGIN
    SELECT RAISE(ABORT, 'automation grant metrics are immutable');
END;

COMMIT;
"""
