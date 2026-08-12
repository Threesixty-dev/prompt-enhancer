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


MIGRATION_13 = r"""
BEGIN IMMEDIATE;

ALTER TABLE session_analysis_runs
ADD COLUMN metric_scope_state TEXT NOT NULL DEFAULT 'legacy_unknown'
    CHECK(metric_scope_state IN ('exact', 'legacy_unknown'));

-- The previous terminal-row immutability trigger predates scope provenance and
-- must be replaced before this one-time, content-free backfill updates it.
DROP TRIGGER session_analysis_runs_terminal_transition_only;

CREATE TABLE session_analysis_run_metrics (
    run_id TEXT NOT NULL
        REFERENCES session_analysis_runs(run_id) ON DELETE CASCADE,
    metric_key TEXT NOT NULL CHECK(
        length(metric_key) BETWEEN 1 AND 128
        AND metric_key GLOB '[A-Za-z0-9]*'
        AND metric_key NOT GLOB '*[^A-Za-z0-9._+:/-]*'
    ),
    ordinal INTEGER NOT NULL CHECK(ordinal BETWEEN 0 AND 99),
    PRIMARY KEY(run_id, metric_key),
    UNIQUE(run_id, ordinal)
);

-- Completed runs expose their requested key set through persisted results.
-- Scope is intentionally key-level, so multiple historical versions of one
-- metric collapse to one selected key rather than conflicting in the child PK.
WITH completed_metric_keys(run_id, metric_key) AS (
    SELECT run.run_id, result.key
    FROM session_analysis_runs AS run
    JOIN session_analysis_results AS result ON result.run_id = run.run_id
    WHERE run.status = 'completed'
      AND (
          (run.analysis_profile_key = 'standard_engineering'
           AND run.analysis_profile_version = 1
           AND run.metric_pack_key = 'core.redacted-text.prompt-logic'
           AND run.metric_pack_version = 1)
          OR
          (run.analysis_profile_key = 'explicit.user-profile'
           AND run.analysis_profile_version = 1
           AND run.metric_pack_key = 'core.redacted-text.prompt-logic'
           AND run.metric_pack_version = 1)
          OR
          (run.analysis_profile_key = 'coaching_profile'
           AND run.analysis_profile_version = 1
           AND run.metric_pack_key = 'experimental.redacted-text.coaching'
           AND run.metric_pack_version = 3)
      )
    GROUP BY run.run_id, result.key
)
INSERT INTO session_analysis_run_metrics(run_id, metric_key, ordinal)
SELECT completed.run_id, completed.metric_key,
       ROW_NUMBER() OVER (
           PARTITION BY completed.run_id ORDER BY completed.metric_key
       ) - 1
FROM completed_metric_keys AS completed;

UPDATE session_analysis_runs
SET metric_scope_state = 'exact'
WHERE status = 'completed'
  AND EXISTS (
      SELECT 1 FROM session_analysis_run_metrics AS selected
      WHERE selected.run_id = session_analysis_runs.run_id
  );

-- A terminal result set is unavailable for historical running/failed rows.
-- Only runs written before schema v12 introduced subset execution can be
-- recovered as the full reviewed pack. Schema-v12 rows may be either full or
-- subset runs and therefore remain explicitly unknown rather than guessed.
WITH recognized_metrics(
    analysis_profile_key,
    analysis_profile_version,
    metric_pack_key,
    metric_pack_version,
    metric_key
) AS (
    VALUES
    ('standard_engineering', 1, 'core.redacted-text.prompt-logic', 1, 'logic.conversation_loop_closure'),
    ('standard_engineering', 1, 'core.redacted-text.prompt-logic', 1, 'logic.decision_rationale_coverage'),
    ('standard_engineering', 1, 'core.redacted-text.prompt-logic', 1, 'logic.plan_state_accounting'),
    ('standard_engineering', 1, 'core.redacted-text.prompt-logic', 1, 'logic.requirement_action_traceability'),
    ('standard_engineering', 1, 'core.redacted-text.prompt-logic', 1, 'logic.scoped_consistency_candidate_rate'),
    ('standard_engineering', 1, 'core.redacted-text.prompt-logic', 1, 'prompt.completion_evaluability'),
    ('standard_engineering', 1, 'core.redacted-text.prompt-logic', 1, 'prompt.constraint_resolution'),
    ('standard_engineering', 1, 'core.redacted-text.prompt-logic', 1, 'prompt.deliverable_contract'),
    ('standard_engineering', 1, 'core.redacted-text.prompt-logic', 1, 'prompt.goal_definition'),
    ('standard_engineering', 1, 'core.redacted-text.prompt-logic', 1, 'prompt.open_decision_load'),
    ('explicit.user-profile', 1, 'core.redacted-text.prompt-logic', 1, 'logic.conversation_loop_closure'),
    ('explicit.user-profile', 1, 'core.redacted-text.prompt-logic', 1, 'logic.decision_rationale_coverage'),
    ('explicit.user-profile', 1, 'core.redacted-text.prompt-logic', 1, 'logic.plan_state_accounting'),
    ('explicit.user-profile', 1, 'core.redacted-text.prompt-logic', 1, 'logic.requirement_action_traceability'),
    ('explicit.user-profile', 1, 'core.redacted-text.prompt-logic', 1, 'logic.scoped_consistency_candidate_rate'),
    ('explicit.user-profile', 1, 'core.redacted-text.prompt-logic', 1, 'prompt.completion_evaluability'),
    ('explicit.user-profile', 1, 'core.redacted-text.prompt-logic', 1, 'prompt.constraint_resolution'),
    ('explicit.user-profile', 1, 'core.redacted-text.prompt-logic', 1, 'prompt.deliverable_contract'),
    ('explicit.user-profile', 1, 'core.redacted-text.prompt-logic', 1, 'prompt.goal_definition'),
    ('explicit.user-profile', 1, 'core.redacted-text.prompt-logic', 1, 'prompt.open_decision_load'),
    ('coaching_profile', 1, 'experimental.redacted-text.coaching', 3, 'collaboration.ambiguity_resolution'),
    ('coaching_profile', 1, 'experimental.redacted-text.coaching', 3, 'collaboration.clarification_yield'),
    ('coaching_profile', 1, 'experimental.redacted-text.coaching', 3, 'collaboration.exploration_conversion'),
    ('coaching_profile', 1, 'experimental.redacted-text.coaching', 3, 'collaboration.rework_candidate_rate'),
    ('coaching_profile', 1, 'experimental.redacted-text.coaching', 3, 'collaboration.scope_change_discipline'),
    ('coaching_profile', 1, 'experimental.redacted-text.coaching', 3, 'logic.decision_rationale_coverage'),
    ('coaching_profile', 1, 'experimental.redacted-text.coaching', 3, 'logic.decomposition_coverage'),
    ('coaching_profile', 1, 'experimental.redacted-text.coaching', 3, 'logic.hypothesis_test_linkage'),
    ('coaching_profile', 1, 'experimental.redacted-text.coaching', 3, 'logic.open_loop_closure'),
    ('coaching_profile', 1, 'experimental.redacted-text.coaching', 3, 'logic.requirement_action_traceability'),
    ('coaching_profile', 1, 'experimental.redacted-text.coaching', 3, 'outcome.agent_claim_grounding'),
    ('coaching_profile', 1, 'experimental.redacted-text.coaching', 3, 'outcome.first_pass_verification'),
    ('coaching_profile', 1, 'experimental.redacted-text.coaching', 3, 'outcome.verification_strategy_adequacy'),
    ('coaching_profile', 1, 'experimental.redacted-text.coaching', 3, 'outcome.verified_requirement_coverage'),
    ('coaching_profile', 1, 'experimental.redacted-text.coaching', 3, 'prompt.acceptance_testability'),
    ('coaching_profile', 1, 'experimental.redacted-text.coaching', 3, 'prompt.constraint_precision'),
    ('coaching_profile', 1, 'experimental.redacted-text.coaching', 3, 'prompt.context_sufficiency'),
    ('coaching_profile', 1, 'experimental.redacted-text.coaching', 3, 'prompt.deliverable_contract'),
    ('coaching_profile', 1, 'experimental.redacted-text.coaching', 3, 'prompt.problem_evidence_quality'),
    ('coaching_profile', 1, 'experimental.redacted-text.coaching', 3, 'prompt.task_definition_coverage')
)
INSERT INTO session_analysis_run_metrics(run_id, metric_key, ordinal)
SELECT run.run_id, recognized.metric_key,
       ROW_NUMBER() OVER (
           PARTITION BY run.run_id ORDER BY recognized.metric_key
       ) - 1
FROM session_analysis_runs AS run
JOIN recognized_metrics AS recognized
  ON recognized.analysis_profile_key = run.analysis_profile_key
 AND recognized.analysis_profile_version = run.analysis_profile_version
 AND recognized.metric_pack_key = run.metric_pack_key
 AND recognized.metric_pack_version = run.metric_pack_version
WHERE run.status <> 'completed'
  AND run.schema_version <= 11;

UPDATE session_analysis_runs
SET metric_scope_state = 'exact'
WHERE status <> 'completed'
  AND EXISTS (
      SELECT 1 FROM session_analysis_run_metrics AS selected
      WHERE selected.run_id = session_analysis_runs.run_id
  );

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
    OR NEW.metric_scope_state IS NOT OLD.metric_scope_state
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
    OR (NEW.status = 'completed' AND (
        OLD.metric_scope_state <> 'exact'
        OR NOT EXISTS (
            SELECT 1 FROM session_analysis_results WHERE run_id = OLD.run_id
        )
        OR EXISTS (
            SELECT 1 FROM session_analysis_results AS result
            WHERE result.run_id = OLD.run_id
              AND NOT EXISTS (
                  SELECT 1 FROM session_analysis_run_metrics AS selected
                  WHERE selected.run_id = OLD.run_id
                    AND selected.metric_key = result.key
              )
        )
        OR EXISTS (
            SELECT 1 FROM session_analysis_run_metrics AS selected
            WHERE selected.run_id = OLD.run_id
              AND NOT EXISTS (
                  SELECT 1 FROM session_analysis_results AS result
                  WHERE result.run_id = OLD.run_id
                    AND result.key = selected.metric_key
              )
        )
    ))
    OR (NEW.status = 'failed' AND EXISTS (
        SELECT 1 FROM session_analysis_results WHERE run_id = OLD.run_id
    ))
BEGIN
    SELECT RAISE(ABORT, 'session analysis run transition is invalid');
END;

CREATE TRIGGER session_analysis_run_metrics_running_insert_only
BEFORE INSERT ON session_analysis_run_metrics
WHEN COALESCE(
    (SELECT status FROM session_analysis_runs WHERE run_id = NEW.run_id), ''
) <> 'running'
OR COALESCE(
    (SELECT metric_scope_state FROM session_analysis_runs WHERE run_id = NEW.run_id), ''
) <> 'exact'
BEGIN
    SELECT RAISE(ABORT, 'session analysis metric scope requires an exact running run');
END;

CREATE TRIGGER session_analysis_run_metrics_no_update
BEFORE UPDATE ON session_analysis_run_metrics
BEGIN
    SELECT RAISE(ABORT, 'session analysis metric scope is immutable');
END;

CREATE TRIGGER session_analysis_run_metrics_privacy_delete_only
BEFORE DELETE ON session_analysis_run_metrics
WHEN EXISTS (
    SELECT 1 FROM session_analysis_runs WHERE run_id = OLD.run_id
)
BEGIN
    SELECT RAISE(ABORT, 'session analysis metric scope requires parent privacy deletion');
END;

COMMIT;
"""


MIGRATION_14 = r"""
BEGIN IMMEDIATE;

-- Migration 13 recovered completed legacy scopes from result keys. Repair only
-- the classifications that cannot prove the historical request boundary:
-- pre-v12 partial packs and v12 rows containing keys outside the recognized
-- pack. Legitimate v12 subsets and complete pre-v12 packs remain exact.
DROP TRIGGER session_analysis_runs_terminal_transition_only;
DROP TRIGGER session_analysis_run_metrics_privacy_delete_only;

CREATE TEMP TABLE migration14_recognized_metrics (
    analysis_profile_key TEXT NOT NULL,
    analysis_profile_version INTEGER NOT NULL,
    metric_pack_key TEXT NOT NULL,
    metric_pack_version INTEGER NOT NULL,
    metric_key TEXT NOT NULL,
    PRIMARY KEY(
        analysis_profile_key,
        analysis_profile_version,
        metric_pack_key,
        metric_pack_version,
        metric_key
    )
) WITHOUT ROWID;

INSERT INTO migration14_recognized_metrics(
    analysis_profile_key,
    analysis_profile_version,
    metric_pack_key,
    metric_pack_version,
    metric_key
) VALUES
('standard_engineering', 1, 'core.redacted-text.prompt-logic', 1, 'logic.conversation_loop_closure'),
('standard_engineering', 1, 'core.redacted-text.prompt-logic', 1, 'logic.decision_rationale_coverage'),
('standard_engineering', 1, 'core.redacted-text.prompt-logic', 1, 'logic.plan_state_accounting'),
('standard_engineering', 1, 'core.redacted-text.prompt-logic', 1, 'logic.requirement_action_traceability'),
('standard_engineering', 1, 'core.redacted-text.prompt-logic', 1, 'logic.scoped_consistency_candidate_rate'),
('standard_engineering', 1, 'core.redacted-text.prompt-logic', 1, 'prompt.completion_evaluability'),
('standard_engineering', 1, 'core.redacted-text.prompt-logic', 1, 'prompt.constraint_resolution'),
('standard_engineering', 1, 'core.redacted-text.prompt-logic', 1, 'prompt.deliverable_contract'),
('standard_engineering', 1, 'core.redacted-text.prompt-logic', 1, 'prompt.goal_definition'),
('standard_engineering', 1, 'core.redacted-text.prompt-logic', 1, 'prompt.open_decision_load'),
('explicit.user-profile', 1, 'core.redacted-text.prompt-logic', 1, 'logic.conversation_loop_closure'),
('explicit.user-profile', 1, 'core.redacted-text.prompt-logic', 1, 'logic.decision_rationale_coverage'),
('explicit.user-profile', 1, 'core.redacted-text.prompt-logic', 1, 'logic.plan_state_accounting'),
('explicit.user-profile', 1, 'core.redacted-text.prompt-logic', 1, 'logic.requirement_action_traceability'),
('explicit.user-profile', 1, 'core.redacted-text.prompt-logic', 1, 'logic.scoped_consistency_candidate_rate'),
('explicit.user-profile', 1, 'core.redacted-text.prompt-logic', 1, 'prompt.completion_evaluability'),
('explicit.user-profile', 1, 'core.redacted-text.prompt-logic', 1, 'prompt.constraint_resolution'),
('explicit.user-profile', 1, 'core.redacted-text.prompt-logic', 1, 'prompt.deliverable_contract'),
('explicit.user-profile', 1, 'core.redacted-text.prompt-logic', 1, 'prompt.goal_definition'),
('explicit.user-profile', 1, 'core.redacted-text.prompt-logic', 1, 'prompt.open_decision_load'),
('coaching_profile', 1, 'experimental.redacted-text.coaching', 3, 'collaboration.ambiguity_resolution'),
('coaching_profile', 1, 'experimental.redacted-text.coaching', 3, 'collaboration.clarification_yield'),
('coaching_profile', 1, 'experimental.redacted-text.coaching', 3, 'collaboration.exploration_conversion'),
('coaching_profile', 1, 'experimental.redacted-text.coaching', 3, 'collaboration.rework_candidate_rate'),
('coaching_profile', 1, 'experimental.redacted-text.coaching', 3, 'collaboration.scope_change_discipline'),
('coaching_profile', 1, 'experimental.redacted-text.coaching', 3, 'logic.decision_rationale_coverage'),
('coaching_profile', 1, 'experimental.redacted-text.coaching', 3, 'logic.decomposition_coverage'),
('coaching_profile', 1, 'experimental.redacted-text.coaching', 3, 'logic.hypothesis_test_linkage'),
('coaching_profile', 1, 'experimental.redacted-text.coaching', 3, 'logic.open_loop_closure'),
('coaching_profile', 1, 'experimental.redacted-text.coaching', 3, 'logic.requirement_action_traceability'),
('coaching_profile', 1, 'experimental.redacted-text.coaching', 3, 'outcome.agent_claim_grounding'),
('coaching_profile', 1, 'experimental.redacted-text.coaching', 3, 'outcome.first_pass_verification'),
('coaching_profile', 1, 'experimental.redacted-text.coaching', 3, 'outcome.verification_strategy_adequacy'),
('coaching_profile', 1, 'experimental.redacted-text.coaching', 3, 'outcome.verified_requirement_coverage'),
('coaching_profile', 1, 'experimental.redacted-text.coaching', 3, 'prompt.acceptance_testability'),
('coaching_profile', 1, 'experimental.redacted-text.coaching', 3, 'prompt.constraint_precision'),
('coaching_profile', 1, 'experimental.redacted-text.coaching', 3, 'prompt.context_sufficiency'),
('coaching_profile', 1, 'experimental.redacted-text.coaching', 3, 'prompt.deliverable_contract'),
('coaching_profile', 1, 'experimental.redacted-text.coaching', 3, 'prompt.problem_evidence_quality'),
('coaching_profile', 1, 'experimental.redacted-text.coaching', 3, 'prompt.task_definition_coverage');

CREATE TEMP TABLE migration14_untrusted_scope_runs (
    run_id TEXT PRIMARY KEY
) WITHOUT ROWID;

INSERT INTO migration14_untrusted_scope_runs(run_id)
SELECT run.run_id
FROM session_analysis_runs AS run
WHERE run.status = 'completed'
  AND run.metric_scope_state = 'exact'
  AND run.schema_version <= 12
  AND (
      NOT EXISTS (
          SELECT 1
          FROM migration14_recognized_metrics AS recognized
          WHERE recognized.analysis_profile_key = run.analysis_profile_key
            AND recognized.analysis_profile_version = run.analysis_profile_version
            AND recognized.metric_pack_key = run.metric_pack_key
            AND recognized.metric_pack_version = run.metric_pack_version
      )
      OR NOT EXISTS (
          SELECT 1
          FROM session_analysis_run_metrics AS selected
          WHERE selected.run_id = run.run_id
      )
      OR EXISTS (
          SELECT 1
          FROM session_analysis_run_metrics AS selected
          WHERE selected.run_id = run.run_id
            AND NOT EXISTS (
                SELECT 1
                FROM migration14_recognized_metrics AS recognized
                WHERE recognized.analysis_profile_key = run.analysis_profile_key
                  AND recognized.analysis_profile_version = run.analysis_profile_version
                  AND recognized.metric_pack_key = run.metric_pack_key
                  AND recognized.metric_pack_version = run.metric_pack_version
                  AND recognized.metric_key = selected.metric_key
            )
      )
      OR EXISTS (
          SELECT 1
          FROM session_analysis_results AS result
          WHERE result.run_id = run.run_id
            AND NOT EXISTS (
                SELECT 1
                FROM migration14_recognized_metrics AS recognized
                WHERE recognized.analysis_profile_key = run.analysis_profile_key
                  AND recognized.analysis_profile_version = run.analysis_profile_version
                  AND recognized.metric_pack_key = run.metric_pack_key
                  AND recognized.metric_pack_version = run.metric_pack_version
                  AND recognized.metric_key = result.key
            )
      )
      OR EXISTS (
          SELECT 1
          FROM session_analysis_results AS result
          WHERE result.run_id = run.run_id
            AND NOT EXISTS (
                SELECT 1
                FROM session_analysis_run_metrics AS selected
                WHERE selected.run_id = run.run_id
                  AND selected.metric_key = result.key
            )
      )
      OR EXISTS (
          SELECT 1
          FROM session_analysis_run_metrics AS selected
          WHERE selected.run_id = run.run_id
            AND NOT EXISTS (
                SELECT 1
                FROM session_analysis_results AS result
                WHERE result.run_id = run.run_id
                  AND result.key = selected.metric_key
            )
      )
      OR (
          run.schema_version <= 11
          AND EXISTS (
              SELECT 1
              FROM migration14_recognized_metrics AS recognized
              WHERE recognized.analysis_profile_key = run.analysis_profile_key
                AND recognized.analysis_profile_version = run.analysis_profile_version
                AND recognized.metric_pack_key = run.metric_pack_key
                AND recognized.metric_pack_version = run.metric_pack_version
                AND NOT EXISTS (
                    SELECT 1
                    FROM session_analysis_run_metrics AS selected
                    WHERE selected.run_id = run.run_id
                      AND selected.metric_key = recognized.metric_key
                )
          )
      )
  );

DELETE FROM session_analysis_run_metrics
WHERE run_id IN (SELECT run_id FROM migration14_untrusted_scope_runs);

UPDATE session_analysis_runs
SET metric_scope_state = 'legacy_unknown'
WHERE run_id IN (SELECT run_id FROM migration14_untrusted_scope_runs);

DROP TABLE migration14_untrusted_scope_runs;
DROP TABLE migration14_recognized_metrics;

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
    OR NEW.metric_scope_state IS NOT OLD.metric_scope_state
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
    OR (NEW.status = 'completed' AND (
        OLD.metric_scope_state <> 'exact'
        OR NOT EXISTS (
            SELECT 1 FROM session_analysis_results WHERE run_id = OLD.run_id
        )
        OR EXISTS (
            SELECT 1 FROM session_analysis_results AS result
            WHERE result.run_id = OLD.run_id
              AND NOT EXISTS (
                  SELECT 1 FROM session_analysis_run_metrics AS selected
                  WHERE selected.run_id = OLD.run_id
                    AND selected.metric_key = result.key
              )
        )
        OR EXISTS (
            SELECT 1 FROM session_analysis_run_metrics AS selected
            WHERE selected.run_id = OLD.run_id
              AND NOT EXISTS (
                  SELECT 1 FROM session_analysis_results AS result
                  WHERE result.run_id = OLD.run_id
                    AND result.key = selected.metric_key
              )
        )
    ))
    OR (NEW.status = 'failed' AND EXISTS (
        SELECT 1 FROM session_analysis_results WHERE run_id = OLD.run_id
    ))
BEGIN
    SELECT RAISE(ABORT, 'session analysis run transition is invalid');
END;

CREATE TRIGGER session_analysis_run_metrics_privacy_delete_only
BEFORE DELETE ON session_analysis_run_metrics
WHEN EXISTS (
    SELECT 1 FROM session_analysis_runs WHERE run_id = OLD.run_id
)
BEGIN
    SELECT RAISE(ABORT, 'session analysis metric scope requires parent privacy deletion');
END;

COMMIT;
"""


MIGRATION_15 = r"""
BEGIN IMMEDIATE;

-- P1 estimator persistence stores provenance and structured scalar judgments
-- only.  There are deliberately no JSON, BLOB, prompt, excerpt, response,
-- rationale, commentary, or evidence-body columns in this schema.
CREATE TABLE estimator_model_artifacts (
    artifact_fingerprint TEXT PRIMARY KEY
        CHECK(length(artifact_fingerprint) = 64
              AND artifact_fingerprint NOT GLOB '*[^0-9a-f]*'),
    contract_version TEXT NOT NULL CHECK(
        length(contract_version) BETWEEN 1 AND 128
        AND contract_version GLOB '[A-Za-z0-9]*'
        AND contract_version NOT GLOB '*[^A-Za-z0-9._+:/-]*'),
    source TEXT NOT NULL CHECK(source IN (
        'local_weights', 'openai_api', 'anthropic_api', 'codex_cli',
        'claude_cli', 'synthetic')),
    requested_model_id TEXT NOT NULL CHECK(
        length(requested_model_id) BETWEEN 1 AND 128
        AND requested_model_id GLOB '[A-Za-z0-9]*'
        AND requested_model_id NOT GLOB '*[^A-Za-z0-9._+:/-]*'),
    served_model_id TEXT NOT NULL CHECK(
        length(served_model_id) BETWEEN 1 AND 128
        AND served_model_id GLOB '[A-Za-z0-9]*'
        AND served_model_id NOT GLOB '*[^A-Za-z0-9._+:/-]*'),
    requested_revision TEXT NOT NULL CHECK(
        length(requested_revision) BETWEEN 1 AND 128
        AND requested_revision GLOB '[A-Za-z0-9]*'
        AND requested_revision NOT GLOB '*[^A-Za-z0-9._+:/-]*'),
    served_revision TEXT NOT NULL CHECK(
        length(served_revision) BETWEEN 1 AND 128
        AND served_revision GLOB '[A-Za-z0-9]*'
        AND served_revision NOT GLOB '*[^A-Za-z0-9._+:/-]*'),
    requested_execution_mode TEXT NOT NULL
        CHECK(requested_execution_mode IN ('standard', 'pro')),
    served_execution_mode TEXT NOT NULL
        CHECK(served_execution_mode IN ('standard', 'pro')),
    weight_availability TEXT NOT NULL CHECK(weight_availability IN (
        'pinned_hashes', 'provider_managed', 'synthetic_no_weights')),
    weight_file_count INTEGER NOT NULL CHECK(weight_file_count BETWEEN 0 AND 256),
    tokenizer_id TEXT NOT NULL CHECK(
        length(tokenizer_id) BETWEEN 1 AND 128
        AND tokenizer_id GLOB '[A-Za-z0-9]*'
        AND tokenizer_id NOT GLOB '*[^A-Za-z0-9._+:/-]*'),
    tokenizer_revision TEXT NOT NULL CHECK(
        length(tokenizer_revision) BETWEEN 1 AND 128
        AND tokenizer_revision GLOB '[A-Za-z0-9]*'
        AND tokenizer_revision NOT GLOB '*[^A-Za-z0-9._+:/-]*'),
    tokenizer_availability TEXT NOT NULL CHECK(tokenizer_availability IN (
        'pinned_hashes', 'provider_managed', 'synthetic_no_weights')),
    tokenizer_file_count INTEGER NOT NULL CHECK(tokenizer_file_count BETWEEN 0 AND 64),
    license_id TEXT NOT NULL CHECK(
        length(license_id) BETWEEN 1 AND 128
        AND license_id GLOB '[A-Za-z0-9]*'
        AND license_id NOT GLOB '*[^A-Za-z0-9._+:/-]*'),
    trust_remote_code INTEGER NOT NULL CHECK(trust_remote_code = 0)
);

CREATE TABLE estimator_model_weight_files (
    artifact_fingerprint TEXT NOT NULL
        REFERENCES estimator_model_artifacts(artifact_fingerprint)
        ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED,
    ordinal INTEGER NOT NULL CHECK(ordinal BETWEEN 0 AND 255),
    file_name TEXT NOT NULL CHECK(
        length(file_name) BETWEEN 1 AND 128
        AND file_name GLOB '[A-Za-z0-9]*'
        AND file_name NOT GLOB '*[^A-Za-z0-9._+-]*'),
    sha256 TEXT NOT NULL CHECK(length(sha256) = 64 AND sha256 NOT GLOB '*[^0-9a-f]*'),
    PRIMARY KEY(artifact_fingerprint, ordinal),
    UNIQUE(artifact_fingerprint, file_name)
);

CREATE TABLE estimator_model_tokenizer_files (
    artifact_fingerprint TEXT NOT NULL
        REFERENCES estimator_model_artifacts(artifact_fingerprint)
        ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED,
    ordinal INTEGER NOT NULL CHECK(ordinal BETWEEN 0 AND 63),
    file_name TEXT NOT NULL CHECK(
        length(file_name) BETWEEN 1 AND 128
        AND file_name GLOB '[A-Za-z0-9]*'
        AND file_name NOT GLOB '*[^A-Za-z0-9._+-]*'),
    sha256 TEXT NOT NULL CHECK(length(sha256) = 64 AND sha256 NOT GLOB '*[^0-9a-f]*'),
    PRIMARY KEY(artifact_fingerprint, ordinal),
    UNIQUE(artifact_fingerprint, file_name)
);

CREATE TRIGGER estimator_model_artifacts_validate_children
BEFORE INSERT ON estimator_model_artifacts
WHEN NEW.contract_version GLOB '[A-Za-z]:/*'
    OR NEW.license_id GLOB '[A-Za-z]:/*'
    OR NEW.requested_model_id GLOB '[A-Za-z]:/*'
    OR NEW.served_model_id GLOB '[A-Za-z]:/*'
    OR NEW.tokenizer_id GLOB '[A-Za-z]:/*'
    OR NEW.requested_revision GLOB '[A-Za-z]:/*'
    OR NEW.served_revision GLOB '[A-Za-z]:/*'
    OR NEW.tokenizer_revision GLOB '[A-Za-z]:/*'
    OR NEW.contract_version GLOB '/*' OR NEW.license_id GLOB '/*'
    OR NEW.requested_model_id GLOB '/*' OR NEW.served_model_id GLOB '/*'
    OR NEW.tokenizer_id GLOB '/*' OR NEW.requested_revision GLOB '/*'
    OR NEW.served_revision GLOB '/*' OR NEW.tokenizer_revision GLOB '/*'
    OR instr(NEW.requested_model_id, '://') > 0
    OR instr(NEW.served_model_id, '://') > 0
    OR instr(NEW.tokenizer_id, '://') > 0
    OR instr(NEW.requested_revision, '://') > 0
    OR instr(NEW.served_revision, '://') > 0
    OR instr(NEW.tokenizer_revision, '://') > 0
    OR instr(NEW.contract_version, '://') > 0
    OR instr(NEW.license_id, '://') > 0
    OR instr('/' || NEW.requested_model_id || '/', '/../') > 0
    OR instr('/' || NEW.served_model_id || '/', '/../') > 0
    OR instr('/' || NEW.tokenizer_id || '/', '/../') > 0
    OR instr('/' || NEW.requested_revision || '/', '/../') > 0
    OR instr('/' || NEW.served_revision || '/', '/../') > 0
    OR instr('/' || NEW.tokenizer_revision || '/', '/../') > 0
    OR instr('/' || NEW.contract_version || '/', '/../') > 0
    OR instr('/' || NEW.license_id || '/', '/../') > 0
    OR NEW.weight_file_count <> (
        SELECT COUNT(*) FROM estimator_model_weight_files
        WHERE artifact_fingerprint = NEW.artifact_fingerprint
    )
    OR NEW.tokenizer_file_count <> (
        SELECT COUNT(*) FROM estimator_model_tokenizer_files
        WHERE artifact_fingerprint = NEW.artifact_fingerprint
    )
    OR (NEW.source = 'local_weights' AND (
        NEW.weight_availability <> 'pinned_hashes'
        OR NEW.tokenizer_availability <> 'pinned_hashes'
        OR NEW.weight_file_count = 0 OR NEW.tokenizer_file_count = 0))
    OR (NEW.source = 'synthetic' AND (
        NEW.weight_availability <> 'synthetic_no_weights'
        OR NEW.tokenizer_availability <> 'synthetic_no_weights'
        OR NEW.weight_file_count <> 0 OR NEW.tokenizer_file_count <> 0))
    OR (NEW.source NOT IN ('local_weights', 'synthetic') AND (
        NEW.weight_availability <> 'provider_managed'
        OR NEW.tokenizer_availability <> 'provider_managed'
        OR NEW.weight_file_count <> 0 OR NEW.tokenizer_file_count <> 0))
BEGIN
    SELECT RAISE(ABORT, 'estimator artifact children are inconsistent');
END;

CREATE TABLE estimator_metric_questions (
    question_fingerprint TEXT PRIMARY KEY
        CHECK(length(question_fingerprint) = 64
              AND question_fingerprint NOT GLOB '*[^0-9a-f]*'),
    contract_version TEXT NOT NULL CHECK(length(contract_version) BETWEEN 1 AND 128),
    metric_key TEXT NOT NULL CHECK(
        length(metric_key) BETWEEN 1 AND 128
        AND metric_key GLOB '[a-z]*'
        AND metric_key NOT GLOB '*[^a-z0-9_.:-]*'),
    metric_definition_version TEXT NOT NULL CHECK(length(metric_definition_version) BETWEEN 1 AND 128),
    question_id TEXT NOT NULL CHECK(
        length(question_id) BETWEEN 1 AND 128
        AND question_id GLOB '[a-z]*'
        AND question_id NOT GLOB '*[^a-z0-9_.:-]*'),
    question_version TEXT NOT NULL CHECK(length(question_version) BETWEEN 1 AND 128),
    question_sha256 TEXT NOT NULL CHECK(length(question_sha256) = 64 AND question_sha256 NOT GLOB '*[^0-9a-f]*'),
    prompt_template_id TEXT NOT NULL CHECK(
        length(prompt_template_id) BETWEEN 1 AND 128
        AND prompt_template_id GLOB '[a-z]*'
        AND prompt_template_id NOT GLOB '*[^a-z0-9_.:-]*'),
    prompt_template_version TEXT NOT NULL CHECK(length(prompt_template_version) BETWEEN 1 AND 128),
    prompt_template_sha256 TEXT NOT NULL CHECK(length(prompt_template_sha256) = 64 AND prompt_template_sha256 NOT GLOB '*[^0-9a-f]*'),
    rubric_id TEXT NOT NULL CHECK(
        length(rubric_id) BETWEEN 1 AND 128
        AND rubric_id GLOB '[a-z]*'
        AND rubric_id NOT GLOB '*[^a-z0-9_.:-]*'),
    rubric_version TEXT NOT NULL CHECK(length(rubric_version) BETWEEN 1 AND 128),
    rubric_sha256 TEXT NOT NULL CHECK(length(rubric_sha256) = 64 AND rubric_sha256 NOT GLOB '*[^0-9a-f]*'),
    output_schema_version TEXT NOT NULL CHECK(length(output_schema_version) BETWEEN 1 AND 128),
    value_kind TEXT NOT NULL CHECK(value_kind IN ('continuous', 'fraction', 'binary', 'categorical')),
    unit_code TEXT NOT NULL CHECK(
        length(unit_code) BETWEEN 1 AND 128
        AND unit_code GLOB '[a-z]*'
        AND unit_code NOT GLOB '*[^a-z0-9_.:-]*'),
    direction TEXT NOT NULL CHECK(direction IN ('higher_is_better', 'lower_is_better', 'descriptive')),
    lower_bound REAL,
    upper_bound REAL,
    CHECK((value_kind IN ('continuous', 'fraction')
           AND lower_bound IS NOT NULL AND upper_bound IS NOT NULL
           AND lower_bound < upper_bound)
          OR (value_kind IN ('binary', 'categorical')
              AND lower_bound IS NULL AND upper_bound IS NULL)),
    CHECK(value_kind <> 'fraction' OR (lower_bound = 0.0 AND upper_bound = 1.0))
);

CREATE TABLE estimator_plans (
    plan_fingerprint TEXT PRIMARY KEY
        CHECK(length(plan_fingerprint) = 64 AND plan_fingerprint NOT GLOB '*[^0-9a-f]*'),
    contract_version TEXT NOT NULL CHECK(length(contract_version) BETWEEN 1 AND 128),
    plan_key TEXT NOT NULL CHECK(
        length(plan_key) BETWEEN 1 AND 128
        AND plan_key GLOB '[a-z]*'
        AND plan_key NOT GLOB '*[^a-z0-9_.:-]*'),
    plan_version TEXT NOT NULL CHECK(length(plan_version) BETWEEN 1 AND 128),
    route TEXT NOT NULL CHECK(route IN ('fast', 'balanced', 'deep')),
    evidence_packet_schema_version TEXT NOT NULL CHECK(length(evidence_packet_schema_version) BETWEEN 1 AND 128),
    preprocessing_version TEXT NOT NULL CHECK(length(preprocessing_version) BETWEEN 1 AND 128),
    preprocessing_sha256 TEXT NOT NULL CHECK(length(preprocessing_sha256) = 64 AND preprocessing_sha256 NOT GLOB '*[^0-9a-f]*'),
    reasoning_effort TEXT NOT NULL CHECK(reasoning_effort IN ('none', 'minimal', 'low', 'medium', 'high', 'xhigh', 'max')),
    calibration_version TEXT NOT NULL CHECK(length(calibration_version) BETWEEN 1 AND 128),
    calibration_sha256 TEXT NOT NULL CHECK(length(calibration_sha256) = 64 AND calibration_sha256 NOT GLOB '*[^0-9a-f]*'),
    router_version TEXT NOT NULL CHECK(length(router_version) BETWEEN 1 AND 128),
    router_sha256 TEXT NOT NULL CHECK(length(router_sha256) = 64 AND router_sha256 NOT GLOB '*[^0-9a-f]*'),
    redactor_version TEXT NOT NULL CHECK(length(redactor_version) BETWEEN 1 AND 128),
    redactor_sha256 TEXT NOT NULL CHECK(length(redactor_sha256) = 64 AND redactor_sha256 NOT GLOB '*[^0-9a-f]*'),
    execution_mode TEXT NOT NULL CHECK(execution_mode = 'serial'),
    model_load_policy TEXT NOT NULL CHECK(model_load_policy = 'one_at_a_time'),
    max_loaded_models INTEGER NOT NULL CHECK(max_loaded_models = 1),
    question_count INTEGER NOT NULL CHECK(question_count BETWEEN 1 AND 100),
    provider_schema_count INTEGER NOT NULL CHECK(provider_schema_count >= 1),
    candidate_family_count INTEGER NOT NULL CHECK(candidate_family_count BETWEEN 0 AND 100),
    uses_synthetic_model INTEGER NOT NULL CHECK(uses_synthetic_model IN (0, 1)),
    registered_at TEXT NOT NULL,
    UNIQUE(plan_key, plan_version)
);

CREATE TABLE estimator_plan_questions (
    plan_fingerprint TEXT NOT NULL REFERENCES estimator_plans(plan_fingerprint)
        ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED,
    ordinal INTEGER NOT NULL CHECK(ordinal BETWEEN 0 AND 99),
    question_fingerprint TEXT NOT NULL REFERENCES estimator_metric_questions(question_fingerprint)
        DEFERRABLE INITIALLY DEFERRED,
    PRIMARY KEY(plan_fingerprint, ordinal),
    UNIQUE(plan_fingerprint, question_fingerprint)
);

CREATE TABLE estimator_plan_provider_schemas (
    plan_fingerprint TEXT NOT NULL REFERENCES estimator_plans(plan_fingerprint)
        ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED,
    ordinal INTEGER NOT NULL CHECK(ordinal BETWEEN 0 AND 99),
    provider TEXT NOT NULL CHECK(provider IN ('codex', 'claude_code', 'synthetic')),
    adapter_version TEXT NOT NULL CHECK(length(adapter_version) BETWEEN 1 AND 128),
    provider_schema_version TEXT NOT NULL CHECK(length(provider_schema_version) BETWEEN 1 AND 128),
    PRIMARY KEY(plan_fingerprint, ordinal),
    UNIQUE(plan_fingerprint, provider, adapter_version, provider_schema_version)
);

CREATE TABLE estimator_candidate_families (
    plan_fingerprint TEXT NOT NULL REFERENCES estimator_plans(plan_fingerprint)
        ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED,
    ordinal INTEGER NOT NULL CHECK(ordinal BETWEEN 0 AND 99),
    family_key TEXT NOT NULL CHECK(
        length(family_key) BETWEEN 1 AND 128
        AND family_key GLOB '[a-z]*'
        AND family_key NOT GLOB '*[^a-z0-9_.:-]*'),
    candidate_count INTEGER NOT NULL CHECK(candidate_count BETWEEN 1 AND 5),
    promotion_count INTEGER NOT NULL CHECK(promotion_count BETWEEN 0 AND 2),
    baseline_count INTEGER NOT NULL CHECK(baseline_count BETWEEN 0 AND 16),
    PRIMARY KEY(plan_fingerprint, family_key),
    UNIQUE(plan_fingerprint, ordinal)
);

CREATE TABLE estimator_candidate_models (
    plan_fingerprint TEXT NOT NULL,
    family_key TEXT NOT NULL,
    ordinal INTEGER NOT NULL CHECK(ordinal BETWEEN 0 AND 4),
    artifact_fingerprint TEXT NOT NULL REFERENCES estimator_model_artifacts(artifact_fingerprint)
        DEFERRABLE INITIALLY DEFERRED,
    PRIMARY KEY(plan_fingerprint, family_key, ordinal),
    UNIQUE(plan_fingerprint, family_key, artifact_fingerprint),
    FOREIGN KEY(plan_fingerprint, family_key)
        REFERENCES estimator_candidate_families(plan_fingerprint, family_key)
        ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE estimator_candidate_promotions (
    plan_fingerprint TEXT NOT NULL,
    family_key TEXT NOT NULL,
    ordinal INTEGER NOT NULL CHECK(ordinal BETWEEN 0 AND 1),
    artifact_fingerprint TEXT NOT NULL REFERENCES estimator_model_artifacts(artifact_fingerprint)
        DEFERRABLE INITIALLY DEFERRED,
    PRIMARY KEY(plan_fingerprint, family_key, ordinal),
    UNIQUE(plan_fingerprint, family_key, artifact_fingerprint),
    FOREIGN KEY(plan_fingerprint, family_key)
        REFERENCES estimator_candidate_families(plan_fingerprint, family_key)
        ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE estimator_candidate_baselines (
    plan_fingerprint TEXT NOT NULL,
    family_key TEXT NOT NULL,
    ordinal INTEGER NOT NULL CHECK(ordinal BETWEEN 0 AND 15),
    baseline_id TEXT NOT NULL CHECK(
        length(baseline_id) BETWEEN 1 AND 128
        AND baseline_id GLOB '[A-Za-z0-9]*'
        AND baseline_id NOT GLOB '*[^A-Za-z0-9._+:/-]*'),
    PRIMARY KEY(plan_fingerprint, family_key, ordinal),
    UNIQUE(plan_fingerprint, family_key, baseline_id),
    FOREIGN KEY(plan_fingerprint, family_key)
        REFERENCES estimator_candidate_families(plan_fingerprint, family_key)
        ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE estimator_plan_stages (
    plan_fingerprint TEXT NOT NULL REFERENCES estimator_plans(plan_fingerprint)
        ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED,
    ordinal INTEGER NOT NULL CHECK(ordinal BETWEEN 1 AND 7),
    kind TEXT NOT NULL CHECK(kind IN (
        'objective_evidence', 'bm25_retrieval', 'embedding_retrieval',
        'reranker', 'specialist', 'second_opinion', 'human_adjudication')),
    condition_code TEXT NOT NULL CHECK(condition_code IN (
        'always', 'disagreement_low_confidence_drift_audit_or_high_value',
        'unresolved_disagreement')),
    component_version TEXT NOT NULL CHECK(length(component_version) BETWEEN 1 AND 128),
    configuration_sha256 TEXT NOT NULL CHECK(length(configuration_sha256) = 64 AND configuration_sha256 NOT GLOB '*[^0-9a-f]*'),
    output_schema_version TEXT NOT NULL CHECK(length(output_schema_version) BETWEEN 1 AND 128),
    artifact_fingerprint TEXT REFERENCES estimator_model_artifacts(artifact_fingerprint)
        DEFERRABLE INITIALLY DEFERRED,
    candidate_family_key TEXT,
    PRIMARY KEY(plan_fingerprint, ordinal),
    FOREIGN KEY(plan_fingerprint, candidate_family_key)
        REFERENCES estimator_candidate_families(plan_fingerprint, family_key)
        DEFERRABLE INITIALLY DEFERRED
);

CREATE TRIGGER estimator_plans_validate_children
BEFORE INSERT ON estimator_plans
WHEN NEW.question_count <> (
        SELECT COUNT(*) FROM estimator_plan_questions WHERE plan_fingerprint = NEW.plan_fingerprint)
    OR NEW.provider_schema_count <> (
        SELECT COUNT(*) FROM estimator_plan_provider_schemas WHERE plan_fingerprint = NEW.plan_fingerprint)
    OR NEW.candidate_family_count <> (
        SELECT COUNT(*) FROM estimator_candidate_families WHERE plan_fingerprint = NEW.plan_fingerprint)
    OR 7 <> (SELECT COUNT(*) FROM estimator_plan_stages WHERE plan_fingerprint = NEW.plan_fingerprint)
    OR NOT EXISTS (SELECT 1 FROM estimator_plan_stages WHERE plan_fingerprint = NEW.plan_fingerprint AND ordinal = 1 AND kind = 'objective_evidence' AND condition_code = 'always' AND artifact_fingerprint IS NULL AND candidate_family_key IS NULL)
    OR NOT EXISTS (SELECT 1 FROM estimator_plan_stages WHERE plan_fingerprint = NEW.plan_fingerprint AND ordinal = 2 AND kind = 'bm25_retrieval' AND condition_code = 'always' AND artifact_fingerprint IS NULL AND candidate_family_key IS NULL)
    OR NOT EXISTS (SELECT 1 FROM estimator_plan_stages WHERE plan_fingerprint = NEW.plan_fingerprint AND ordinal = 3 AND kind = 'embedding_retrieval' AND condition_code = 'always' AND artifact_fingerprint IS NOT NULL)
    OR NOT EXISTS (SELECT 1 FROM estimator_plan_stages WHERE plan_fingerprint = NEW.plan_fingerprint AND ordinal = 4 AND kind = 'reranker' AND condition_code = 'always' AND artifact_fingerprint IS NOT NULL)
    OR NOT EXISTS (SELECT 1 FROM estimator_plan_stages WHERE plan_fingerprint = NEW.plan_fingerprint AND ordinal = 5 AND kind = 'specialist' AND condition_code = 'always' AND artifact_fingerprint IS NOT NULL)
    OR NOT EXISTS (SELECT 1 FROM estimator_plan_stages WHERE plan_fingerprint = NEW.plan_fingerprint AND ordinal = 6 AND kind = 'second_opinion' AND condition_code = 'disagreement_low_confidence_drift_audit_or_high_value' AND artifact_fingerprint IS NOT NULL)
    OR NOT EXISTS (SELECT 1 FROM estimator_plan_stages WHERE plan_fingerprint = NEW.plan_fingerprint AND ordinal = 7 AND kind = 'human_adjudication' AND condition_code = 'unresolved_disagreement' AND artifact_fingerprint IS NULL AND candidate_family_key IS NULL)
    OR EXISTS (
        SELECT 1 FROM estimator_candidate_families AS family
        WHERE family.plan_fingerprint = NEW.plan_fingerprint
          AND (family.candidate_count <> (SELECT COUNT(*) FROM estimator_candidate_models AS candidate WHERE candidate.plan_fingerprint = family.plan_fingerprint AND candidate.family_key = family.family_key)
               OR family.promotion_count <> (SELECT COUNT(*) FROM estimator_candidate_promotions AS promotion WHERE promotion.plan_fingerprint = family.plan_fingerprint AND promotion.family_key = family.family_key)
               OR family.baseline_count <> (SELECT COUNT(*) FROM estimator_candidate_baselines AS baseline WHERE baseline.plan_fingerprint = family.plan_fingerprint AND baseline.family_key = family.family_key)
               OR EXISTS (SELECT 1 FROM estimator_candidate_models AS candidate JOIN estimator_model_artifacts AS artifact ON artifact.artifact_fingerprint = candidate.artifact_fingerprint WHERE candidate.plan_fingerprint = family.plan_fingerprint AND candidate.family_key = family.family_key AND artifact.source <> 'local_weights')
               OR EXISTS (SELECT 1 FROM estimator_candidate_promotions AS promotion WHERE promotion.plan_fingerprint = family.plan_fingerprint AND promotion.family_key = family.family_key AND NOT EXISTS (SELECT 1 FROM estimator_candidate_models AS candidate WHERE candidate.plan_fingerprint = promotion.plan_fingerprint AND candidate.family_key = promotion.family_key AND candidate.artifact_fingerprint = promotion.artifact_fingerprint)))
    )
    OR EXISTS (
        SELECT 1 FROM estimator_plan_stages AS stage
        JOIN estimator_model_artifacts AS artifact ON artifact.artifact_fingerprint = stage.artifact_fingerprint
        WHERE stage.plan_fingerprint = NEW.plan_fingerprint
          AND ((artifact.source = 'local_weights' AND (stage.candidate_family_key IS NULL OR NOT EXISTS (
                    SELECT 1 FROM estimator_candidate_promotions AS promotion
                    WHERE promotion.plan_fingerprint = stage.plan_fingerprint
                      AND promotion.family_key = stage.candidate_family_key
                      AND promotion.artifact_fingerprint = stage.artifact_fingerprint)))
               OR (artifact.source <> 'local_weights' AND stage.candidate_family_key IS NOT NULL))
    )
    OR NEW.uses_synthetic_model <> EXISTS(
        SELECT 1 FROM estimator_plan_stages AS stage
        JOIN estimator_model_artifacts AS artifact ON artifact.artifact_fingerprint = stage.artifact_fingerprint
        WHERE stage.plan_fingerprint = NEW.plan_fingerprint AND artifact.source = 'synthetic')
BEGIN
    SELECT RAISE(ABORT, 'estimator plan children are inconsistent');
END;

CREATE TABLE estimator_synthetic_cases (
    case_id TEXT PRIMARY KEY CHECK(length(case_id) = 64 AND case_id NOT GLOB '*[^0-9a-f]*'),
    case_schema_version TEXT NOT NULL CHECK(length(case_schema_version) BETWEEN 1 AND 128),
    plan_fingerprint TEXT NOT NULL REFERENCES estimator_plans(plan_fingerprint)
        DEFERRABLE INITIALLY DEFERRED,
    evidence_packet_fingerprint TEXT NOT NULL UNIQUE
        CHECK(length(evidence_packet_fingerprint) = 64
              AND evidence_packet_fingerprint NOT GLOB '*[^0-9a-f]*'),
    created_at TEXT NOT NULL,
    source_kind TEXT NOT NULL CHECK(source_kind = 'synthetic'),
    FOREIGN KEY(evidence_packet_fingerprint, case_id)
        REFERENCES estimator_evidence_packets(packet_fingerprint, case_id)
        DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE estimator_evidence_packets (
    packet_fingerprint TEXT PRIMARY KEY
        CHECK(length(packet_fingerprint) = 64 AND packet_fingerprint NOT GLOB '*[^0-9a-f]*'),
    case_id TEXT NOT NULL REFERENCES estimator_synthetic_cases(case_id)
        ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED,
    contract_version TEXT NOT NULL CHECK(length(contract_version) BETWEEN 1 AND 128),
    packet_schema_version TEXT NOT NULL CHECK(length(packet_schema_version) BETWEEN 1 AND 128),
    packet_sha256 TEXT NOT NULL CHECK(length(packet_sha256) = 64 AND packet_sha256 NOT GLOB '*[^0-9a-f]*'),
    requirements_sha256 TEXT NOT NULL CHECK(length(requirements_sha256) = 64 AND requirements_sha256 NOT GLOB '*[^0-9a-f]*'),
    chronology_sha256 TEXT NOT NULL CHECK(length(chronology_sha256) = 64 AND chronology_sha256 NOT GLOB '*[^0-9a-f]*'),
    retrieval_index_sha256 TEXT NOT NULL CHECK(length(retrieval_index_sha256) = 64 AND retrieval_index_sha256 NOT GLOB '*[^0-9a-f]*'),
    provider TEXT NOT NULL CHECK(provider IN ('codex', 'claude_code', 'synthetic')),
    adapter_version TEXT NOT NULL CHECK(length(adapter_version) BETWEEN 1 AND 128),
    provider_schema_version TEXT NOT NULL CHECK(length(provider_schema_version) BETWEEN 1 AND 128),
    preprocessing_version TEXT NOT NULL CHECK(length(preprocessing_version) BETWEEN 1 AND 128),
    preprocessing_sha256 TEXT NOT NULL CHECK(length(preprocessing_sha256) = 64 AND preprocessing_sha256 NOT GLOB '*[^0-9a-f]*'),
    redactor_version TEXT NOT NULL CHECK(length(redactor_version) BETWEEN 1 AND 128),
    redactor_sha256 TEXT NOT NULL CHECK(length(redactor_sha256) = 64 AND redactor_sha256 NOT GLOB '*[^0-9a-f]*'),
    source_record_count INTEGER NOT NULL CHECK(source_record_count BETWEEN 0 AND 10000000),
    requirement_count INTEGER NOT NULL CHECK(requirement_count BETWEEN 0 AND 1000000),
    action_count INTEGER NOT NULL CHECK(action_count BETWEEN 0 AND 1000000),
    decision_count INTEGER NOT NULL CHECK(decision_count BETWEEN 0 AND 1000000),
    feedback_count INTEGER NOT NULL CHECK(feedback_count BETWEEN 0 AND 1000000),
    verification_count INTEGER NOT NULL CHECK(verification_count BETWEEN 0 AND 1000000),
    evidence_ref_count INTEGER NOT NULL CHECK(evidence_ref_count BETWEEN 0 AND 512),
    created_at TEXT NOT NULL,
    ephemeral_payload_retained INTEGER NOT NULL CHECK(ephemeral_payload_retained = 0),
    UNIQUE(case_id),
    UNIQUE(packet_fingerprint, case_id)
);

CREATE TABLE estimator_evidence_refs (
    packet_fingerprint TEXT NOT NULL REFERENCES estimator_evidence_packets(packet_fingerprint)
        ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED,
    ordinal INTEGER NOT NULL CHECK(ordinal BETWEEN 0 AND 511),
    evidence_ref TEXT NOT NULL CHECK(length(evidence_ref) = 64 AND evidence_ref NOT GLOB '*[^0-9a-f]*'),
    PRIMARY KEY(packet_fingerprint, ordinal),
    UNIQUE(packet_fingerprint, evidence_ref)
);

CREATE TRIGGER estimator_evidence_packets_validate_children
BEFORE INSERT ON estimator_evidence_packets
WHEN NEW.evidence_ref_count <> (
    SELECT COUNT(*) FROM estimator_evidence_refs WHERE packet_fingerprint = NEW.packet_fingerprint)
BEGIN
    SELECT RAISE(ABORT, 'estimator evidence receipt children are inconsistent');
END;

CREATE TABLE estimator_executions (
    execution_id TEXT PRIMARY KEY CHECK(length(execution_id) = 64 AND execution_id NOT GLOB '*[^0-9a-f]*'),
    case_id TEXT NOT NULL REFERENCES estimator_synthetic_cases(case_id)
        ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED,
    contract_version TEXT NOT NULL CHECK(length(contract_version) BETWEEN 1 AND 128),
    plan_fingerprint TEXT NOT NULL REFERENCES estimator_plans(plan_fingerprint)
        DEFERRABLE INITIALLY DEFERRED,
    evidence_packet_fingerprint TEXT NOT NULL REFERENCES estimator_evidence_packets(packet_fingerprint)
        DEFERRABLE INITIALLY DEFERRED,
    route TEXT NOT NULL CHECK(route IN ('fast', 'balanced', 'deep')),
    project_id TEXT CHECK(project_id IS NULL OR (length(project_id) = 64 AND project_id NOT GLOB '*[^0-9a-f]*')),
    session_id TEXT CHECK(session_id IS NULL OR (length(session_id) = 64 AND session_id NOT GLOB '*[^0-9a-f]*')),
    state TEXT NOT NULL CHECK(state = 'completed'),
    created_at TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT NOT NULL,
    cascade_stop_stage_ordinal INTEGER NOT NULL CHECK(cascade_stop_stage_ordinal BETWEEN 1 AND 7),
    cascade_stop_stage_kind TEXT NOT NULL CHECK(cascade_stop_stage_kind IN (
        'objective_evidence', 'bm25_retrieval', 'embedding_retrieval',
        'reranker', 'specialist', 'second_opinion', 'human_adjudication')),
    cascade_stop_reason_code TEXT NOT NULL CHECK(
        length(cascade_stop_reason_code) BETWEEN 1 AND 128
        AND cascade_stop_reason_code GLOB '[a-z]*'
        AND cascade_stop_reason_code NOT GLOB '*[^a-z0-9_.:-]*'),
    stage_receipt_count INTEGER NOT NULL CHECK(stage_receipt_count BETWEEN 1 AND 7),
    model_run_count INTEGER NOT NULL CHECK(model_run_count BETWEEN 0 AND 1000),
    model_vote_count INTEGER NOT NULL CHECK(model_vote_count BETWEEN 0 AND 10000),
    metric_estimate_count INTEGER NOT NULL CHECK(metric_estimate_count BETWEEN 1 AND 100)
);

CREATE TABLE estimator_stage_receipts (
    execution_id TEXT NOT NULL REFERENCES estimator_executions(execution_id)
        ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED,
    ordinal INTEGER NOT NULL CHECK(ordinal BETWEEN 1 AND 7),
    kind TEXT NOT NULL CHECK(kind IN (
        'objective_evidence', 'bm25_retrieval', 'embedding_retrieval',
        'reranker', 'specialist', 'second_opinion', 'human_adjudication')),
    state TEXT NOT NULL CHECK(state IN ('completed', 'skipped', 'failed', 'cancelled')),
    outcome_code TEXT NOT NULL CHECK(
        length(outcome_code) BETWEEN 1 AND 128
        AND outcome_code GLOB '[a-z]*'
        AND outcome_code NOT GLOB '*[^a-z0-9_.:-]*'),
    started_at TEXT,
    finished_at TEXT,
    PRIMARY KEY(execution_id, ordinal),
    CHECK((state = 'skipped' AND started_at IS NULL AND finished_at IS NULL)
          OR (state <> 'skipped' AND started_at IS NOT NULL AND finished_at IS NOT NULL))
);

CREATE TABLE estimator_model_runs (
    run_id TEXT PRIMARY KEY CHECK(length(run_id) = 64 AND run_id NOT GLOB '*[^0-9a-f]*'),
    execution_id TEXT NOT NULL REFERENCES estimator_executions(execution_id)
        ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED,
    contract_version TEXT NOT NULL CHECK(length(contract_version) BETWEEN 1 AND 128),
    plan_fingerprint TEXT NOT NULL REFERENCES estimator_plans(plan_fingerprint) DEFERRABLE INITIALLY DEFERRED,
    evidence_packet_fingerprint TEXT NOT NULL REFERENCES estimator_evidence_packets(packet_fingerprint) DEFERRABLE INITIALLY DEFERRED,
    route TEXT NOT NULL CHECK(route IN ('fast', 'balanced', 'deep')),
    stage_ordinal INTEGER NOT NULL CHECK(stage_ordinal BETWEEN 3 AND 6),
    stage_kind TEXT NOT NULL CHECK(stage_kind IN ('embedding_retrieval', 'reranker', 'specialist', 'second_opinion')),
    artifact_fingerprint TEXT NOT NULL REFERENCES estimator_model_artifacts(artifact_fingerprint) DEFERRABLE INITIALLY DEFERRED,
    destination TEXT NOT NULL CHECK(destination IN ('local_device', 'openai_api', 'anthropic_api', 'codex_cli', 'claude_api', 'manual_import', 'synthetic_test')),
    retention_class TEXT NOT NULL CHECK(retention_class IN ('local_ephemeral', 'provider_zero_day', 'provider_30_day', 'provider_disclosed_other', 'manual_export', 'synthetic')),
    retention_days INTEGER CHECK(retention_days IS NULL OR retention_days BETWEEN 0 AND 3650),
    disclosure_version TEXT NOT NULL CHECK(length(disclosure_version) BETWEEN 1 AND 128),
    approval_receipt_id TEXT CHECK(approval_receipt_id IS NULL OR (length(approval_receipt_id) = 64 AND approval_receipt_id NOT GLOB '*[^0-9a-f]*')),
    retention_acknowledged INTEGER NOT NULL CHECK(retention_acknowledged IN (0, 1)),
    state TEXT NOT NULL CHECK(state IN ('completed', 'failed', 'refused', 'timed_out', 'out_of_memory', 'cancelled')),
    started_at TEXT NOT NULL,
    finished_at TEXT NOT NULL,
    cold_start INTEGER NOT NULL CHECK(cold_start IN (0, 1)),
    queue_latency_ms INTEGER NOT NULL CHECK(queue_latency_ms >= 0),
    latency_ms INTEGER NOT NULL CHECK(latency_ms >= 0),
    input_tokens INTEGER CHECK(input_tokens IS NULL OR input_tokens >= 0),
    output_tokens INTEGER CHECK(output_tokens IS NULL OR output_tokens >= 0),
    peak_ram_mib INTEGER CHECK(peak_ram_mib IS NULL OR peak_ram_mib >= 0),
    peak_vram_mib INTEGER CHECK(peak_vram_mib IS NULL OR peak_vram_mib >= 0),
    disk_mib INTEGER CHECK(disk_mib IS NULL OR disk_mib >= 0),
    energy_mwh INTEGER CHECK(energy_mwh IS NULL OR energy_mwh >= 0),
    api_cost_microusd INTEGER CHECK(api_cost_microusd IS NULL OR api_cost_microusd >= 0),
    throughput_unit_code TEXT CHECK(throughput_unit_code IS NULL OR (length(throughput_unit_code) BETWEEN 1 AND 128 AND throughput_unit_code GLOB '[a-z]*' AND throughput_unit_code NOT GLOB '*[^a-z0-9_.:-]*')),
    measured_unit_count INTEGER CHECK(measured_unit_count IS NULL OR measured_unit_count >= 0),
    throughput_window_ms INTEGER CHECK(throughput_window_ms IS NULL OR throughput_window_ms > 0),
    throughput_provenance_version TEXT CHECK(throughput_provenance_version IS NULL OR length(throughput_provenance_version) BETWEEN 1 AND 128),
    usage_provenance_version TEXT NOT NULL CHECK(length(usage_provenance_version) BETWEEN 1 AND 128),
    response_schema_version TEXT NOT NULL CHECK(length(response_schema_version) BETWEEN 1 AND 128),
    structured_output_valid INTEGER NOT NULL CHECK(structured_output_valid IN (0, 1)),
    fallback_used INTEGER NOT NULL CHECK(fallback_used IN (0, 1)),
    fallback_reason_code TEXT CHECK(fallback_reason_code IS NULL OR (
        length(fallback_reason_code) BETWEEN 1 AND 128
        AND fallback_reason_code GLOB '[a-z]*'
        AND fallback_reason_code NOT GLOB '*[^a-z0-9_.:-]*')),
    refusal_code TEXT CHECK(refusal_code IS NULL OR (
        length(refusal_code) BETWEEN 1 AND 128
        AND refusal_code GLOB '[a-z]*'
        AND refusal_code NOT GLOB '*[^a-z0-9_.:-]*')),
    failure_code TEXT CHECK(failure_code IS NULL OR (
        length(failure_code) BETWEEN 1 AND 128
        AND failure_code GLOB '[a-z]*'
        AND failure_code NOT GLOB '*[^a-z0-9_.:-]*')),
    CHECK((throughput_unit_code IS NULL AND measured_unit_count IS NULL AND throughput_window_ms IS NULL AND throughput_provenance_version IS NULL)
          OR (throughput_unit_code IS NOT NULL AND measured_unit_count IS NOT NULL AND throughput_window_ms IS NOT NULL AND throughput_provenance_version IS NOT NULL))
);

CREATE TRIGGER estimator_model_runs_validate_shape
BEFORE INSERT ON estimator_model_runs
WHEN NEW.destination <> 'synthetic_test'
    OR NEW.retention_class <> 'synthetic'
    OR NEW.retention_days <> 0
    OR NEW.approval_receipt_id IS NOT NULL
    OR NEW.retention_acknowledged <> 0
    OR NOT EXISTS (
        SELECT 1 FROM estimator_model_artifacts AS artifact
        WHERE artifact.artifact_fingerprint = NEW.artifact_fingerprint
          AND artifact.source = 'synthetic'
          AND NEW.fallback_used = (
              artifact.requested_model_id <> artifact.served_model_id
              OR artifact.requested_revision <> artifact.served_revision
              OR artifact.requested_execution_mode <> artifact.served_execution_mode)
          AND NEW.fallback_used = (NEW.fallback_reason_code IS NOT NULL))
    OR NOT EXISTS (
        SELECT 1 FROM estimator_plan_stages AS stage
        WHERE stage.plan_fingerprint = NEW.plan_fingerprint
          AND stage.ordinal = NEW.stage_ordinal
          AND stage.kind = NEW.stage_kind
          AND stage.artifact_fingerprint = NEW.artifact_fingerprint
          AND stage.output_schema_version = NEW.response_schema_version)
    OR (NEW.state = 'completed' AND (
        NEW.structured_output_valid <> 1
        OR NEW.refusal_code IS NOT NULL OR NEW.failure_code IS NOT NULL))
    OR (NEW.state = 'refused' AND (
        NEW.structured_output_valid <> 0
        OR NEW.refusal_code IS NULL OR NEW.failure_code IS NOT NULL))
    OR (NEW.state NOT IN ('completed', 'refused') AND (
        NEW.structured_output_valid <> 0
        OR NEW.failure_code IS NULL OR NEW.refusal_code IS NOT NULL))
BEGIN
    SELECT RAISE(ABORT, 'estimator model run shape is inconsistent');
END;

CREATE TABLE estimator_model_votes (
    vote_id TEXT PRIMARY KEY CHECK(length(vote_id) = 64 AND vote_id NOT GLOB '*[^0-9a-f]*'),
    execution_id TEXT NOT NULL REFERENCES estimator_executions(execution_id)
        ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED,
    model_run_id TEXT NOT NULL REFERENCES estimator_model_runs(run_id) DEFERRABLE INITIALLY DEFERRED,
    contract_version TEXT NOT NULL CHECK(length(contract_version) BETWEEN 1 AND 128),
    plan_fingerprint TEXT NOT NULL REFERENCES estimator_plans(plan_fingerprint) DEFERRABLE INITIALLY DEFERRED,
    evidence_packet_fingerprint TEXT NOT NULL REFERENCES estimator_evidence_packets(packet_fingerprint) DEFERRABLE INITIALLY DEFERRED,
    metric_question_fingerprint TEXT NOT NULL REFERENCES estimator_metric_questions(question_fingerprint) DEFERRABLE INITIALLY DEFERRED,
    metric_key TEXT NOT NULL CHECK(
        length(metric_key) BETWEEN 1 AND 128
        AND metric_key GLOB '[a-z]*'
        AND metric_key NOT GLOB '*[^a-z0-9_.:-]*'),
    state TEXT NOT NULL CHECK(state IN ('known', 'unknown', 'abstained', 'not_applicable', 'failed')),
    value_kind TEXT NOT NULL CHECK(value_kind IN ('continuous', 'fraction', 'binary', 'categorical')),
    numeric_value REAL,
    label_code TEXT CHECK(label_code IS NULL OR (
        length(label_code) BETWEEN 1 AND 128
        AND label_code GLOB '[a-z]*'
        AND label_code NOT GLOB '*[^a-z0-9_.:-]*')),
    confidence REAL CHECK(confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
    unknown_reason_code TEXT CHECK(unknown_reason_code IS NULL OR (
        length(unknown_reason_code) BETWEEN 1 AND 128
        AND unknown_reason_code GLOB '[a-z]*'
        AND unknown_reason_code NOT GLOB '*[^a-z0-9_.:-]*')),
    abstention_reason_code TEXT CHECK(abstention_reason_code IS NULL OR (
        length(abstention_reason_code) BETWEEN 1 AND 128
        AND abstention_reason_code GLOB '[a-z]*'
        AND abstention_reason_code NOT GLOB '*[^a-z0-9_.:-]*')),
    not_applicable_reason_code TEXT CHECK(not_applicable_reason_code IS NULL OR (
        length(not_applicable_reason_code) BETWEEN 1 AND 128
        AND not_applicable_reason_code GLOB '[a-z]*'
        AND not_applicable_reason_code NOT GLOB '*[^a-z0-9_.:-]*')),
    failure_code TEXT CHECK(failure_code IS NULL OR (
        length(failure_code) BETWEEN 1 AND 128
        AND failure_code GLOB '[a-z]*'
        AND failure_code NOT GLOB '*[^a-z0-9_.:-]*')),
    probability_count INTEGER NOT NULL CHECK(probability_count BETWEEN 0 AND 128),
    evidence_ref_count INTEGER NOT NULL CHECK(evidence_ref_count BETWEEN 0 AND 512)
);

CREATE TABLE estimator_vote_probabilities (
    vote_id TEXT NOT NULL REFERENCES estimator_model_votes(vote_id)
        ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED,
    ordinal INTEGER NOT NULL CHECK(ordinal BETWEEN 0 AND 127),
    label_code TEXT NOT NULL CHECK(
        length(label_code) BETWEEN 1 AND 128
        AND label_code GLOB '[a-z]*'
        AND label_code NOT GLOB '*[^a-z0-9_.:-]*'),
    probability REAL NOT NULL CHECK(probability >= 0 AND probability <= 1),
    PRIMARY KEY(vote_id, ordinal),
    UNIQUE(vote_id, label_code)
);

CREATE TABLE estimator_vote_evidence_refs (
    vote_id TEXT NOT NULL REFERENCES estimator_model_votes(vote_id)
        ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED,
    ordinal INTEGER NOT NULL CHECK(ordinal BETWEEN 0 AND 511),
    evidence_ref TEXT NOT NULL CHECK(length(evidence_ref) = 64 AND evidence_ref NOT GLOB '*[^0-9a-f]*'),
    PRIMARY KEY(vote_id, ordinal),
    UNIQUE(vote_id, evidence_ref)
);

CREATE TRIGGER estimator_model_votes_validate_children
BEFORE INSERT ON estimator_model_votes
WHEN NEW.probability_count <> (
        SELECT COUNT(*) FROM estimator_vote_probabilities WHERE vote_id = NEW.vote_id)
    OR NEW.evidence_ref_count <> (
        SELECT COUNT(*) FROM estimator_vote_evidence_refs WHERE vote_id = NEW.vote_id)
    OR (NEW.probability_count > 0 AND ABS(1.0 - (
        SELECT SUM(probability) FROM estimator_vote_probabilities WHERE vote_id = NEW.vote_id)) > 0.000001)
    OR (NEW.state = 'known' AND (
        NEW.confidence IS NULL
        OR NEW.evidence_ref_count = 0
        OR NEW.unknown_reason_code IS NOT NULL
        OR NEW.abstention_reason_code IS NOT NULL
        OR NEW.not_applicable_reason_code IS NOT NULL
        OR NEW.failure_code IS NOT NULL
        OR (NEW.value_kind IN ('continuous', 'fraction') AND (
            NEW.numeric_value IS NULL OR NEW.label_code IS NOT NULL
            OR NEW.probability_count <> 0))
        OR (NEW.value_kind IN ('binary', 'categorical') AND (
            NEW.numeric_value IS NOT NULL OR NEW.label_code IS NULL
            OR NEW.probability_count = 0
            OR NOT EXISTS (
                SELECT 1 FROM estimator_vote_probabilities AS probability
                WHERE probability.vote_id = NEW.vote_id
                  AND probability.label_code = NEW.label_code)))
        OR (NEW.value_kind = 'fraction'
            AND (NEW.numeric_value < 0 OR NEW.numeric_value > 1))))
    OR (NEW.state <> 'known' AND (
        NEW.numeric_value IS NOT NULL OR NEW.label_code IS NOT NULL
        OR NEW.confidence IS NOT NULL OR NEW.probability_count <> 0
        OR (NEW.state = 'unknown' AND (
            NEW.unknown_reason_code IS NULL
            OR NEW.abstention_reason_code IS NOT NULL
            OR NEW.not_applicable_reason_code IS NOT NULL
            OR NEW.failure_code IS NOT NULL))
        OR (NEW.state = 'abstained' AND (
            NEW.unknown_reason_code IS NOT NULL
            OR NEW.abstention_reason_code IS NULL
            OR NEW.not_applicable_reason_code IS NOT NULL
            OR NEW.failure_code IS NOT NULL))
        OR (NEW.state = 'not_applicable' AND (
            NEW.unknown_reason_code IS NOT NULL
            OR NEW.abstention_reason_code IS NOT NULL
            OR NEW.not_applicable_reason_code IS NULL
            OR NEW.failure_code IS NOT NULL))
        OR (NEW.state = 'failed' AND (
            NEW.unknown_reason_code IS NOT NULL
            OR NEW.abstention_reason_code IS NOT NULL
            OR NEW.not_applicable_reason_code IS NOT NULL
            OR NEW.failure_code IS NULL))))
BEGIN
    SELECT RAISE(ABORT, 'estimator vote children are inconsistent');
END;

CREATE TABLE estimator_metric_estimates (
    estimate_id TEXT PRIMARY KEY CHECK(length(estimate_id) = 64 AND estimate_id NOT GLOB '*[^0-9a-f]*'),
    execution_id TEXT NOT NULL REFERENCES estimator_executions(execution_id)
        ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED,
    contract_version TEXT NOT NULL CHECK(length(contract_version) BETWEEN 1 AND 128),
    plan_fingerprint TEXT NOT NULL REFERENCES estimator_plans(plan_fingerprint) DEFERRABLE INITIALLY DEFERRED,
    evidence_packet_fingerprint TEXT NOT NULL REFERENCES estimator_evidence_packets(packet_fingerprint) DEFERRABLE INITIALLY DEFERRED,
    metric_question_fingerprint TEXT NOT NULL REFERENCES estimator_metric_questions(question_fingerprint) DEFERRABLE INITIALLY DEFERRED,
    metric_key TEXT NOT NULL CHECK(
        length(metric_key) BETWEEN 1 AND 128
        AND metric_key GLOB '[a-z]*'
        AND metric_key NOT GLOB '*[^a-z0-9_.:-]*'),
    source TEXT NOT NULL CHECK(source IN ('objective_evidence', 'deterministic', 'model_cascade', 'human_adjudicated')),
    state TEXT NOT NULL CHECK(state IN ('known', 'unknown', 'abstained', 'not_applicable', 'failed')),
    value_kind TEXT NOT NULL CHECK(value_kind IN ('continuous', 'fraction', 'binary', 'categorical')),
    unit_code TEXT NOT NULL CHECK(
        length(unit_code) BETWEEN 1 AND 128
        AND unit_code GLOB '[a-z]*'
        AND unit_code NOT GLOB '*[^a-z0-9_.:-]*'),
    numeric_value REAL,
    label_code TEXT CHECK(label_code IS NULL OR (
        length(label_code) BETWEEN 1 AND 128
        AND label_code GLOB '[a-z]*'
        AND label_code NOT GLOB '*[^a-z0-9_.:-]*')),
    numerator INTEGER CHECK(numerator IS NULL OR numerator >= 0),
    denominator INTEGER CHECK(denominator IS NULL OR denominator > 0),
    uncertainty_kind TEXT CHECK(uncertainty_kind IN ('confidence', 'interval', 'distribution', 'not_quantified')),
    uncertainty_confidence REAL CHECK(uncertainty_confidence IS NULL OR (uncertainty_confidence >= 0 AND uncertainty_confidence <= 1)),
    uncertainty_lower_bound REAL,
    uncertainty_upper_bound REAL,
    uncertainty_confidence_level REAL CHECK(uncertainty_confidence_level IS NULL OR (uncertainty_confidence_level > 0 AND uncertainty_confidence_level < 1)),
    uncertainty_entropy REAL CHECK(uncertainty_entropy IS NULL OR uncertainty_entropy >= 0),
    uncertainty_reason_code TEXT CHECK(uncertainty_reason_code IS NULL OR (
        length(uncertainty_reason_code) BETWEEN 1 AND 128
        AND uncertainty_reason_code GLOB '[a-z]*'
        AND uncertainty_reason_code NOT GLOB '*[^a-z0-9_.:-]*')),
    evidence_coverage REAL NOT NULL CHECK(evidence_coverage >= 0 AND evidence_coverage <= 1),
    adjudication_id TEXT CHECK(adjudication_id IS NULL OR (length(adjudication_id) = 64 AND adjudication_id NOT GLOB '*[^0-9a-f]*')),
    unknown_reason_code TEXT CHECK(unknown_reason_code IS NULL OR (
        length(unknown_reason_code) BETWEEN 1 AND 128
        AND unknown_reason_code GLOB '[a-z]*'
        AND unknown_reason_code NOT GLOB '*[^a-z0-9_.:-]*')),
    abstention_reason_code TEXT CHECK(abstention_reason_code IS NULL OR (
        length(abstention_reason_code) BETWEEN 1 AND 128
        AND abstention_reason_code GLOB '[a-z]*'
        AND abstention_reason_code NOT GLOB '*[^a-z0-9_.:-]*')),
    not_applicable_reason_code TEXT CHECK(not_applicable_reason_code IS NULL OR (
        length(not_applicable_reason_code) BETWEEN 1 AND 128
        AND not_applicable_reason_code GLOB '[a-z]*'
        AND not_applicable_reason_code NOT GLOB '*[^a-z0-9_.:-]*')),
    failure_code TEXT CHECK(failure_code IS NULL OR (
        length(failure_code) BETWEEN 1 AND 128
        AND failure_code GLOB '[a-z]*'
        AND failure_code NOT GLOB '*[^a-z0-9_.:-]*')),
    vote_count INTEGER NOT NULL CHECK(vote_count BETWEEN 0 AND 32),
    created_at TEXT NOT NULL,
    UNIQUE(execution_id, metric_question_fingerprint)
);

CREATE TABLE estimator_estimate_votes (
    estimate_id TEXT NOT NULL REFERENCES estimator_metric_estimates(estimate_id)
        ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED,
    ordinal INTEGER NOT NULL CHECK(ordinal BETWEEN 0 AND 31),
    vote_id TEXT NOT NULL REFERENCES estimator_model_votes(vote_id) DEFERRABLE INITIALLY DEFERRED,
    PRIMARY KEY(estimate_id, ordinal),
    UNIQUE(estimate_id, vote_id)
);

CREATE TRIGGER estimator_metric_estimates_validate_children
BEFORE INSERT ON estimator_metric_estimates
WHEN NEW.vote_count <> (
    SELECT COUNT(*) FROM estimator_estimate_votes WHERE estimate_id = NEW.estimate_id)
    OR (NEW.state = 'known' AND (
        NEW.uncertainty_kind IS NULL
        OR NEW.unknown_reason_code IS NOT NULL
        OR NEW.abstention_reason_code IS NOT NULL
        OR NEW.not_applicable_reason_code IS NOT NULL
        OR NEW.failure_code IS NOT NULL
        OR (NEW.value_kind IN ('continuous', 'fraction') AND (
            NEW.numeric_value IS NULL OR NEW.label_code IS NOT NULL))
        OR (NEW.value_kind IN ('binary', 'categorical') AND (
            NEW.numeric_value IS NOT NULL OR NEW.label_code IS NULL))
        OR (NEW.value_kind = 'fraction' AND (
            NEW.numeric_value < 0 OR NEW.numeric_value > 1
            OR (NEW.numerator IS NULL) <> (NEW.denominator IS NULL)
            OR (NEW.numerator IS NOT NULL AND ABS(
                NEW.numeric_value - (1.0 * NEW.numerator / NEW.denominator)
            ) > 0.000000001)))
        OR (NEW.value_kind <> 'fraction' AND (
            NEW.numerator IS NOT NULL OR NEW.denominator IS NOT NULL))))
    OR (NEW.state <> 'known' AND (
        NEW.numeric_value IS NOT NULL OR NEW.label_code IS NOT NULL
        OR NEW.numerator IS NOT NULL OR NEW.denominator IS NOT NULL
        OR NEW.uncertainty_kind IS NOT NULL
        OR NEW.uncertainty_confidence IS NOT NULL
        OR NEW.uncertainty_lower_bound IS NOT NULL
        OR NEW.uncertainty_upper_bound IS NOT NULL
        OR NEW.uncertainty_confidence_level IS NOT NULL
        OR NEW.uncertainty_entropy IS NOT NULL
        OR NEW.uncertainty_reason_code IS NOT NULL
        OR (NEW.state = 'unknown' AND (
            NEW.unknown_reason_code IS NULL
            OR NEW.abstention_reason_code IS NOT NULL
            OR NEW.not_applicable_reason_code IS NOT NULL
            OR NEW.failure_code IS NOT NULL))
        OR (NEW.state = 'abstained' AND (
            NEW.unknown_reason_code IS NOT NULL
            OR NEW.abstention_reason_code IS NULL
            OR NEW.not_applicable_reason_code IS NOT NULL
            OR NEW.failure_code IS NOT NULL))
        OR (NEW.state = 'not_applicable' AND (
            NEW.unknown_reason_code IS NOT NULL
            OR NEW.abstention_reason_code IS NOT NULL
            OR NEW.not_applicable_reason_code IS NULL
            OR NEW.failure_code IS NOT NULL))
        OR (NEW.state = 'failed' AND (
            NEW.unknown_reason_code IS NOT NULL
            OR NEW.abstention_reason_code IS NOT NULL
            OR NEW.not_applicable_reason_code IS NOT NULL
            OR NEW.failure_code IS NULL))))
    OR (NEW.state = 'known' AND (
        (NEW.uncertainty_kind = 'confidence' AND (
            NEW.uncertainty_confidence IS NULL
            OR NEW.uncertainty_lower_bound IS NOT NULL
            OR NEW.uncertainty_upper_bound IS NOT NULL
            OR NEW.uncertainty_confidence_level IS NOT NULL
            OR NEW.uncertainty_entropy IS NOT NULL
            OR NEW.uncertainty_reason_code IS NOT NULL))
        OR (NEW.uncertainty_kind = 'interval' AND (
            NEW.uncertainty_confidence IS NOT NULL
            OR NEW.uncertainty_lower_bound IS NULL
            OR NEW.uncertainty_upper_bound IS NULL
            OR NEW.uncertainty_lower_bound > NEW.uncertainty_upper_bound
            OR NEW.uncertainty_confidence_level IS NULL
            OR NEW.uncertainty_entropy IS NOT NULL
            OR NEW.uncertainty_reason_code IS NOT NULL))
        OR (NEW.uncertainty_kind = 'distribution' AND (
            NEW.uncertainty_confidence IS NOT NULL
            OR NEW.uncertainty_lower_bound IS NOT NULL
            OR NEW.uncertainty_upper_bound IS NOT NULL
            OR NEW.uncertainty_confidence_level IS NOT NULL
            OR NEW.uncertainty_entropy IS NULL
            OR NEW.uncertainty_reason_code IS NOT NULL))
        OR (NEW.uncertainty_kind = 'not_quantified' AND (
            NEW.uncertainty_confidence IS NOT NULL
            OR NEW.uncertainty_lower_bound IS NOT NULL
            OR NEW.uncertainty_upper_bound IS NOT NULL
            OR NEW.uncertainty_confidence_level IS NOT NULL
            OR NEW.uncertainty_entropy IS NOT NULL
            OR NEW.uncertainty_reason_code IS NULL))))
    OR (NEW.source = 'model_cascade' AND NEW.vote_count = 0)
    OR (NEW.source = 'model_cascade' AND NEW.state = 'known'
        AND NEW.evidence_coverage <= 0)
    OR (NEW.source <> 'model_cascade' AND NEW.vote_count <> 0)
    OR NEW.source = 'human_adjudicated'
    OR NEW.adjudication_id IS NOT NULL
BEGIN
    SELECT RAISE(ABORT, 'estimator estimate children are inconsistent');
END;

CREATE TRIGGER estimator_executions_validate_bundle
BEFORE INSERT ON estimator_executions
WHEN NEW.project_id IS NOT NULL OR NEW.session_id IS NOT NULL
    OR NEW.created_at > NEW.started_at OR NEW.started_at > NEW.finished_at
    OR julianday(NEW.created_at) IS NULL
    OR julianday(NEW.started_at) IS NULL
    OR julianday(NEW.finished_at) IS NULL
    OR NOT EXISTS (
        SELECT 1 FROM estimator_synthetic_cases AS test_case
        JOIN estimator_plans AS plan ON plan.plan_fingerprint = test_case.plan_fingerprint
        JOIN estimator_evidence_packets AS packet ON packet.case_id = test_case.case_id
        WHERE test_case.case_id = NEW.case_id
          AND test_case.plan_fingerprint = NEW.plan_fingerprint
          AND test_case.evidence_packet_fingerprint = NEW.evidence_packet_fingerprint
          AND packet.packet_fingerprint = NEW.evidence_packet_fingerprint
          AND packet.packet_schema_version = plan.evidence_packet_schema_version
          AND packet.preprocessing_version = plan.preprocessing_version
          AND packet.preprocessing_sha256 = plan.preprocessing_sha256
          AND packet.redactor_version = plan.redactor_version
          AND packet.redactor_sha256 = plan.redactor_sha256
          AND packet.created_at <= test_case.created_at
          AND test_case.created_at <= NEW.created_at
          AND plan.route = NEW.route
          AND plan.uses_synthetic_model = 1
          AND EXISTS (
              SELECT 1 FROM estimator_plan_provider_schemas AS provider_schema
              WHERE provider_schema.plan_fingerprint = plan.plan_fingerprint
                AND provider_schema.provider = packet.provider
                AND provider_schema.adapter_version = packet.adapter_version
                AND provider_schema.provider_schema_version = packet.provider_schema_version))
    OR NEW.stage_receipt_count <> (
        SELECT COUNT(*) FROM estimator_stage_receipts WHERE execution_id = NEW.execution_id)
    OR NOT EXISTS (
        SELECT 1 FROM estimator_stage_receipts
        WHERE execution_id = NEW.execution_id AND ordinal = 1)
    OR NEW.stage_receipt_count <> (
        SELECT MAX(ordinal) FROM estimator_stage_receipts
        WHERE execution_id = NEW.execution_id)
    OR EXISTS (
        SELECT 1 FROM estimator_stage_receipts AS receipt
        LEFT JOIN estimator_plan_stages AS stage
          ON stage.plan_fingerprint = NEW.plan_fingerprint
         AND stage.ordinal = receipt.ordinal
        WHERE receipt.execution_id = NEW.execution_id
          AND (stage.ordinal IS NULL OR stage.kind <> receipt.kind))
    OR EXISTS (
        SELECT 1 FROM estimator_stage_receipts AS receipt
        WHERE receipt.execution_id = NEW.execution_id
          AND receipt.state <> 'skipped'
          AND (julianday(receipt.started_at) IS NULL
               OR julianday(receipt.finished_at) IS NULL
               OR receipt.started_at < NEW.started_at
               OR receipt.started_at > receipt.finished_at
               OR receipt.finished_at > NEW.finished_at))
    OR EXISTS (
        SELECT 1
        FROM estimator_stage_receipts AS earlier
        JOIN estimator_stage_receipts AS later
          ON later.execution_id = earlier.execution_id
         AND later.ordinal > earlier.ordinal
        WHERE earlier.execution_id = NEW.execution_id
          AND earlier.state <> 'skipped' AND later.state <> 'skipped'
          AND later.started_at < earlier.finished_at)
    OR NEW.cascade_stop_stage_ordinal <> NEW.stage_receipt_count
    OR NOT EXISTS (
        SELECT 1 FROM estimator_stage_receipts AS receipt
        WHERE receipt.execution_id = NEW.execution_id
          AND receipt.ordinal = NEW.cascade_stop_stage_ordinal
          AND receipt.kind = NEW.cascade_stop_stage_kind)
    OR NEW.model_run_count <> (
        SELECT COUNT(*) FROM estimator_model_runs WHERE execution_id = NEW.execution_id)
    OR EXISTS (
        SELECT 1
        FROM estimator_model_runs AS earlier
        JOIN estimator_model_runs AS later
          ON later.execution_id = earlier.execution_id
         AND (later.stage_ordinal > earlier.stage_ordinal
              OR (later.stage_ordinal = earlier.stage_ordinal
                  AND (later.started_at > earlier.started_at
                       OR (later.started_at = earlier.started_at
                           AND (later.finished_at > earlier.finished_at
                                OR (later.finished_at = earlier.finished_at
                                    AND later.run_id > earlier.run_id))))))
        WHERE earlier.execution_id = NEW.execution_id
          AND later.started_at < earlier.finished_at)
    OR NEW.model_vote_count <> (
        SELECT COUNT(*) FROM estimator_model_votes WHERE execution_id = NEW.execution_id)
    OR NEW.metric_estimate_count <> (
        SELECT COUNT(*) FROM estimator_metric_estimates WHERE execution_id = NEW.execution_id)
    OR NEW.metric_estimate_count <> (
        SELECT question_count FROM estimator_plans WHERE plan_fingerprint = NEW.plan_fingerprint)
    OR EXISTS (
        SELECT 1 FROM estimator_model_runs AS run
        WHERE run.execution_id = NEW.execution_id
          AND (run.plan_fingerprint <> NEW.plan_fingerprint
               OR run.evidence_packet_fingerprint <> NEW.evidence_packet_fingerprint
               OR run.route <> NEW.route
               OR run.destination <> 'synthetic_test'
               OR NOT (
                    NEW.started_at <= run.started_at
                    AND run.started_at <= run.finished_at
                    AND run.finished_at <= NEW.finished_at)
               OR run.latency_ms <> CAST(
                    (julianday(run.finished_at) - julianday(run.started_at))
                    * 86400000.0 + 0.5 AS INTEGER)
               OR NOT EXISTS (
                    SELECT 1 FROM estimator_stage_receipts AS receipt
                    WHERE receipt.execution_id = NEW.execution_id
                      AND receipt.ordinal = run.stage_ordinal
                      AND receipt.kind = run.stage_kind
                      AND ((run.state = 'completed' AND receipt.state = 'completed')
                           OR (run.state <> 'completed'
                               AND receipt.state IN ('completed', 'failed', 'cancelled')))
                      AND receipt.started_at <= run.started_at
                      AND run.finished_at <= receipt.finished_at)
               OR NOT EXISTS (
                    SELECT 1 FROM estimator_plan_stages AS stage
                    JOIN estimator_model_artifacts AS artifact
                      ON artifact.artifact_fingerprint = stage.artifact_fingerprint
                    WHERE stage.plan_fingerprint = NEW.plan_fingerprint
                      AND stage.ordinal = run.stage_ordinal
                      AND stage.kind = run.stage_kind
                      AND stage.artifact_fingerprint = run.artifact_fingerprint
                      AND stage.output_schema_version = run.response_schema_version
                      AND artifact.source = 'synthetic')))
    OR EXISTS (
        SELECT 1 FROM estimator_stage_receipts AS receipt
        JOIN estimator_plan_stages AS stage
          ON stage.plan_fingerprint = NEW.plan_fingerprint
         AND stage.ordinal = receipt.ordinal
        WHERE receipt.execution_id = NEW.execution_id
          AND receipt.state = 'skipped'
          AND stage.condition_code = 'always')
    OR EXISTS (
        SELECT 1 FROM estimator_stage_receipts AS receipt
        WHERE receipt.execution_id = NEW.execution_id
          AND receipt.kind IN ('embedding_retrieval', 'reranker', 'specialist', 'second_opinion')
          AND ((receipt.state = 'skipped' AND EXISTS (
                    SELECT 1 FROM estimator_model_runs AS run
                    WHERE run.execution_id = NEW.execution_id
                      AND run.stage_ordinal = receipt.ordinal))
               OR (receipt.state = 'completed' AND NOT EXISTS (
                    SELECT 1 FROM estimator_model_runs AS run
                    WHERE run.execution_id = NEW.execution_id
                      AND run.stage_ordinal = receipt.ordinal
                      AND run.state = 'completed'))
               OR (receipt.state = 'failed' AND (
                    NOT EXISTS (
                        SELECT 1 FROM estimator_model_runs AS run
                        WHERE run.execution_id = NEW.execution_id
                          AND run.stage_ordinal = receipt.ordinal)
                    OR EXISTS (
                        SELECT 1 FROM estimator_model_runs AS run
                        WHERE run.execution_id = NEW.execution_id
                          AND run.stage_ordinal = receipt.ordinal
                          AND run.state = 'completed')
                    OR NOT EXISTS (
                        SELECT 1 FROM estimator_model_runs AS run
                        WHERE run.execution_id = NEW.execution_id
                          AND run.stage_ordinal = receipt.ordinal
                          AND run.state IN ('failed', 'refused', 'timed_out', 'out_of_memory'))))
               OR (receipt.state = 'cancelled' AND (
                    NOT EXISTS (
                        SELECT 1 FROM estimator_model_runs AS run
                        WHERE run.execution_id = NEW.execution_id
                          AND run.stage_ordinal = receipt.ordinal)
                    OR EXISTS (
                        SELECT 1 FROM estimator_model_runs AS run
                        WHERE run.execution_id = NEW.execution_id
                          AND run.stage_ordinal = receipt.ordinal
                          AND run.state <> 'cancelled')))))
    OR EXISTS (
        SELECT 1 FROM estimator_stage_receipts AS receipt
        WHERE receipt.execution_id = NEW.execution_id
          AND receipt.kind = 'human_adjudication'
          AND receipt.state <> 'skipped')
    OR EXISTS (
        SELECT 1 FROM estimator_model_votes AS vote
        WHERE vote.execution_id = NEW.execution_id
          AND (vote.plan_fingerprint <> NEW.plan_fingerprint
               OR vote.evidence_packet_fingerprint <> NEW.evidence_packet_fingerprint
               OR NOT EXISTS (
                    SELECT 1 FROM estimator_model_runs AS run
                    WHERE run.run_id = vote.model_run_id
                      AND run.execution_id = NEW.execution_id
                      AND run.stage_kind IN ('specialist', 'second_opinion')
                      AND ((vote.state IN ('known', 'unknown', 'not_applicable')
                            AND run.state = 'completed'
                            AND run.structured_output_valid = 1)
                           OR (vote.state = 'abstained'
                               AND ((run.state = 'completed'
                                     AND run.structured_output_valid = 1)
                                    OR (run.state = 'refused'
                                        AND run.structured_output_valid = 0
                                        AND vote.abstention_reason_code = run.refusal_code)))
                           OR (vote.state = 'failed'
                               AND run.state IN ('failed', 'timed_out', 'out_of_memory', 'cancelled')
                               AND run.structured_output_valid = 0
                               AND vote.failure_code = run.failure_code)))
               OR NOT EXISTS (
                    SELECT 1 FROM estimator_plan_questions AS selected
                    JOIN estimator_metric_questions AS question
                      ON question.question_fingerprint = selected.question_fingerprint
                    WHERE selected.plan_fingerprint = NEW.plan_fingerprint
                      AND selected.question_fingerprint = vote.metric_question_fingerprint
                      AND question.metric_key = vote.metric_key
                      AND question.value_kind = vote.value_kind
                      AND (vote.numeric_value IS NULL OR (
                          question.lower_bound IS NOT NULL
                          AND vote.numeric_value >= question.lower_bound
                          AND vote.numeric_value <= question.upper_bound)))
               OR EXISTS (
                    SELECT 1 FROM estimator_vote_evidence_refs AS reference
                    WHERE reference.vote_id = vote.vote_id
                      AND NOT EXISTS (
                          SELECT 1 FROM estimator_evidence_refs AS packet_reference
                            WHERE packet_reference.packet_fingerprint = NEW.evidence_packet_fingerprint
                            AND packet_reference.evidence_ref = reference.evidence_ref))))
    OR EXISTS (
        SELECT 1 FROM estimator_model_runs AS run
        WHERE run.execution_id = NEW.execution_id
          AND run.stage_kind IN ('specialist', 'second_opinion')
          AND run.state = 'completed'
          AND NOT EXISTS (
              SELECT 1 FROM estimator_model_votes AS vote
              WHERE vote.model_run_id = run.run_id))
    OR EXISTS (
        SELECT 1 FROM estimator_model_votes AS vote
        WHERE vote.execution_id = NEW.execution_id
          AND NOT EXISTS (
              SELECT 1 FROM estimator_estimate_votes AS selected_vote
              WHERE selected_vote.vote_id = vote.vote_id))
    OR EXISTS (
        SELECT 1 FROM estimator_metric_estimates AS estimate
        WHERE estimate.execution_id = NEW.execution_id
          AND (estimate.plan_fingerprint <> NEW.plan_fingerprint
               OR estimate.evidence_packet_fingerprint <> NEW.evidence_packet_fingerprint
               OR estimate.created_at < NEW.started_at
               OR estimate.created_at > NEW.finished_at
               OR NOT EXISTS (
                    SELECT 1 FROM estimator_plan_questions AS selected
                    JOIN estimator_metric_questions AS question
                      ON question.question_fingerprint = selected.question_fingerprint
                    WHERE selected.plan_fingerprint = NEW.plan_fingerprint
                      AND selected.question_fingerprint = estimate.metric_question_fingerprint
                      AND question.metric_key = estimate.metric_key
                      AND question.value_kind = estimate.value_kind
                      AND question.unit_code = estimate.unit_code
                      AND (estimate.numeric_value IS NULL OR (
                          question.lower_bound IS NOT NULL
                          AND estimate.numeric_value >= question.lower_bound
                          AND estimate.numeric_value <= question.upper_bound)))
               OR EXISTS (
                    SELECT 1 FROM estimator_estimate_votes AS selected_vote
                    JOIN estimator_model_votes AS vote ON vote.vote_id = selected_vote.vote_id
                    WHERE selected_vote.estimate_id = estimate.estimate_id
                      AND (vote.execution_id <> NEW.execution_id
                           OR vote.metric_question_fingerprint <> estimate.metric_question_fingerprint)))
               OR (estimate.source = 'model_cascade' AND NOT EXISTS (
                    SELECT 1 FROM estimator_estimate_votes AS selected_vote
                    JOIN estimator_model_votes AS vote ON vote.vote_id = selected_vote.vote_id
                    WHERE selected_vote.estimate_id = estimate.estimate_id
                      AND vote.state = estimate.state))
               OR (estimate.source = 'model_cascade' AND EXISTS (
                    SELECT 1 FROM estimator_estimate_votes AS selected_vote
                    JOIN estimator_model_votes AS vote ON vote.vote_id = selected_vote.vote_id
                    JOIN estimator_model_runs AS run ON run.run_id = vote.model_run_id
                    WHERE selected_vote.estimate_id = estimate.estimate_id
                      AND estimate.created_at < run.finished_at))
               OR (estimate.source = 'model_cascade'
                   AND estimate.state = 'known'
                   AND NOT EXISTS (
                       SELECT 1 FROM estimator_estimate_votes AS selected_vote
                       JOIN estimator_model_votes AS vote ON vote.vote_id = selected_vote.vote_id
                       WHERE selected_vote.estimate_id = estimate.estimate_id
                         AND vote.state = 'known'
                         AND vote.evidence_ref_count > 0)))
    OR EXISTS (
        SELECT 1 FROM estimator_metric_estimates AS estimate
        JOIN estimator_metric_questions AS question
          ON question.question_fingerprint = estimate.metric_question_fingerprint
        WHERE estimate.execution_id = NEW.execution_id
          AND estimate.state = 'known'
          AND estimate.numeric_value IS NOT NULL
          AND estimate.uncertainty_kind = 'interval'
          AND NOT (
              question.lower_bound <= estimate.uncertainty_lower_bound
              AND estimate.uncertainty_lower_bound <= estimate.numeric_value
              AND estimate.numeric_value <= estimate.uncertainty_upper_bound
              AND estimate.uncertainty_upper_bound <= question.upper_bound))
    OR EXISTS (
        SELECT 1 FROM estimator_metric_estimates AS estimate
        WHERE estimate.execution_id = NEW.execution_id
          AND ((estimate.source = 'objective_evidence' AND NOT EXISTS (
                    SELECT 1 FROM estimator_stage_receipts AS receipt
                    WHERE receipt.execution_id = NEW.execution_id
                      AND receipt.ordinal = 1 AND receipt.state = 'completed'))
               OR (estimate.source = 'deterministic' AND NOT EXISTS (
                    SELECT 1 FROM estimator_stage_receipts AS receipt
                    WHERE receipt.execution_id = NEW.execution_id
                      AND receipt.ordinal = 2 AND receipt.state = 'completed'))
               OR (estimate.source = 'objective_evidence' AND EXISTS (
                    SELECT 1 FROM estimator_stage_receipts AS receipt
                    WHERE receipt.execution_id = NEW.execution_id
                      AND receipt.ordinal = 1
                      AND estimate.created_at < receipt.finished_at))
               OR (estimate.source = 'deterministic' AND EXISTS (
                    SELECT 1 FROM estimator_stage_receipts AS receipt
                    WHERE receipt.execution_id = NEW.execution_id
                      AND receipt.ordinal = 2
                      AND estimate.created_at < receipt.finished_at))
               OR (estimate.state = 'known'
                   AND estimate.source IN ('objective_evidence', 'deterministic')
                   AND (estimate.evidence_coverage <= 0
                        OR NOT EXISTS (
                            SELECT 1 FROM estimator_evidence_refs AS reference
                            WHERE reference.packet_fingerprint = NEW.evidence_packet_fingerprint)
                        OR (estimate.source = 'objective_evidence'
                            AND NOT EXISTS (
                                SELECT 1 FROM estimator_evidence_packets AS packet
                                WHERE packet.packet_fingerprint = NEW.evidence_packet_fingerprint
                                  AND packet.verification_count > 0))))))
BEGIN
    SELECT RAISE(ABORT, 'estimator execution bundle is inconsistent');
END;

-- Direct SQL is also a privacy boundary.  These triggers apply the same
-- content-free identifier alphabet used by application contracts and require
-- canonical microsecond UTC timestamps.  They prevent internal callers from
-- repurposing version or timestamp fields as arbitrary text storage.
CREATE TRIGGER estimator_metric_questions_safe_metadata
BEFORE INSERT ON estimator_metric_questions
WHEN NEW.contract_version NOT GLOB '[A-Za-z0-9]*'
    OR NEW.contract_version GLOB '*[^A-Za-z0-9._+:/-]*'
    OR NEW.metric_definition_version NOT GLOB '[A-Za-z0-9]*'
    OR NEW.metric_definition_version GLOB '*[^A-Za-z0-9._+:/-]*'
    OR NEW.question_version NOT GLOB '[A-Za-z0-9]*'
    OR NEW.question_version GLOB '*[^A-Za-z0-9._+:/-]*'
    OR NEW.prompt_template_version NOT GLOB '[A-Za-z0-9]*'
    OR NEW.prompt_template_version GLOB '*[^A-Za-z0-9._+:/-]*'
    OR NEW.rubric_version NOT GLOB '[A-Za-z0-9]*'
    OR NEW.rubric_version GLOB '*[^A-Za-z0-9._+:/-]*'
    OR NEW.output_schema_version NOT GLOB '[A-Za-z0-9]*'
    OR NEW.output_schema_version GLOB '*[^A-Za-z0-9._+:/-]*'
    OR NEW.contract_version GLOB '[A-Za-z]:/*'
    OR NEW.metric_definition_version GLOB '[A-Za-z]:/*'
    OR NEW.question_version GLOB '[A-Za-z]:/*'
    OR NEW.prompt_template_version GLOB '[A-Za-z]:/*'
    OR NEW.rubric_version GLOB '[A-Za-z]:/*'
    OR NEW.output_schema_version GLOB '[A-Za-z]:/*'
    OR NEW.contract_version GLOB '/*'
    OR NEW.metric_definition_version GLOB '/*'
    OR NEW.question_version GLOB '/*'
    OR NEW.prompt_template_version GLOB '/*'
    OR NEW.rubric_version GLOB '/*'
    OR NEW.output_schema_version GLOB '/*'
    OR instr(NEW.contract_version, '://') > 0
    OR instr(NEW.metric_definition_version, '://') > 0
    OR instr(NEW.question_version, '://') > 0
    OR instr(NEW.prompt_template_version, '://') > 0
    OR instr(NEW.rubric_version, '://') > 0
    OR instr(NEW.output_schema_version, '://') > 0
    OR instr('/' || NEW.contract_version || '/', '/../') > 0
    OR instr('/' || NEW.metric_definition_version || '/', '/../') > 0
    OR instr('/' || NEW.question_version || '/', '/../') > 0
    OR instr('/' || NEW.prompt_template_version || '/', '/../') > 0
    OR instr('/' || NEW.rubric_version || '/', '/../') > 0
    OR instr('/' || NEW.output_schema_version || '/', '/../') > 0
BEGIN SELECT RAISE(ABORT, 'estimator metadata must be content-free'); END;

CREATE TRIGGER estimator_plans_safe_metadata
BEFORE INSERT ON estimator_plans
WHEN NEW.contract_version NOT GLOB '[A-Za-z0-9]*'
    OR NEW.contract_version GLOB '*[^A-Za-z0-9._+:/-]*'
    OR NEW.plan_version NOT GLOB '[A-Za-z0-9]*'
    OR NEW.plan_version GLOB '*[^A-Za-z0-9._+:/-]*'
    OR NEW.plan_version GLOB '[A-Za-z]:/*'
    OR NEW.contract_version GLOB '[A-Za-z]:/*'
    OR NEW.evidence_packet_schema_version GLOB '[A-Za-z]:/*'
    OR NEW.preprocessing_version GLOB '[A-Za-z]:/*'
    OR NEW.calibration_version GLOB '[A-Za-z]:/*'
    OR NEW.router_version GLOB '[A-Za-z]:/*'
    OR NEW.redactor_version GLOB '[A-Za-z]:/*'
    OR NEW.plan_version GLOB '/*' OR NEW.contract_version GLOB '/*'
    OR NEW.evidence_packet_schema_version GLOB '/*'
    OR NEW.preprocessing_version GLOB '/*' OR NEW.calibration_version GLOB '/*'
    OR NEW.router_version GLOB '/*' OR NEW.redactor_version GLOB '/*'
    OR instr(NEW.plan_version, '://') > 0
    OR instr(NEW.contract_version, '://') > 0
    OR instr(NEW.evidence_packet_schema_version, '://') > 0
    OR instr(NEW.preprocessing_version, '://') > 0
    OR instr(NEW.calibration_version, '://') > 0
    OR instr(NEW.router_version, '://') > 0
    OR instr(NEW.redactor_version, '://') > 0
    OR instr('/' || NEW.plan_version || '/', '/../') > 0
    OR instr('/' || NEW.contract_version || '/', '/../') > 0
    OR instr('/' || NEW.evidence_packet_schema_version || '/', '/../') > 0
    OR instr('/' || NEW.preprocessing_version || '/', '/../') > 0
    OR instr('/' || NEW.calibration_version || '/', '/../') > 0
    OR instr('/' || NEW.router_version || '/', '/../') > 0
    OR instr('/' || NEW.redactor_version || '/', '/../') > 0
    OR NEW.evidence_packet_schema_version NOT GLOB '[A-Za-z0-9]*'
    OR NEW.evidence_packet_schema_version GLOB '*[^A-Za-z0-9._+:/-]*'
    OR NEW.preprocessing_version NOT GLOB '[A-Za-z0-9]*'
    OR NEW.preprocessing_version GLOB '*[^A-Za-z0-9._+:/-]*'
    OR NEW.calibration_version NOT GLOB '[A-Za-z0-9]*'
    OR NEW.calibration_version GLOB '*[^A-Za-z0-9._+:/-]*'
    OR NEW.router_version NOT GLOB '[A-Za-z0-9]*'
    OR NEW.router_version GLOB '*[^A-Za-z0-9._+:/-]*'
    OR NEW.redactor_version NOT GLOB '[A-Za-z0-9]*'
    OR NEW.redactor_version GLOB '*[^A-Za-z0-9._+:/-]*'
    OR NEW.registered_at NOT GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]+00:00'
    OR julianday(NEW.registered_at) IS NULL
BEGIN SELECT RAISE(ABORT, 'estimator metadata must be content-free'); END;

CREATE TRIGGER estimator_plan_provider_schemas_safe_metadata
BEFORE INSERT ON estimator_plan_provider_schemas
WHEN NEW.adapter_version NOT GLOB '[A-Za-z0-9]*'
    OR NEW.adapter_version GLOB '*[^A-Za-z0-9._+:/-]*'
    OR NEW.provider_schema_version NOT GLOB '[A-Za-z0-9]*'
    OR NEW.provider_schema_version GLOB '*[^A-Za-z0-9._+:/-]*'
    OR NEW.adapter_version GLOB '[A-Za-z]:/*'
    OR NEW.provider_schema_version GLOB '[A-Za-z]:/*'
    OR NEW.adapter_version GLOB '/*' OR NEW.provider_schema_version GLOB '/*'
    OR instr(NEW.adapter_version, '://') > 0
    OR instr(NEW.provider_schema_version, '://') > 0
    OR instr('/' || NEW.adapter_version || '/', '/../') > 0
    OR instr('/' || NEW.provider_schema_version || '/', '/../') > 0
    OR NEW.adapter_version NOT GLOB '[A-Za-z0-9]*'
    OR NEW.adapter_version GLOB '*[^A-Za-z0-9._+:/-]*'
BEGIN SELECT RAISE(ABORT, 'estimator metadata must be content-free'); END;

CREATE TRIGGER estimator_plan_stages_safe_metadata
BEFORE INSERT ON estimator_plan_stages
WHEN NEW.component_version NOT GLOB '[A-Za-z0-9]*'
    OR NEW.component_version GLOB '*[^A-Za-z0-9._+:/-]*'
    OR NEW.output_schema_version NOT GLOB '[A-Za-z0-9]*'
    OR NEW.output_schema_version GLOB '*[^A-Za-z0-9._+:/-]*'
    OR NEW.component_version GLOB '[A-Za-z]:/*'
    OR NEW.output_schema_version GLOB '[A-Za-z]:/*'
    OR NEW.component_version GLOB '/*' OR NEW.output_schema_version GLOB '/*'
    OR instr(NEW.component_version, '://') > 0
    OR instr(NEW.output_schema_version, '://') > 0
    OR instr('/' || NEW.component_version || '/', '/../') > 0
    OR instr('/' || NEW.output_schema_version || '/', '/../') > 0
BEGIN SELECT RAISE(ABORT, 'estimator metadata must be content-free'); END;

CREATE TRIGGER estimator_candidate_baselines_safe_metadata
BEFORE INSERT ON estimator_candidate_baselines
WHEN NEW.baseline_id GLOB '[A-Za-z]:/*'
    OR NEW.baseline_id GLOB '/*'
    OR instr(NEW.baseline_id, '://') > 0
    OR instr('/' || NEW.baseline_id || '/', '/../') > 0
BEGIN SELECT RAISE(ABORT, 'estimator metadata must be content-free'); END;

CREATE TRIGGER estimator_synthetic_cases_safe_metadata
BEFORE INSERT ON estimator_synthetic_cases
WHEN NEW.case_schema_version NOT GLOB '[A-Za-z0-9]*'
    OR NEW.case_schema_version GLOB '*[^A-Za-z0-9._+:/-]*'
    OR NEW.case_schema_version GLOB '[A-Za-z]:/*'
    OR NEW.case_schema_version GLOB '/*'
    OR instr(NEW.case_schema_version, '://') > 0
    OR instr('/' || NEW.case_schema_version || '/', '/../') > 0
    OR NEW.created_at NOT GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]+00:00'
    OR julianday(NEW.created_at) IS NULL
BEGIN SELECT RAISE(ABORT, 'estimator metadata must be content-free'); END;

CREATE TRIGGER estimator_evidence_packets_safe_metadata
BEFORE INSERT ON estimator_evidence_packets
WHEN NEW.contract_version NOT GLOB '[A-Za-z0-9]*'
    OR NEW.contract_version GLOB '*[^A-Za-z0-9._+:/-]*'
    OR NEW.packet_schema_version NOT GLOB '[A-Za-z0-9]*'
    OR NEW.packet_schema_version GLOB '*[^A-Za-z0-9._+:/-]*'
    OR NEW.adapter_version NOT GLOB '[A-Za-z0-9]*'
    OR NEW.adapter_version GLOB '*[^A-Za-z0-9._+:/-]*'
    OR NEW.provider_schema_version NOT GLOB '[A-Za-z0-9]*'
    OR NEW.provider_schema_version GLOB '*[^A-Za-z0-9._+:/-]*'
    OR NEW.preprocessing_version NOT GLOB '[A-Za-z0-9]*'
    OR NEW.preprocessing_version GLOB '*[^A-Za-z0-9._+:/-]*'
    OR NEW.redactor_version NOT GLOB '[A-Za-z0-9]*'
    OR NEW.redactor_version GLOB '*[^A-Za-z0-9._+:/-]*'
    OR NEW.contract_version GLOB '[A-Za-z]:/*'
    OR NEW.packet_schema_version GLOB '[A-Za-z]:/*'
    OR NEW.adapter_version GLOB '[A-Za-z]:/*'
    OR NEW.provider_schema_version GLOB '[A-Za-z]:/*'
    OR NEW.preprocessing_version GLOB '[A-Za-z]:/*'
    OR NEW.redactor_version GLOB '[A-Za-z]:/*'
    OR NEW.contract_version GLOB '/*' OR NEW.packet_schema_version GLOB '/*'
    OR NEW.adapter_version GLOB '/*' OR NEW.provider_schema_version GLOB '/*'
    OR NEW.preprocessing_version GLOB '/*' OR NEW.redactor_version GLOB '/*'
    OR instr(NEW.contract_version, '://') > 0
    OR instr(NEW.packet_schema_version, '://') > 0
    OR instr(NEW.adapter_version, '://') > 0
    OR instr(NEW.provider_schema_version, '://') > 0
    OR instr(NEW.preprocessing_version, '://') > 0
    OR instr(NEW.redactor_version, '://') > 0
    OR instr('/' || NEW.contract_version || '/', '/../') > 0
    OR instr('/' || NEW.packet_schema_version || '/', '/../') > 0
    OR instr('/' || NEW.adapter_version || '/', '/../') > 0
    OR instr('/' || NEW.provider_schema_version || '/', '/../') > 0
    OR instr('/' || NEW.preprocessing_version || '/', '/../') > 0
    OR instr('/' || NEW.redactor_version || '/', '/../') > 0
    OR NEW.created_at NOT GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]+00:00'
    OR julianday(NEW.created_at) IS NULL
BEGIN SELECT RAISE(ABORT, 'estimator metadata must be content-free'); END;

CREATE TRIGGER estimator_executions_safe_metadata
BEFORE INSERT ON estimator_executions
WHEN NEW.contract_version NOT GLOB '[A-Za-z0-9]*'
    OR NEW.contract_version GLOB '*[^A-Za-z0-9._+:/-]*'
    OR NEW.contract_version GLOB '[A-Za-z]:/*'
    OR NEW.contract_version GLOB '/*'
    OR instr(NEW.contract_version, '://') > 0
    OR instr('/' || NEW.contract_version || '/', '/../') > 0
    OR NEW.created_at NOT GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]+00:00'
    OR NEW.started_at NOT GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]+00:00'
    OR NEW.finished_at NOT GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]+00:00'
    OR julianday(NEW.created_at) IS NULL OR julianday(NEW.started_at) IS NULL
    OR julianday(NEW.finished_at) IS NULL
BEGIN SELECT RAISE(ABORT, 'estimator metadata must be content-free'); END;

CREATE TRIGGER estimator_stage_receipts_safe_metadata
BEFORE INSERT ON estimator_stage_receipts
WHEN (NEW.started_at IS NOT NULL AND NEW.started_at NOT GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]+00:00')
    OR (NEW.finished_at IS NOT NULL AND NEW.finished_at NOT GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]+00:00')
    OR (NEW.started_at IS NOT NULL AND julianday(NEW.started_at) IS NULL)
    OR (NEW.finished_at IS NOT NULL AND julianday(NEW.finished_at) IS NULL)
BEGIN SELECT RAISE(ABORT, 'estimator metadata must be content-free'); END;

CREATE TRIGGER estimator_model_runs_safe_metadata
BEFORE INSERT ON estimator_model_runs
WHEN NEW.contract_version NOT GLOB '[A-Za-z0-9]*'
    OR NEW.contract_version GLOB '*[^A-Za-z0-9._+:/-]*'
    OR NEW.disclosure_version NOT GLOB '[A-Za-z0-9]*'
    OR NEW.disclosure_version GLOB '*[^A-Za-z0-9._+:/-]*'
    OR (NEW.throughput_provenance_version IS NOT NULL AND (
        NEW.throughput_provenance_version NOT GLOB '[A-Za-z0-9]*'
        OR NEW.throughput_provenance_version GLOB '*[^A-Za-z0-9._+:/-]*'))
    OR NEW.usage_provenance_version NOT GLOB '[A-Za-z0-9]*'
    OR NEW.usage_provenance_version GLOB '*[^A-Za-z0-9._+:/-]*'
    OR NEW.response_schema_version NOT GLOB '[A-Za-z0-9]*'
    OR NEW.response_schema_version GLOB '*[^A-Za-z0-9._+:/-]*'
    OR NEW.contract_version GLOB '[A-Za-z]:/*'
    OR NEW.disclosure_version GLOB '[A-Za-z]:/*'
    OR NEW.usage_provenance_version GLOB '[A-Za-z]:/*'
    OR NEW.response_schema_version GLOB '[A-Za-z]:/*'
    OR (NEW.throughput_provenance_version IS NOT NULL AND (
        NEW.throughput_provenance_version GLOB '[A-Za-z]:/*'
        OR NEW.throughput_provenance_version GLOB '/*'
        OR instr(NEW.throughput_provenance_version, '://') > 0
        OR instr('/' || NEW.throughput_provenance_version || '/', '/../') > 0))
    OR NEW.contract_version GLOB '/*' OR NEW.disclosure_version GLOB '/*'
    OR NEW.usage_provenance_version GLOB '/*'
    OR NEW.response_schema_version GLOB '/*'
    OR instr(NEW.contract_version, '://') > 0
    OR instr(NEW.disclosure_version, '://') > 0
    OR instr(NEW.usage_provenance_version, '://') > 0
    OR instr(NEW.response_schema_version, '://') > 0
    OR instr('/' || NEW.contract_version || '/', '/../') > 0
    OR instr('/' || NEW.disclosure_version || '/', '/../') > 0
    OR instr('/' || NEW.usage_provenance_version || '/', '/../') > 0
    OR instr('/' || NEW.response_schema_version || '/', '/../') > 0
    OR NEW.started_at NOT GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]+00:00'
    OR NEW.finished_at NOT GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]+00:00'
    OR julianday(NEW.started_at) IS NULL OR julianday(NEW.finished_at) IS NULL
BEGIN SELECT RAISE(ABORT, 'estimator metadata must be content-free'); END;

CREATE TRIGGER estimator_model_votes_safe_metadata
BEFORE INSERT ON estimator_model_votes
WHEN NEW.contract_version NOT GLOB '[A-Za-z0-9]*'
    OR NEW.contract_version GLOB '*[^A-Za-z0-9._+:/-]*'
    OR NEW.contract_version GLOB '[A-Za-z]:/*'
    OR NEW.contract_version GLOB '/*'
    OR instr(NEW.contract_version, '://') > 0
    OR instr('/' || NEW.contract_version || '/', '/../') > 0
BEGIN SELECT RAISE(ABORT, 'estimator metadata must be content-free'); END;

CREATE TRIGGER estimator_metric_estimates_safe_metadata
BEFORE INSERT ON estimator_metric_estimates
WHEN NEW.contract_version NOT GLOB '[A-Za-z0-9]*'
    OR NEW.contract_version GLOB '*[^A-Za-z0-9._+:/-]*'
    OR NEW.contract_version GLOB '[A-Za-z]:/*'
    OR NEW.contract_version GLOB '/*'
    OR instr(NEW.contract_version, '://') > 0
    OR instr('/' || NEW.contract_version || '/', '/../') > 0
    OR NEW.created_at NOT GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]+00:00'
    OR julianday(NEW.created_at) IS NULL
BEGIN SELECT RAISE(ABORT, 'estimator metadata must be content-free'); END;

-- Every estimator row is immutable.  Safe synthetic case deletion is the only
-- removal surface; its descendants can disappear only through FK cascades.
CREATE TRIGGER estimator_model_artifacts_no_update BEFORE UPDATE ON estimator_model_artifacts BEGIN SELECT RAISE(ABORT, 'estimator row is immutable'); END;
CREATE TRIGGER estimator_model_weight_files_no_update BEFORE UPDATE ON estimator_model_weight_files BEGIN SELECT RAISE(ABORT, 'estimator row is immutable'); END;
CREATE TRIGGER estimator_model_tokenizer_files_no_update BEFORE UPDATE ON estimator_model_tokenizer_files BEGIN SELECT RAISE(ABORT, 'estimator row is immutable'); END;
CREATE TRIGGER estimator_metric_questions_no_update BEFORE UPDATE ON estimator_metric_questions BEGIN SELECT RAISE(ABORT, 'estimator row is immutable'); END;
CREATE TRIGGER estimator_plans_no_update BEFORE UPDATE ON estimator_plans BEGIN SELECT RAISE(ABORT, 'estimator row is immutable'); END;
CREATE TRIGGER estimator_plan_questions_no_update BEFORE UPDATE ON estimator_plan_questions BEGIN SELECT RAISE(ABORT, 'estimator row is immutable'); END;
CREATE TRIGGER estimator_plan_provider_schemas_no_update BEFORE UPDATE ON estimator_plan_provider_schemas BEGIN SELECT RAISE(ABORT, 'estimator row is immutable'); END;
CREATE TRIGGER estimator_candidate_families_no_update BEFORE UPDATE ON estimator_candidate_families BEGIN SELECT RAISE(ABORT, 'estimator row is immutable'); END;
CREATE TRIGGER estimator_candidate_models_no_update BEFORE UPDATE ON estimator_candidate_models BEGIN SELECT RAISE(ABORT, 'estimator row is immutable'); END;
CREATE TRIGGER estimator_candidate_promotions_no_update BEFORE UPDATE ON estimator_candidate_promotions BEGIN SELECT RAISE(ABORT, 'estimator row is immutable'); END;
CREATE TRIGGER estimator_candidate_baselines_no_update BEFORE UPDATE ON estimator_candidate_baselines BEGIN SELECT RAISE(ABORT, 'estimator row is immutable'); END;
CREATE TRIGGER estimator_plan_stages_no_update BEFORE UPDATE ON estimator_plan_stages BEGIN SELECT RAISE(ABORT, 'estimator row is immutable'); END;
CREATE TRIGGER estimator_synthetic_cases_no_update BEFORE UPDATE ON estimator_synthetic_cases BEGIN SELECT RAISE(ABORT, 'estimator row is immutable'); END;
CREATE TRIGGER estimator_evidence_packets_no_update BEFORE UPDATE ON estimator_evidence_packets BEGIN SELECT RAISE(ABORT, 'estimator row is immutable'); END;
CREATE TRIGGER estimator_evidence_refs_no_update BEFORE UPDATE ON estimator_evidence_refs BEGIN SELECT RAISE(ABORT, 'estimator row is immutable'); END;
CREATE TRIGGER estimator_executions_no_update BEFORE UPDATE ON estimator_executions BEGIN SELECT RAISE(ABORT, 'estimator row is immutable'); END;
CREATE TRIGGER estimator_stage_receipts_no_update BEFORE UPDATE ON estimator_stage_receipts BEGIN SELECT RAISE(ABORT, 'estimator row is immutable'); END;
CREATE TRIGGER estimator_model_runs_no_update BEFORE UPDATE ON estimator_model_runs BEGIN SELECT RAISE(ABORT, 'estimator row is immutable'); END;
CREATE TRIGGER estimator_model_votes_no_update BEFORE UPDATE ON estimator_model_votes BEGIN SELECT RAISE(ABORT, 'estimator row is immutable'); END;
CREATE TRIGGER estimator_vote_probabilities_no_update BEFORE UPDATE ON estimator_vote_probabilities BEGIN SELECT RAISE(ABORT, 'estimator row is immutable'); END;
CREATE TRIGGER estimator_vote_evidence_refs_no_update BEFORE UPDATE ON estimator_vote_evidence_refs BEGIN SELECT RAISE(ABORT, 'estimator row is immutable'); END;
CREATE TRIGGER estimator_metric_estimates_no_update BEFORE UPDATE ON estimator_metric_estimates BEGIN SELECT RAISE(ABORT, 'estimator row is immutable'); END;
CREATE TRIGGER estimator_estimate_votes_no_update BEFORE UPDATE ON estimator_estimate_votes BEGIN SELECT RAISE(ABORT, 'estimator row is immutable'); END;

-- Children are written before their validating parent.  Once the parent
-- exists, no later transaction may append rows and silently change a snapshot.
CREATE TRIGGER estimator_model_weight_files_parent_seals_insert BEFORE INSERT ON estimator_model_weight_files
WHEN EXISTS (SELECT 1 FROM estimator_model_artifacts WHERE artifact_fingerprint = NEW.artifact_fingerprint)
BEGIN SELECT RAISE(ABORT, 'estimator artifact is already sealed'); END;
CREATE TRIGGER estimator_model_tokenizer_files_parent_seals_insert BEFORE INSERT ON estimator_model_tokenizer_files
WHEN EXISTS (SELECT 1 FROM estimator_model_artifacts WHERE artifact_fingerprint = NEW.artifact_fingerprint)
BEGIN SELECT RAISE(ABORT, 'estimator artifact is already sealed'); END;
CREATE TRIGGER estimator_plan_questions_parent_seals_insert BEFORE INSERT ON estimator_plan_questions
WHEN EXISTS (SELECT 1 FROM estimator_plans WHERE plan_fingerprint = NEW.plan_fingerprint)
BEGIN SELECT RAISE(ABORT, 'estimator plan is already sealed'); END;
CREATE TRIGGER estimator_plan_provider_schemas_parent_seals_insert BEFORE INSERT ON estimator_plan_provider_schemas
WHEN EXISTS (SELECT 1 FROM estimator_plans WHERE plan_fingerprint = NEW.plan_fingerprint)
BEGIN SELECT RAISE(ABORT, 'estimator plan is already sealed'); END;
CREATE TRIGGER estimator_candidate_families_parent_seals_insert BEFORE INSERT ON estimator_candidate_families
WHEN EXISTS (SELECT 1 FROM estimator_plans WHERE plan_fingerprint = NEW.plan_fingerprint)
BEGIN SELECT RAISE(ABORT, 'estimator plan is already sealed'); END;
CREATE TRIGGER estimator_candidate_models_parent_seals_insert BEFORE INSERT ON estimator_candidate_models
WHEN EXISTS (SELECT 1 FROM estimator_candidate_families WHERE plan_fingerprint = NEW.plan_fingerprint AND family_key = NEW.family_key)
BEGIN SELECT RAISE(ABORT, 'estimator candidate family is already sealed'); END;
CREATE TRIGGER estimator_candidate_promotions_parent_seals_insert BEFORE INSERT ON estimator_candidate_promotions
WHEN EXISTS (SELECT 1 FROM estimator_candidate_families WHERE plan_fingerprint = NEW.plan_fingerprint AND family_key = NEW.family_key)
BEGIN SELECT RAISE(ABORT, 'estimator candidate family is already sealed'); END;
CREATE TRIGGER estimator_candidate_baselines_parent_seals_insert BEFORE INSERT ON estimator_candidate_baselines
WHEN EXISTS (SELECT 1 FROM estimator_candidate_families WHERE plan_fingerprint = NEW.plan_fingerprint AND family_key = NEW.family_key)
BEGIN SELECT RAISE(ABORT, 'estimator candidate family is already sealed'); END;
CREATE TRIGGER estimator_plan_stages_parent_seals_insert BEFORE INSERT ON estimator_plan_stages
WHEN EXISTS (SELECT 1 FROM estimator_plans WHERE plan_fingerprint = NEW.plan_fingerprint)
BEGIN SELECT RAISE(ABORT, 'estimator plan is already sealed'); END;
CREATE TRIGGER estimator_evidence_refs_parent_seals_insert BEFORE INSERT ON estimator_evidence_refs
WHEN EXISTS (SELECT 1 FROM estimator_evidence_packets WHERE packet_fingerprint = NEW.packet_fingerprint)
BEGIN SELECT RAISE(ABORT, 'estimator evidence receipt is already sealed'); END;
CREATE TRIGGER estimator_stage_receipts_parent_seals_insert BEFORE INSERT ON estimator_stage_receipts
WHEN EXISTS (SELECT 1 FROM estimator_executions WHERE execution_id = NEW.execution_id)
BEGIN SELECT RAISE(ABORT, 'estimator execution is already sealed'); END;
CREATE TRIGGER estimator_model_runs_parent_seals_insert BEFORE INSERT ON estimator_model_runs
WHEN EXISTS (SELECT 1 FROM estimator_executions WHERE execution_id = NEW.execution_id)
BEGIN SELECT RAISE(ABORT, 'estimator execution is already sealed'); END;
CREATE TRIGGER estimator_model_votes_parent_seals_insert BEFORE INSERT ON estimator_model_votes
WHEN EXISTS (SELECT 1 FROM estimator_executions WHERE execution_id = NEW.execution_id)
BEGIN SELECT RAISE(ABORT, 'estimator execution is already sealed'); END;
CREATE TRIGGER estimator_vote_probabilities_parent_seals_insert BEFORE INSERT ON estimator_vote_probabilities
WHEN EXISTS (SELECT 1 FROM estimator_model_votes WHERE vote_id = NEW.vote_id)
BEGIN SELECT RAISE(ABORT, 'estimator model vote is already sealed'); END;
CREATE TRIGGER estimator_vote_evidence_refs_parent_seals_insert BEFORE INSERT ON estimator_vote_evidence_refs
WHEN EXISTS (SELECT 1 FROM estimator_model_votes WHERE vote_id = NEW.vote_id)
BEGIN SELECT RAISE(ABORT, 'estimator model vote is already sealed'); END;
CREATE TRIGGER estimator_metric_estimates_parent_seals_insert BEFORE INSERT ON estimator_metric_estimates
WHEN EXISTS (SELECT 1 FROM estimator_executions WHERE execution_id = NEW.execution_id)
BEGIN SELECT RAISE(ABORT, 'estimator execution is already sealed'); END;
CREATE TRIGGER estimator_estimate_votes_parent_seals_insert BEFORE INSERT ON estimator_estimate_votes
WHEN EXISTS (SELECT 1 FROM estimator_metric_estimates WHERE estimate_id = NEW.estimate_id)
BEGIN SELECT RAISE(ABORT, 'estimator metric estimate is already sealed'); END;

CREATE TRIGGER estimator_plans_no_delete BEFORE DELETE ON estimator_plans BEGIN SELECT RAISE(ABORT, 'estimator plan is immutable'); END;
CREATE TRIGGER estimator_model_artifacts_no_delete BEFORE DELETE ON estimator_model_artifacts BEGIN SELECT RAISE(ABORT, 'estimator artifact is immutable'); END;
CREATE TRIGGER estimator_metric_questions_no_delete BEFORE DELETE ON estimator_metric_questions BEGIN SELECT RAISE(ABORT, 'estimator question is immutable'); END;
CREATE TRIGGER estimator_model_weight_files_no_delete BEFORE DELETE ON estimator_model_weight_files BEGIN SELECT RAISE(ABORT, 'estimator artifact file is immutable'); END;
CREATE TRIGGER estimator_model_tokenizer_files_no_delete BEFORE DELETE ON estimator_model_tokenizer_files BEGIN SELECT RAISE(ABORT, 'estimator artifact file is immutable'); END;
CREATE TRIGGER estimator_plan_questions_no_delete BEFORE DELETE ON estimator_plan_questions BEGIN SELECT RAISE(ABORT, 'estimator plan child is immutable'); END;
CREATE TRIGGER estimator_plan_provider_schemas_no_delete BEFORE DELETE ON estimator_plan_provider_schemas BEGIN SELECT RAISE(ABORT, 'estimator plan child is immutable'); END;
CREATE TRIGGER estimator_candidate_families_no_delete BEFORE DELETE ON estimator_candidate_families BEGIN SELECT RAISE(ABORT, 'estimator plan child is immutable'); END;
CREATE TRIGGER estimator_candidate_models_no_delete BEFORE DELETE ON estimator_candidate_models BEGIN SELECT RAISE(ABORT, 'estimator plan child is immutable'); END;
CREATE TRIGGER estimator_candidate_promotions_no_delete BEFORE DELETE ON estimator_candidate_promotions BEGIN SELECT RAISE(ABORT, 'estimator plan child is immutable'); END;
CREATE TRIGGER estimator_candidate_baselines_no_delete BEFORE DELETE ON estimator_candidate_baselines BEGIN SELECT RAISE(ABORT, 'estimator plan child is immutable'); END;
CREATE TRIGGER estimator_plan_stages_no_delete BEFORE DELETE ON estimator_plan_stages BEGIN SELECT RAISE(ABORT, 'estimator plan child is immutable'); END;
CREATE TRIGGER estimator_evidence_packets_parent_delete_only BEFORE DELETE ON estimator_evidence_packets
WHEN EXISTS (SELECT 1 FROM estimator_synthetic_cases WHERE case_id = OLD.case_id)
BEGIN SELECT RAISE(ABORT, 'estimator evidence requires parent privacy deletion'); END;
CREATE TRIGGER estimator_executions_parent_delete_only BEFORE DELETE ON estimator_executions
WHEN EXISTS (SELECT 1 FROM estimator_synthetic_cases WHERE case_id = OLD.case_id)
BEGIN SELECT RAISE(ABORT, 'estimator execution requires parent privacy deletion'); END;
CREATE TRIGGER estimator_evidence_refs_parent_delete_only BEFORE DELETE ON estimator_evidence_refs
WHEN EXISTS (SELECT 1 FROM estimator_evidence_packets WHERE packet_fingerprint = OLD.packet_fingerprint)
BEGIN SELECT RAISE(ABORT, 'estimator evidence reference requires parent privacy deletion'); END;
CREATE TRIGGER estimator_stage_receipts_parent_delete_only BEFORE DELETE ON estimator_stage_receipts
WHEN EXISTS (SELECT 1 FROM estimator_executions WHERE execution_id = OLD.execution_id)
BEGIN SELECT RAISE(ABORT, 'estimator stage receipt requires parent privacy deletion'); END;
CREATE TRIGGER estimator_model_runs_parent_delete_only BEFORE DELETE ON estimator_model_runs
WHEN EXISTS (SELECT 1 FROM estimator_executions WHERE execution_id = OLD.execution_id)
BEGIN SELECT RAISE(ABORT, 'estimator model run requires parent privacy deletion'); END;
CREATE TRIGGER estimator_model_votes_parent_delete_only BEFORE DELETE ON estimator_model_votes
WHEN EXISTS (SELECT 1 FROM estimator_executions WHERE execution_id = OLD.execution_id)
BEGIN SELECT RAISE(ABORT, 'estimator vote requires parent privacy deletion'); END;
CREATE TRIGGER estimator_vote_probabilities_parent_delete_only BEFORE DELETE ON estimator_vote_probabilities
WHEN EXISTS (SELECT 1 FROM estimator_model_votes WHERE vote_id = OLD.vote_id)
BEGIN SELECT RAISE(ABORT, 'estimator probability requires parent privacy deletion'); END;
CREATE TRIGGER estimator_vote_evidence_refs_parent_delete_only BEFORE DELETE ON estimator_vote_evidence_refs
WHEN EXISTS (SELECT 1 FROM estimator_model_votes WHERE vote_id = OLD.vote_id)
BEGIN SELECT RAISE(ABORT, 'estimator vote evidence requires parent privacy deletion'); END;
CREATE TRIGGER estimator_metric_estimates_parent_delete_only BEFORE DELETE ON estimator_metric_estimates
WHEN EXISTS (SELECT 1 FROM estimator_executions WHERE execution_id = OLD.execution_id)
BEGIN SELECT RAISE(ABORT, 'estimator estimate requires parent privacy deletion'); END;
CREATE TRIGGER estimator_estimate_votes_parent_delete_only BEFORE DELETE ON estimator_estimate_votes
WHEN EXISTS (SELECT 1 FROM estimator_metric_estimates WHERE estimate_id = OLD.estimate_id)
BEGIN SELECT RAISE(ABORT, 'estimator estimate vote requires parent privacy deletion'); END;

CREATE INDEX estimator_executions_plan_idx ON estimator_executions(plan_fingerprint, finished_at DESC);
CREATE INDEX estimator_model_runs_execution_idx ON estimator_model_runs(execution_id, stage_ordinal, run_id);
CREATE INDEX estimator_model_votes_execution_idx ON estimator_model_votes(execution_id, metric_key, vote_id);
CREATE INDEX estimator_metric_estimates_execution_idx ON estimator_metric_estimates(execution_id, metric_key, estimate_id);

COMMIT;
"""
