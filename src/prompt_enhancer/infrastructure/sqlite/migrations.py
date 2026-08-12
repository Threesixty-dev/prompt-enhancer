"""Ordered SQLite migrations added after the original Phase 1 schema."""

from __future__ import annotations

import hashlib
import json


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


MIGRATION_16 = r"""
BEGIN IMMEDIATE;

-- P1 calibration preregistration contains scalar commitments only.  No JSON,
-- BLOB, prompt, evidence body, model output, reviewer prose, or commentary is
-- permitted in this normalized schema.
CREATE TABLE estimator_gate_policies (
    policy_fingerprint TEXT PRIMARY KEY CHECK(length(policy_fingerprint) = 64 AND policy_fingerprint NOT GLOB '*[^0-9a-f]*'),
    contract_version TEXT NOT NULL CHECK(contract_version = 'gate-policy-v1'),
    policy_id TEXT NOT NULL UNIQUE CHECK(length(policy_id) = 64 AND policy_id NOT GLOB '*[^0-9a-f]*'),
    minimum_active_learning_count INTEGER NOT NULL CHECK(minimum_active_learning_count BETWEEN 100 AND 200),
    maximum_active_learning_count INTEGER NOT NULL CHECK(maximum_active_learning_count BETWEEN 100 AND 200),
    minimum_holdout_count INTEGER NOT NULL CHECK(minimum_holdout_count > 0),
    minimum_holdout_per_metric INTEGER NOT NULL CHECK(minimum_holdout_per_metric > 0),
    minimum_holdout_per_stratum INTEGER NOT NULL CHECK(minimum_holdout_per_stratum > 0),
    minimum_holdout_per_language INTEGER NOT NULL CHECK(minimum_holdout_per_language > 0),
    minimum_operational_samples_per_latency_class INTEGER NOT NULL CHECK(minimum_operational_samples_per_latency_class > 0),
    minimum_subgroup_size INTEGER NOT NULL CHECK(minimum_subgroup_size > 0),
    minimum_baseline_margin REAL NOT NULL CHECK(minimum_baseline_margin >= 0 AND minimum_baseline_margin <= 1.0e308),
    maximum_human_gap REAL NOT NULL CHECK(maximum_human_gap BETWEEN 0 AND 1),
    maximum_ece REAL NOT NULL CHECK(maximum_ece BETWEEN 0 AND 1),
    minimum_repeat_stability REAL NOT NULL CHECK(minimum_repeat_stability BETWEEN 0 AND 1),
    minimum_selective_coverage REAL NOT NULL CHECK(minimum_selective_coverage BETWEEN 0 AND 1),
    maximum_selective_risk REAL NOT NULL CHECK(maximum_selective_risk BETWEEN 0 AND 1),
    false_confidence_threshold REAL NOT NULL CHECK(false_confidence_threshold BETWEEN 0 AND 1),
    maximum_false_confident_error_rate REAL NOT NULL CHECK(maximum_false_confident_error_rate BETWEEN 0 AND 1),
    maximum_cold_p95_latency_ms REAL NOT NULL CHECK(maximum_cold_p95_latency_ms >= 0 AND maximum_cold_p95_latency_ms <= 1.0e308),
    maximum_warm_p95_latency_ms REAL NOT NULL CHECK(maximum_warm_p95_latency_ms >= 0 AND maximum_warm_p95_latency_ms <= 1.0e308),
    maximum_oom_rate REAL NOT NULL CHECK(maximum_oom_rate BETWEEN 0 AND 1),
    maximum_error_rate REAL NOT NULL CHECK(maximum_error_rate BETWEEN 0 AND 1),
    maximum_refusal_rate REAL NOT NULL CHECK(maximum_refusal_rate BETWEEN 0 AND 1),
    maximum_material_subgroup_regression REAL NOT NULL CHECK(maximum_material_subgroup_regression BETWEEN 0 AND 1),
    required_strata_count INTEGER NOT NULL CHECK(required_strata_count = 4),
    required_language_count INTEGER NOT NULL CHECK(required_language_count = 2),
    subgroup_dimension_count INTEGER NOT NULL CHECK(subgroup_dimension_count BETWEEN 1 AND 4),
    high_risk_rule_count INTEGER NOT NULL CHECK(high_risk_rule_count BETWEEN 0 AND 100),
    CHECK(minimum_active_learning_count <= maximum_active_learning_count)
);

CREATE TABLE estimator_gate_policy_strata (
    policy_fingerprint TEXT NOT NULL REFERENCES estimator_gate_policies(policy_fingerprint) ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED,
    ordinal INTEGER NOT NULL CHECK(ordinal BETWEEN 0 AND 3),
    task_stratum TEXT NOT NULL CHECK(task_stratum IN ('bug_fix', 'feature', 'code_review', 'research_design')),
    PRIMARY KEY(policy_fingerprint, ordinal),
    UNIQUE(policy_fingerprint, task_stratum)
);
CREATE TABLE estimator_gate_policy_languages (
    policy_fingerprint TEXT NOT NULL REFERENCES estimator_gate_policies(policy_fingerprint) ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED,
    ordinal INTEGER NOT NULL CHECK(ordinal BETWEEN 0 AND 1),
    language TEXT NOT NULL CHECK(language IN ('en', 'pl')),
    PRIMARY KEY(policy_fingerprint, ordinal),
    UNIQUE(policy_fingerprint, language)
);
CREATE TABLE estimator_gate_policy_subgroups (
    policy_fingerprint TEXT NOT NULL REFERENCES estimator_gate_policies(policy_fingerprint) ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED,
    ordinal INTEGER NOT NULL CHECK(ordinal BETWEEN 0 AND 3),
    dimension TEXT NOT NULL CHECK(dimension IN ('task_stratum', 'language', 'provider', 'evidence_tier')),
    PRIMARY KEY(policy_fingerprint, ordinal),
    UNIQUE(policy_fingerprint, dimension)
);
CREATE TABLE estimator_gate_policy_high_risk_rules (
    policy_fingerprint TEXT NOT NULL REFERENCES estimator_gate_policies(policy_fingerprint) ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED,
    ordinal INTEGER NOT NULL CHECK(ordinal BETWEEN 0 AND 99),
    metric_key TEXT NOT NULL CHECK(length(metric_key) BETWEEN 1 AND 64 AND metric_key GLOB '[a-z0-9]*' AND metric_key NOT GLOB '*[^a-z0-9._-]*'),
    minimum_precision REAL NOT NULL CHECK(minimum_precision BETWEEN 0 AND 1),
    minimum_positive_predictions INTEGER NOT NULL CHECK(minimum_positive_predictions > 0),
    PRIMARY KEY(policy_fingerprint, ordinal),
    UNIQUE(policy_fingerprint, metric_key)
);

CREATE TRIGGER estimator_gate_policies_validate_children BEFORE INSERT ON estimator_gate_policies
WHEN NEW.required_strata_count <> (SELECT COUNT(*) FROM estimator_gate_policy_strata WHERE policy_fingerprint = NEW.policy_fingerprint)
 OR NEW.required_language_count <> (SELECT COUNT(*) FROM estimator_gate_policy_languages WHERE policy_fingerprint = NEW.policy_fingerprint)
 OR NEW.subgroup_dimension_count <> (SELECT COUNT(*) FROM estimator_gate_policy_subgroups WHERE policy_fingerprint = NEW.policy_fingerprint)
 OR NEW.high_risk_rule_count <> (SELECT COUNT(*) FROM estimator_gate_policy_high_risk_rules WHERE policy_fingerprint = NEW.policy_fingerprint)
 OR NOT EXISTS (SELECT 1 FROM estimator_gate_policy_strata WHERE policy_fingerprint = NEW.policy_fingerprint AND ordinal = 0 AND task_stratum = 'bug_fix')
 OR NOT EXISTS (SELECT 1 FROM estimator_gate_policy_strata WHERE policy_fingerprint = NEW.policy_fingerprint AND ordinal = 1 AND task_stratum = 'feature')
 OR NOT EXISTS (SELECT 1 FROM estimator_gate_policy_strata WHERE policy_fingerprint = NEW.policy_fingerprint AND ordinal = 2 AND task_stratum = 'code_review')
 OR NOT EXISTS (SELECT 1 FROM estimator_gate_policy_strata WHERE policy_fingerprint = NEW.policy_fingerprint AND ordinal = 3 AND task_stratum = 'research_design')
 OR NOT EXISTS (SELECT 1 FROM estimator_gate_policy_languages WHERE policy_fingerprint = NEW.policy_fingerprint AND ordinal = 0 AND language = 'en')
 OR NOT EXISTS (SELECT 1 FROM estimator_gate_policy_languages WHERE policy_fingerprint = NEW.policy_fingerprint AND ordinal = 1 AND language = 'pl')
BEGIN SELECT RAISE(ABORT, 'estimator gate policy children are inconsistent'); END;

-- A campaign may bind a plan written under v15, whose general-purpose version
-- grammar is intentionally broader. This sealed audit projects every bound
-- TEXT identifier into one SQL-computable surface and applies v16's stricter
-- no-colon/no-control/no-traversal policy before any campaign root can exist.
CREATE VIEW estimator_gate_bound_plan_artifacts AS
SELECT plan_fingerprint, artifact_fingerprint
FROM estimator_plan_stages WHERE artifact_fingerprint IS NOT NULL
UNION
SELECT plan_fingerprint, artifact_fingerprint FROM estimator_candidate_models;

CREATE VIEW estimator_gate_bound_plan_identifier_values AS
SELECT plan_fingerprint, plan_fingerprint AS value FROM estimator_plans
UNION ALL SELECT plan_fingerprint, contract_version FROM estimator_plans
UNION ALL SELECT plan_fingerprint, plan_key FROM estimator_plans
UNION ALL SELECT plan_fingerprint, plan_version FROM estimator_plans
UNION ALL SELECT plan_fingerprint, evidence_packet_schema_version FROM estimator_plans
UNION ALL SELECT plan_fingerprint, preprocessing_version FROM estimator_plans
UNION ALL SELECT plan_fingerprint, preprocessing_sha256 FROM estimator_plans
UNION ALL SELECT plan_fingerprint, calibration_version FROM estimator_plans
UNION ALL SELECT plan_fingerprint, calibration_sha256 FROM estimator_plans
UNION ALL SELECT plan_fingerprint, router_version FROM estimator_plans
UNION ALL SELECT plan_fingerprint, router_sha256 FROM estimator_plans
UNION ALL SELECT plan_fingerprint, redactor_version FROM estimator_plans
UNION ALL SELECT plan_fingerprint, redactor_sha256 FROM estimator_plans
UNION ALL SELECT plan_fingerprint, execution_mode FROM estimator_plans
UNION ALL SELECT plan_fingerprint, model_load_policy FROM estimator_plans
UNION ALL SELECT link.plan_fingerprint, link.question_fingerprint FROM estimator_plan_questions AS link
UNION ALL SELECT link.plan_fingerprint, question.contract_version FROM estimator_plan_questions AS link JOIN estimator_metric_questions AS question USING(question_fingerprint)
UNION ALL SELECT link.plan_fingerprint, question.metric_key FROM estimator_plan_questions AS link JOIN estimator_metric_questions AS question USING(question_fingerprint)
UNION ALL SELECT link.plan_fingerprint, question.metric_definition_version FROM estimator_plan_questions AS link JOIN estimator_metric_questions AS question USING(question_fingerprint)
UNION ALL SELECT link.plan_fingerprint, question.question_id FROM estimator_plan_questions AS link JOIN estimator_metric_questions AS question USING(question_fingerprint)
UNION ALL SELECT link.plan_fingerprint, question.question_version FROM estimator_plan_questions AS link JOIN estimator_metric_questions AS question USING(question_fingerprint)
UNION ALL SELECT link.plan_fingerprint, question.question_sha256 FROM estimator_plan_questions AS link JOIN estimator_metric_questions AS question USING(question_fingerprint)
UNION ALL SELECT link.plan_fingerprint, question.prompt_template_id FROM estimator_plan_questions AS link JOIN estimator_metric_questions AS question USING(question_fingerprint)
UNION ALL SELECT link.plan_fingerprint, question.prompt_template_version FROM estimator_plan_questions AS link JOIN estimator_metric_questions AS question USING(question_fingerprint)
UNION ALL SELECT link.plan_fingerprint, question.prompt_template_sha256 FROM estimator_plan_questions AS link JOIN estimator_metric_questions AS question USING(question_fingerprint)
UNION ALL SELECT link.plan_fingerprint, question.rubric_id FROM estimator_plan_questions AS link JOIN estimator_metric_questions AS question USING(question_fingerprint)
UNION ALL SELECT link.plan_fingerprint, question.rubric_version FROM estimator_plan_questions AS link JOIN estimator_metric_questions AS question USING(question_fingerprint)
UNION ALL SELECT link.plan_fingerprint, question.rubric_sha256 FROM estimator_plan_questions AS link JOIN estimator_metric_questions AS question USING(question_fingerprint)
UNION ALL SELECT link.plan_fingerprint, question.output_schema_version FROM estimator_plan_questions AS link JOIN estimator_metric_questions AS question USING(question_fingerprint)
UNION ALL SELECT link.plan_fingerprint, question.unit_code FROM estimator_plan_questions AS link JOIN estimator_metric_questions AS question USING(question_fingerprint)
UNION ALL SELECT plan_fingerprint, provider FROM estimator_plan_provider_schemas
UNION ALL SELECT plan_fingerprint, adapter_version FROM estimator_plan_provider_schemas
UNION ALL SELECT plan_fingerprint, provider_schema_version FROM estimator_plan_provider_schemas
UNION ALL SELECT plan_fingerprint, family_key FROM estimator_candidate_families
UNION ALL SELECT plan_fingerprint, artifact_fingerprint FROM estimator_candidate_models
UNION ALL SELECT plan_fingerprint, artifact_fingerprint FROM estimator_candidate_promotions
UNION ALL SELECT plan_fingerprint, baseline_id FROM estimator_candidate_baselines
UNION ALL SELECT plan_fingerprint, kind FROM estimator_plan_stages
UNION ALL SELECT plan_fingerprint, condition_code FROM estimator_plan_stages
UNION ALL SELECT plan_fingerprint, component_version FROM estimator_plan_stages
UNION ALL SELECT plan_fingerprint, configuration_sha256 FROM estimator_plan_stages
UNION ALL SELECT plan_fingerprint, output_schema_version FROM estimator_plan_stages
UNION ALL SELECT plan_fingerprint, artifact_fingerprint FROM estimator_plan_stages WHERE artifact_fingerprint IS NOT NULL
UNION ALL SELECT plan_fingerprint, candidate_family_key FROM estimator_plan_stages WHERE candidate_family_key IS NOT NULL
UNION ALL SELECT bound.plan_fingerprint, artifact.artifact_fingerprint FROM estimator_gate_bound_plan_artifacts AS bound JOIN estimator_model_artifacts AS artifact USING(artifact_fingerprint)
UNION ALL SELECT bound.plan_fingerprint, artifact.contract_version FROM estimator_gate_bound_plan_artifacts AS bound JOIN estimator_model_artifacts AS artifact USING(artifact_fingerprint)
UNION ALL SELECT bound.plan_fingerprint, artifact.source FROM estimator_gate_bound_plan_artifacts AS bound JOIN estimator_model_artifacts AS artifact USING(artifact_fingerprint)
UNION ALL SELECT bound.plan_fingerprint, artifact.requested_model_id FROM estimator_gate_bound_plan_artifacts AS bound JOIN estimator_model_artifacts AS artifact USING(artifact_fingerprint)
UNION ALL SELECT bound.plan_fingerprint, artifact.served_model_id FROM estimator_gate_bound_plan_artifacts AS bound JOIN estimator_model_artifacts AS artifact USING(artifact_fingerprint)
UNION ALL SELECT bound.plan_fingerprint, artifact.requested_revision FROM estimator_gate_bound_plan_artifacts AS bound JOIN estimator_model_artifacts AS artifact USING(artifact_fingerprint)
UNION ALL SELECT bound.plan_fingerprint, artifact.served_revision FROM estimator_gate_bound_plan_artifacts AS bound JOIN estimator_model_artifacts AS artifact USING(artifact_fingerprint)
UNION ALL SELECT bound.plan_fingerprint, artifact.requested_execution_mode FROM estimator_gate_bound_plan_artifacts AS bound JOIN estimator_model_artifacts AS artifact USING(artifact_fingerprint)
UNION ALL SELECT bound.plan_fingerprint, artifact.served_execution_mode FROM estimator_gate_bound_plan_artifacts AS bound JOIN estimator_model_artifacts AS artifact USING(artifact_fingerprint)
UNION ALL SELECT bound.plan_fingerprint, artifact.weight_availability FROM estimator_gate_bound_plan_artifacts AS bound JOIN estimator_model_artifacts AS artifact USING(artifact_fingerprint)
UNION ALL SELECT bound.plan_fingerprint, artifact.tokenizer_id FROM estimator_gate_bound_plan_artifacts AS bound JOIN estimator_model_artifacts AS artifact USING(artifact_fingerprint)
UNION ALL SELECT bound.plan_fingerprint, artifact.tokenizer_revision FROM estimator_gate_bound_plan_artifacts AS bound JOIN estimator_model_artifacts AS artifact USING(artifact_fingerprint)
UNION ALL SELECT bound.plan_fingerprint, artifact.tokenizer_availability FROM estimator_gate_bound_plan_artifacts AS bound JOIN estimator_model_artifacts AS artifact USING(artifact_fingerprint)
UNION ALL SELECT bound.plan_fingerprint, artifact.license_id FROM estimator_gate_bound_plan_artifacts AS bound JOIN estimator_model_artifacts AS artifact USING(artifact_fingerprint)
UNION ALL SELECT bound.plan_fingerprint, weight.file_name FROM estimator_gate_bound_plan_artifacts AS bound JOIN estimator_model_weight_files AS weight USING(artifact_fingerprint)
UNION ALL SELECT bound.plan_fingerprint, weight.sha256 FROM estimator_gate_bound_plan_artifacts AS bound JOIN estimator_model_weight_files AS weight USING(artifact_fingerprint)
UNION ALL SELECT bound.plan_fingerprint, tokenizer.file_name FROM estimator_gate_bound_plan_artifacts AS bound JOIN estimator_model_tokenizer_files AS tokenizer USING(artifact_fingerprint)
UNION ALL SELECT bound.plan_fingerprint, tokenizer.sha256 FROM estimator_gate_bound_plan_artifacts AS bound JOIN estimator_model_tokenizer_files AS tokenizer USING(artifact_fingerprint);

CREATE TABLE estimator_gate_safe_plan_audits (
    plan_fingerprint TEXT PRIMARY KEY REFERENCES estimator_plans(plan_fingerprint) DEFERRABLE INITIALLY DEFERRED
);
CREATE TRIGGER estimator_gate_safe_plan_audits_validate BEFORE INSERT ON estimator_gate_safe_plan_audits
WHEN NOT EXISTS (SELECT 1 FROM estimator_plans WHERE plan_fingerprint = NEW.plan_fingerprint)
 OR EXISTS (
    SELECT 1 FROM estimator_gate_bound_plan_identifier_values AS identifier
    WHERE identifier.plan_fingerprint = NEW.plan_fingerprint AND (
        identifier.value GLOB '/*'
        OR instr(identifier.value, ':') > 0
        OR instr(identifier.value, '\') > 0
        OR instr(identifier.value, '..') > 0
        OR EXISTS (
            WITH RECURSIVE controls(code) AS (
                SELECT 0 UNION ALL SELECT code + 1 FROM controls WHERE code < 31
            )
            SELECT 1 FROM controls
            WHERE instr(identifier.value, char(code)) > 0
        )
        OR instr(identifier.value, char(127)) > 0
    )
 )
 OR (SELECT question_count FROM estimator_plans WHERE plan_fingerprint = NEW.plan_fingerprint) <> (
    SELECT COUNT(DISTINCT question.metric_key)
    FROM estimator_plan_questions AS link
    JOIN estimator_metric_questions AS question USING(question_fingerprint)
    WHERE link.plan_fingerprint = NEW.plan_fingerprint
 )
 OR (SELECT provider_schema_count FROM estimator_plans WHERE plan_fingerprint = NEW.plan_fingerprint) <> 1
BEGIN SELECT RAISE(ABORT, 'estimator plan is unsafe for a v16 campaign'); END;
CREATE TRIGGER estimator_gate_safe_plan_audits_no_update BEFORE UPDATE ON estimator_gate_safe_plan_audits BEGIN SELECT RAISE(ABORT, 'estimator safe-plan audit is immutable'); END;
CREATE TRIGGER estimator_gate_safe_plan_audits_no_delete BEFORE DELETE ON estimator_gate_safe_plan_audits BEGIN SELECT RAISE(ABORT, 'estimator safe-plan audit is retained'); END;

CREATE TABLE estimator_case_manifests_v2 (
    manifest_fingerprint TEXT PRIMARY KEY CHECK(length(manifest_fingerprint) = 64 AND manifest_fingerprint NOT GLOB '*[^0-9a-f]*'),
    contract_version TEXT NOT NULL CHECK(contract_version = 'case-assignment-manifest-v2'),
    manifest_id TEXT NOT NULL UNIQUE CHECK(length(manifest_id) = 64 AND manifest_id NOT GLOB '*[^0-9a-f]*'),
    plan_fingerprint TEXT NOT NULL REFERENCES estimator_plans(plan_fingerprint) DEFERRABLE INITIALLY DEFERRED,
    frozen_at TEXT NOT NULL,
    assignment_count INTEGER NOT NULL CHECK(assignment_count BETWEEN 1 AND 1000000)
);
CREATE TABLE estimator_case_assignments_v2 (
    manifest_fingerprint TEXT NOT NULL REFERENCES estimator_case_manifests_v2(manifest_fingerprint) ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED,
    ordinal INTEGER NOT NULL CHECK(ordinal BETWEEN 0 AND 999999),
    contract_version TEXT NOT NULL CHECK(contract_version = 'case-assignment-v2'),
    case_id TEXT NOT NULL CHECK(length(case_id) = 64 AND case_id NOT GLOB '*[^0-9a-f]*'),
    project_id TEXT NOT NULL CHECK(length(project_id) = 64 AND project_id NOT GLOB '*[^0-9a-f]*'),
    session_revision_id TEXT NOT NULL CHECK(length(session_revision_id) = 64 AND session_revision_id NOT GLOB '*[^0-9a-f]*'),
    metric_key TEXT NOT NULL CHECK(length(metric_key) BETWEEN 1 AND 64 AND metric_key GLOB '[a-z0-9]*' AND metric_key NOT GLOB '*[^a-z0-9._-]*'),
    provider TEXT NOT NULL CHECK(provider IN ('codex', 'claude_code', 'synthetic')),
    origin TEXT NOT NULL CHECK(origin IN ('private_representative', 'public_benchmark', 'synthetic')),
    task_stratum TEXT NOT NULL CHECK(task_stratum IN ('bug_fix', 'feature', 'code_review', 'research_design')),
    language TEXT NOT NULL CHECK(language IN ('en', 'pl')),
    evidence_tier TEXT NOT NULL CHECK(evidence_tier IN ('objective', 'human', 'inferred')),
    observed_at TEXT NOT NULL,
    plan_fingerprint TEXT NOT NULL REFERENCES estimator_plans(plan_fingerprint) DEFERRABLE INITIALLY DEFERRED,
    metric_question_fingerprint TEXT NOT NULL REFERENCES estimator_metric_questions(question_fingerprint) DEFERRABLE INITIALLY DEFERRED,
    evidence_packet_fingerprint TEXT NOT NULL CHECK(length(evidence_packet_fingerprint) = 64 AND evidence_packet_fingerprint NOT GLOB '*[^0-9a-f]*'),
    PRIMARY KEY(manifest_fingerprint, ordinal),
    UNIQUE(manifest_fingerprint, case_id)
);
CREATE TRIGGER estimator_case_manifests_v2_validate_children BEFORE INSERT ON estimator_case_manifests_v2
WHEN julianday(NEW.frozen_at) IS NULL
 OR NEW.assignment_count <> (SELECT COUNT(*) FROM estimator_case_assignments_v2 WHERE manifest_fingerprint = NEW.manifest_fingerprint)
 OR EXISTS (SELECT 1 FROM estimator_case_assignments_v2 AS item WHERE item.manifest_fingerprint = NEW.manifest_fingerprint AND (item.plan_fingerprint <> NEW.plan_fingerprint OR julianday(item.observed_at) IS NULL OR item.observed_at > NEW.frozen_at OR NOT EXISTS (SELECT 1 FROM estimator_plan_questions AS plan_question JOIN estimator_metric_questions AS question ON question.question_fingerprint = plan_question.question_fingerprint WHERE plan_question.plan_fingerprint = NEW.plan_fingerprint AND plan_question.question_fingerprint = item.metric_question_fingerprint AND question.metric_key = item.metric_key)))
 OR EXISTS (SELECT 1 FROM estimator_case_assignments_v2 AS earlier JOIN estimator_case_assignments_v2 AS later ON later.manifest_fingerprint = earlier.manifest_fingerprint AND later.ordinal > earlier.ordinal WHERE earlier.manifest_fingerprint = NEW.manifest_fingerprint AND earlier.case_id >= later.case_id)
BEGIN SELECT RAISE(ABORT, 'estimator case manifest children are inconsistent'); END;

CREATE TABLE estimator_calibration_splits (
    split_fingerprint TEXT PRIMARY KEY CHECK(length(split_fingerprint) = 64 AND split_fingerprint NOT GLOB '*[^0-9a-f]*'),
    contract_version TEXT NOT NULL CHECK(contract_version = 'calibration-split-v1'),
    split_id TEXT NOT NULL UNIQUE CHECK(length(split_id) = 64 AND split_id NOT GLOB '*[^0-9a-f]*'),
    assignment_manifest_fingerprint TEXT NOT NULL REFERENCES estimator_case_manifests_v2(manifest_fingerprint) DEFERRABLE INITIALLY DEFERRED,
    frozen_at TEXT NOT NULL,
    development_count INTEGER NOT NULL CHECK(development_count BETWEEN 0 AND 1000000),
    active_learning_count INTEGER NOT NULL CHECK(active_learning_count BETWEEN 1 AND 1000000),
    holdout_count INTEGER NOT NULL CHECK(holdout_count BETWEEN 1 AND 1000000)
);
CREATE TABLE estimator_calibration_split_cases (
    split_fingerprint TEXT NOT NULL REFERENCES estimator_calibration_splits(split_fingerprint) ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED,
    partition_code TEXT NOT NULL CHECK(partition_code IN ('development', 'active_learning', 'holdout')),
    ordinal INTEGER NOT NULL CHECK(ordinal BETWEEN 0 AND 999999),
    case_id TEXT NOT NULL CHECK(length(case_id) = 64 AND case_id NOT GLOB '*[^0-9a-f]*'),
    PRIMARY KEY(split_fingerprint, partition_code, ordinal),
    UNIQUE(split_fingerprint, case_id)
);
CREATE TRIGGER estimator_calibration_splits_validate_children BEFORE INSERT ON estimator_calibration_splits
WHEN julianday(NEW.frozen_at) IS NULL
 OR NEW.frozen_at < (SELECT frozen_at FROM estimator_case_manifests_v2 WHERE manifest_fingerprint = NEW.assignment_manifest_fingerprint)
 OR NEW.development_count <> (SELECT COUNT(*) FROM estimator_calibration_split_cases WHERE split_fingerprint = NEW.split_fingerprint AND partition_code = 'development')
 OR NEW.active_learning_count <> (SELECT COUNT(*) FROM estimator_calibration_split_cases WHERE split_fingerprint = NEW.split_fingerprint AND partition_code = 'active_learning')
 OR NEW.holdout_count <> (SELECT COUNT(*) FROM estimator_calibration_split_cases WHERE split_fingerprint = NEW.split_fingerprint AND partition_code = 'holdout')
 OR EXISTS (SELECT 1 FROM estimator_calibration_split_cases AS earlier JOIN estimator_calibration_split_cases AS later ON later.split_fingerprint = earlier.split_fingerprint AND later.partition_code = earlier.partition_code AND later.ordinal > earlier.ordinal WHERE earlier.split_fingerprint = NEW.split_fingerprint AND earlier.case_id >= later.case_id)
 OR EXISTS (SELECT 1 FROM estimator_calibration_split_cases AS item WHERE item.split_fingerprint = NEW.split_fingerprint AND NOT EXISTS (SELECT 1 FROM estimator_case_assignments_v2 AS assignment WHERE assignment.manifest_fingerprint = NEW.assignment_manifest_fingerprint AND assignment.case_id = item.case_id))
 OR EXISTS (SELECT 1 FROM estimator_case_assignments_v2 AS assignment WHERE assignment.manifest_fingerprint = NEW.assignment_manifest_fingerprint AND NOT EXISTS (SELECT 1 FROM estimator_calibration_split_cases AS item WHERE item.split_fingerprint = NEW.split_fingerprint AND item.case_id = assignment.case_id))
BEGIN SELECT RAISE(ABORT, 'estimator calibration split children are inconsistent'); END;

CREATE TABLE estimator_legacy_preregistrations (
    preregistration_fingerprint TEXT PRIMARY KEY CHECK(length(preregistration_fingerprint) = 64 AND preregistration_fingerprint NOT GLOB '*[^0-9a-f]*'),
    contract_version TEXT NOT NULL CHECK(contract_version = 'gate-preregistration-v1'),
    preregistration_id TEXT NOT NULL UNIQUE CHECK(length(preregistration_id) = 64 AND preregistration_id NOT GLOB '*[^0-9a-f]*'),
    policy_fingerprint TEXT NOT NULL REFERENCES estimator_gate_policies(policy_fingerprint) DEFERRABLE INITIALLY DEFERRED,
    assignment_manifest_fingerprint TEXT NOT NULL REFERENCES estimator_case_manifests_v2(manifest_fingerprint) DEFERRABLE INITIALLY DEFERRED,
    split_fingerprint TEXT NOT NULL REFERENCES estimator_calibration_splits(split_fingerprint) DEFERRABLE INITIALLY DEFERRED,
    estimator_identity_fingerprint TEXT NOT NULL CHECK(length(estimator_identity_fingerprint) = 64 AND estimator_identity_fingerprint NOT GLOB '*[^0-9a-f]*'),
    registered_at TEXT NOT NULL,
    metric_spec_count INTEGER NOT NULL CHECK(metric_spec_count BETWEEN 1 AND 100)
);
CREATE TABLE estimator_legacy_metric_specs (
    preregistration_fingerprint TEXT NOT NULL REFERENCES estimator_legacy_preregistrations(preregistration_fingerprint) ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED,
    ordinal INTEGER NOT NULL CHECK(ordinal BETWEEN 0 AND 99),
    metric_key TEXT NOT NULL CHECK(length(metric_key) BETWEEN 1 AND 64 AND metric_key GLOB '[a-z0-9]*' AND metric_key NOT GLOB '*[^a-z0-9._-]*'),
    risk_tier TEXT NOT NULL CHECK(risk_tier IN ('standard', 'high')),
    positive_label TEXT CHECK(positive_label IS NULL OR (length(positive_label) BETWEEN 1 AND 64 AND positive_label GLOB '[a-z0-9]*' AND positive_label NOT GLOB '*[^a-z0-9._-]*')),
    label_count INTEGER NOT NULL CHECK(label_count BETWEEN 2 AND 100),
    PRIMARY KEY(preregistration_fingerprint, ordinal),
    UNIQUE(preregistration_fingerprint, metric_key),
    CHECK((risk_tier = 'high' AND positive_label IS NOT NULL) OR (risk_tier = 'standard' AND positive_label IS NULL))
);
CREATE TABLE estimator_legacy_metric_labels (
    preregistration_fingerprint TEXT NOT NULL,
    metric_key TEXT NOT NULL,
    ordinal INTEGER NOT NULL CHECK(ordinal BETWEEN 0 AND 99),
    label_code TEXT NOT NULL CHECK(length(label_code) BETWEEN 1 AND 64 AND label_code GLOB '[a-z0-9]*' AND label_code NOT GLOB '*[^a-z0-9._-]*'),
    PRIMARY KEY(preregistration_fingerprint, metric_key, ordinal),
    UNIQUE(preregistration_fingerprint, metric_key, label_code),
    FOREIGN KEY(preregistration_fingerprint, metric_key) REFERENCES estimator_legacy_metric_specs(preregistration_fingerprint, metric_key) ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED
);
CREATE TRIGGER estimator_legacy_metric_specs_validate_children BEFORE INSERT ON estimator_legacy_metric_specs
WHEN NEW.label_count <> (SELECT COUNT(*) FROM estimator_legacy_metric_labels WHERE preregistration_fingerprint = NEW.preregistration_fingerprint AND metric_key = NEW.metric_key)
 OR (NEW.positive_label IS NOT NULL AND NOT EXISTS (SELECT 1 FROM estimator_legacy_metric_labels WHERE preregistration_fingerprint = NEW.preregistration_fingerprint AND metric_key = NEW.metric_key AND label_code = NEW.positive_label))
 OR EXISTS (SELECT 1 FROM estimator_legacy_metric_labels AS earlier JOIN estimator_legacy_metric_labels AS later ON later.preregistration_fingerprint = earlier.preregistration_fingerprint AND later.metric_key = earlier.metric_key AND later.ordinal > earlier.ordinal WHERE earlier.preregistration_fingerprint = NEW.preregistration_fingerprint AND earlier.metric_key = NEW.metric_key AND earlier.label_code >= later.label_code)
BEGIN SELECT RAISE(ABORT, 'estimator legacy metric labels are inconsistent'); END;
CREATE TRIGGER estimator_legacy_preregistrations_validate_children BEFORE INSERT ON estimator_legacy_preregistrations
WHEN julianday(NEW.registered_at) IS NULL
 OR NEW.metric_spec_count <> (SELECT COUNT(*) FROM estimator_legacy_metric_specs WHERE preregistration_fingerprint = NEW.preregistration_fingerprint)
 OR NEW.assignment_manifest_fingerprint <> (SELECT assignment_manifest_fingerprint FROM estimator_calibration_splits WHERE split_fingerprint = NEW.split_fingerprint)
 OR NEW.registered_at < (SELECT frozen_at FROM estimator_calibration_splits WHERE split_fingerprint = NEW.split_fingerprint)
 OR EXISTS (SELECT 1 FROM estimator_legacy_metric_specs AS spec WHERE spec.preregistration_fingerprint = NEW.preregistration_fingerprint AND NOT EXISTS (SELECT 1 FROM estimator_case_assignments_v2 AS assignment WHERE assignment.manifest_fingerprint = NEW.assignment_manifest_fingerprint AND assignment.metric_key = spec.metric_key))
 OR EXISTS (SELECT 1 FROM estimator_case_assignments_v2 AS assignment WHERE assignment.manifest_fingerprint = NEW.assignment_manifest_fingerprint AND NOT EXISTS (SELECT 1 FROM estimator_legacy_metric_specs AS spec WHERE spec.preregistration_fingerprint = NEW.preregistration_fingerprint AND spec.metric_key = assignment.metric_key))
 OR EXISTS (SELECT 1 FROM estimator_legacy_metric_specs AS spec WHERE spec.preregistration_fingerprint = NEW.preregistration_fingerprint AND ((spec.risk_tier = 'high' AND NOT EXISTS (SELECT 1 FROM estimator_gate_policy_high_risk_rules AS rule WHERE rule.policy_fingerprint = NEW.policy_fingerprint AND rule.metric_key = spec.metric_key)) OR (spec.risk_tier = 'standard' AND EXISTS (SELECT 1 FROM estimator_gate_policy_high_risk_rules AS rule WHERE rule.policy_fingerprint = NEW.policy_fingerprint AND rule.metric_key = spec.metric_key))))
 OR EXISTS (SELECT 1 FROM estimator_gate_policy_high_risk_rules AS rule WHERE rule.policy_fingerprint = NEW.policy_fingerprint AND NOT EXISTS (SELECT 1 FROM estimator_legacy_metric_specs AS spec WHERE spec.preregistration_fingerprint = NEW.preregistration_fingerprint AND spec.metric_key = rule.metric_key AND spec.risk_tier = 'high'))
 OR EXISTS (SELECT 1 FROM estimator_legacy_metric_specs AS earlier JOIN estimator_legacy_metric_specs AS later ON later.preregistration_fingerprint = earlier.preregistration_fingerprint AND later.ordinal > earlier.ordinal WHERE earlier.preregistration_fingerprint = NEW.preregistration_fingerprint AND earlier.metric_key >= later.metric_key)
BEGIN SELECT RAISE(ABORT, 'estimator legacy preregistration children are inconsistent'); END;

CREATE TABLE estimator_constellations (
    constellation_fingerprint TEXT PRIMARY KEY CHECK(length(constellation_fingerprint) = 64 AND constellation_fingerprint NOT GLOB '*[^0-9a-f]*'),
    contract_version TEXT NOT NULL CHECK(contract_version = 'constellation-identity-receipt-v1'),
    constellation_id TEXT NOT NULL UNIQUE CHECK(length(constellation_id) = 64 AND constellation_id NOT GLOB '*[^0-9a-f]*'),
    plan_fingerprint TEXT NOT NULL REFERENCES estimator_plans(plan_fingerprint) DEFERRABLE INITIALLY DEFERRED,
    frozen_at TEXT NOT NULL,
    stage_count INTEGER NOT NULL CHECK(stage_count BETWEEN 1 AND 4)
);
CREATE TABLE estimator_constellation_stages (
    constellation_fingerprint TEXT NOT NULL REFERENCES estimator_constellations(constellation_fingerprint) ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED,
    ordinal INTEGER NOT NULL CHECK(ordinal BETWEEN 1 AND 7),
    contract_version TEXT NOT NULL CHECK(contract_version = 'constellation-stage-identity-v1'),
    kind TEXT NOT NULL CHECK(kind IN ('embedding_retrieval', 'reranker', 'specialist', 'second_opinion')),
    source TEXT NOT NULL CHECK(source IN ('local_weights', 'openai_api', 'anthropic_api', 'codex_cli', 'claude_cli')),
    stage_fingerprint TEXT NOT NULL CHECK(length(stage_fingerprint) = 64 AND stage_fingerprint NOT GLOB '*[^0-9a-f]*'),
    model_artifact_fingerprint TEXT NOT NULL REFERENCES estimator_model_artifacts(artifact_fingerprint) DEFERRABLE INITIALLY DEFERRED,
    stage_configuration_sha256 TEXT NOT NULL CHECK(length(stage_configuration_sha256) = 64 AND stage_configuration_sha256 NOT GLOB '*[^0-9a-f]*'),
    component_version TEXT NOT NULL CHECK(length(component_version) BETWEEN 1 AND 128),
    output_schema_version TEXT NOT NULL CHECK(length(output_schema_version) BETWEEN 1 AND 128),
    PRIMARY KEY(constellation_fingerprint, ordinal),
    UNIQUE(constellation_fingerprint, stage_fingerprint)
);
CREATE TRIGGER estimator_constellations_validate_children BEFORE INSERT ON estimator_constellations
WHEN julianday(NEW.frozen_at) IS NULL
 OR NEW.stage_count <> (SELECT COUNT(*) FROM estimator_constellation_stages WHERE constellation_fingerprint = NEW.constellation_fingerprint)
 OR NEW.stage_count <> (SELECT COUNT(*) FROM estimator_plan_stages WHERE plan_fingerprint = NEW.plan_fingerprint AND artifact_fingerprint IS NOT NULL)
 OR EXISTS (SELECT 1 FROM estimator_constellation_stages AS identity LEFT JOIN estimator_plan_stages AS stage ON stage.plan_fingerprint = NEW.plan_fingerprint AND stage.ordinal = identity.ordinal LEFT JOIN estimator_model_artifacts AS artifact ON artifact.artifact_fingerprint = identity.model_artifact_fingerprint WHERE identity.constellation_fingerprint = NEW.constellation_fingerprint AND (stage.ordinal IS NULL OR stage.kind <> identity.kind OR stage.artifact_fingerprint <> identity.model_artifact_fingerprint OR stage.configuration_sha256 <> identity.stage_configuration_sha256 OR stage.component_version <> identity.component_version OR stage.output_schema_version <> identity.output_schema_version OR artifact.source <> identity.source))
 OR EXISTS (SELECT 1 FROM estimator_plan_stages AS stage WHERE stage.plan_fingerprint = NEW.plan_fingerprint AND stage.artifact_fingerprint IS NOT NULL AND NOT EXISTS (SELECT 1 FROM estimator_constellation_stages AS identity WHERE identity.constellation_fingerprint = NEW.constellation_fingerprint AND identity.ordinal = stage.ordinal))
BEGIN SELECT RAISE(ABORT, 'estimator constellation children are inconsistent'); END;

CREATE TABLE estimator_preregistrations_v2 (
    preregistration_fingerprint TEXT PRIMARY KEY CHECK(length(preregistration_fingerprint) = 64 AND preregistration_fingerprint NOT GLOB '*[^0-9a-f]*'),
    contract_version TEXT NOT NULL CHECK(contract_version = 'gate-preregistration-v2'),
    preregistration_id TEXT NOT NULL UNIQUE CHECK(length(preregistration_id) = 64 AND preregistration_id NOT GLOB '*[^0-9a-f]*'),
    policy_fingerprint TEXT NOT NULL REFERENCES estimator_gate_policies(policy_fingerprint) DEFERRABLE INITIALLY DEFERRED,
    assignment_manifest_fingerprint TEXT NOT NULL REFERENCES estimator_case_manifests_v2(manifest_fingerprint) DEFERRABLE INITIALLY DEFERRED,
    split_fingerprint TEXT NOT NULL REFERENCES estimator_calibration_splits(split_fingerprint) DEFERRABLE INITIALLY DEFERRED,
    stored_plan_fingerprint TEXT NOT NULL REFERENCES estimator_plans(plan_fingerprint) DEFERRABLE INITIALLY DEFERRED,
    constellation_fingerprint TEXT NOT NULL REFERENCES estimator_constellations(constellation_fingerprint) DEFERRABLE INITIALLY DEFERRED,
    legacy_preregistration_fingerprint TEXT NOT NULL REFERENCES estimator_legacy_preregistrations(preregistration_fingerprint) DEFERRABLE INITIALLY DEFERRED,
    registered_at TEXT NOT NULL
);
CREATE TRIGGER estimator_preregistrations_v2_validate_lineage BEFORE INSERT ON estimator_preregistrations_v2
WHEN julianday(NEW.registered_at) IS NULL
 OR NEW.assignment_manifest_fingerprint <> (SELECT assignment_manifest_fingerprint FROM estimator_calibration_splits WHERE split_fingerprint = NEW.split_fingerprint)
 OR NEW.stored_plan_fingerprint <> (SELECT plan_fingerprint FROM estimator_case_manifests_v2 WHERE manifest_fingerprint = NEW.assignment_manifest_fingerprint)
 OR NEW.stored_plan_fingerprint <> (SELECT plan_fingerprint FROM estimator_constellations WHERE constellation_fingerprint = NEW.constellation_fingerprint)
 OR NEW.policy_fingerprint <> (SELECT policy_fingerprint FROM estimator_legacy_preregistrations WHERE preregistration_fingerprint = NEW.legacy_preregistration_fingerprint)
 OR NEW.assignment_manifest_fingerprint <> (SELECT assignment_manifest_fingerprint FROM estimator_legacy_preregistrations WHERE preregistration_fingerprint = NEW.legacy_preregistration_fingerprint)
 OR NEW.split_fingerprint <> (SELECT split_fingerprint FROM estimator_legacy_preregistrations WHERE preregistration_fingerprint = NEW.legacy_preregistration_fingerprint)
 OR NEW.registered_at < (SELECT registered_at FROM estimator_legacy_preregistrations WHERE preregistration_fingerprint = NEW.legacy_preregistration_fingerprint)
 OR NEW.registered_at < (SELECT frozen_at FROM estimator_constellations WHERE constellation_fingerprint = NEW.constellation_fingerprint)
 OR (SELECT frozen_at FROM estimator_calibration_splits WHERE split_fingerprint = NEW.split_fingerprint) > (SELECT frozen_at FROM estimator_constellations WHERE constellation_fingerprint = NEW.constellation_fingerprint)
 OR (SELECT frozen_at FROM estimator_constellations WHERE constellation_fingerprint = NEW.constellation_fingerprint) > (SELECT registered_at FROM estimator_legacy_preregistrations WHERE preregistration_fingerprint = NEW.legacy_preregistration_fingerprint)
BEGIN SELECT RAISE(ABORT, 'estimator v2 preregistration lineage is inconsistent'); END;

CREATE TABLE estimator_gate_campaigns (
    campaign_id TEXT PRIMARY KEY CHECK(length(campaign_id) = 64 AND campaign_id NOT GLOB '*[^0-9a-f]*'),
    campaign_fingerprint TEXT NOT NULL UNIQUE CHECK(length(campaign_fingerprint) = 64 AND campaign_fingerprint NOT GLOB '*[^0-9a-f]*'),
    contract_version TEXT NOT NULL CHECK(contract_version = 'estimator-gate-campaign-v1'),
    stored_plan_fingerprint TEXT NOT NULL REFERENCES estimator_plans(plan_fingerprint) DEFERRABLE INITIALLY DEFERRED,
    policy_fingerprint TEXT NOT NULL REFERENCES estimator_gate_policies(policy_fingerprint) DEFERRABLE INITIALLY DEFERRED,
    assignment_manifest_fingerprint TEXT NOT NULL UNIQUE REFERENCES estimator_case_manifests_v2(manifest_fingerprint) DEFERRABLE INITIALLY DEFERRED,
    split_fingerprint TEXT NOT NULL UNIQUE REFERENCES estimator_calibration_splits(split_fingerprint) DEFERRABLE INITIALLY DEFERRED,
    legacy_preregistration_fingerprint TEXT NOT NULL UNIQUE REFERENCES estimator_legacy_preregistrations(preregistration_fingerprint) DEFERRABLE INITIALLY DEFERRED,
    preregistration_v2_fingerprint TEXT NOT NULL UNIQUE REFERENCES estimator_preregistrations_v2(preregistration_fingerprint) DEFERRABLE INITIALLY DEFERRED,
    constellation_fingerprint TEXT NOT NULL UNIQUE REFERENCES estimator_constellations(constellation_fingerprint) DEFERRABLE INITIALLY DEFERRED,
    registered_at TEXT NOT NULL,
    activation_allowed INTEGER NOT NULL CHECK(activation_allowed = 0),
    private_export_allowed INTEGER NOT NULL CHECK(private_export_allowed = 0),
    team_share_allowed INTEGER NOT NULL CHECK(team_share_allowed = 0)
);
CREATE TABLE estimator_gate_campaign_tombstones (
    revocation_key TEXT PRIMARY KEY CHECK(length(revocation_key) = 64 AND revocation_key NOT GLOB '*[^0-9a-f]*'),
    deleted_at TEXT NOT NULL
);
CREATE TRIGGER estimator_gate_campaigns_validate_lineage BEFORE INSERT ON estimator_gate_campaigns
WHEN julianday(NEW.registered_at) IS NULL
 OR (SELECT uses_synthetic_model FROM estimator_plans WHERE plan_fingerprint = NEW.stored_plan_fingerprint) <> 0
 OR NOT EXISTS (SELECT 1 FROM estimator_gate_safe_plan_audits WHERE plan_fingerprint = NEW.stored_plan_fingerprint)
 OR NEW.policy_fingerprint <> (SELECT policy_fingerprint FROM estimator_preregistrations_v2 WHERE preregistration_fingerprint = NEW.preregistration_v2_fingerprint)
 OR NEW.assignment_manifest_fingerprint <> (SELECT assignment_manifest_fingerprint FROM estimator_preregistrations_v2 WHERE preregistration_fingerprint = NEW.preregistration_v2_fingerprint)
 OR NEW.split_fingerprint <> (SELECT split_fingerprint FROM estimator_preregistrations_v2 WHERE preregistration_fingerprint = NEW.preregistration_v2_fingerprint)
 OR NEW.stored_plan_fingerprint <> (SELECT stored_plan_fingerprint FROM estimator_preregistrations_v2 WHERE preregistration_fingerprint = NEW.preregistration_v2_fingerprint)
 OR NEW.constellation_fingerprint <> (SELECT constellation_fingerprint FROM estimator_preregistrations_v2 WHERE preregistration_fingerprint = NEW.preregistration_v2_fingerprint)
 OR NEW.legacy_preregistration_fingerprint <> (SELECT legacy_preregistration_fingerprint FROM estimator_preregistrations_v2 WHERE preregistration_fingerprint = NEW.preregistration_v2_fingerprint)
 OR NEW.registered_at < (SELECT registered_at FROM estimator_preregistrations_v2 WHERE preregistration_fingerprint = NEW.preregistration_v2_fingerprint)
 OR EXISTS (SELECT 1 FROM estimator_plan_questions AS question WHERE question.plan_fingerprint = NEW.stored_plan_fingerprint AND NOT EXISTS (SELECT 1 FROM estimator_case_assignments_v2 AS assignment WHERE assignment.manifest_fingerprint = NEW.assignment_manifest_fingerprint AND assignment.metric_question_fingerprint = question.question_fingerprint))
 OR EXISTS (SELECT 1 FROM estimator_case_assignments_v2 AS assignment WHERE assignment.manifest_fingerprint = NEW.assignment_manifest_fingerprint AND assignment.provider <> (SELECT provider FROM estimator_plan_provider_schemas WHERE plan_fingerprint = NEW.stored_plan_fingerprint))
 OR (SELECT active_learning_count FROM estimator_calibration_splits WHERE split_fingerprint = NEW.split_fingerprint) < (SELECT minimum_active_learning_count FROM estimator_gate_policies WHERE policy_fingerprint = NEW.policy_fingerprint)
 OR (SELECT active_learning_count FROM estimator_calibration_splits WHERE split_fingerprint = NEW.split_fingerprint) > (SELECT maximum_active_learning_count FROM estimator_gate_policies WHERE policy_fingerprint = NEW.policy_fingerprint)
 OR (SELECT holdout_count FROM estimator_calibration_splits WHERE split_fingerprint = NEW.split_fingerprint) < (SELECT minimum_holdout_count FROM estimator_gate_policies WHERE policy_fingerprint = NEW.policy_fingerprint)
 OR EXISTS (SELECT 1 FROM estimator_legacy_metric_specs AS spec WHERE spec.preregistration_fingerprint = NEW.legacy_preregistration_fingerprint AND (SELECT COUNT(*) FROM estimator_calibration_split_cases AS split_case JOIN estimator_case_assignments_v2 AS assignment ON assignment.manifest_fingerprint = NEW.assignment_manifest_fingerprint AND assignment.case_id = split_case.case_id WHERE split_case.split_fingerprint = NEW.split_fingerprint AND split_case.partition_code = 'holdout' AND assignment.metric_key = spec.metric_key) < (SELECT minimum_holdout_per_metric FROM estimator_gate_policies WHERE policy_fingerprint = NEW.policy_fingerprint))
 OR EXISTS (SELECT 1 FROM estimator_gate_policy_strata AS required WHERE required.policy_fingerprint = NEW.policy_fingerprint AND (SELECT COUNT(*) FROM estimator_calibration_split_cases AS split_case JOIN estimator_case_assignments_v2 AS assignment ON assignment.manifest_fingerprint = NEW.assignment_manifest_fingerprint AND assignment.case_id = split_case.case_id WHERE split_case.split_fingerprint = NEW.split_fingerprint AND split_case.partition_code = 'holdout' AND assignment.task_stratum = required.task_stratum) < (SELECT minimum_holdout_per_stratum FROM estimator_gate_policies WHERE policy_fingerprint = NEW.policy_fingerprint))
 OR EXISTS (SELECT 1 FROM estimator_gate_policy_languages AS required WHERE required.policy_fingerprint = NEW.policy_fingerprint AND (SELECT COUNT(*) FROM estimator_calibration_split_cases AS split_case JOIN estimator_case_assignments_v2 AS assignment ON assignment.manifest_fingerprint = NEW.assignment_manifest_fingerprint AND assignment.case_id = split_case.case_id WHERE split_case.split_fingerprint = NEW.split_fingerprint AND split_case.partition_code = 'holdout' AND assignment.language = required.language) < (SELECT minimum_holdout_per_language FROM estimator_gate_policies WHERE policy_fingerprint = NEW.policy_fingerprint))
BEGIN SELECT RAISE(ABORT, 'estimator campaign lineage is inconsistent'); END;

-- Every row is immutable.  Child collections seal when their parent root is
-- inserted.  Global plans and policies are retained; campaign-owned rows may
-- disappear only after the campaign root has been removed.
CREATE TRIGGER estimator_gate_policies_no_update BEFORE UPDATE ON estimator_gate_policies BEGIN SELECT RAISE(ABORT, 'estimator gate row is immutable'); END;
CREATE TRIGGER estimator_gate_policy_strata_no_update BEFORE UPDATE ON estimator_gate_policy_strata BEGIN SELECT RAISE(ABORT, 'estimator gate row is immutable'); END;
CREATE TRIGGER estimator_gate_policy_languages_no_update BEFORE UPDATE ON estimator_gate_policy_languages BEGIN SELECT RAISE(ABORT, 'estimator gate row is immutable'); END;
CREATE TRIGGER estimator_gate_policy_subgroups_no_update BEFORE UPDATE ON estimator_gate_policy_subgroups BEGIN SELECT RAISE(ABORT, 'estimator gate row is immutable'); END;
CREATE TRIGGER estimator_gate_policy_high_risk_rules_no_update BEFORE UPDATE ON estimator_gate_policy_high_risk_rules BEGIN SELECT RAISE(ABORT, 'estimator gate row is immutable'); END;
CREATE TRIGGER estimator_case_manifests_v2_no_update BEFORE UPDATE ON estimator_case_manifests_v2 BEGIN SELECT RAISE(ABORT, 'estimator gate row is immutable'); END;
CREATE TRIGGER estimator_case_assignments_v2_no_update BEFORE UPDATE ON estimator_case_assignments_v2 BEGIN SELECT RAISE(ABORT, 'estimator gate row is immutable'); END;
CREATE TRIGGER estimator_calibration_splits_no_update BEFORE UPDATE ON estimator_calibration_splits BEGIN SELECT RAISE(ABORT, 'estimator gate row is immutable'); END;
CREATE TRIGGER estimator_calibration_split_cases_no_update BEFORE UPDATE ON estimator_calibration_split_cases BEGIN SELECT RAISE(ABORT, 'estimator gate row is immutable'); END;
CREATE TRIGGER estimator_legacy_preregistrations_no_update BEFORE UPDATE ON estimator_legacy_preregistrations BEGIN SELECT RAISE(ABORT, 'estimator gate row is immutable'); END;
CREATE TRIGGER estimator_legacy_metric_specs_no_update BEFORE UPDATE ON estimator_legacy_metric_specs BEGIN SELECT RAISE(ABORT, 'estimator gate row is immutable'); END;
CREATE TRIGGER estimator_legacy_metric_labels_no_update BEFORE UPDATE ON estimator_legacy_metric_labels BEGIN SELECT RAISE(ABORT, 'estimator gate row is immutable'); END;
CREATE TRIGGER estimator_constellations_no_update BEFORE UPDATE ON estimator_constellations BEGIN SELECT RAISE(ABORT, 'estimator gate row is immutable'); END;
CREATE TRIGGER estimator_constellation_stages_no_update BEFORE UPDATE ON estimator_constellation_stages BEGIN SELECT RAISE(ABORT, 'estimator gate row is immutable'); END;
CREATE TRIGGER estimator_preregistrations_v2_no_update BEFORE UPDATE ON estimator_preregistrations_v2 BEGIN SELECT RAISE(ABORT, 'estimator gate row is immutable'); END;
CREATE TRIGGER estimator_gate_campaigns_no_update BEFORE UPDATE ON estimator_gate_campaigns BEGIN SELECT RAISE(ABORT, 'estimator gate row is immutable'); END;
CREATE TRIGGER estimator_gate_campaign_tombstones_no_update BEFORE UPDATE ON estimator_gate_campaign_tombstones BEGIN SELECT RAISE(ABORT, 'estimator campaign tombstone is immutable'); END;

CREATE TRIGGER estimator_gate_policy_strata_sealed_insert BEFORE INSERT ON estimator_gate_policy_strata WHEN EXISTS (SELECT 1 FROM estimator_gate_policies WHERE policy_fingerprint = NEW.policy_fingerprint) BEGIN SELECT RAISE(ABORT, 'estimator gate policy is sealed'); END;
CREATE TRIGGER estimator_gate_policy_languages_sealed_insert BEFORE INSERT ON estimator_gate_policy_languages WHEN EXISTS (SELECT 1 FROM estimator_gate_policies WHERE policy_fingerprint = NEW.policy_fingerprint) BEGIN SELECT RAISE(ABORT, 'estimator gate policy is sealed'); END;
CREATE TRIGGER estimator_gate_policy_subgroups_sealed_insert BEFORE INSERT ON estimator_gate_policy_subgroups WHEN EXISTS (SELECT 1 FROM estimator_gate_policies WHERE policy_fingerprint = NEW.policy_fingerprint) BEGIN SELECT RAISE(ABORT, 'estimator gate policy is sealed'); END;
CREATE TRIGGER estimator_gate_policy_high_risk_rules_sealed_insert BEFORE INSERT ON estimator_gate_policy_high_risk_rules WHEN EXISTS (SELECT 1 FROM estimator_gate_policies WHERE policy_fingerprint = NEW.policy_fingerprint) BEGIN SELECT RAISE(ABORT, 'estimator gate policy is sealed'); END;
CREATE TRIGGER estimator_case_assignments_v2_sealed_insert BEFORE INSERT ON estimator_case_assignments_v2 WHEN EXISTS (SELECT 1 FROM estimator_case_manifests_v2 WHERE manifest_fingerprint = NEW.manifest_fingerprint) BEGIN SELECT RAISE(ABORT, 'estimator case manifest is sealed'); END;
CREATE TRIGGER estimator_calibration_split_cases_sealed_insert BEFORE INSERT ON estimator_calibration_split_cases WHEN EXISTS (SELECT 1 FROM estimator_calibration_splits WHERE split_fingerprint = NEW.split_fingerprint) BEGIN SELECT RAISE(ABORT, 'estimator calibration split is sealed'); END;
CREATE TRIGGER estimator_legacy_metric_labels_sealed_insert BEFORE INSERT ON estimator_legacy_metric_labels WHEN EXISTS (SELECT 1 FROM estimator_legacy_metric_specs WHERE preregistration_fingerprint = NEW.preregistration_fingerprint AND metric_key = NEW.metric_key) BEGIN SELECT RAISE(ABORT, 'estimator legacy metric spec is sealed'); END;
CREATE TRIGGER estimator_legacy_metric_specs_sealed_insert BEFORE INSERT ON estimator_legacy_metric_specs WHEN EXISTS (SELECT 1 FROM estimator_legacy_preregistrations WHERE preregistration_fingerprint = NEW.preregistration_fingerprint) BEGIN SELECT RAISE(ABORT, 'estimator legacy preregistration is sealed'); END;
CREATE TRIGGER estimator_constellation_stages_sealed_insert BEFORE INSERT ON estimator_constellation_stages WHEN EXISTS (SELECT 1 FROM estimator_constellations WHERE constellation_fingerprint = NEW.constellation_fingerprint) BEGIN SELECT RAISE(ABORT, 'estimator constellation is sealed'); END;

CREATE TRIGGER estimator_gate_policies_no_delete BEFORE DELETE ON estimator_gate_policies BEGIN SELECT RAISE(ABORT, 'estimator gate policy is retained'); END;
CREATE TRIGGER estimator_gate_campaign_tombstones_no_delete BEFORE DELETE ON estimator_gate_campaign_tombstones BEGIN SELECT RAISE(ABORT, 'estimator campaign tombstone is retained'); END;
CREATE TRIGGER estimator_gate_policy_strata_no_delete BEFORE DELETE ON estimator_gate_policy_strata BEGIN SELECT RAISE(ABORT, 'estimator gate policy is retained'); END;
CREATE TRIGGER estimator_gate_policy_languages_no_delete BEFORE DELETE ON estimator_gate_policy_languages BEGIN SELECT RAISE(ABORT, 'estimator gate policy is retained'); END;
CREATE TRIGGER estimator_gate_policy_subgroups_no_delete BEFORE DELETE ON estimator_gate_policy_subgroups BEGIN SELECT RAISE(ABORT, 'estimator gate policy is retained'); END;
CREATE TRIGGER estimator_gate_policy_high_risk_rules_no_delete BEFORE DELETE ON estimator_gate_policy_high_risk_rules BEGIN SELECT RAISE(ABORT, 'estimator gate policy is retained'); END;
CREATE TRIGGER estimator_case_assignments_v2_parent_delete_only BEFORE DELETE ON estimator_case_assignments_v2 WHEN EXISTS (SELECT 1 FROM estimator_case_manifests_v2 WHERE manifest_fingerprint = OLD.manifest_fingerprint) BEGIN SELECT RAISE(ABORT, 'estimator gate child requires campaign privacy deletion'); END;
CREATE TRIGGER estimator_calibration_split_cases_parent_delete_only BEFORE DELETE ON estimator_calibration_split_cases WHEN EXISTS (SELECT 1 FROM estimator_calibration_splits WHERE split_fingerprint = OLD.split_fingerprint) BEGIN SELECT RAISE(ABORT, 'estimator gate child requires campaign privacy deletion'); END;
CREATE TRIGGER estimator_legacy_metric_specs_parent_delete_only BEFORE DELETE ON estimator_legacy_metric_specs WHEN EXISTS (SELECT 1 FROM estimator_legacy_preregistrations WHERE preregistration_fingerprint = OLD.preregistration_fingerprint) BEGIN SELECT RAISE(ABORT, 'estimator gate child requires campaign privacy deletion'); END;
CREATE TRIGGER estimator_legacy_metric_labels_parent_delete_only BEFORE DELETE ON estimator_legacy_metric_labels WHEN EXISTS (SELECT 1 FROM estimator_legacy_metric_specs WHERE preregistration_fingerprint = OLD.preregistration_fingerprint AND metric_key = OLD.metric_key) BEGIN SELECT RAISE(ABORT, 'estimator gate child requires campaign privacy deletion'); END;
CREATE TRIGGER estimator_constellation_stages_parent_delete_only BEFORE DELETE ON estimator_constellation_stages WHEN EXISTS (SELECT 1 FROM estimator_constellations WHERE constellation_fingerprint = OLD.constellation_fingerprint) BEGIN SELECT RAISE(ABORT, 'estimator gate child requires campaign privacy deletion'); END;
CREATE TRIGGER estimator_case_manifests_v2_campaign_delete_only BEFORE DELETE ON estimator_case_manifests_v2 WHEN EXISTS (SELECT 1 FROM estimator_gate_campaigns WHERE assignment_manifest_fingerprint = OLD.manifest_fingerprint) BEGIN SELECT RAISE(ABORT, 'estimator gate root requires campaign privacy deletion'); END;
CREATE TRIGGER estimator_calibration_splits_campaign_delete_only BEFORE DELETE ON estimator_calibration_splits WHEN EXISTS (SELECT 1 FROM estimator_gate_campaigns WHERE split_fingerprint = OLD.split_fingerprint) BEGIN SELECT RAISE(ABORT, 'estimator gate root requires campaign privacy deletion'); END;
CREATE TRIGGER estimator_legacy_preregistrations_campaign_delete_only BEFORE DELETE ON estimator_legacy_preregistrations WHEN EXISTS (SELECT 1 FROM estimator_gate_campaigns WHERE legacy_preregistration_fingerprint = OLD.preregistration_fingerprint) BEGIN SELECT RAISE(ABORT, 'estimator gate root requires campaign privacy deletion'); END;
CREATE TRIGGER estimator_constellations_campaign_delete_only BEFORE DELETE ON estimator_constellations WHEN EXISTS (SELECT 1 FROM estimator_gate_campaigns WHERE constellation_fingerprint = OLD.constellation_fingerprint) BEGIN SELECT RAISE(ABORT, 'estimator gate root requires campaign privacy deletion'); END;
CREATE TRIGGER estimator_preregistrations_v2_campaign_delete_only BEFORE DELETE ON estimator_preregistrations_v2 WHEN EXISTS (SELECT 1 FROM estimator_gate_campaigns WHERE preregistration_v2_fingerprint = OLD.preregistration_fingerprint) BEGIN SELECT RAISE(ABORT, 'estimator gate root requires campaign privacy deletion'); END;

-- Raw SQL receives the same canonical UTC and safe-version restrictions as the
-- application contracts. Equivalent instants in another spelling are not an
-- immutable identity, and path/URI-shaped versions are never provenance IDs.
CREATE TRIGGER estimator_case_manifests_v2_safe_insert BEFORE INSERT ON estimator_case_manifests_v2
WHEN NEW.frozen_at NOT GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]+00:00'
 OR julianday(NEW.frozen_at) IS NULL
 OR CAST(substr(NEW.frozen_at, 1, 4) AS INTEGER) NOT BETWEEN 1 AND 9999
 OR date(substr(NEW.frozen_at, 1, 10), '+0 days') <> substr(NEW.frozen_at, 1, 10)
 OR CAST(substr(NEW.frozen_at, 12, 2) AS INTEGER) NOT BETWEEN 0 AND 23
 OR CAST(substr(NEW.frozen_at, 15, 2) AS INTEGER) NOT BETWEEN 0 AND 59
 OR CAST(substr(NEW.frozen_at, 18, 2) AS INTEGER) NOT BETWEEN 0 AND 59
BEGIN SELECT RAISE(ABORT, 'estimator gate timestamp is not canonical UTC'); END;
CREATE TRIGGER estimator_case_assignments_v2_safe_insert BEFORE INSERT ON estimator_case_assignments_v2
WHEN NEW.observed_at NOT GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]+00:00'
 OR julianday(NEW.observed_at) IS NULL
 OR CAST(substr(NEW.observed_at, 1, 4) AS INTEGER) NOT BETWEEN 1 AND 9999
 OR date(substr(NEW.observed_at, 1, 10), '+0 days') <> substr(NEW.observed_at, 1, 10)
 OR CAST(substr(NEW.observed_at, 12, 2) AS INTEGER) NOT BETWEEN 0 AND 23
 OR CAST(substr(NEW.observed_at, 15, 2) AS INTEGER) NOT BETWEEN 0 AND 59
 OR CAST(substr(NEW.observed_at, 18, 2) AS INTEGER) NOT BETWEEN 0 AND 59
BEGIN SELECT RAISE(ABORT, 'estimator gate timestamp is not canonical UTC'); END;
CREATE TRIGGER estimator_calibration_splits_safe_insert BEFORE INSERT ON estimator_calibration_splits
WHEN NEW.frozen_at NOT GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]+00:00'
 OR julianday(NEW.frozen_at) IS NULL
 OR CAST(substr(NEW.frozen_at, 1, 4) AS INTEGER) NOT BETWEEN 1 AND 9999
 OR date(substr(NEW.frozen_at, 1, 10), '+0 days') <> substr(NEW.frozen_at, 1, 10)
 OR CAST(substr(NEW.frozen_at, 12, 2) AS INTEGER) NOT BETWEEN 0 AND 23
 OR CAST(substr(NEW.frozen_at, 15, 2) AS INTEGER) NOT BETWEEN 0 AND 59
 OR CAST(substr(NEW.frozen_at, 18, 2) AS INTEGER) NOT BETWEEN 0 AND 59
BEGIN SELECT RAISE(ABORT, 'estimator gate timestamp is not canonical UTC'); END;
CREATE TRIGGER estimator_legacy_preregistrations_safe_insert BEFORE INSERT ON estimator_legacy_preregistrations
WHEN NEW.registered_at NOT GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]+00:00'
 OR julianday(NEW.registered_at) IS NULL
 OR CAST(substr(NEW.registered_at, 1, 4) AS INTEGER) NOT BETWEEN 1 AND 9999
 OR date(substr(NEW.registered_at, 1, 10), '+0 days') <> substr(NEW.registered_at, 1, 10)
 OR CAST(substr(NEW.registered_at, 12, 2) AS INTEGER) NOT BETWEEN 0 AND 23
 OR CAST(substr(NEW.registered_at, 15, 2) AS INTEGER) NOT BETWEEN 0 AND 59
 OR CAST(substr(NEW.registered_at, 18, 2) AS INTEGER) NOT BETWEEN 0 AND 59
BEGIN SELECT RAISE(ABORT, 'estimator gate timestamp is not canonical UTC'); END;
CREATE TRIGGER estimator_constellations_safe_insert BEFORE INSERT ON estimator_constellations
WHEN NEW.frozen_at NOT GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]+00:00'
 OR julianday(NEW.frozen_at) IS NULL
 OR CAST(substr(NEW.frozen_at, 1, 4) AS INTEGER) NOT BETWEEN 1 AND 9999
 OR date(substr(NEW.frozen_at, 1, 10), '+0 days') <> substr(NEW.frozen_at, 1, 10)
 OR CAST(substr(NEW.frozen_at, 12, 2) AS INTEGER) NOT BETWEEN 0 AND 23
 OR CAST(substr(NEW.frozen_at, 15, 2) AS INTEGER) NOT BETWEEN 0 AND 59
 OR CAST(substr(NEW.frozen_at, 18, 2) AS INTEGER) NOT BETWEEN 0 AND 59
BEGIN SELECT RAISE(ABORT, 'estimator gate timestamp is not canonical UTC'); END;
CREATE TRIGGER estimator_preregistrations_v2_safe_insert BEFORE INSERT ON estimator_preregistrations_v2
WHEN NEW.registered_at NOT GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]+00:00'
 OR julianday(NEW.registered_at) IS NULL
 OR CAST(substr(NEW.registered_at, 1, 4) AS INTEGER) NOT BETWEEN 1 AND 9999
 OR date(substr(NEW.registered_at, 1, 10), '+0 days') <> substr(NEW.registered_at, 1, 10)
 OR CAST(substr(NEW.registered_at, 12, 2) AS INTEGER) NOT BETWEEN 0 AND 23
 OR CAST(substr(NEW.registered_at, 15, 2) AS INTEGER) NOT BETWEEN 0 AND 59
 OR CAST(substr(NEW.registered_at, 18, 2) AS INTEGER) NOT BETWEEN 0 AND 59
BEGIN SELECT RAISE(ABORT, 'estimator gate timestamp is not canonical UTC'); END;
CREATE TRIGGER estimator_gate_campaigns_safe_insert BEFORE INSERT ON estimator_gate_campaigns
WHEN NEW.registered_at NOT GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]+00:00'
 OR julianday(NEW.registered_at) IS NULL
 OR CAST(substr(NEW.registered_at, 1, 4) AS INTEGER) NOT BETWEEN 1 AND 9999
 OR date(substr(NEW.registered_at, 1, 10), '+0 days') <> substr(NEW.registered_at, 1, 10)
 OR CAST(substr(NEW.registered_at, 12, 2) AS INTEGER) NOT BETWEEN 0 AND 23
 OR CAST(substr(NEW.registered_at, 15, 2) AS INTEGER) NOT BETWEEN 0 AND 59
 OR CAST(substr(NEW.registered_at, 18, 2) AS INTEGER) NOT BETWEEN 0 AND 59
BEGIN SELECT RAISE(ABORT, 'estimator gate timestamp is not canonical UTC'); END;
CREATE TRIGGER estimator_constellation_stages_safe_insert BEFORE INSERT ON estimator_constellation_stages
WHEN NEW.component_version NOT GLOB '[A-Za-z0-9]*'
 OR NEW.component_version GLOB '*[^A-Za-z0-9._+:/-]*'
 OR length(NEW.component_version) NOT BETWEEN 1 AND 128
 OR NEW.output_schema_version NOT GLOB '[A-Za-z0-9]*'
 OR NEW.output_schema_version GLOB '*[^A-Za-z0-9._+:/-]*'
 OR length(NEW.output_schema_version) NOT BETWEEN 1 AND 128
 OR instr(NEW.component_version, ':') > 0
 OR instr(NEW.output_schema_version, ':') > 0
 OR instr(NEW.component_version, '\') > 0
 OR instr(NEW.output_schema_version, '\') > 0
 OR instr('/' || NEW.component_version || '/', '/../') > 0
 OR instr('/' || NEW.output_schema_version || '/', '/../') > 0
BEGIN SELECT RAISE(ABORT, 'estimator gate version is path or URI shaped'); END;

-- SQLite's length()/GLOB operators stop at embedded NUL.  Reject the entire
-- ASCII control range (including NUL and DEL) from every v16 TEXT projection
-- before any shape, digest, chronology, or lineage test can be bypassed.
CREATE TRIGGER estimator_gate_policies_no_controls BEFORE INSERT ON estimator_gate_policies
WHEN EXISTS (WITH RECURSIVE controls(code) AS (SELECT 0 UNION ALL SELECT code + 1 FROM controls WHERE code < 31) SELECT 1 FROM controls WHERE instr(NEW.policy_fingerprint || NEW.contract_version || NEW.policy_id, char(code)) > 0)
 OR instr(NEW.policy_fingerprint || NEW.contract_version || NEW.policy_id, char(127)) > 0
BEGIN SELECT RAISE(ABORT, 'estimator gate text contains an ASCII control'); END;
CREATE TRIGGER estimator_gate_policy_strata_no_controls BEFORE INSERT ON estimator_gate_policy_strata
WHEN EXISTS (WITH RECURSIVE controls(code) AS (SELECT 0 UNION ALL SELECT code + 1 FROM controls WHERE code < 31) SELECT 1 FROM controls WHERE instr(NEW.policy_fingerprint || NEW.task_stratum, char(code)) > 0)
 OR instr(NEW.policy_fingerprint || NEW.task_stratum, char(127)) > 0
BEGIN SELECT RAISE(ABORT, 'estimator gate text contains an ASCII control'); END;
CREATE TRIGGER estimator_gate_policy_languages_no_controls BEFORE INSERT ON estimator_gate_policy_languages
WHEN EXISTS (WITH RECURSIVE controls(code) AS (SELECT 0 UNION ALL SELECT code + 1 FROM controls WHERE code < 31) SELECT 1 FROM controls WHERE instr(NEW.policy_fingerprint || NEW.language, char(code)) > 0)
 OR instr(NEW.policy_fingerprint || NEW.language, char(127)) > 0
BEGIN SELECT RAISE(ABORT, 'estimator gate text contains an ASCII control'); END;
CREATE TRIGGER estimator_gate_policy_subgroups_no_controls BEFORE INSERT ON estimator_gate_policy_subgroups
WHEN EXISTS (WITH RECURSIVE controls(code) AS (SELECT 0 UNION ALL SELECT code + 1 FROM controls WHERE code < 31) SELECT 1 FROM controls WHERE instr(NEW.policy_fingerprint || NEW.dimension, char(code)) > 0)
 OR instr(NEW.policy_fingerprint || NEW.dimension, char(127)) > 0
BEGIN SELECT RAISE(ABORT, 'estimator gate text contains an ASCII control'); END;
CREATE TRIGGER estimator_gate_policy_high_risk_rules_no_controls BEFORE INSERT ON estimator_gate_policy_high_risk_rules
WHEN EXISTS (WITH RECURSIVE controls(code) AS (SELECT 0 UNION ALL SELECT code + 1 FROM controls WHERE code < 31) SELECT 1 FROM controls WHERE instr(NEW.policy_fingerprint || NEW.metric_key, char(code)) > 0)
 OR instr(NEW.policy_fingerprint || NEW.metric_key, char(127)) > 0
BEGIN SELECT RAISE(ABORT, 'estimator gate text contains an ASCII control'); END;
CREATE TRIGGER estimator_case_manifests_v2_no_controls BEFORE INSERT ON estimator_case_manifests_v2
WHEN EXISTS (WITH RECURSIVE controls(code) AS (SELECT 0 UNION ALL SELECT code + 1 FROM controls WHERE code < 31) SELECT 1 FROM controls WHERE instr(NEW.manifest_fingerprint || NEW.contract_version || NEW.manifest_id || NEW.plan_fingerprint || NEW.frozen_at, char(code)) > 0)
 OR instr(NEW.manifest_fingerprint || NEW.contract_version || NEW.manifest_id || NEW.plan_fingerprint || NEW.frozen_at, char(127)) > 0
BEGIN SELECT RAISE(ABORT, 'estimator gate text contains an ASCII control'); END;
CREATE TRIGGER estimator_case_assignments_v2_no_controls BEFORE INSERT ON estimator_case_assignments_v2
WHEN EXISTS (WITH RECURSIVE controls(code) AS (SELECT 0 UNION ALL SELECT code + 1 FROM controls WHERE code < 31) SELECT 1 FROM controls WHERE instr(NEW.manifest_fingerprint || NEW.contract_version || NEW.case_id || NEW.project_id || NEW.session_revision_id || NEW.metric_key || NEW.provider || NEW.origin || NEW.task_stratum || NEW.language || NEW.evidence_tier || NEW.observed_at || NEW.plan_fingerprint || NEW.metric_question_fingerprint || NEW.evidence_packet_fingerprint, char(code)) > 0)
 OR instr(NEW.manifest_fingerprint || NEW.contract_version || NEW.case_id || NEW.project_id || NEW.session_revision_id || NEW.metric_key || NEW.provider || NEW.origin || NEW.task_stratum || NEW.language || NEW.evidence_tier || NEW.observed_at || NEW.plan_fingerprint || NEW.metric_question_fingerprint || NEW.evidence_packet_fingerprint, char(127)) > 0
BEGIN SELECT RAISE(ABORT, 'estimator gate text contains an ASCII control'); END;
CREATE TRIGGER estimator_calibration_splits_no_controls BEFORE INSERT ON estimator_calibration_splits
WHEN EXISTS (WITH RECURSIVE controls(code) AS (SELECT 0 UNION ALL SELECT code + 1 FROM controls WHERE code < 31) SELECT 1 FROM controls WHERE instr(NEW.split_fingerprint || NEW.contract_version || NEW.split_id || NEW.assignment_manifest_fingerprint || NEW.frozen_at, char(code)) > 0)
 OR instr(NEW.split_fingerprint || NEW.contract_version || NEW.split_id || NEW.assignment_manifest_fingerprint || NEW.frozen_at, char(127)) > 0
BEGIN SELECT RAISE(ABORT, 'estimator gate text contains an ASCII control'); END;
CREATE TRIGGER estimator_calibration_split_cases_no_controls BEFORE INSERT ON estimator_calibration_split_cases
WHEN EXISTS (WITH RECURSIVE controls(code) AS (SELECT 0 UNION ALL SELECT code + 1 FROM controls WHERE code < 31) SELECT 1 FROM controls WHERE instr(NEW.split_fingerprint || NEW.partition_code || NEW.case_id, char(code)) > 0)
 OR instr(NEW.split_fingerprint || NEW.partition_code || NEW.case_id, char(127)) > 0
BEGIN SELECT RAISE(ABORT, 'estimator gate text contains an ASCII control'); END;
CREATE TRIGGER estimator_legacy_preregistrations_no_controls BEFORE INSERT ON estimator_legacy_preregistrations
WHEN EXISTS (WITH RECURSIVE controls(code) AS (SELECT 0 UNION ALL SELECT code + 1 FROM controls WHERE code < 31) SELECT 1 FROM controls WHERE instr(NEW.preregistration_fingerprint || NEW.contract_version || NEW.preregistration_id || NEW.policy_fingerprint || NEW.assignment_manifest_fingerprint || NEW.split_fingerprint || NEW.estimator_identity_fingerprint || NEW.registered_at, char(code)) > 0)
 OR instr(NEW.preregistration_fingerprint || NEW.contract_version || NEW.preregistration_id || NEW.policy_fingerprint || NEW.assignment_manifest_fingerprint || NEW.split_fingerprint || NEW.estimator_identity_fingerprint || NEW.registered_at, char(127)) > 0
BEGIN SELECT RAISE(ABORT, 'estimator gate text contains an ASCII control'); END;
CREATE TRIGGER estimator_legacy_metric_specs_no_controls BEFORE INSERT ON estimator_legacy_metric_specs
WHEN EXISTS (WITH RECURSIVE controls(code) AS (SELECT 0 UNION ALL SELECT code + 1 FROM controls WHERE code < 31) SELECT 1 FROM controls WHERE instr(NEW.preregistration_fingerprint || NEW.metric_key || NEW.risk_tier || coalesce(NEW.positive_label, ''), char(code)) > 0)
 OR instr(NEW.preregistration_fingerprint || NEW.metric_key || NEW.risk_tier || coalesce(NEW.positive_label, ''), char(127)) > 0
BEGIN SELECT RAISE(ABORT, 'estimator gate text contains an ASCII control'); END;
CREATE TRIGGER estimator_legacy_metric_labels_no_controls BEFORE INSERT ON estimator_legacy_metric_labels
WHEN EXISTS (WITH RECURSIVE controls(code) AS (SELECT 0 UNION ALL SELECT code + 1 FROM controls WHERE code < 31) SELECT 1 FROM controls WHERE instr(NEW.preregistration_fingerprint || NEW.metric_key || NEW.label_code, char(code)) > 0)
 OR instr(NEW.preregistration_fingerprint || NEW.metric_key || NEW.label_code, char(127)) > 0
BEGIN SELECT RAISE(ABORT, 'estimator gate text contains an ASCII control'); END;
CREATE TRIGGER estimator_constellations_no_controls BEFORE INSERT ON estimator_constellations
WHEN EXISTS (WITH RECURSIVE controls(code) AS (SELECT 0 UNION ALL SELECT code + 1 FROM controls WHERE code < 31) SELECT 1 FROM controls WHERE instr(NEW.constellation_fingerprint || NEW.contract_version || NEW.constellation_id || NEW.plan_fingerprint || NEW.frozen_at, char(code)) > 0)
 OR instr(NEW.constellation_fingerprint || NEW.contract_version || NEW.constellation_id || NEW.plan_fingerprint || NEW.frozen_at, char(127)) > 0
BEGIN SELECT RAISE(ABORT, 'estimator gate text contains an ASCII control'); END;
CREATE TRIGGER estimator_constellation_stages_no_controls BEFORE INSERT ON estimator_constellation_stages
WHEN EXISTS (WITH RECURSIVE controls(code) AS (SELECT 0 UNION ALL SELECT code + 1 FROM controls WHERE code < 31) SELECT 1 FROM controls WHERE instr(NEW.constellation_fingerprint || NEW.contract_version || NEW.kind || NEW.source || NEW.stage_fingerprint || NEW.model_artifact_fingerprint || NEW.stage_configuration_sha256 || NEW.component_version || NEW.output_schema_version, char(code)) > 0)
 OR instr(NEW.constellation_fingerprint || NEW.contract_version || NEW.kind || NEW.source || NEW.stage_fingerprint || NEW.model_artifact_fingerprint || NEW.stage_configuration_sha256 || NEW.component_version || NEW.output_schema_version, char(127)) > 0
BEGIN SELECT RAISE(ABORT, 'estimator gate text contains an ASCII control'); END;
CREATE TRIGGER estimator_preregistrations_v2_no_controls BEFORE INSERT ON estimator_preregistrations_v2
WHEN EXISTS (WITH RECURSIVE controls(code) AS (SELECT 0 UNION ALL SELECT code + 1 FROM controls WHERE code < 31) SELECT 1 FROM controls WHERE instr(NEW.preregistration_fingerprint || NEW.contract_version || NEW.preregistration_id || NEW.policy_fingerprint || NEW.assignment_manifest_fingerprint || NEW.split_fingerprint || NEW.stored_plan_fingerprint || NEW.constellation_fingerprint || NEW.legacy_preregistration_fingerprint || NEW.registered_at, char(code)) > 0)
 OR instr(NEW.preregistration_fingerprint || NEW.contract_version || NEW.preregistration_id || NEW.policy_fingerprint || NEW.assignment_manifest_fingerprint || NEW.split_fingerprint || NEW.stored_plan_fingerprint || NEW.constellation_fingerprint || NEW.legacy_preregistration_fingerprint || NEW.registered_at, char(127)) > 0
BEGIN SELECT RAISE(ABORT, 'estimator gate text contains an ASCII control'); END;
CREATE TRIGGER estimator_gate_campaigns_no_controls BEFORE INSERT ON estimator_gate_campaigns
WHEN EXISTS (WITH RECURSIVE controls(code) AS (SELECT 0 UNION ALL SELECT code + 1 FROM controls WHERE code < 31) SELECT 1 FROM controls WHERE instr(NEW.campaign_id || NEW.campaign_fingerprint || NEW.contract_version || NEW.stored_plan_fingerprint || NEW.policy_fingerprint || NEW.assignment_manifest_fingerprint || NEW.split_fingerprint || NEW.legacy_preregistration_fingerprint || NEW.preregistration_v2_fingerprint || NEW.constellation_fingerprint || NEW.registered_at, char(code)) > 0)
 OR instr(NEW.campaign_id || NEW.campaign_fingerprint || NEW.contract_version || NEW.stored_plan_fingerprint || NEW.policy_fingerprint || NEW.assignment_manifest_fingerprint || NEW.split_fingerprint || NEW.legacy_preregistration_fingerprint || NEW.preregistration_v2_fingerprint || NEW.constellation_fingerprint || NEW.registered_at, char(127)) > 0
BEGIN SELECT RAISE(ABORT, 'estimator gate text contains an ASCII control'); END;
CREATE TRIGGER estimator_gate_campaign_tombstones_safe_insert BEFORE INSERT ON estimator_gate_campaign_tombstones
WHEN NEW.deleted_at NOT GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]+00:00'
 OR julianday(NEW.deleted_at) IS NULL
 OR CAST(substr(NEW.deleted_at, 1, 4) AS INTEGER) NOT BETWEEN 1 AND 9999
 OR date(substr(NEW.deleted_at, 1, 10), '+0 days') <> substr(NEW.deleted_at, 1, 10)
 OR CAST(substr(NEW.deleted_at, 12, 2) AS INTEGER) NOT BETWEEN 0 AND 23
 OR CAST(substr(NEW.deleted_at, 15, 2) AS INTEGER) NOT BETWEEN 0 AND 59
 OR CAST(substr(NEW.deleted_at, 18, 2) AS INTEGER) NOT BETWEEN 0 AND 59
 OR EXISTS (WITH RECURSIVE controls(code) AS (SELECT 0 UNION ALL SELECT code + 1 FROM controls WHERE code < 31) SELECT 1 FROM controls WHERE instr(NEW.revocation_key || NEW.deleted_at, char(code)) > 0)
 OR instr(NEW.revocation_key || NEW.deleted_at, char(127)) > 0
BEGIN SELECT RAISE(ABORT, 'estimator campaign tombstone is unsafe'); END;

CREATE INDEX estimator_gate_campaigns_plan_idx ON estimator_gate_campaigns(stored_plan_fingerprint, registered_at DESC);
CREATE INDEX estimator_case_assignments_v2_metric_idx ON estimator_case_assignments_v2(manifest_fingerprint, metric_key, case_id);

COMMIT;
"""


MIGRATION_17 = r"""
BEGIN IMMEDIATE;

-- V17 stores only normalized, content-free scalar calibration evidence. Raw
-- outputs, prompts, evidence bodies, paths, URIs, prose, and arbitrary JSON or
-- BLOB payloads have no column in this schema. Timestamps are canonical UTC
-- microseconds from the Unix epoch, eliminating textual calendar aliases.
CREATE TABLE estimator_evidence_attempt_launches (
    submission_id TEXT NOT NULL CHECK(length(submission_id) = 64 AND submission_id NOT GLOB '*[^0-9a-f]*' AND instr(submission_id, char(0)) = 0),
    launch_id TEXT NOT NULL CHECK(length(launch_id) = 64 AND launch_id NOT GLOB '*[^0-9a-f]*' AND instr(launch_id, char(0)) = 0),
    campaign_id TEXT NOT NULL REFERENCES estimator_gate_campaigns(campaign_id) ON DELETE CASCADE,
    attempt_id TEXT NOT NULL CHECK(length(attempt_id) = 64 AND attempt_id NOT GLOB '*[^0-9a-f]*' AND instr(attempt_id, char(0)) = 0),
    execution_id TEXT NOT NULL CHECK(length(execution_id) = 64 AND execution_id NOT GLOB '*[^0-9a-f]*' AND instr(execution_id, char(0)) = 0),
    case_id TEXT NOT NULL CHECK(length(case_id) = 64 AND case_id NOT GLOB '*[^0-9a-f]*' AND instr(case_id, char(0)) = 0),
    plan_fingerprint TEXT NOT NULL REFERENCES estimator_plans(plan_fingerprint),
    metric_question_fingerprint TEXT NOT NULL REFERENCES estimator_metric_questions(question_fingerprint),
    evidence_packet_fingerprint TEXT NOT NULL CHECK(length(evidence_packet_fingerprint) = 64 AND evidence_packet_fingerprint NOT GLOB '*[^0-9a-f]*'),
    constellation_stage_fingerprint TEXT NOT NULL CHECK(length(constellation_stage_fingerprint) = 64 AND constellation_stage_fingerprint NOT GLOB '*[^0-9a-f]*'),
    stage_ordinal INTEGER NOT NULL CHECK(stage_ordinal BETWEEN 1 AND 7),
    stage_kind TEXT NOT NULL CHECK(stage_kind IN ('embedding_retrieval','reranker','specialist','second_opinion')),
    stage_configuration_sha256 TEXT NOT NULL CHECK(length(stage_configuration_sha256) = 64 AND stage_configuration_sha256 NOT GLOB '*[^0-9a-f]*'),
    model_artifact_fingerprint TEXT NOT NULL REFERENCES estimator_model_artifacts(artifact_fingerprint),
    requested_source TEXT NOT NULL CHECK(requested_source IN ('local_weights','openai_api','anthropic_api','codex_cli','claude_cli','synthetic')),
    requested_model_id TEXT NOT NULL CHECK(length(requested_model_id) BETWEEN 1 AND 128 AND requested_model_id GLOB '[A-Za-z0-9]*' AND requested_model_id NOT GLOB '*[^A-Za-z0-9._+-]*' AND instr(requested_model_id, '..') = 0),
    requested_revision TEXT NOT NULL CHECK(length(requested_revision) BETWEEN 1 AND 128 AND requested_revision GLOB '[A-Za-z0-9]*' AND requested_revision NOT GLOB '*[^A-Za-z0-9._+-]*' AND instr(requested_revision, '..') = 0),
    requested_execution_mode TEXT NOT NULL CHECK(requested_execution_mode IN ('standard','pro')),
    runner_adapter_key TEXT NOT NULL CHECK(length(runner_adapter_key) BETWEEN 1 AND 128 AND runner_adapter_key GLOB '[A-Za-z0-9]*' AND runner_adapter_key NOT GLOB '*[^A-Za-z0-9._+-]*' AND instr(runner_adapter_key, '..') = 0),
    runner_adapter_version TEXT NOT NULL CHECK(length(runner_adapter_version) BETWEEN 1 AND 128 AND runner_adapter_version GLOB '[A-Za-z0-9]*' AND runner_adapter_version NOT GLOB '*[^A-Za-z0-9._+-]*' AND instr(runner_adapter_version, '..') = 0),
    runner_configuration_sha256 TEXT NOT NULL CHECK(length(runner_configuration_sha256) = 64 AND runner_configuration_sha256 NOT GLOB '*[^0-9a-f]*'),
    response_schema_version TEXT NOT NULL CHECK(length(response_schema_version) BETWEEN 1 AND 128 AND response_schema_version GLOB '[A-Za-z0-9]*' AND response_schema_version NOT GLOB '*[^A-Za-z0-9._+-]*' AND instr(response_schema_version, '..') = 0),
    destination TEXT NOT NULL CHECK(destination IN ('local_device','openai_api','anthropic_api','codex_cli','claude_api','manual_import','synthetic_test')),
    retention_class TEXT NOT NULL CHECK(retention_class IN ('local_ephemeral','provider_zero_day','provider_30_day','provider_disclosed_other','manual_export','synthetic')),
    approval_kind TEXT NOT NULL CHECK(approval_kind IN ('not_required_local','fresh_redaction_preview','manual_import','synthetic_test')),
    approval_id TEXT CHECK(approval_id IS NULL OR (length(approval_id) = 64 AND approval_id NOT GLOB '*[^0-9a-f]*')),
    redaction_preview_fingerprint TEXT CHECK(redaction_preview_fingerprint IS NULL OR (length(redaction_preview_fingerprint) = 64 AND redaction_preview_fingerprint NOT GLOB '*[^0-9a-f]*')),
    approved_at_us INTEGER CHECK(approved_at_us IS NULL OR typeof(approved_at_us) = 'integer'),
    launched_at_us INTEGER NOT NULL CHECK(typeof(launched_at_us) = 'integer'),
    launch_fingerprint TEXT NOT NULL CHECK(length(launch_fingerprint) = 64 AND launch_fingerprint NOT GLOB '*[^0-9a-f]*'),
    PRIMARY KEY(submission_id, attempt_id),
    UNIQUE(submission_id, launch_id),
    CHECK((destination = 'local_device' AND requested_source = 'local_weights' AND retention_class = 'local_ephemeral' AND approval_kind = 'not_required_local' AND approval_id IS NULL AND redaction_preview_fingerprint IS NULL AND approved_at_us IS NULL)
       OR (destination = 'synthetic_test' AND requested_source = 'synthetic' AND retention_class = 'synthetic' AND approval_kind = 'synthetic_test' AND approval_id IS NULL AND redaction_preview_fingerprint IS NULL AND approved_at_us IS NULL)
       OR (destination = 'manual_import' AND requested_source = 'claude_cli' AND retention_class = 'manual_export' AND approval_kind = 'manual_import' AND approval_id IS NULL AND redaction_preview_fingerprint IS NULL AND approved_at_us IS NULL)
       OR (destination IN ('openai_api','anthropic_api','codex_cli','claude_api') AND approval_kind = 'fresh_redaction_preview' AND approval_id IS NOT NULL AND redaction_preview_fingerprint IS NOT NULL AND approved_at_us IS NOT NULL AND approved_at_us <= launched_at_us
           AND ((destination = 'openai_api' AND requested_source = 'openai_api') OR (destination IN ('anthropic_api','claude_api') AND requested_source = 'anthropic_api') OR (destination = 'codex_cli' AND requested_source = 'codex_cli'))
           AND retention_class IN ('provider_zero_day','provider_30_day','provider_disclosed_other')))
);

CREATE TABLE estimator_evidence_append_authorizations (
    authorization_id TEXT PRIMARY KEY CHECK(length(authorization_id)=64 AND authorization_id NOT GLOB '*[^0-9a-f]*'),
    submission_id TEXT NOT NULL CHECK(length(submission_id)=64 AND submission_id NOT GLOB '*[^0-9a-f]*'),
    campaign_id TEXT NOT NULL REFERENCES estimator_gate_campaigns(campaign_id) ON DELETE CASCADE,
    authorization_tag TEXT NOT NULL CHECK(length(authorization_tag)=64 AND authorization_tag NOT GLOB '*[^0-9a-f]*'),
    UNIQUE(submission_id, campaign_id)
);
CREATE TRIGGER estimator_evidence_append_authorizations_validate BEFORE INSERT ON estimator_evidence_append_authorizations WHEN NEW.authorization_tag<>estimator_evidence_authorization_tag(NEW.authorization_id,NEW.submission_id,NEW.campaign_id) BEGIN SELECT RAISE(ABORT,'estimator evidence authorization is invalid'); END;
CREATE TRIGGER estimator_evidence_append_authorizations_no_update BEFORE UPDATE ON estimator_evidence_append_authorizations BEGIN SELECT RAISE(ABORT,'estimator evidence authorization is immutable'); END;
CREATE TRIGGER estimator_evidence_append_authorizations_no_delete BEFORE DELETE ON estimator_evidence_append_authorizations WHEN OLD.authorization_tag<>estimator_evidence_authorization_tag(OLD.authorization_id,OLD.submission_id,OLD.campaign_id) BEGIN SELECT RAISE(ABORT,'estimator evidence authorization is invalid'); END;

CREATE TABLE estimator_evidence_delete_authorizations (
    authorization_id TEXT PRIMARY KEY CHECK(length(authorization_id)=64 AND authorization_id NOT GLOB '*[^0-9a-f]*'),
    campaign_id TEXT NOT NULL UNIQUE REFERENCES estimator_gate_campaigns(campaign_id) ON DELETE CASCADE,
    authorization_tag TEXT NOT NULL CHECK(length(authorization_tag)=64 AND authorization_tag NOT GLOB '*[^0-9a-f]*')
);
CREATE TRIGGER estimator_evidence_delete_authorizations_validate BEFORE INSERT ON estimator_evidence_delete_authorizations WHEN NEW.authorization_tag<>estimator_evidence_delete_authorization_tag(NEW.authorization_id,NEW.campaign_id) BEGIN SELECT RAISE(ABORT,'estimator evidence delete authorization is invalid'); END;
CREATE TRIGGER estimator_evidence_delete_authorizations_no_update BEFORE UPDATE ON estimator_evidence_delete_authorizations BEGIN SELECT RAISE(ABORT,'estimator evidence delete authorization is immutable'); END;
CREATE TRIGGER estimator_evidence_delete_authorizations_no_delete BEFORE DELETE ON estimator_evidence_delete_authorizations WHEN EXISTS (SELECT 1 FROM estimator_gate_campaigns WHERE campaign_id=OLD.campaign_id) AND OLD.authorization_tag<>estimator_evidence_delete_authorization_tag(OLD.authorization_id,OLD.campaign_id) BEGIN SELECT RAISE(ABORT,'estimator evidence delete authorization is invalid'); END;

CREATE TABLE estimator_evidence_attempt_outcomes (
    submission_id TEXT NOT NULL,
    outcome_id TEXT NOT NULL CHECK(length(outcome_id) = 64 AND outcome_id NOT GLOB '*[^0-9a-f]*'),
    outcome_fingerprint TEXT NOT NULL CHECK(length(outcome_fingerprint) = 64 AND outcome_fingerprint NOT GLOB '*[^0-9a-f]*'),
    campaign_id TEXT NOT NULL REFERENCES estimator_gate_campaigns(campaign_id) ON DELETE CASCADE,
    attempt_id TEXT NOT NULL,
    execution_id TEXT NOT NULL CHECK(length(execution_id) = 64 AND execution_id NOT GLOB '*[^0-9a-f]*'),
    case_id TEXT NOT NULL CHECK(length(case_id) = 64 AND case_id NOT GLOB '*[^0-9a-f]*'),
    plan_fingerprint TEXT NOT NULL REFERENCES estimator_plans(plan_fingerprint),
    metric_question_fingerprint TEXT NOT NULL REFERENCES estimator_metric_questions(question_fingerprint),
    evidence_packet_fingerprint TEXT NOT NULL CHECK(length(evidence_packet_fingerprint) = 64 AND evidence_packet_fingerprint NOT GLOB '*[^0-9a-f]*'),
    terminal_state TEXT NOT NULL CHECK(terminal_state IN ('success','refusal','error','oom','timeout','cancelled','worker_lost')),
    structured_output_fingerprint TEXT CHECK(structured_output_fingerprint IS NULL OR (length(structured_output_fingerprint) = 64 AND structured_output_fingerprint NOT GLOB '*[^0-9a-f]*')),
    terminal_reason_code TEXT CHECK(terminal_reason_code IS NULL OR (length(terminal_reason_code) BETWEEN 1 AND 128 AND terminal_reason_code GLOB '[a-z]*' AND terminal_reason_code NOT GLOB '*[^a-z0-9._-]*' AND instr(terminal_reason_code, '..') = 0)),
    served_state TEXT NOT NULL CHECK(served_state IN ('observed','unavailable')),
    served_source TEXT CHECK(served_source IS NULL OR served_source IN ('local_weights','openai_api','anthropic_api','codex_cli','claude_cli','synthetic')),
    served_model_id TEXT CHECK(served_model_id IS NULL OR (length(served_model_id) BETWEEN 1 AND 128 AND served_model_id GLOB '[A-Za-z0-9]*' AND served_model_id NOT GLOB '*[^A-Za-z0-9._+-]*' AND instr(served_model_id, '..') = 0)),
    served_revision TEXT CHECK(served_revision IS NULL OR (length(served_revision) BETWEEN 1 AND 128 AND served_revision GLOB '[A-Za-z0-9]*' AND served_revision NOT GLOB '*[^A-Za-z0-9._+-]*' AND instr(served_revision, '..') = 0)),
    served_execution_mode TEXT CHECK(served_execution_mode IS NULL OR served_execution_mode IN ('standard','pro')),
    fallback_used INTEGER CHECK(fallback_used IS NULL OR fallback_used IN (0,1)),
    fallback_reason_code TEXT CHECK(fallback_reason_code IS NULL OR (length(fallback_reason_code) BETWEEN 1 AND 128 AND fallback_reason_code GLOB '[a-z]*' AND fallback_reason_code NOT GLOB '*[^a-z0-9._-]*' AND instr(fallback_reason_code, '..') = 0)),
    served_unavailable_reason_code TEXT CHECK(served_unavailable_reason_code IS NULL OR (length(served_unavailable_reason_code) BETWEEN 1 AND 128 AND served_unavailable_reason_code GLOB '[a-z]*' AND served_unavailable_reason_code NOT GLOB '*[^a-z0-9._-]*' AND instr(served_unavailable_reason_code, '..') = 0)),
    token_state TEXT NOT NULL CHECK(token_state IN ('observed','unavailable','not_applicable')),
    token_collector_version TEXT NOT NULL CHECK(length(token_collector_version) BETWEEN 1 AND 128 AND token_collector_version GLOB '[A-Za-z0-9]*' AND token_collector_version NOT GLOB '*[^A-Za-z0-9._+-]*' AND instr(token_collector_version,'..')=0),
    input_tokens INTEGER CHECK(input_tokens IS NULL OR (typeof(input_tokens) = 'integer' AND input_tokens BETWEEN 0 AND 9007199254740991)),
    cached_input_tokens INTEGER CHECK(cached_input_tokens IS NULL OR (typeof(cached_input_tokens) = 'integer' AND cached_input_tokens BETWEEN 0 AND 9007199254740991)),
    output_tokens INTEGER CHECK(output_tokens IS NULL OR (typeof(output_tokens) = 'integer' AND output_tokens BETWEEN 0 AND 9007199254740991)),
    reasoning_output_tokens INTEGER CHECK(reasoning_output_tokens IS NULL OR (typeof(reasoning_output_tokens) = 'integer' AND reasoning_output_tokens BETWEEN 0 AND 9007199254740991)),
    total_tokens INTEGER CHECK(total_tokens IS NULL OR (typeof(total_tokens) = 'integer' AND total_tokens BETWEEN 0 AND 9007199254740991)),
    token_reason_code TEXT CHECK(token_reason_code IS NULL OR (length(token_reason_code) BETWEEN 1 AND 128 AND token_reason_code GLOB '[a-z]*' AND token_reason_code NOT GLOB '*[^a-z0-9._-]*' AND instr(token_reason_code,'..')=0)),
    resource_state TEXT NOT NULL CHECK(resource_state IN ('observed','unavailable','not_applicable')),
    resource_collector_version TEXT NOT NULL CHECK(length(resource_collector_version) BETWEEN 1 AND 128 AND resource_collector_version GLOB '[A-Za-z0-9]*' AND resource_collector_version NOT GLOB '*[^A-Za-z0-9._+-]*' AND instr(resource_collector_version,'..')=0),
    peak_ram_bytes INTEGER CHECK(peak_ram_bytes IS NULL OR (typeof(peak_ram_bytes) = 'integer' AND peak_ram_bytes BETWEEN 0 AND 9007199254740991)),
    peak_vram_bytes INTEGER CHECK(peak_vram_bytes IS NULL OR (typeof(peak_vram_bytes) = 'integer' AND peak_vram_bytes BETWEEN 0 AND 9007199254740991)),
    energy_millijoules REAL CHECK(energy_millijoules IS NULL OR (typeof(energy_millijoules) IN ('real','integer') AND energy_millijoules BETWEEN 0 AND 1.0e308)),
    resource_reason_code TEXT CHECK(resource_reason_code IS NULL OR (length(resource_reason_code) BETWEEN 1 AND 128 AND resource_reason_code GLOB '[a-z]*' AND resource_reason_code NOT GLOB '*[^a-z0-9._-]*' AND instr(resource_reason_code,'..')=0)),
    cost_state TEXT NOT NULL CHECK(cost_state IN ('observed','unavailable','not_applicable')),
    cost_collector_version TEXT NOT NULL CHECK(length(cost_collector_version) BETWEEN 1 AND 128 AND cost_collector_version GLOB '[A-Za-z0-9]*' AND cost_collector_version NOT GLOB '*[^A-Za-z0-9._+-]*' AND instr(cost_collector_version,'..')=0),
    amount_microusd INTEGER CHECK(amount_microusd IS NULL OR (typeof(amount_microusd) = 'integer' AND amount_microusd BETWEEN 0 AND 9007199254740991)),
    cost_reason_code TEXT CHECK(cost_reason_code IS NULL OR (length(cost_reason_code) BETWEEN 1 AND 128 AND cost_reason_code GLOB '[a-z]*' AND cost_reason_code NOT GLOB '*[^a-z0-9._-]*' AND instr(cost_reason_code,'..')=0)),
    queue_key TEXT NOT NULL CHECK(length(queue_key) BETWEEN 1 AND 128 AND queue_key GLOB '[a-z]*' AND queue_key NOT GLOB '*[^a-z0-9._-]*' AND instr(queue_key, '..') = 0),
    queue_version TEXT NOT NULL CHECK(length(queue_version) BETWEEN 1 AND 128 AND queue_version GLOB '[A-Za-z0-9]*' AND queue_version NOT GLOB '*[^A-Za-z0-9._+-]*' AND instr(queue_version,'..')=0),
    worker_id TEXT NOT NULL CHECK(length(worker_id) = 64 AND worker_id NOT GLOB '*[^0-9a-f]*'),
    enqueued_at_us INTEGER NOT NULL CHECK(typeof(enqueued_at_us) = 'integer'),
    dequeued_at_us INTEGER NOT NULL CHECK(typeof(dequeued_at_us) = 'integer'),
    wait_ms INTEGER NOT NULL CHECK(typeof(wait_ms) = 'integer' AND wait_ms BETWEEN 0 AND 604800000),
    started_at_us INTEGER NOT NULL CHECK(typeof(started_at_us) = 'integer'),
    finished_at_us INTEGER NOT NULL CHECK(typeof(finished_at_us) = 'integer'),
    latency_ms INTEGER NOT NULL CHECK(typeof(latency_ms) = 'integer' AND latency_ms BETWEEN 0 AND 604800000),
    PRIMARY KEY(submission_id, attempt_id),
    UNIQUE(submission_id, outcome_id),
    FOREIGN KEY(submission_id, attempt_id) REFERENCES estimator_evidence_attempt_launches(submission_id, attempt_id) ON DELETE CASCADE,
    CHECK(dequeued_at_us >= enqueued_at_us AND started_at_us >= dequeued_at_us AND finished_at_us >= started_at_us),
    CHECK(abs((dequeued_at_us - enqueued_at_us) - wait_ms * 1000) <= 500),
    CHECK(abs((finished_at_us - started_at_us) - latency_ms * 1000) <= 500),
    CHECK((terminal_state = 'success' AND structured_output_fingerprint IS NOT NULL AND terminal_reason_code IS NULL AND served_state = 'observed') OR (terminal_state <> 'success' AND structured_output_fingerprint IS NULL AND terminal_reason_code IS NOT NULL)),
    CHECK((served_state = 'observed' AND served_source IS NOT NULL AND served_model_id IS NOT NULL AND served_revision IS NOT NULL AND served_execution_mode IS NOT NULL AND fallback_used IS NOT NULL AND served_unavailable_reason_code IS NULL AND ((fallback_used = 1 AND fallback_reason_code IS NOT NULL) OR (fallback_used = 0 AND fallback_reason_code IS NULL))) OR (served_state = 'unavailable' AND served_source IS NULL AND served_model_id IS NULL AND served_revision IS NULL AND served_execution_mode IS NULL AND fallback_used IS NULL AND fallback_reason_code IS NULL AND served_unavailable_reason_code IS NOT NULL)),
    CHECK((token_state = 'observed' AND input_tokens IS NOT NULL AND output_tokens IS NOT NULL AND total_tokens = input_tokens + output_tokens AND token_reason_code IS NULL AND (cached_input_tokens IS NULL OR cached_input_tokens <= input_tokens) AND (reasoning_output_tokens IS NULL OR reasoning_output_tokens <= output_tokens)) OR (token_state <> 'observed' AND input_tokens IS NULL AND cached_input_tokens IS NULL AND output_tokens IS NULL AND reasoning_output_tokens IS NULL AND total_tokens IS NULL AND token_reason_code IS NOT NULL)),
    CHECK((resource_state = 'observed' AND (peak_ram_bytes IS NOT NULL OR peak_vram_bytes IS NOT NULL OR energy_millijoules IS NOT NULL) AND resource_reason_code IS NULL) OR (resource_state <> 'observed' AND peak_ram_bytes IS NULL AND peak_vram_bytes IS NULL AND energy_millijoules IS NULL AND resource_reason_code IS NOT NULL)),
    CHECK((cost_state = 'observed' AND amount_microusd IS NOT NULL AND cost_reason_code IS NULL) OR (cost_state <> 'observed' AND amount_microusd IS NULL AND cost_reason_code IS NOT NULL))
);

CREATE TABLE estimator_evidence_expected_attempts (
    submission_id TEXT NOT NULL,
    manifest_id TEXT NOT NULL,
    ordinal INTEGER NOT NULL CHECK(ordinal BETWEEN 0 AND 19999),
    attempt_id TEXT NOT NULL,
    execution_id TEXT NOT NULL,
    case_id TEXT NOT NULL,
    plan_fingerprint TEXT NOT NULL,
    metric_question_fingerprint TEXT NOT NULL,
    evidence_packet_fingerprint TEXT NOT NULL,
    constellation_stage_fingerprint TEXT NOT NULL,
    stage_configuration_sha256 TEXT NOT NULL,
    stage_ordinal INTEGER NOT NULL CHECK(stage_ordinal BETWEEN 1 AND 7),
    stage_kind TEXT NOT NULL CHECK(stage_kind IN ('embedding_retrieval','reranker','specialist','second_opinion')),
    attempt_fingerprint TEXT NOT NULL,
    campaign_id TEXT NOT NULL REFERENCES estimator_gate_campaigns(campaign_id) ON DELETE CASCADE,
    PRIMARY KEY(submission_id, ordinal),
    UNIQUE(submission_id, attempt_id),
    CHECK(length(manifest_id)=64 AND manifest_id NOT GLOB '*[^0-9a-f]*'),
    CHECK(length(attempt_id)=64 AND attempt_id NOT GLOB '*[^0-9a-f]*'),
    CHECK(length(execution_id)=64 AND execution_id NOT GLOB '*[^0-9a-f]*'),
    CHECK(length(case_id)=64 AND case_id NOT GLOB '*[^0-9a-f]*'),
    CHECK(length(plan_fingerprint)=64 AND plan_fingerprint NOT GLOB '*[^0-9a-f]*'),
    CHECK(length(metric_question_fingerprint)=64 AND metric_question_fingerprint NOT GLOB '*[^0-9a-f]*'),
    CHECK(length(evidence_packet_fingerprint)=64 AND evidence_packet_fingerprint NOT GLOB '*[^0-9a-f]*'),
    CHECK(length(constellation_stage_fingerprint)=64 AND constellation_stage_fingerprint NOT GLOB '*[^0-9a-f]*'),
    CHECK(length(stage_configuration_sha256)=64 AND stage_configuration_sha256 NOT GLOB '*[^0-9a-f]*'),
    CHECK(length(attempt_fingerprint)=64 AND attempt_fingerprint NOT GLOB '*[^0-9a-f]*')
);
CREATE TABLE estimator_evidence_expected_manifests (
    submission_id TEXT PRIMARY KEY,
    manifest_id TEXT NOT NULL UNIQUE,
    manifest_fingerprint TEXT NOT NULL UNIQUE,
    execution_set_fingerprint TEXT NOT NULL,
    campaign_id TEXT NOT NULL REFERENCES estimator_gate_campaigns(campaign_id) ON DELETE CASCADE,
    plan_fingerprint TEXT NOT NULL REFERENCES estimator_plans(plan_fingerprint),
    frozen_at_us INTEGER NOT NULL CHECK(typeof(frozen_at_us)='integer'),
    attempt_count INTEGER NOT NULL CHECK(attempt_count BETWEEN 1 AND 20000),
    CHECK(length(submission_id)=64 AND submission_id NOT GLOB '*[^0-9a-f]*'),
    CHECK(length(manifest_id)=64 AND manifest_id NOT GLOB '*[^0-9a-f]*'),
    CHECK(length(manifest_fingerprint)=64 AND manifest_fingerprint NOT GLOB '*[^0-9a-f]*'),
    CHECK(length(execution_set_fingerprint)=64 AND execution_set_fingerprint NOT GLOB '*[^0-9a-f]*')
);

CREATE TABLE estimator_evidence_access_events (
    submission_id TEXT NOT NULL,
    manifest_id TEXT NOT NULL,
    ordinal INTEGER NOT NULL CHECK(ordinal BETWEEN 0 AND 19999),
    event_id TEXT NOT NULL,
    event_fingerprint TEXT NOT NULL,
    campaign_id TEXT NOT NULL REFERENCES estimator_gate_campaigns(campaign_id) ON DELETE CASCADE,
    case_id TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    actor_kind TEXT NOT NULL CHECK(actor_kind IN ('candidate_runner','deterministic_baseline','independent_labeler','adjudicator','system_auditor')),
    access_kind TEXT NOT NULL CHECK(access_kind IN ('case_input_read','candidate_output_read','reference_truth_read','objective_truth_read','label_write')),
    occurred_at_us INTEGER NOT NULL CHECK(typeof(occurred_at_us)='integer'),
    PRIMARY KEY(submission_id, manifest_id, ordinal),
    UNIQUE(submission_id, event_id),
    CHECK(length(event_id)=64 AND event_id NOT GLOB '*[^0-9a-f]*'),
    CHECK(length(event_fingerprint)=64 AND event_fingerprint NOT GLOB '*[^0-9a-f]*'),
    CHECK(length(case_id)=64 AND case_id NOT GLOB '*[^0-9a-f]*'),
    CHECK(length(actor_id)=64 AND actor_id NOT GLOB '*[^0-9a-f]*')
);
CREATE TABLE estimator_evidence_access_gaps (
    submission_id TEXT NOT NULL,
    manifest_id TEXT NOT NULL,
    ordinal INTEGER NOT NULL CHECK(ordinal BETWEEN 0 AND 19999),
    gap_id TEXT NOT NULL,
    campaign_id TEXT NOT NULL REFERENCES estimator_gate_campaigns(campaign_id) ON DELETE CASCADE,
    reason_code TEXT NOT NULL CHECK(length(reason_code) BETWEEN 1 AND 128 AND reason_code GLOB '[a-z]*' AND reason_code NOT GLOB '*[^a-z0-9._-]*' AND instr(reason_code,'..')=0),
    started_at_us INTEGER NOT NULL CHECK(typeof(started_at_us)='integer'),
    ended_at_us INTEGER NOT NULL CHECK(typeof(ended_at_us)='integer' AND ended_at_us > started_at_us),
    PRIMARY KEY(submission_id, manifest_id, ordinal),
    UNIQUE(submission_id, gap_id),
    CHECK(length(gap_id)=64 AND gap_id NOT GLOB '*[^0-9a-f]*')
);
CREATE TABLE estimator_evidence_access_manifests (
    submission_id TEXT PRIMARY KEY,
    manifest_id TEXT NOT NULL UNIQUE,
    manifest_fingerprint TEXT NOT NULL UNIQUE,
    event_set_fingerprint TEXT NOT NULL,
    gap_set_fingerprint TEXT NOT NULL,
    campaign_id TEXT NOT NULL REFERENCES estimator_gate_campaigns(campaign_id) ON DELETE CASCADE,
    auditor_version TEXT NOT NULL CHECK(length(auditor_version) BETWEEN 1 AND 128 AND auditor_version GLOB '[A-Za-z0-9]*' AND auditor_version NOT GLOB '*[^A-Za-z0-9._+-]*' AND instr(auditor_version,'..')=0),
    coverage_started_at_us INTEGER NOT NULL CHECK(typeof(coverage_started_at_us)='integer'),
    coverage_ended_at_us INTEGER NOT NULL CHECK(typeof(coverage_ended_at_us)='integer' AND coverage_ended_at_us >= coverage_started_at_us),
    frozen_at_us INTEGER NOT NULL CHECK(typeof(frozen_at_us)='integer' AND frozen_at_us >= coverage_ended_at_us),
    event_count INTEGER NOT NULL CHECK(event_count BETWEEN 1 AND 20000),
    gap_count INTEGER NOT NULL CHECK(gap_count BETWEEN 0 AND 20000),
    CHECK(length(manifest_id)=64 AND manifest_id NOT GLOB '*[^0-9a-f]*'),
    CHECK(length(manifest_fingerprint)=64 AND manifest_fingerprint NOT GLOB '*[^0-9a-f]*'),
    CHECK(length(event_set_fingerprint)=64 AND event_set_fingerprint NOT GLOB '*[^0-9a-f]*'),
    CHECK(length(gap_set_fingerprint)=64 AND gap_set_fingerprint NOT GLOB '*[^0-9a-f]*')
);
CREATE TABLE estimator_evidence_access_audit_cases (
    submission_id TEXT NOT NULL,
    audit_id TEXT NOT NULL,
    ordinal INTEGER NOT NULL CHECK(ordinal BETWEEN 0 AND 999999),
    case_id TEXT NOT NULL,
    campaign_id TEXT NOT NULL REFERENCES estimator_gate_campaigns(campaign_id) ON DELETE CASCADE,
    PRIMARY KEY(submission_id, ordinal),
    UNIQUE(submission_id, case_id),
    CHECK(length(audit_id)=64 AND audit_id NOT GLOB '*[^0-9a-f]*'),
    CHECK(length(case_id)=64 AND case_id NOT GLOB '*[^0-9a-f]*')
);
CREATE TABLE estimator_evidence_access_audits (
    submission_id TEXT PRIMARY KEY,
    audit_id TEXT NOT NULL UNIQUE,
    audit_fingerprint TEXT NOT NULL UNIQUE,
    campaign_id TEXT NOT NULL REFERENCES estimator_gate_campaigns(campaign_id) ON DELETE CASCADE,
    manifest_id TEXT NOT NULL,
    holdout_unsealed_at_us INTEGER NOT NULL CHECK(typeof(holdout_unsealed_at_us)='integer'),
    completed_at_us INTEGER NOT NULL CHECK(typeof(completed_at_us)='integer'),
    holdout_count INTEGER NOT NULL CHECK(holdout_count BETWEEN 1 AND 1000000),
    CHECK(length(audit_id)=64 AND audit_id NOT GLOB '*[^0-9a-f]*'),
    CHECK(length(audit_fingerprint)=64 AND audit_fingerprint NOT GLOB '*[^0-9a-f]*')
);

CREATE TABLE estimator_evidence_privacy_artifacts (
    submission_id TEXT NOT NULL,
    manifest_id TEXT NOT NULL,
    set_kind TEXT NOT NULL CHECK(set_kind IN ('expected','scanned')),
    ordinal INTEGER NOT NULL CHECK(ordinal BETWEEN 0 AND 19999),
    artifact_fingerprint TEXT NOT NULL,
    campaign_id TEXT NOT NULL REFERENCES estimator_gate_campaigns(campaign_id) ON DELETE CASCADE,
    PRIMARY KEY(submission_id, set_kind, ordinal),
    UNIQUE(submission_id, set_kind, artifact_fingerprint),
    CHECK(length(artifact_fingerprint)=64 AND artifact_fingerprint NOT GLOB '*[^0-9a-f]*')
);
CREATE TABLE estimator_evidence_privacy_findings (
    submission_id TEXT NOT NULL,
    manifest_id TEXT NOT NULL,
    ordinal INTEGER NOT NULL CHECK(ordinal BETWEEN 0 AND 19999),
    finding_id TEXT NOT NULL,
    finding_fingerprint TEXT NOT NULL,
    campaign_id TEXT NOT NULL REFERENCES estimator_gate_campaigns(campaign_id) ON DELETE CASCADE,
    artifact_fingerprint TEXT NOT NULL,
    detector_key TEXT NOT NULL CHECK(length(detector_key) BETWEEN 1 AND 128 AND detector_key GLOB '[a-z]*' AND detector_key NOT GLOB '*[^a-z0-9._-]*' AND instr(detector_key,'..')=0),
    detector_version TEXT NOT NULL CHECK(length(detector_version) BETWEEN 1 AND 128 AND detector_version GLOB '[A-Za-z0-9]*' AND detector_version NOT GLOB '*[^A-Za-z0-9._+-]*' AND instr(detector_version,'..')=0),
    category TEXT NOT NULL CHECK(category IN ('prompt_text','evidence_text','model_output_text','reasoning_trace','reviewer_prose','filesystem_path','uri','credential','personal_data','provider_identifier')),
    occurrence_count INTEGER NOT NULL CHECK(typeof(occurrence_count)='integer' AND occurrence_count BETWEEN 1 AND 1000000),
    detected_at_us INTEGER NOT NULL CHECK(typeof(detected_at_us)='integer'),
    PRIMARY KEY(submission_id, manifest_id, ordinal),
    UNIQUE(submission_id, finding_id),
    CHECK(length(finding_id)=64 AND finding_id NOT GLOB '*[^0-9a-f]*'),
    CHECK(length(finding_fingerprint)=64 AND finding_fingerprint NOT GLOB '*[^0-9a-f]*'),
    CHECK(length(artifact_fingerprint)=64 AND artifact_fingerprint NOT GLOB '*[^0-9a-f]*')
);
CREATE TABLE estimator_evidence_privacy_manifests (
    submission_id TEXT PRIMARY KEY,
    manifest_id TEXT NOT NULL UNIQUE,
    manifest_fingerprint TEXT NOT NULL UNIQUE,
    finding_set_fingerprint TEXT NOT NULL,
    campaign_id TEXT NOT NULL REFERENCES estimator_gate_campaigns(campaign_id) ON DELETE CASCADE,
    frozen_at_us INTEGER NOT NULL CHECK(typeof(frozen_at_us)='integer'),
    expected_count INTEGER NOT NULL CHECK(expected_count BETWEEN 1 AND 20000),
    scanned_count INTEGER NOT NULL CHECK(scanned_count BETWEEN 1 AND 20000),
    finding_row_count INTEGER NOT NULL CHECK(finding_row_count BETWEEN 0 AND 20000),
    finding_occurrence_count INTEGER NOT NULL CHECK(finding_occurrence_count BETWEEN 0 AND 20000000000),
    CHECK(length(manifest_id)=64 AND manifest_id NOT GLOB '*[^0-9a-f]*'),
    CHECK(length(manifest_fingerprint)=64 AND manifest_fingerprint NOT GLOB '*[^0-9a-f]*'),
    CHECK(length(finding_set_fingerprint)=64 AND finding_set_fingerprint NOT GLOB '*[^0-9a-f]*')
);
CREATE TABLE estimator_evidence_privacy_scans (
    submission_id TEXT PRIMARY KEY,
    scan_id TEXT NOT NULL UNIQUE,
    scan_fingerprint TEXT NOT NULL UNIQUE,
    campaign_id TEXT NOT NULL REFERENCES estimator_gate_campaigns(campaign_id) ON DELETE CASCADE,
    manifest_id TEXT NOT NULL,
    scanner_version TEXT NOT NULL CHECK(length(scanner_version) BETWEEN 1 AND 128 AND scanner_version GLOB '[A-Za-z0-9]*' AND scanner_version NOT GLOB '*[^A-Za-z0-9._+-]*' AND instr(scanner_version,'..')=0),
    started_at_us INTEGER NOT NULL CHECK(typeof(started_at_us)='integer'),
    completed_at_us INTEGER NOT NULL CHECK(typeof(completed_at_us)='integer' AND completed_at_us >= started_at_us),
    CHECK(length(scan_id)=64 AND scan_id NOT GLOB '*[^0-9a-f]*'),
    CHECK(length(scan_fingerprint)=64 AND scan_fingerprint NOT GLOB '*[^0-9a-f]*')
);

CREATE TABLE estimator_evidence_structured_estimates (
    submission_id TEXT NOT NULL,
    receipt_id TEXT NOT NULL,
    receipt_fingerprint TEXT NOT NULL,
    campaign_id TEXT NOT NULL REFERENCES estimator_gate_campaigns(campaign_id) ON DELETE CASCADE,
    case_id TEXT NOT NULL,
    plan_fingerprint TEXT NOT NULL,
    metric_question_fingerprint TEXT NOT NULL,
    evidence_packet_fingerprint TEXT NOT NULL,
    attempt_id TEXT NOT NULL,
    outcome_id TEXT NOT NULL,
    outcome_fingerprint TEXT NOT NULL,
    structured_output_fingerprint TEXT NOT NULL,
    value_kind TEXT NOT NULL CHECK(value_kind IN ('continuous','fraction','binary','categorical')),
    value_state TEXT NOT NULL CHECK(value_state IN ('known','unknown','abstained','not_applicable')),
    numeric_value REAL CHECK(numeric_value IS NULL OR (typeof(numeric_value) IN ('real','integer') AND numeric_value BETWEEN -1.0e308 AND 1.0e308)),
    label_code TEXT CHECK(label_code IS NULL OR (length(label_code) BETWEEN 1 AND 128 AND label_code GLOB '[a-z]*' AND label_code NOT GLOB '*[^a-z0-9._-]*' AND instr(label_code,'..')=0)),
    confidence REAL CHECK(confidence IS NULL OR (typeof(confidence) IN ('real','integer') AND confidence BETWEEN 0 AND 1)),
    reason_code TEXT CHECK(reason_code IS NULL OR (length(reason_code) BETWEEN 1 AND 128 AND reason_code GLOB '[a-z]*' AND reason_code NOT GLOB '*[^a-z0-9._-]*' AND instr(reason_code,'..')=0)),
    recorded_at_us INTEGER NOT NULL CHECK(typeof(recorded_at_us)='integer'),
    PRIMARY KEY(submission_id, receipt_id),
    UNIQUE(submission_id, receipt_fingerprint),
    CHECK(length(receipt_id)=64 AND receipt_id NOT GLOB '*[^0-9a-f]*'),
    CHECK(length(receipt_fingerprint)=64 AND receipt_fingerprint NOT GLOB '*[^0-9a-f]*'),
    CHECK((value_state='known' AND reason_code IS NULL AND confidence IS NOT NULL AND ((value_kind IN ('continuous','fraction') AND numeric_value IS NOT NULL AND label_code IS NULL) OR (value_kind IN ('binary','categorical') AND numeric_value IS NULL AND label_code IS NOT NULL))) OR (value_state<>'known' AND numeric_value IS NULL AND label_code IS NULL AND confidence IS NULL AND reason_code IS NOT NULL)),
    CHECK(value_kind<>'fraction' OR numeric_value IS NULL OR numeric_value BETWEEN 0 AND 1)
);

CREATE TABLE estimator_evidence_candidate_projections (
    submission_id TEXT NOT NULL,
    projection_id TEXT NOT NULL,
    projection_fingerprint TEXT NOT NULL,
    campaign_id TEXT NOT NULL REFERENCES estimator_gate_campaigns(campaign_id) ON DELETE CASCADE,
    case_id TEXT NOT NULL,
    plan_fingerprint TEXT NOT NULL,
    metric_question_fingerprint TEXT NOT NULL,
    evidence_packet_fingerprint TEXT NOT NULL,
    attempt_id TEXT NOT NULL,
    outcome_id TEXT NOT NULL,
    outcome_fingerprint TEXT NOT NULL,
    estimate_receipt_id TEXT NOT NULL,
    estimate_receipt_fingerprint TEXT NOT NULL,
    stage_ordinal INTEGER NOT NULL CHECK(stage_ordinal IN (5,6)),
    stage_kind TEXT NOT NULL CHECK(stage_kind IN ('specialist','second_opinion')),
    selected_at_us INTEGER NOT NULL CHECK(typeof(selected_at_us)='integer'),
    PRIMARY KEY(submission_id, projection_id),
    UNIQUE(submission_id, case_id, metric_question_fingerprint),
    CHECK(length(projection_id)=64 AND projection_id NOT GLOB '*[^0-9a-f]*'),
    CHECK(length(projection_fingerprint)=64 AND projection_fingerprint NOT GLOB '*[^0-9a-f]*')
);

CREATE TABLE estimator_evidence_baseline_projections (
    submission_id TEXT NOT NULL,
    projection_id TEXT NOT NULL,
    projection_fingerprint TEXT NOT NULL,
    campaign_id TEXT NOT NULL REFERENCES estimator_gate_campaigns(campaign_id) ON DELETE CASCADE,
    case_id TEXT NOT NULL,
    plan_fingerprint TEXT NOT NULL,
    metric_question_fingerprint TEXT NOT NULL,
    evidence_packet_fingerprint TEXT NOT NULL,
    baseline_id TEXT NOT NULL CHECK(length(baseline_id) BETWEEN 1 AND 128 AND baseline_id GLOB '[A-Za-z0-9]*' AND baseline_id NOT GLOB '*[^A-Za-z0-9._+-]*' AND instr(baseline_id,'..')=0),
    baseline_version TEXT NOT NULL CHECK(length(baseline_version) BETWEEN 1 AND 128 AND baseline_version GLOB '[A-Za-z0-9]*' AND baseline_version NOT GLOB '*[^A-Za-z0-9._+-]*' AND instr(baseline_version,'..')=0),
    baseline_configuration_sha256 TEXT NOT NULL,
    final_estimate_fingerprint TEXT NOT NULL,
    value_kind TEXT NOT NULL CHECK(value_kind IN ('continuous','fraction','binary','categorical')),
    value_state TEXT NOT NULL CHECK(value_state IN ('known','unknown','abstained','not_applicable')),
    numeric_value REAL CHECK(numeric_value IS NULL OR (typeof(numeric_value) IN ('real','integer') AND numeric_value BETWEEN -1.0e308 AND 1.0e308)),
    label_code TEXT CHECK(label_code IS NULL OR (length(label_code) BETWEEN 1 AND 128 AND label_code GLOB '[a-z]*' AND label_code NOT GLOB '*[^a-z0-9._-]*' AND instr(label_code,'..')=0)),
    reason_code TEXT CHECK(reason_code IS NULL OR (length(reason_code) BETWEEN 1 AND 128 AND reason_code GLOB '[a-z]*' AND reason_code NOT GLOB '*[^a-z0-9._-]*' AND instr(reason_code,'..')=0)),
    evaluated_at_us INTEGER NOT NULL CHECK(typeof(evaluated_at_us)='integer'),
    PRIMARY KEY(submission_id, projection_id),
    UNIQUE(submission_id, case_id, metric_question_fingerprint),
    CHECK(length(projection_id)=64 AND projection_id NOT GLOB '*[^0-9a-f]*'),
    CHECK(length(projection_fingerprint)=64 AND projection_fingerprint NOT GLOB '*[^0-9a-f]*'),
    CHECK((value_state='known' AND reason_code IS NULL AND ((value_kind IN ('continuous','fraction') AND numeric_value IS NOT NULL AND label_code IS NULL) OR (value_kind IN ('binary','categorical') AND numeric_value IS NULL AND label_code IS NOT NULL))) OR (value_state<>'known' AND numeric_value IS NULL AND label_code IS NULL AND reason_code IS NOT NULL))
);

CREATE TABLE estimator_evidence_objective_projections (
    submission_id TEXT NOT NULL,
    projection_id TEXT NOT NULL,
    projection_fingerprint TEXT NOT NULL,
    campaign_id TEXT NOT NULL REFERENCES estimator_gate_campaigns(campaign_id) ON DELETE CASCADE,
    case_id TEXT NOT NULL,
    plan_fingerprint TEXT NOT NULL,
    metric_question_fingerprint TEXT NOT NULL,
    evidence_packet_fingerprint TEXT NOT NULL,
    truth_kind TEXT NOT NULL CHECK(truth_kind IN ('test_result','acceptance_artifact','provider_verification','human_verified_artifact')),
    objective_evidence_fingerprint TEXT NOT NULL,
    verification_adapter_version TEXT NOT NULL CHECK(length(verification_adapter_version) BETWEEN 1 AND 128 AND verification_adapter_version GLOB '[A-Za-z0-9]*' AND verification_adapter_version NOT GLOB '*[^A-Za-z0-9._+-]*' AND instr(verification_adapter_version,'..')=0),
    value_kind TEXT NOT NULL CHECK(value_kind IN ('continuous','fraction','binary','categorical')),
    value_state TEXT NOT NULL CHECK(value_state IN ('known','unknown','abstained','not_applicable')),
    numeric_value REAL CHECK(numeric_value IS NULL OR (typeof(numeric_value) IN ('real','integer') AND numeric_value BETWEEN -1.0e308 AND 1.0e308)),
    label_code TEXT CHECK(label_code IS NULL OR (length(label_code) BETWEEN 1 AND 128 AND label_code GLOB '[a-z]*' AND label_code NOT GLOB '*[^a-z0-9._-]*' AND instr(label_code,'..')=0)),
    reason_code TEXT CHECK(reason_code IS NULL OR (length(reason_code) BETWEEN 1 AND 128 AND reason_code GLOB '[a-z]*' AND reason_code NOT GLOB '*[^a-z0-9._-]*' AND instr(reason_code,'..')=0)),
    observed_at_us INTEGER NOT NULL CHECK(typeof(observed_at_us)='integer'),
    PRIMARY KEY(submission_id, projection_id),
    UNIQUE(submission_id, case_id, metric_question_fingerprint),
    CHECK(length(projection_id)=64 AND projection_id NOT GLOB '*[^0-9a-f]*'),
    CHECK(length(projection_fingerprint)=64 AND projection_fingerprint NOT GLOB '*[^0-9a-f]*'),
    CHECK(length(objective_evidence_fingerprint)=64 AND objective_evidence_fingerprint NOT GLOB '*[^0-9a-f]*'),
    CHECK((value_state='known' AND reason_code IS NULL AND ((value_kind IN ('continuous','fraction') AND numeric_value IS NOT NULL AND label_code IS NULL) OR (value_kind IN ('binary','categorical') AND numeric_value IS NULL AND label_code IS NOT NULL))) OR (value_state<>'known' AND numeric_value IS NULL AND label_code IS NULL AND reason_code IS NOT NULL))
);

CREATE TABLE estimator_evidence_blind_judgments (
    submission_id TEXT NOT NULL,
    judgment_id TEXT NOT NULL,
    judgment_fingerprint TEXT NOT NULL,
    campaign_id TEXT NOT NULL REFERENCES estimator_gate_campaigns(campaign_id) ON DELETE CASCADE,
    case_id TEXT NOT NULL,
    plan_fingerprint TEXT NOT NULL,
    metric_question_fingerprint TEXT NOT NULL,
    evidence_packet_fingerprint TEXT NOT NULL,
    participant_id TEXT NOT NULL,
    participant_kind TEXT NOT NULL CHECK(participant_kind IN ('independent_annotator','domain_expert')),
    annotation_protocol_version TEXT NOT NULL CHECK(length(annotation_protocol_version) BETWEEN 1 AND 128 AND annotation_protocol_version GLOB '[A-Za-z0-9]*' AND annotation_protocol_version NOT GLOB '*[^A-Za-z0-9._+-]*' AND instr(annotation_protocol_version,'..')=0),
    value_kind TEXT NOT NULL CHECK(value_kind IN ('continuous','fraction','binary','categorical')),
    value_state TEXT NOT NULL CHECK(value_state IN ('known','unknown','abstained','not_applicable')),
    numeric_value REAL CHECK(numeric_value IS NULL OR (typeof(numeric_value) IN ('real','integer') AND numeric_value BETWEEN -1.0e308 AND 1.0e308)),
    label_code TEXT CHECK(label_code IS NULL OR (length(label_code) BETWEEN 1 AND 128 AND label_code GLOB '[a-z]*' AND label_code NOT GLOB '*[^a-z0-9._-]*' AND instr(label_code,'..')=0)),
    reason_code TEXT CHECK(reason_code IS NULL OR (length(reason_code) BETWEEN 1 AND 128 AND reason_code GLOB '[a-z]*' AND reason_code NOT GLOB '*[^a-z0-9._-]*' AND instr(reason_code,'..')=0)),
    created_at_us INTEGER NOT NULL CHECK(typeof(created_at_us)='integer'),
    PRIMARY KEY(submission_id, judgment_id),
    CHECK(length(judgment_id)=64 AND judgment_id NOT GLOB '*[^0-9a-f]*'),
    CHECK(length(judgment_fingerprint)=64 AND judgment_fingerprint NOT GLOB '*[^0-9a-f]*'),
    CHECK(length(participant_id)=64 AND participant_id NOT GLOB '*[^0-9a-f]*'),
    CHECK((value_state='known' AND reason_code IS NULL AND ((value_kind IN ('continuous','fraction') AND numeric_value IS NOT NULL AND label_code IS NULL) OR (value_kind IN ('binary','categorical') AND numeric_value IS NULL AND label_code IS NOT NULL))) OR (value_state<>'known' AND numeric_value IS NULL AND label_code IS NULL AND reason_code IS NOT NULL))
);
CREATE TABLE estimator_evidence_adjudication_judgments (
    submission_id TEXT NOT NULL,
    adjudication_id TEXT NOT NULL,
    ordinal INTEGER NOT NULL CHECK(ordinal BETWEEN 0 AND 31),
    judgment_id TEXT NOT NULL,
    campaign_id TEXT NOT NULL REFERENCES estimator_gate_campaigns(campaign_id) ON DELETE CASCADE,
    PRIMARY KEY(submission_id, adjudication_id, ordinal),
    UNIQUE(submission_id, adjudication_id, judgment_id)
);
CREATE TABLE estimator_evidence_blind_adjudications (
    submission_id TEXT NOT NULL,
    adjudication_id TEXT NOT NULL,
    adjudication_fingerprint TEXT NOT NULL,
    campaign_id TEXT NOT NULL REFERENCES estimator_gate_campaigns(campaign_id) ON DELETE CASCADE,
    case_id TEXT NOT NULL,
    plan_fingerprint TEXT NOT NULL,
    metric_question_fingerprint TEXT NOT NULL,
    evidence_packet_fingerprint TEXT NOT NULL,
    resolver_id TEXT NOT NULL,
    resolution TEXT NOT NULL CHECK(resolution IN ('resolved','unresolved')),
    annotation_protocol_version TEXT NOT NULL CHECK(length(annotation_protocol_version) BETWEEN 1 AND 128 AND annotation_protocol_version GLOB '[A-Za-z0-9]*' AND annotation_protocol_version NOT GLOB '*[^A-Za-z0-9._+-]*' AND instr(annotation_protocol_version,'..')=0),
    value_kind TEXT NOT NULL CHECK(value_kind IN ('continuous','fraction','binary','categorical')),
    value_state TEXT NOT NULL CHECK(value_state IN ('known','unknown')),
    numeric_value REAL CHECK(numeric_value IS NULL OR (typeof(numeric_value) IN ('real','integer') AND numeric_value BETWEEN -1.0e308 AND 1.0e308)),
    label_code TEXT CHECK(label_code IS NULL OR (length(label_code) BETWEEN 1 AND 128 AND label_code GLOB '[a-z]*' AND label_code NOT GLOB '*[^a-z0-9._-]*' AND instr(label_code,'..')=0)),
    reason_code TEXT CHECK(reason_code IS NULL OR (length(reason_code) BETWEEN 1 AND 128 AND reason_code GLOB '[a-z]*' AND reason_code NOT GLOB '*[^a-z0-9._-]*' AND instr(reason_code,'..')=0)),
    completed_at_us INTEGER NOT NULL CHECK(typeof(completed_at_us)='integer'),
    judgment_count INTEGER NOT NULL CHECK(judgment_count BETWEEN 2 AND 32),
    PRIMARY KEY(submission_id, adjudication_id),
    UNIQUE(submission_id, case_id, metric_question_fingerprint),
    CHECK(length(adjudication_id)=64 AND adjudication_id NOT GLOB '*[^0-9a-f]*'),
    CHECK(length(adjudication_fingerprint)=64 AND adjudication_fingerprint NOT GLOB '*[^0-9a-f]*'),
    CHECK(length(resolver_id)=64 AND resolver_id NOT GLOB '*[^0-9a-f]*'),
    CHECK((resolution='resolved' AND value_state='known' AND reason_code IS NULL AND ((value_kind IN ('continuous','fraction') AND numeric_value IS NOT NULL AND label_code IS NULL) OR (value_kind IN ('binary','categorical') AND numeric_value IS NULL AND label_code IS NOT NULL))) OR (resolution='unresolved' AND value_state='unknown' AND numeric_value IS NULL AND label_code IS NULL AND reason_code IS NOT NULL))
);

CREATE TABLE estimator_evidence_stability_trials (
    submission_id TEXT NOT NULL,
    series_id TEXT NOT NULL,
    trial_ordinal INTEGER NOT NULL CHECK(trial_ordinal BETWEEN 1 AND 20),
    receipt_id TEXT NOT NULL,
    receipt_fingerprint TEXT NOT NULL,
    campaign_id TEXT NOT NULL REFERENCES estimator_gate_campaigns(campaign_id) ON DELETE CASCADE,
    case_id TEXT NOT NULL,
    plan_fingerprint TEXT NOT NULL,
    metric_question_fingerprint TEXT NOT NULL,
    evidence_packet_fingerprint TEXT NOT NULL,
    condition_code TEXT NOT NULL CHECK(condition_code IN ('repeat','order','format','injection')),
    attempt_id TEXT NOT NULL,
    outcome_id TEXT NOT NULL,
    outcome_fingerprint TEXT NOT NULL,
    estimate_receipt_id TEXT NOT NULL,
    estimate_receipt_fingerprint TEXT NOT NULL,
    recorded_at_us INTEGER NOT NULL CHECK(typeof(recorded_at_us)='integer'),
    PRIMARY KEY(submission_id, series_id, trial_ordinal),
    UNIQUE(submission_id, receipt_id),
    UNIQUE(submission_id, series_id, attempt_id),
    CHECK(length(series_id)=64 AND series_id NOT GLOB '*[^0-9a-f]*'),
    CHECK(length(receipt_id)=64 AND receipt_id NOT GLOB '*[^0-9a-f]*'),
    CHECK(length(receipt_fingerprint)=64 AND receipt_fingerprint NOT GLOB '*[^0-9a-f]*')
);
CREATE TABLE estimator_evidence_stability_series (
    submission_id TEXT NOT NULL,
    series_id TEXT NOT NULL,
    series_fingerprint TEXT NOT NULL,
    trial_set_fingerprint TEXT NOT NULL,
    campaign_id TEXT NOT NULL REFERENCES estimator_gate_campaigns(campaign_id) ON DELETE CASCADE,
    case_id TEXT NOT NULL,
    plan_fingerprint TEXT NOT NULL,
    metric_question_fingerprint TEXT NOT NULL,
    evidence_packet_fingerprint TEXT NOT NULL,
    condition_code TEXT NOT NULL CHECK(condition_code IN ('repeat','order','format','injection')),
    frozen_at_us INTEGER NOT NULL CHECK(typeof(frozen_at_us)='integer'),
    trial_count INTEGER NOT NULL CHECK(trial_count BETWEEN 2 AND 20),
    PRIMARY KEY(submission_id, series_id),
    UNIQUE(submission_id, series_fingerprint),
    CHECK(length(series_id)=64 AND series_id NOT GLOB '*[^0-9a-f]*'),
    CHECK(length(series_fingerprint)=64 AND series_fingerprint NOT GLOB '*[^0-9a-f]*'),
    CHECK(length(trial_set_fingerprint)=64 AND trial_set_fingerprint NOT GLOB '*[^0-9a-f]*')
);

CREATE TABLE estimator_evidence_submission_holdout_cases (
    submission_id TEXT NOT NULL,
    ordinal INTEGER NOT NULL CHECK(ordinal BETWEEN 0 AND 999999),
    case_id TEXT NOT NULL,
    campaign_id TEXT NOT NULL REFERENCES estimator_gate_campaigns(campaign_id) ON DELETE CASCADE,
    PRIMARY KEY(submission_id, ordinal),
    UNIQUE(submission_id, case_id),
    CHECK(length(submission_id)=64 AND submission_id NOT GLOB '*[^0-9a-f]*'),
    CHECK(length(case_id)=64 AND case_id NOT GLOB '*[^0-9a-f]*')
);
CREATE TABLE estimator_evidence_submissions (
    submission_id TEXT PRIMARY KEY,
    submission_fingerprint TEXT NOT NULL UNIQUE,
    campaign_id TEXT NOT NULL UNIQUE REFERENCES estimator_gate_campaigns(campaign_id) ON DELETE CASCADE,
    expected_manifest_id TEXT NOT NULL,
    access_audit_id TEXT NOT NULL,
    privacy_scan_id TEXT NOT NULL,
    submitted_at_us INTEGER NOT NULL CHECK(typeof(submitted_at_us)='integer'),
    holdout_count INTEGER NOT NULL CHECK(holdout_count BETWEEN 1 AND 1000000),
    launch_count INTEGER NOT NULL CHECK(launch_count BETWEEN 1 AND 20000),
    outcome_count INTEGER NOT NULL CHECK(outcome_count BETWEEN 1 AND 20000),
    structured_estimate_count INTEGER NOT NULL CHECK(structured_estimate_count BETWEEN 0 AND 20000),
    candidate_projection_count INTEGER NOT NULL CHECK(candidate_projection_count BETWEEN 0 AND 20000),
    baseline_projection_count INTEGER NOT NULL CHECK(baseline_projection_count BETWEEN 0 AND 20000),
    objective_projection_count INTEGER NOT NULL CHECK(objective_projection_count BETWEEN 0 AND 20000),
    judgment_count INTEGER NOT NULL CHECK(judgment_count BETWEEN 0 AND 20000),
    adjudication_count INTEGER NOT NULL CHECK(adjudication_count BETWEEN 0 AND 20000),
    stability_series_count INTEGER NOT NULL CHECK(stability_series_count BETWEEN 0 AND 20000),
    activation_allowed INTEGER NOT NULL DEFAULT 0 CHECK(activation_allowed=0),
    private_export_allowed INTEGER NOT NULL DEFAULT 0 CHECK(private_export_allowed=0),
    team_share_allowed INTEGER NOT NULL DEFAULT 0 CHECK(team_share_allowed=0),
    CHECK(length(submission_id)=64 AND submission_id NOT GLOB '*[^0-9a-f]*'),
    CHECK(length(submission_fingerprint)=64 AND submission_fingerprint NOT GLOB '*[^0-9a-f]*')
);

-- Component roots are always written after their leaves and validate counts,
-- campaign ownership, chronology, ordering, and frozen membership.
CREATE TRIGGER estimator_evidence_expected_manifest_validate BEFORE INSERT ON estimator_evidence_expected_manifests
WHEN NEW.attempt_count <> (SELECT COUNT(*) FROM estimator_evidence_expected_attempts WHERE submission_id=NEW.submission_id AND manifest_id=NEW.manifest_id)
 OR NEW.plan_fingerprint <> (SELECT stored_plan_fingerprint FROM estimator_gate_campaigns WHERE campaign_id=NEW.campaign_id)
 OR EXISTS (SELECT 1 FROM estimator_evidence_expected_attempts WHERE submission_id=NEW.submission_id AND (campaign_id<>NEW.campaign_id OR plan_fingerprint<>NEW.plan_fingerprint))
 OR EXISTS (SELECT 1 FROM estimator_evidence_expected_attempts AS item LEFT JOIN estimator_constellation_stages AS stage ON stage.stage_fingerprint=item.constellation_stage_fingerprint WHERE item.submission_id=NEW.submission_id AND (stage.ordinal IS NULL OR stage.ordinal<>item.stage_ordinal OR stage.kind<>item.stage_kind OR stage.stage_configuration_sha256<>item.stage_configuration_sha256))
 OR EXISTS (SELECT 1 FROM estimator_evidence_attempt_launches AS launch JOIN estimator_evidence_expected_attempts AS expected USING(submission_id,attempt_id) WHERE launch.submission_id=NEW.submission_id AND launch.launched_at_us<NEW.frozen_at_us)
 OR NEW.frozen_at_us < CAST((julianday((SELECT registered_at FROM estimator_gate_campaigns WHERE campaign_id=NEW.campaign_id)) - 2440587.5) * 86400000000 AS INTEGER) - 1
 OR EXISTS (SELECT 1 FROM estimator_evidence_expected_attempts AS earlier JOIN estimator_evidence_expected_attempts AS later ON later.submission_id=earlier.submission_id AND later.ordinal=earlier.ordinal+1 WHERE earlier.submission_id=NEW.submission_id AND (earlier.case_id>later.case_id OR (earlier.case_id=later.case_id AND earlier.stage_ordinal>later.stage_ordinal) OR (earlier.case_id=later.case_id AND earlier.stage_ordinal=later.stage_ordinal AND earlier.execution_id>later.execution_id) OR (earlier.case_id=later.case_id AND earlier.stage_ordinal=later.stage_ordinal AND earlier.execution_id=later.execution_id AND earlier.attempt_id>=later.attempt_id)))
BEGIN SELECT RAISE(ABORT,'estimator evidence expected manifest is inconsistent'); END;

CREATE TRIGGER estimator_evidence_access_manifest_validate BEFORE INSERT ON estimator_evidence_access_manifests
WHEN NEW.event_count <> (SELECT COUNT(*) FROM estimator_evidence_access_events WHERE submission_id=NEW.submission_id AND manifest_id=NEW.manifest_id)
 OR NEW.gap_count <> (SELECT COUNT(*) FROM estimator_evidence_access_gaps WHERE submission_id=NEW.submission_id AND manifest_id=NEW.manifest_id)
 OR EXISTS (SELECT 1 FROM estimator_evidence_access_events WHERE submission_id=NEW.submission_id AND (campaign_id<>NEW.campaign_id OR occurred_at_us<NEW.coverage_started_at_us OR occurred_at_us>NEW.coverage_ended_at_us))
 OR EXISTS (SELECT 1 FROM estimator_evidence_access_gaps WHERE submission_id=NEW.submission_id AND (campaign_id<>NEW.campaign_id OR started_at_us<NEW.coverage_started_at_us OR ended_at_us>NEW.coverage_ended_at_us))
 OR EXISTS (SELECT 1 FROM estimator_evidence_access_events AS earlier JOIN estimator_evidence_access_events AS later ON later.submission_id=earlier.submission_id AND later.manifest_id=earlier.manifest_id AND later.ordinal=earlier.ordinal+1 WHERE earlier.submission_id=NEW.submission_id AND earlier.manifest_id=NEW.manifest_id AND (earlier.occurred_at_us>later.occurred_at_us OR (earlier.occurred_at_us=later.occurred_at_us AND earlier.event_id>=later.event_id)))
 OR EXISTS (SELECT 1 FROM estimator_evidence_access_gaps AS earlier JOIN estimator_evidence_access_gaps AS later ON later.submission_id=earlier.submission_id AND later.manifest_id=earlier.manifest_id AND later.ordinal=earlier.ordinal+1 WHERE earlier.submission_id=NEW.submission_id AND earlier.manifest_id=NEW.manifest_id AND (earlier.started_at_us>later.started_at_us OR (earlier.started_at_us=later.started_at_us AND (earlier.ended_at_us>later.ended_at_us OR (earlier.ended_at_us=later.ended_at_us AND earlier.gap_id>=later.gap_id))) OR later.started_at_us<earlier.ended_at_us))
BEGIN SELECT RAISE(ABORT,'estimator evidence access manifest is inconsistent'); END;

CREATE TRIGGER estimator_evidence_access_audit_validate BEFORE INSERT ON estimator_evidence_access_audits
WHEN NEW.holdout_count <> (SELECT COUNT(*) FROM estimator_evidence_access_audit_cases WHERE submission_id=NEW.submission_id AND audit_id=NEW.audit_id)
 OR NOT EXISTS (SELECT 1 FROM estimator_evidence_access_manifests WHERE submission_id=NEW.submission_id AND manifest_id=NEW.manifest_id AND campaign_id=NEW.campaign_id AND coverage_started_at_us<=NEW.holdout_unsealed_at_us AND coverage_ended_at_us>=NEW.holdout_unsealed_at_us AND frozen_at_us<=NEW.completed_at_us)
 OR EXISTS (SELECT 1 FROM estimator_evidence_access_audit_cases WHERE submission_id=NEW.submission_id AND campaign_id<>NEW.campaign_id)
 OR EXISTS (SELECT 1 FROM estimator_evidence_access_events AS event WHERE event.submission_id=NEW.submission_id AND NOT EXISTS (SELECT 1 FROM estimator_evidence_access_audit_cases AS item WHERE item.submission_id=NEW.submission_id AND item.case_id=event.case_id))
BEGIN SELECT RAISE(ABORT,'estimator evidence access audit is inconsistent'); END;

CREATE TRIGGER estimator_evidence_privacy_manifest_validate BEFORE INSERT ON estimator_evidence_privacy_manifests
WHEN NEW.expected_count <> (SELECT COUNT(*) FROM estimator_evidence_privacy_artifacts WHERE submission_id=NEW.submission_id AND manifest_id=NEW.manifest_id AND set_kind='expected')
 OR NEW.scanned_count <> (SELECT COUNT(*) FROM estimator_evidence_privacy_artifacts WHERE submission_id=NEW.submission_id AND manifest_id=NEW.manifest_id AND set_kind='scanned')
 OR NEW.finding_row_count <> (SELECT COUNT(*) FROM estimator_evidence_privacy_findings WHERE submission_id=NEW.submission_id AND manifest_id=NEW.manifest_id)
 OR NEW.finding_occurrence_count <> COALESCE((SELECT SUM(occurrence_count) FROM estimator_evidence_privacy_findings WHERE submission_id=NEW.submission_id AND manifest_id=NEW.manifest_id),0)
 OR EXISTS (SELECT 1 FROM estimator_evidence_privacy_artifacts AS scanned WHERE scanned.submission_id=NEW.submission_id AND scanned.set_kind='scanned' AND NOT EXISTS (SELECT 1 FROM estimator_evidence_privacy_artifacts AS expected WHERE expected.submission_id=scanned.submission_id AND expected.set_kind='expected' AND expected.artifact_fingerprint=scanned.artifact_fingerprint))
 OR EXISTS (SELECT 1 FROM estimator_evidence_privacy_findings AS finding WHERE finding.submission_id=NEW.submission_id AND (finding.campaign_id<>NEW.campaign_id OR finding.detected_at_us>NEW.frozen_at_us OR NOT EXISTS (SELECT 1 FROM estimator_evidence_privacy_artifacts AS scanned WHERE scanned.submission_id=finding.submission_id AND scanned.set_kind='scanned' AND scanned.artifact_fingerprint=finding.artifact_fingerprint)))
BEGIN SELECT RAISE(ABORT,'estimator evidence privacy manifest is inconsistent'); END;

CREATE TRIGGER estimator_evidence_privacy_scan_validate BEFORE INSERT ON estimator_evidence_privacy_scans
WHEN NOT EXISTS (SELECT 1 FROM estimator_evidence_privacy_manifests WHERE submission_id=NEW.submission_id AND manifest_id=NEW.manifest_id AND campaign_id=NEW.campaign_id AND frozen_at_us<=NEW.completed_at_us)
BEGIN SELECT RAISE(ABORT,'estimator evidence privacy scan is inconsistent'); END;

CREATE TRIGGER estimator_evidence_adjudication_validate BEFORE INSERT ON estimator_evidence_blind_adjudications
WHEN NEW.judgment_count <> (SELECT COUNT(*) FROM estimator_evidence_adjudication_judgments WHERE submission_id=NEW.submission_id AND adjudication_id=NEW.adjudication_id)
 OR EXISTS (SELECT 1 FROM estimator_evidence_adjudication_judgments AS link LEFT JOIN estimator_evidence_blind_judgments AS judgment ON judgment.submission_id=link.submission_id AND judgment.judgment_id=link.judgment_id WHERE link.submission_id=NEW.submission_id AND link.adjudication_id=NEW.adjudication_id AND (judgment.judgment_id IS NULL OR judgment.campaign_id<>NEW.campaign_id OR judgment.case_id<>NEW.case_id OR judgment.metric_question_fingerprint<>NEW.metric_question_fingerprint OR judgment.evidence_packet_fingerprint<>NEW.evidence_packet_fingerprint OR judgment.annotation_protocol_version<>NEW.annotation_protocol_version OR judgment.created_at_us>NEW.completed_at_us OR judgment.participant_id=NEW.resolver_id))
 OR (SELECT COUNT(DISTINCT judgment.participant_id) FROM estimator_evidence_adjudication_judgments AS link JOIN estimator_evidence_blind_judgments AS judgment ON judgment.submission_id=link.submission_id AND judgment.judgment_id=link.judgment_id WHERE link.submission_id=NEW.submission_id AND link.adjudication_id=NEW.adjudication_id) < 2
BEGIN SELECT RAISE(ABORT,'estimator evidence adjudication is inconsistent'); END;

CREATE TRIGGER estimator_evidence_stability_series_validate BEFORE INSERT ON estimator_evidence_stability_series
WHEN NEW.trial_count <> (SELECT COUNT(*) FROM estimator_evidence_stability_trials WHERE submission_id=NEW.submission_id AND series_id=NEW.series_id)
 OR EXISTS (SELECT 1 FROM estimator_evidence_stability_trials WHERE submission_id=NEW.submission_id AND series_id=NEW.series_id AND (campaign_id<>NEW.campaign_id OR case_id<>NEW.case_id OR plan_fingerprint<>NEW.plan_fingerprint OR metric_question_fingerprint<>NEW.metric_question_fingerprint OR evidence_packet_fingerprint<>NEW.evidence_packet_fingerprint OR condition_code<>NEW.condition_code OR recorded_at_us>NEW.frozen_at_us))
BEGIN SELECT RAISE(ABORT,'estimator evidence stability series is inconsistent'); END;

-- The final root is the only sealed evidence-set marker. It rechecks every
-- aggregate from child rows and the exact v16 campaign holdout/lineage.
CREATE TRIGGER estimator_evidence_submission_validate BEFORE INSERT ON estimator_evidence_submissions
WHEN NOT EXISTS (SELECT 1 FROM estimator_gate_campaigns WHERE campaign_id=NEW.campaign_id)
 OR NOT EXISTS (SELECT 1 FROM estimator_evidence_expected_manifests WHERE submission_id=NEW.submission_id AND manifest_id=NEW.expected_manifest_id AND campaign_id=NEW.campaign_id)
 OR NOT EXISTS (SELECT 1 FROM estimator_evidence_access_audits WHERE submission_id=NEW.submission_id AND audit_id=NEW.access_audit_id AND campaign_id=NEW.campaign_id)
 OR NOT EXISTS (SELECT 1 FROM estimator_evidence_privacy_scans WHERE submission_id=NEW.submission_id AND scan_id=NEW.privacy_scan_id AND campaign_id=NEW.campaign_id AND completed_at_us<=NEW.submitted_at_us)
 OR NEW.holdout_count<>(SELECT COUNT(*) FROM estimator_evidence_submission_holdout_cases WHERE submission_id=NEW.submission_id)
 OR NEW.launch_count<>(SELECT COUNT(*) FROM estimator_evidence_attempt_launches WHERE submission_id=NEW.submission_id)
 OR NEW.outcome_count<>(SELECT COUNT(*) FROM estimator_evidence_attempt_outcomes WHERE submission_id=NEW.submission_id)
 OR NEW.structured_estimate_count<>(SELECT COUNT(*) FROM estimator_evidence_structured_estimates WHERE submission_id=NEW.submission_id)
 OR NEW.candidate_projection_count<>(SELECT COUNT(*) FROM estimator_evidence_candidate_projections WHERE submission_id=NEW.submission_id)
 OR NEW.baseline_projection_count<>(SELECT COUNT(*) FROM estimator_evidence_baseline_projections WHERE submission_id=NEW.submission_id)
 OR NEW.objective_projection_count<>(SELECT COUNT(*) FROM estimator_evidence_objective_projections WHERE submission_id=NEW.submission_id)
 OR NEW.judgment_count<>(SELECT COUNT(*) FROM estimator_evidence_blind_judgments WHERE submission_id=NEW.submission_id)
 OR NEW.adjudication_count<>(SELECT COUNT(*) FROM estimator_evidence_blind_adjudications WHERE submission_id=NEW.submission_id)
 OR NEW.stability_series_count<>(SELECT COUNT(*) FROM estimator_evidence_stability_series WHERE submission_id=NEW.submission_id)
 OR EXISTS (SELECT 1 FROM estimator_evidence_submission_holdout_cases WHERE submission_id=NEW.submission_id AND campaign_id<>NEW.campaign_id)
 OR EXISTS (SELECT 1 FROM estimator_calibration_split_cases AS split JOIN estimator_gate_campaigns AS campaign ON campaign.split_fingerprint=split.split_fingerprint WHERE campaign.campaign_id=NEW.campaign_id AND split.partition_code='holdout' AND NOT EXISTS (SELECT 1 FROM estimator_evidence_submission_holdout_cases AS item WHERE item.submission_id=NEW.submission_id AND item.case_id=split.case_id))
 OR EXISTS (SELECT 1 FROM estimator_evidence_submission_holdout_cases AS item WHERE item.submission_id=NEW.submission_id AND NOT EXISTS (SELECT 1 FROM estimator_calibration_split_cases AS split JOIN estimator_gate_campaigns AS campaign ON campaign.split_fingerprint=split.split_fingerprint WHERE campaign.campaign_id=NEW.campaign_id AND split.partition_code='holdout' AND split.case_id=item.case_id))
 OR NEW.launch_count<>(SELECT attempt_count FROM estimator_evidence_expected_manifests WHERE submission_id=NEW.submission_id)
 OR NEW.outcome_count<>(SELECT attempt_count FROM estimator_evidence_expected_manifests WHERE submission_id=NEW.submission_id)
 OR EXISTS (SELECT 1 FROM estimator_evidence_expected_attempts AS expected LEFT JOIN estimator_evidence_attempt_launches AS launch ON launch.submission_id=expected.submission_id AND launch.attempt_id=expected.attempt_id LEFT JOIN estimator_evidence_attempt_outcomes AS outcome ON outcome.submission_id=expected.submission_id AND outcome.attempt_id=expected.attempt_id LEFT JOIN estimator_gate_campaigns AS campaign ON campaign.campaign_id=NEW.campaign_id LEFT JOIN estimator_case_assignments_v2 AS assignment ON assignment.manifest_fingerprint=campaign.assignment_manifest_fingerprint AND assignment.case_id=expected.case_id LEFT JOIN estimator_constellation_stages AS stage ON stage.constellation_fingerprint=campaign.constellation_fingerprint AND stage.stage_fingerprint=expected.constellation_stage_fingerprint LEFT JOIN estimator_model_artifacts AS artifact ON artifact.artifact_fingerprint=stage.model_artifact_fingerprint WHERE expected.submission_id=NEW.submission_id AND (assignment.case_id IS NULL OR stage.stage_fingerprint IS NULL OR artifact.artifact_fingerprint IS NULL OR expected.campaign_id<>NEW.campaign_id OR expected.plan_fingerprint<>campaign.stored_plan_fingerprint OR expected.metric_question_fingerprint<>assignment.metric_question_fingerprint OR expected.evidence_packet_fingerprint<>assignment.evidence_packet_fingerprint OR stage.ordinal<>expected.stage_ordinal OR stage.kind<>expected.stage_kind OR stage.stage_configuration_sha256<>expected.stage_configuration_sha256 OR launch.attempt_id IS NULL OR outcome.attempt_id IS NULL OR launch.campaign_id<>NEW.campaign_id OR outcome.campaign_id<>NEW.campaign_id OR launch.execution_id<>expected.execution_id OR launch.case_id<>expected.case_id OR launch.plan_fingerprint<>expected.plan_fingerprint OR launch.metric_question_fingerprint<>expected.metric_question_fingerprint OR launch.evidence_packet_fingerprint<>expected.evidence_packet_fingerprint OR launch.constellation_stage_fingerprint<>expected.constellation_stage_fingerprint OR launch.stage_ordinal<>expected.stage_ordinal OR launch.stage_kind<>expected.stage_kind OR launch.stage_configuration_sha256<>expected.stage_configuration_sha256 OR launch.model_artifact_fingerprint<>stage.model_artifact_fingerprint OR launch.requested_source<>artifact.source OR launch.requested_model_id<>artifact.requested_model_id OR launch.requested_revision<>artifact.requested_revision OR launch.requested_execution_mode<>artifact.requested_execution_mode OR launch.response_schema_version<>stage.output_schema_version OR outcome.execution_id<>launch.execution_id OR outcome.case_id<>launch.case_id OR outcome.plan_fingerprint<>launch.plan_fingerprint OR outcome.metric_question_fingerprint<>launch.metric_question_fingerprint OR outcome.evidence_packet_fingerprint<>launch.evidence_packet_fingerprint OR outcome.started_at_us<>launch.launched_at_us OR (outcome.served_state='observed' AND outcome.fallback_used <> (outcome.served_source<>launch.requested_source OR outcome.served_model_id<>launch.requested_model_id OR outcome.served_revision<>launch.requested_revision OR outcome.served_execution_mode<>launch.requested_execution_mode))))
 OR EXISTS (SELECT 1 FROM estimator_evidence_structured_estimates AS estimate LEFT JOIN estimator_evidence_attempt_outcomes AS outcome ON outcome.submission_id=estimate.submission_id AND outcome.attempt_id=estimate.attempt_id WHERE estimate.submission_id=NEW.submission_id AND (outcome.attempt_id IS NULL OR outcome.terminal_state<>'success' OR estimate.campaign_id<>NEW.campaign_id OR estimate.outcome_id<>outcome.outcome_id OR estimate.outcome_fingerprint<>outcome.outcome_fingerprint OR estimate.structured_output_fingerprint<>outcome.structured_output_fingerprint OR estimate.case_id<>outcome.case_id OR estimate.plan_fingerprint<>outcome.plan_fingerprint OR estimate.metric_question_fingerprint<>outcome.metric_question_fingerprint OR estimate.evidence_packet_fingerprint<>outcome.evidence_packet_fingerprint OR estimate.recorded_at_us<outcome.finished_at_us))
 OR EXISTS (SELECT 1 FROM estimator_evidence_candidate_projections AS projection LEFT JOIN estimator_evidence_attempt_launches AS launch ON launch.submission_id=projection.submission_id AND launch.attempt_id=projection.attempt_id LEFT JOIN estimator_evidence_attempt_outcomes AS outcome ON outcome.submission_id=projection.submission_id AND outcome.attempt_id=projection.attempt_id LEFT JOIN estimator_evidence_structured_estimates AS estimate ON estimate.submission_id=projection.submission_id AND estimate.receipt_id=projection.estimate_receipt_id WHERE projection.submission_id=NEW.submission_id AND (launch.attempt_id IS NULL OR outcome.attempt_id IS NULL OR estimate.receipt_id IS NULL OR projection.campaign_id<>NEW.campaign_id OR projection.outcome_id<>outcome.outcome_id OR projection.outcome_fingerprint<>outcome.outcome_fingerprint OR projection.estimate_receipt_fingerprint<>estimate.receipt_fingerprint OR estimate.attempt_id<>projection.attempt_id OR estimate.outcome_id<>projection.outcome_id OR projection.case_id<>launch.case_id OR projection.plan_fingerprint<>launch.plan_fingerprint OR projection.metric_question_fingerprint<>launch.metric_question_fingerprint OR projection.evidence_packet_fingerprint<>launch.evidence_packet_fingerprint OR projection.stage_ordinal<>launch.stage_ordinal OR projection.stage_kind<>launch.stage_kind OR projection.selected_at_us<outcome.finished_at_us OR projection.selected_at_us<estimate.recorded_at_us))
 OR EXISTS (SELECT 1 FROM estimator_evidence_baseline_projections AS projection WHERE projection.submission_id=NEW.submission_id AND (projection.campaign_id<>NEW.campaign_id OR NOT EXISTS (SELECT 1 FROM estimator_evidence_expected_attempts AS expected WHERE expected.submission_id=projection.submission_id AND expected.case_id=projection.case_id AND expected.plan_fingerprint=projection.plan_fingerprint AND expected.metric_question_fingerprint=projection.metric_question_fingerprint AND expected.evidence_packet_fingerprint=projection.evidence_packet_fingerprint)))
 OR EXISTS (SELECT 1 FROM estimator_evidence_objective_projections AS projection WHERE projection.submission_id=NEW.submission_id AND (projection.campaign_id<>NEW.campaign_id OR NOT EXISTS (SELECT 1 FROM estimator_evidence_expected_attempts AS expected WHERE expected.submission_id=projection.submission_id AND expected.case_id=projection.case_id AND expected.plan_fingerprint=projection.plan_fingerprint AND expected.metric_question_fingerprint=projection.metric_question_fingerprint AND expected.evidence_packet_fingerprint=projection.evidence_packet_fingerprint)))
 OR EXISTS (SELECT 1 FROM estimator_evidence_blind_judgments AS judgment WHERE judgment.submission_id=NEW.submission_id AND (judgment.campaign_id<>NEW.campaign_id OR NOT EXISTS (SELECT 1 FROM estimator_evidence_expected_attempts AS expected WHERE expected.submission_id=judgment.submission_id AND expected.case_id=judgment.case_id AND expected.plan_fingerprint=judgment.plan_fingerprint AND expected.metric_question_fingerprint=judgment.metric_question_fingerprint AND expected.evidence_packet_fingerprint=judgment.evidence_packet_fingerprint)))
 OR EXISTS (SELECT 1 FROM estimator_evidence_blind_adjudications AS adjudication WHERE adjudication.submission_id=NEW.submission_id AND (adjudication.campaign_id<>NEW.campaign_id OR NOT EXISTS (SELECT 1 FROM estimator_evidence_expected_attempts AS expected WHERE expected.submission_id=adjudication.submission_id AND expected.case_id=adjudication.case_id AND expected.plan_fingerprint=adjudication.plan_fingerprint AND expected.metric_question_fingerprint=adjudication.metric_question_fingerprint AND expected.evidence_packet_fingerprint=adjudication.evidence_packet_fingerprint)))
 OR EXISTS (SELECT 1 FROM estimator_evidence_stability_trials AS trial LEFT JOIN estimator_evidence_attempt_launches AS launch ON launch.submission_id=trial.submission_id AND launch.attempt_id=trial.attempt_id LEFT JOIN estimator_evidence_attempt_outcomes AS outcome ON outcome.submission_id=trial.submission_id AND outcome.attempt_id=trial.attempt_id LEFT JOIN estimator_evidence_structured_estimates AS estimate ON estimate.submission_id=trial.submission_id AND estimate.receipt_id=trial.estimate_receipt_id WHERE trial.submission_id=NEW.submission_id AND (launch.attempt_id IS NULL OR outcome.attempt_id IS NULL OR estimate.receipt_id IS NULL OR launch.stage_kind NOT IN ('specialist','second_opinion') OR trial.campaign_id<>NEW.campaign_id OR trial.outcome_id<>outcome.outcome_id OR trial.outcome_fingerprint<>outcome.outcome_fingerprint OR trial.estimate_receipt_fingerprint<>estimate.receipt_fingerprint OR estimate.attempt_id<>trial.attempt_id OR estimate.outcome_id<>trial.outcome_id OR trial.case_id<>outcome.case_id OR trial.plan_fingerprint<>outcome.plan_fingerprint OR trial.metric_question_fingerprint<>outcome.metric_question_fingerprint OR trial.evidence_packet_fingerprint<>outcome.evidence_packet_fingerprint OR trial.recorded_at_us<outcome.finished_at_us OR trial.recorded_at_us<estimate.recorded_at_us))
 OR EXISTS (SELECT 1 FROM estimator_evidence_access_audit_cases AS audit_case WHERE audit_case.submission_id=NEW.submission_id AND NOT EXISTS (SELECT 1 FROM estimator_evidence_submission_holdout_cases AS holdout WHERE holdout.submission_id=audit_case.submission_id AND holdout.case_id=audit_case.case_id))
 OR EXISTS (SELECT 1 FROM estimator_evidence_submission_holdout_cases AS holdout WHERE holdout.submission_id=NEW.submission_id AND NOT EXISTS (SELECT 1 FROM estimator_evidence_access_audit_cases AS audit_case WHERE audit_case.submission_id=holdout.submission_id AND audit_case.case_id=holdout.case_id))
 OR (SELECT coverage_started_at_us FROM estimator_evidence_access_manifests WHERE submission_id=NEW.submission_id) > (SELECT MIN(outcome.enqueued_at_us) FROM estimator_evidence_attempt_outcomes AS outcome JOIN estimator_evidence_submission_holdout_cases AS holdout ON holdout.submission_id=outcome.submission_id AND holdout.case_id=outcome.case_id WHERE outcome.submission_id=NEW.submission_id)
 OR EXISTS (SELECT 1 FROM estimator_evidence_attempt_outcomes AS outcome JOIN estimator_evidence_access_manifests AS access USING(submission_id) WHERE outcome.submission_id=NEW.submission_id AND outcome.finished_at_us>access.coverage_ended_at_us)
 OR EXISTS (SELECT 1 FROM estimator_evidence_structured_estimates AS estimate JOIN estimator_evidence_access_manifests AS access USING(submission_id) WHERE estimate.submission_id=NEW.submission_id AND estimate.recorded_at_us>access.coverage_ended_at_us)
 OR EXISTS (SELECT 1 FROM estimator_evidence_candidate_projections AS projection JOIN estimator_evidence_access_manifests AS access USING(submission_id) WHERE projection.submission_id=NEW.submission_id AND projection.selected_at_us>access.coverage_ended_at_us)
 OR EXISTS (SELECT 1 FROM estimator_evidence_baseline_projections AS projection JOIN estimator_evidence_access_manifests AS access USING(submission_id) WHERE projection.submission_id=NEW.submission_id AND projection.evaluated_at_us>access.coverage_ended_at_us)
 OR EXISTS (SELECT 1 FROM estimator_evidence_objective_projections AS projection JOIN estimator_evidence_access_manifests AS access USING(submission_id) WHERE projection.submission_id=NEW.submission_id AND projection.observed_at_us>access.coverage_ended_at_us)
 OR EXISTS (SELECT 1 FROM estimator_evidence_blind_judgments AS judgment JOIN estimator_evidence_access_manifests AS access USING(submission_id) WHERE judgment.submission_id=NEW.submission_id AND judgment.created_at_us>access.coverage_ended_at_us)
 OR EXISTS (SELECT 1 FROM estimator_evidence_blind_adjudications AS adjudication JOIN estimator_evidence_access_manifests AS access USING(submission_id) WHERE adjudication.submission_id=NEW.submission_id AND adjudication.completed_at_us>access.coverage_ended_at_us)
 OR EXISTS (SELECT 1 FROM estimator_evidence_stability_series AS series JOIN estimator_evidence_access_manifests AS access USING(submission_id) WHERE series.submission_id=NEW.submission_id AND series.frozen_at_us>access.coverage_ended_at_us)
 OR EXISTS (SELECT 1 FROM estimator_evidence_candidate_projections AS projection JOIN estimator_evidence_submission_holdout_cases AS holdout ON holdout.submission_id=projection.submission_id AND holdout.case_id=projection.case_id JOIN estimator_evidence_access_audits AS audit USING(submission_id) JOIN estimator_evidence_structured_estimates AS estimate ON estimate.submission_id=projection.submission_id AND estimate.receipt_id=projection.estimate_receipt_id WHERE projection.submission_id=NEW.submission_id AND (projection.selected_at_us>=audit.holdout_unsealed_at_us OR estimate.recorded_at_us>=audit.holdout_unsealed_at_us))
 OR EXISTS (SELECT 1 FROM estimator_evidence_baseline_projections AS projection JOIN estimator_evidence_submission_holdout_cases AS holdout ON holdout.submission_id=projection.submission_id AND holdout.case_id=projection.case_id JOIN estimator_evidence_access_audits AS audit USING(submission_id) WHERE projection.submission_id=NEW.submission_id AND projection.evaluated_at_us>=audit.holdout_unsealed_at_us)
 OR EXISTS (SELECT 1 FROM estimator_evidence_stability_series AS series JOIN estimator_evidence_submission_holdout_cases AS holdout ON holdout.submission_id=series.submission_id AND holdout.case_id=series.case_id JOIN estimator_evidence_access_audits AS audit USING(submission_id) WHERE series.submission_id=NEW.submission_id AND (series.frozen_at_us>=audit.holdout_unsealed_at_us OR EXISTS (SELECT 1 FROM estimator_evidence_stability_trials AS trial WHERE trial.submission_id=series.submission_id AND trial.series_id=series.series_id AND trial.recorded_at_us>=audit.holdout_unsealed_at_us)))
 OR (SELECT completed_at_us FROM estimator_evidence_access_audits WHERE submission_id=NEW.submission_id)>NEW.submitted_at_us
 OR EXISTS (SELECT 1 FROM estimator_evidence_privacy_scans AS scan WHERE scan.submission_id=NEW.submission_id AND (scan.completed_at_us>NEW.submitted_at_us OR EXISTS (SELECT 1 FROM estimator_evidence_attempt_outcomes WHERE submission_id=NEW.submission_id AND finished_at_us>scan.completed_at_us) OR EXISTS (SELECT 1 FROM estimator_evidence_structured_estimates WHERE submission_id=NEW.submission_id AND recorded_at_us>scan.completed_at_us) OR EXISTS (SELECT 1 FROM estimator_evidence_candidate_projections WHERE submission_id=NEW.submission_id AND selected_at_us>scan.completed_at_us) OR EXISTS (SELECT 1 FROM estimator_evidence_baseline_projections WHERE submission_id=NEW.submission_id AND evaluated_at_us>scan.completed_at_us) OR EXISTS (SELECT 1 FROM estimator_evidence_objective_projections WHERE submission_id=NEW.submission_id AND observed_at_us>scan.completed_at_us) OR EXISTS (SELECT 1 FROM estimator_evidence_blind_judgments WHERE submission_id=NEW.submission_id AND created_at_us>scan.completed_at_us) OR EXISTS (SELECT 1 FROM estimator_evidence_blind_adjudications WHERE submission_id=NEW.submission_id AND completed_at_us>scan.completed_at_us) OR EXISTS (SELECT 1 FROM estimator_evidence_stability_series WHERE submission_id=NEW.submission_id AND frozen_at_us>scan.completed_at_us)))
 OR EXISTS (SELECT 1 FROM estimator_evidence_attempt_outcomes AS outcome WHERE outcome.submission_id=NEW.submission_id AND outcome.structured_output_fingerprint IS NOT NULL AND NOT EXISTS (SELECT 1 FROM estimator_evidence_privacy_artifacts AS artifact WHERE artifact.submission_id=NEW.submission_id AND artifact.set_kind='expected' AND artifact.artifact_fingerprint=outcome.structured_output_fingerprint))
 OR EXISTS (SELECT 1 FROM estimator_evidence_baseline_projections AS projection WHERE projection.submission_id=NEW.submission_id AND NOT EXISTS (SELECT 1 FROM estimator_evidence_privacy_artifacts AS artifact WHERE artifact.submission_id=NEW.submission_id AND artifact.set_kind='expected' AND artifact.artifact_fingerprint=projection.final_estimate_fingerprint))
 OR EXISTS (SELECT 1 FROM estimator_evidence_objective_projections AS projection WHERE projection.submission_id=NEW.submission_id AND NOT EXISTS (SELECT 1 FROM estimator_evidence_privacy_artifacts AS artifact WHERE artifact.submission_id=NEW.submission_id AND artifact.set_kind='expected' AND artifact.artifact_fingerprint=projection.objective_evidence_fingerprint))
BEGIN SELECT RAISE(ABORT,'estimator calibration evidence root is inconsistent'); END;

-- Sealing and privacy deletion: rows cannot be mutated or deleted while their
-- campaign exists. During an ON DELETE CASCADE, SQLite removes the parent row
-- before firing child DELETE triggers, so the campaign's own atomic cascade is
-- the sole SQL path through these guards. No caller-writable authority table
-- or persisted deletion capability exists.
CREATE TRIGGER estimator_evidence_campaign_delete_authorized BEFORE DELETE ON estimator_gate_campaigns
WHEN NOT EXISTS (SELECT 1 FROM estimator_evidence_delete_authorizations AS auth WHERE auth.campaign_id=OLD.campaign_id AND auth.authorization_tag=estimator_evidence_delete_authorization_tag(auth.authorization_id,auth.campaign_id))
BEGIN SELECT RAISE(ABORT,'estimator evidence campaign delete is not authorized'); END;

CREATE TRIGGER estimator_evidence_launch_no_update BEFORE UPDATE ON estimator_evidence_attempt_launches BEGIN SELECT RAISE(ABORT,'estimator evidence is immutable'); END;
CREATE TRIGGER estimator_evidence_outcome_no_update BEFORE UPDATE ON estimator_evidence_attempt_outcomes BEGIN SELECT RAISE(ABORT,'estimator evidence is immutable'); END;
CREATE TRIGGER estimator_evidence_expected_attempt_no_update BEFORE UPDATE ON estimator_evidence_expected_attempts BEGIN SELECT RAISE(ABORT,'estimator evidence is immutable'); END;
CREATE TRIGGER estimator_evidence_expected_manifest_no_update BEFORE UPDATE ON estimator_evidence_expected_manifests BEGIN SELECT RAISE(ABORT,'estimator evidence is immutable'); END;
CREATE TRIGGER estimator_evidence_access_event_no_update BEFORE UPDATE ON estimator_evidence_access_events BEGIN SELECT RAISE(ABORT,'estimator evidence is immutable'); END;
CREATE TRIGGER estimator_evidence_access_gap_no_update BEFORE UPDATE ON estimator_evidence_access_gaps BEGIN SELECT RAISE(ABORT,'estimator evidence is immutable'); END;
CREATE TRIGGER estimator_evidence_access_manifest_no_update BEFORE UPDATE ON estimator_evidence_access_manifests BEGIN SELECT RAISE(ABORT,'estimator evidence is immutable'); END;
CREATE TRIGGER estimator_evidence_access_audit_case_no_update BEFORE UPDATE ON estimator_evidence_access_audit_cases BEGIN SELECT RAISE(ABORT,'estimator evidence is immutable'); END;
CREATE TRIGGER estimator_evidence_access_audit_no_update BEFORE UPDATE ON estimator_evidence_access_audits BEGIN SELECT RAISE(ABORT,'estimator evidence is immutable'); END;
CREATE TRIGGER estimator_evidence_privacy_artifact_no_update BEFORE UPDATE ON estimator_evidence_privacy_artifacts BEGIN SELECT RAISE(ABORT,'estimator evidence is immutable'); END;
CREATE TRIGGER estimator_evidence_privacy_finding_no_update BEFORE UPDATE ON estimator_evidence_privacy_findings BEGIN SELECT RAISE(ABORT,'estimator evidence is immutable'); END;
CREATE TRIGGER estimator_evidence_privacy_manifest_no_update BEFORE UPDATE ON estimator_evidence_privacy_manifests BEGIN SELECT RAISE(ABORT,'estimator evidence is immutable'); END;
CREATE TRIGGER estimator_evidence_privacy_scan_no_update BEFORE UPDATE ON estimator_evidence_privacy_scans BEGIN SELECT RAISE(ABORT,'estimator evidence is immutable'); END;
CREATE TRIGGER estimator_evidence_estimate_no_update BEFORE UPDATE ON estimator_evidence_structured_estimates BEGIN SELECT RAISE(ABORT,'estimator evidence is immutable'); END;
CREATE TRIGGER estimator_evidence_candidate_no_update BEFORE UPDATE ON estimator_evidence_candidate_projections BEGIN SELECT RAISE(ABORT,'estimator evidence is immutable'); END;
CREATE TRIGGER estimator_evidence_baseline_no_update BEFORE UPDATE ON estimator_evidence_baseline_projections BEGIN SELECT RAISE(ABORT,'estimator evidence is immutable'); END;
CREATE TRIGGER estimator_evidence_objective_no_update BEFORE UPDATE ON estimator_evidence_objective_projections BEGIN SELECT RAISE(ABORT,'estimator evidence is immutable'); END;
CREATE TRIGGER estimator_evidence_judgment_no_update BEFORE UPDATE ON estimator_evidence_blind_judgments BEGIN SELECT RAISE(ABORT,'estimator evidence is immutable'); END;
CREATE TRIGGER estimator_evidence_adjudication_link_no_update BEFORE UPDATE ON estimator_evidence_adjudication_judgments BEGIN SELECT RAISE(ABORT,'estimator evidence is immutable'); END;
CREATE TRIGGER estimator_evidence_adjudication_no_update BEFORE UPDATE ON estimator_evidence_blind_adjudications BEGIN SELECT RAISE(ABORT,'estimator evidence is immutable'); END;
CREATE TRIGGER estimator_evidence_trial_no_update BEFORE UPDATE ON estimator_evidence_stability_trials BEGIN SELECT RAISE(ABORT,'estimator evidence is immutable'); END;
CREATE TRIGGER estimator_evidence_series_no_update BEFORE UPDATE ON estimator_evidence_stability_series BEGIN SELECT RAISE(ABORT,'estimator evidence is immutable'); END;
CREATE TRIGGER estimator_evidence_holdout_no_update BEFORE UPDATE ON estimator_evidence_submission_holdout_cases BEGIN SELECT RAISE(ABORT,'estimator evidence is immutable'); END;
CREATE TRIGGER estimator_evidence_submission_no_update BEFORE UPDATE ON estimator_evidence_submissions BEGIN SELECT RAISE(ABORT,'estimator evidence is immutable'); END;

CREATE TRIGGER estimator_evidence_launch_no_delete BEFORE DELETE ON estimator_evidence_attempt_launches WHEN EXISTS (SELECT 1 FROM estimator_gate_campaigns WHERE campaign_id=OLD.campaign_id) BEGIN SELECT RAISE(ABORT,'estimator evidence requires campaign privacy deletion'); END;
CREATE TRIGGER estimator_evidence_outcome_no_delete BEFORE DELETE ON estimator_evidence_attempt_outcomes WHEN EXISTS (SELECT 1 FROM estimator_gate_campaigns WHERE campaign_id=OLD.campaign_id) BEGIN SELECT RAISE(ABORT,'estimator evidence requires campaign privacy deletion'); END;
CREATE TRIGGER estimator_evidence_expected_attempt_no_delete BEFORE DELETE ON estimator_evidence_expected_attempts WHEN EXISTS (SELECT 1 FROM estimator_gate_campaigns WHERE campaign_id=OLD.campaign_id) BEGIN SELECT RAISE(ABORT,'estimator evidence requires campaign privacy deletion'); END;
CREATE TRIGGER estimator_evidence_expected_manifest_no_delete BEFORE DELETE ON estimator_evidence_expected_manifests WHEN EXISTS (SELECT 1 FROM estimator_gate_campaigns WHERE campaign_id=OLD.campaign_id) BEGIN SELECT RAISE(ABORT,'estimator evidence requires campaign privacy deletion'); END;
CREATE TRIGGER estimator_evidence_access_event_no_delete BEFORE DELETE ON estimator_evidence_access_events WHEN EXISTS (SELECT 1 FROM estimator_gate_campaigns WHERE campaign_id=OLD.campaign_id) BEGIN SELECT RAISE(ABORT,'estimator evidence requires campaign privacy deletion'); END;
CREATE TRIGGER estimator_evidence_access_gap_no_delete BEFORE DELETE ON estimator_evidence_access_gaps WHEN EXISTS (SELECT 1 FROM estimator_gate_campaigns WHERE campaign_id=OLD.campaign_id) BEGIN SELECT RAISE(ABORT,'estimator evidence requires campaign privacy deletion'); END;
CREATE TRIGGER estimator_evidence_access_manifest_no_delete BEFORE DELETE ON estimator_evidence_access_manifests WHEN EXISTS (SELECT 1 FROM estimator_gate_campaigns WHERE campaign_id=OLD.campaign_id) BEGIN SELECT RAISE(ABORT,'estimator evidence requires campaign privacy deletion'); END;
CREATE TRIGGER estimator_evidence_access_audit_case_no_delete BEFORE DELETE ON estimator_evidence_access_audit_cases WHEN EXISTS (SELECT 1 FROM estimator_gate_campaigns WHERE campaign_id=OLD.campaign_id) BEGIN SELECT RAISE(ABORT,'estimator evidence requires campaign privacy deletion'); END;
CREATE TRIGGER estimator_evidence_access_audit_no_delete BEFORE DELETE ON estimator_evidence_access_audits WHEN EXISTS (SELECT 1 FROM estimator_gate_campaigns WHERE campaign_id=OLD.campaign_id) BEGIN SELECT RAISE(ABORT,'estimator evidence requires campaign privacy deletion'); END;
CREATE TRIGGER estimator_evidence_privacy_artifact_no_delete BEFORE DELETE ON estimator_evidence_privacy_artifacts WHEN EXISTS (SELECT 1 FROM estimator_gate_campaigns WHERE campaign_id=OLD.campaign_id) BEGIN SELECT RAISE(ABORT,'estimator evidence requires campaign privacy deletion'); END;
CREATE TRIGGER estimator_evidence_privacy_finding_no_delete BEFORE DELETE ON estimator_evidence_privacy_findings WHEN EXISTS (SELECT 1 FROM estimator_gate_campaigns WHERE campaign_id=OLD.campaign_id) BEGIN SELECT RAISE(ABORT,'estimator evidence requires campaign privacy deletion'); END;
CREATE TRIGGER estimator_evidence_privacy_manifest_no_delete BEFORE DELETE ON estimator_evidence_privacy_manifests WHEN EXISTS (SELECT 1 FROM estimator_gate_campaigns WHERE campaign_id=OLD.campaign_id) BEGIN SELECT RAISE(ABORT,'estimator evidence requires campaign privacy deletion'); END;
CREATE TRIGGER estimator_evidence_privacy_scan_no_delete BEFORE DELETE ON estimator_evidence_privacy_scans WHEN EXISTS (SELECT 1 FROM estimator_gate_campaigns WHERE campaign_id=OLD.campaign_id) BEGIN SELECT RAISE(ABORT,'estimator evidence requires campaign privacy deletion'); END;
CREATE TRIGGER estimator_evidence_estimate_no_delete BEFORE DELETE ON estimator_evidence_structured_estimates WHEN EXISTS (SELECT 1 FROM estimator_gate_campaigns WHERE campaign_id=OLD.campaign_id) BEGIN SELECT RAISE(ABORT,'estimator evidence requires campaign privacy deletion'); END;
CREATE TRIGGER estimator_evidence_candidate_no_delete BEFORE DELETE ON estimator_evidence_candidate_projections WHEN EXISTS (SELECT 1 FROM estimator_gate_campaigns WHERE campaign_id=OLD.campaign_id) BEGIN SELECT RAISE(ABORT,'estimator evidence requires campaign privacy deletion'); END;
CREATE TRIGGER estimator_evidence_baseline_no_delete BEFORE DELETE ON estimator_evidence_baseline_projections WHEN EXISTS (SELECT 1 FROM estimator_gate_campaigns WHERE campaign_id=OLD.campaign_id) BEGIN SELECT RAISE(ABORT,'estimator evidence requires campaign privacy deletion'); END;
CREATE TRIGGER estimator_evidence_objective_no_delete BEFORE DELETE ON estimator_evidence_objective_projections WHEN EXISTS (SELECT 1 FROM estimator_gate_campaigns WHERE campaign_id=OLD.campaign_id) BEGIN SELECT RAISE(ABORT,'estimator evidence requires campaign privacy deletion'); END;
CREATE TRIGGER estimator_evidence_judgment_no_delete BEFORE DELETE ON estimator_evidence_blind_judgments WHEN EXISTS (SELECT 1 FROM estimator_gate_campaigns WHERE campaign_id=OLD.campaign_id) BEGIN SELECT RAISE(ABORT,'estimator evidence requires campaign privacy deletion'); END;
CREATE TRIGGER estimator_evidence_adjudication_link_no_delete BEFORE DELETE ON estimator_evidence_adjudication_judgments WHEN EXISTS (SELECT 1 FROM estimator_gate_campaigns WHERE campaign_id=OLD.campaign_id) BEGIN SELECT RAISE(ABORT,'estimator evidence requires campaign privacy deletion'); END;
CREATE TRIGGER estimator_evidence_adjudication_no_delete BEFORE DELETE ON estimator_evidence_blind_adjudications WHEN EXISTS (SELECT 1 FROM estimator_gate_campaigns WHERE campaign_id=OLD.campaign_id) BEGIN SELECT RAISE(ABORT,'estimator evidence requires campaign privacy deletion'); END;
CREATE TRIGGER estimator_evidence_trial_no_delete BEFORE DELETE ON estimator_evidence_stability_trials WHEN EXISTS (SELECT 1 FROM estimator_gate_campaigns WHERE campaign_id=OLD.campaign_id) BEGIN SELECT RAISE(ABORT,'estimator evidence requires campaign privacy deletion'); END;
CREATE TRIGGER estimator_evidence_series_no_delete BEFORE DELETE ON estimator_evidence_stability_series WHEN EXISTS (SELECT 1 FROM estimator_gate_campaigns WHERE campaign_id=OLD.campaign_id) BEGIN SELECT RAISE(ABORT,'estimator evidence requires campaign privacy deletion'); END;
CREATE TRIGGER estimator_evidence_holdout_no_delete BEFORE DELETE ON estimator_evidence_submission_holdout_cases WHEN EXISTS (SELECT 1 FROM estimator_gate_campaigns WHERE campaign_id=OLD.campaign_id) BEGIN SELECT RAISE(ABORT,'estimator evidence requires campaign privacy deletion'); END;
CREATE TRIGGER estimator_evidence_submission_no_delete BEFORE DELETE ON estimator_evidence_submissions WHEN EXISTS (SELECT 1 FROM estimator_gate_campaigns WHERE campaign_id=OLD.campaign_id) BEGIN SELECT RAISE(ABORT,'estimator evidence requires campaign privacy deletion'); END;

-- Once a component/final root exists, no additional children may be appended.
CREATE TRIGGER estimator_evidence_attempt_launches_authorized BEFORE INSERT ON estimator_evidence_attempt_launches WHEN NOT EXISTS (SELECT 1 FROM estimator_evidence_append_authorizations AS auth WHERE auth.submission_id=NEW.submission_id AND auth.campaign_id=NEW.campaign_id AND auth.authorization_tag=estimator_evidence_authorization_tag(auth.authorization_id,auth.submission_id,auth.campaign_id)) BEGIN SELECT RAISE(ABORT,'estimator evidence append is not authorized'); END;
CREATE TRIGGER estimator_evidence_attempt_launches_final_sealed BEFORE INSERT ON estimator_evidence_attempt_launches WHEN EXISTS (SELECT 1 FROM estimator_evidence_submissions WHERE submission_id=NEW.submission_id) BEGIN SELECT RAISE(ABORT,'estimator evidence submission is sealed'); END;
CREATE TRIGGER estimator_evidence_attempt_outcomes_authorized BEFORE INSERT ON estimator_evidence_attempt_outcomes WHEN NOT EXISTS (SELECT 1 FROM estimator_evidence_append_authorizations AS auth WHERE auth.submission_id=NEW.submission_id AND auth.campaign_id=NEW.campaign_id AND auth.authorization_tag=estimator_evidence_authorization_tag(auth.authorization_id,auth.submission_id,auth.campaign_id)) BEGIN SELECT RAISE(ABORT,'estimator evidence append is not authorized'); END;
CREATE TRIGGER estimator_evidence_attempt_outcomes_final_sealed BEFORE INSERT ON estimator_evidence_attempt_outcomes WHEN EXISTS (SELECT 1 FROM estimator_evidence_submissions WHERE submission_id=NEW.submission_id) BEGIN SELECT RAISE(ABORT,'estimator evidence submission is sealed'); END;
CREATE TRIGGER estimator_evidence_expected_attempts_authorized BEFORE INSERT ON estimator_evidence_expected_attempts WHEN NOT EXISTS (SELECT 1 FROM estimator_evidence_append_authorizations AS auth WHERE auth.submission_id=NEW.submission_id AND auth.campaign_id=NEW.campaign_id AND auth.authorization_tag=estimator_evidence_authorization_tag(auth.authorization_id,auth.submission_id,auth.campaign_id)) BEGIN SELECT RAISE(ABORT,'estimator evidence append is not authorized'); END;
CREATE TRIGGER estimator_evidence_expected_attempts_final_sealed BEFORE INSERT ON estimator_evidence_expected_attempts WHEN EXISTS (SELECT 1 FROM estimator_evidence_submissions WHERE submission_id=NEW.submission_id) BEGIN SELECT RAISE(ABORT,'estimator evidence submission is sealed'); END;
CREATE TRIGGER estimator_evidence_expected_manifests_authorized BEFORE INSERT ON estimator_evidence_expected_manifests WHEN NOT EXISTS (SELECT 1 FROM estimator_evidence_append_authorizations AS auth WHERE auth.submission_id=NEW.submission_id AND auth.campaign_id=NEW.campaign_id AND auth.authorization_tag=estimator_evidence_authorization_tag(auth.authorization_id,auth.submission_id,auth.campaign_id)) BEGIN SELECT RAISE(ABORT,'estimator evidence append is not authorized'); END;
CREATE TRIGGER estimator_evidence_expected_manifests_final_sealed BEFORE INSERT ON estimator_evidence_expected_manifests WHEN EXISTS (SELECT 1 FROM estimator_evidence_submissions WHERE submission_id=NEW.submission_id) BEGIN SELECT RAISE(ABORT,'estimator evidence submission is sealed'); END;
CREATE TRIGGER estimator_evidence_access_events_authorized BEFORE INSERT ON estimator_evidence_access_events WHEN NOT EXISTS (SELECT 1 FROM estimator_evidence_append_authorizations AS auth WHERE auth.submission_id=NEW.submission_id AND auth.campaign_id=NEW.campaign_id AND auth.authorization_tag=estimator_evidence_authorization_tag(auth.authorization_id,auth.submission_id,auth.campaign_id)) BEGIN SELECT RAISE(ABORT,'estimator evidence append is not authorized'); END;
CREATE TRIGGER estimator_evidence_access_events_final_sealed BEFORE INSERT ON estimator_evidence_access_events WHEN EXISTS (SELECT 1 FROM estimator_evidence_submissions WHERE submission_id=NEW.submission_id) BEGIN SELECT RAISE(ABORT,'estimator evidence submission is sealed'); END;
CREATE TRIGGER estimator_evidence_access_gaps_authorized BEFORE INSERT ON estimator_evidence_access_gaps WHEN NOT EXISTS (SELECT 1 FROM estimator_evidence_append_authorizations AS auth WHERE auth.submission_id=NEW.submission_id AND auth.campaign_id=NEW.campaign_id AND auth.authorization_tag=estimator_evidence_authorization_tag(auth.authorization_id,auth.submission_id,auth.campaign_id)) BEGIN SELECT RAISE(ABORT,'estimator evidence append is not authorized'); END;
CREATE TRIGGER estimator_evidence_access_gaps_final_sealed BEFORE INSERT ON estimator_evidence_access_gaps WHEN EXISTS (SELECT 1 FROM estimator_evidence_submissions WHERE submission_id=NEW.submission_id) BEGIN SELECT RAISE(ABORT,'estimator evidence submission is sealed'); END;
CREATE TRIGGER estimator_evidence_access_manifests_authorized BEFORE INSERT ON estimator_evidence_access_manifests WHEN NOT EXISTS (SELECT 1 FROM estimator_evidence_append_authorizations AS auth WHERE auth.submission_id=NEW.submission_id AND auth.campaign_id=NEW.campaign_id AND auth.authorization_tag=estimator_evidence_authorization_tag(auth.authorization_id,auth.submission_id,auth.campaign_id)) BEGIN SELECT RAISE(ABORT,'estimator evidence append is not authorized'); END;
CREATE TRIGGER estimator_evidence_access_manifests_final_sealed BEFORE INSERT ON estimator_evidence_access_manifests WHEN EXISTS (SELECT 1 FROM estimator_evidence_submissions WHERE submission_id=NEW.submission_id) BEGIN SELECT RAISE(ABORT,'estimator evidence submission is sealed'); END;
CREATE TRIGGER estimator_evidence_access_audit_cases_authorized BEFORE INSERT ON estimator_evidence_access_audit_cases WHEN NOT EXISTS (SELECT 1 FROM estimator_evidence_append_authorizations AS auth WHERE auth.submission_id=NEW.submission_id AND auth.campaign_id=NEW.campaign_id AND auth.authorization_tag=estimator_evidence_authorization_tag(auth.authorization_id,auth.submission_id,auth.campaign_id)) BEGIN SELECT RAISE(ABORT,'estimator evidence append is not authorized'); END;
CREATE TRIGGER estimator_evidence_access_audit_cases_final_sealed BEFORE INSERT ON estimator_evidence_access_audit_cases WHEN EXISTS (SELECT 1 FROM estimator_evidence_submissions WHERE submission_id=NEW.submission_id) BEGIN SELECT RAISE(ABORT,'estimator evidence submission is sealed'); END;
CREATE TRIGGER estimator_evidence_access_audits_authorized BEFORE INSERT ON estimator_evidence_access_audits WHEN NOT EXISTS (SELECT 1 FROM estimator_evidence_append_authorizations AS auth WHERE auth.submission_id=NEW.submission_id AND auth.campaign_id=NEW.campaign_id AND auth.authorization_tag=estimator_evidence_authorization_tag(auth.authorization_id,auth.submission_id,auth.campaign_id)) BEGIN SELECT RAISE(ABORT,'estimator evidence append is not authorized'); END;
CREATE TRIGGER estimator_evidence_access_audits_final_sealed BEFORE INSERT ON estimator_evidence_access_audits WHEN EXISTS (SELECT 1 FROM estimator_evidence_submissions WHERE submission_id=NEW.submission_id) BEGIN SELECT RAISE(ABORT,'estimator evidence submission is sealed'); END;
CREATE TRIGGER estimator_evidence_privacy_artifacts_authorized BEFORE INSERT ON estimator_evidence_privacy_artifacts WHEN NOT EXISTS (SELECT 1 FROM estimator_evidence_append_authorizations AS auth WHERE auth.submission_id=NEW.submission_id AND auth.campaign_id=NEW.campaign_id AND auth.authorization_tag=estimator_evidence_authorization_tag(auth.authorization_id,auth.submission_id,auth.campaign_id)) BEGIN SELECT RAISE(ABORT,'estimator evidence append is not authorized'); END;
CREATE TRIGGER estimator_evidence_privacy_artifacts_final_sealed BEFORE INSERT ON estimator_evidence_privacy_artifacts WHEN EXISTS (SELECT 1 FROM estimator_evidence_submissions WHERE submission_id=NEW.submission_id) BEGIN SELECT RAISE(ABORT,'estimator evidence submission is sealed'); END;
CREATE TRIGGER estimator_evidence_privacy_findings_authorized BEFORE INSERT ON estimator_evidence_privacy_findings WHEN NOT EXISTS (SELECT 1 FROM estimator_evidence_append_authorizations AS auth WHERE auth.submission_id=NEW.submission_id AND auth.campaign_id=NEW.campaign_id AND auth.authorization_tag=estimator_evidence_authorization_tag(auth.authorization_id,auth.submission_id,auth.campaign_id)) BEGIN SELECT RAISE(ABORT,'estimator evidence append is not authorized'); END;
CREATE TRIGGER estimator_evidence_privacy_findings_final_sealed BEFORE INSERT ON estimator_evidence_privacy_findings WHEN EXISTS (SELECT 1 FROM estimator_evidence_submissions WHERE submission_id=NEW.submission_id) BEGIN SELECT RAISE(ABORT,'estimator evidence submission is sealed'); END;
CREATE TRIGGER estimator_evidence_privacy_manifests_authorized BEFORE INSERT ON estimator_evidence_privacy_manifests WHEN NOT EXISTS (SELECT 1 FROM estimator_evidence_append_authorizations AS auth WHERE auth.submission_id=NEW.submission_id AND auth.campaign_id=NEW.campaign_id AND auth.authorization_tag=estimator_evidence_authorization_tag(auth.authorization_id,auth.submission_id,auth.campaign_id)) BEGIN SELECT RAISE(ABORT,'estimator evidence append is not authorized'); END;
CREATE TRIGGER estimator_evidence_privacy_manifests_final_sealed BEFORE INSERT ON estimator_evidence_privacy_manifests WHEN EXISTS (SELECT 1 FROM estimator_evidence_submissions WHERE submission_id=NEW.submission_id) BEGIN SELECT RAISE(ABORT,'estimator evidence submission is sealed'); END;
CREATE TRIGGER estimator_evidence_privacy_scans_authorized BEFORE INSERT ON estimator_evidence_privacy_scans WHEN NOT EXISTS (SELECT 1 FROM estimator_evidence_append_authorizations AS auth WHERE auth.submission_id=NEW.submission_id AND auth.campaign_id=NEW.campaign_id AND auth.authorization_tag=estimator_evidence_authorization_tag(auth.authorization_id,auth.submission_id,auth.campaign_id)) BEGIN SELECT RAISE(ABORT,'estimator evidence append is not authorized'); END;
CREATE TRIGGER estimator_evidence_privacy_scans_final_sealed BEFORE INSERT ON estimator_evidence_privacy_scans WHEN EXISTS (SELECT 1 FROM estimator_evidence_submissions WHERE submission_id=NEW.submission_id) BEGIN SELECT RAISE(ABORT,'estimator evidence submission is sealed'); END;
CREATE TRIGGER estimator_evidence_structured_estimates_authorized BEFORE INSERT ON estimator_evidence_structured_estimates WHEN NOT EXISTS (SELECT 1 FROM estimator_evidence_append_authorizations AS auth WHERE auth.submission_id=NEW.submission_id AND auth.campaign_id=NEW.campaign_id AND auth.authorization_tag=estimator_evidence_authorization_tag(auth.authorization_id,auth.submission_id,auth.campaign_id)) BEGIN SELECT RAISE(ABORT,'estimator evidence append is not authorized'); END;
CREATE TRIGGER estimator_evidence_structured_estimates_final_sealed BEFORE INSERT ON estimator_evidence_structured_estimates WHEN EXISTS (SELECT 1 FROM estimator_evidence_submissions WHERE submission_id=NEW.submission_id) BEGIN SELECT RAISE(ABORT,'estimator evidence submission is sealed'); END;
CREATE TRIGGER estimator_evidence_candidate_projections_authorized BEFORE INSERT ON estimator_evidence_candidate_projections WHEN NOT EXISTS (SELECT 1 FROM estimator_evidence_append_authorizations AS auth WHERE auth.submission_id=NEW.submission_id AND auth.campaign_id=NEW.campaign_id AND auth.authorization_tag=estimator_evidence_authorization_tag(auth.authorization_id,auth.submission_id,auth.campaign_id)) BEGIN SELECT RAISE(ABORT,'estimator evidence append is not authorized'); END;
CREATE TRIGGER estimator_evidence_candidate_projections_final_sealed BEFORE INSERT ON estimator_evidence_candidate_projections WHEN EXISTS (SELECT 1 FROM estimator_evidence_submissions WHERE submission_id=NEW.submission_id) BEGIN SELECT RAISE(ABORT,'estimator evidence submission is sealed'); END;
CREATE TRIGGER estimator_evidence_baseline_projections_authorized BEFORE INSERT ON estimator_evidence_baseline_projections WHEN NOT EXISTS (SELECT 1 FROM estimator_evidence_append_authorizations AS auth WHERE auth.submission_id=NEW.submission_id AND auth.campaign_id=NEW.campaign_id AND auth.authorization_tag=estimator_evidence_authorization_tag(auth.authorization_id,auth.submission_id,auth.campaign_id)) BEGIN SELECT RAISE(ABORT,'estimator evidence append is not authorized'); END;
CREATE TRIGGER estimator_evidence_baseline_projections_final_sealed BEFORE INSERT ON estimator_evidence_baseline_projections WHEN EXISTS (SELECT 1 FROM estimator_evidence_submissions WHERE submission_id=NEW.submission_id) BEGIN SELECT RAISE(ABORT,'estimator evidence submission is sealed'); END;
CREATE TRIGGER estimator_evidence_objective_projections_authorized BEFORE INSERT ON estimator_evidence_objective_projections WHEN NOT EXISTS (SELECT 1 FROM estimator_evidence_append_authorizations AS auth WHERE auth.submission_id=NEW.submission_id AND auth.campaign_id=NEW.campaign_id AND auth.authorization_tag=estimator_evidence_authorization_tag(auth.authorization_id,auth.submission_id,auth.campaign_id)) BEGIN SELECT RAISE(ABORT,'estimator evidence append is not authorized'); END;
CREATE TRIGGER estimator_evidence_objective_projections_final_sealed BEFORE INSERT ON estimator_evidence_objective_projections WHEN EXISTS (SELECT 1 FROM estimator_evidence_submissions WHERE submission_id=NEW.submission_id) BEGIN SELECT RAISE(ABORT,'estimator evidence submission is sealed'); END;
CREATE TRIGGER estimator_evidence_blind_judgments_authorized BEFORE INSERT ON estimator_evidence_blind_judgments WHEN NOT EXISTS (SELECT 1 FROM estimator_evidence_append_authorizations AS auth WHERE auth.submission_id=NEW.submission_id AND auth.campaign_id=NEW.campaign_id AND auth.authorization_tag=estimator_evidence_authorization_tag(auth.authorization_id,auth.submission_id,auth.campaign_id)) BEGIN SELECT RAISE(ABORT,'estimator evidence append is not authorized'); END;
CREATE TRIGGER estimator_evidence_blind_judgments_final_sealed BEFORE INSERT ON estimator_evidence_blind_judgments WHEN EXISTS (SELECT 1 FROM estimator_evidence_submissions WHERE submission_id=NEW.submission_id) BEGIN SELECT RAISE(ABORT,'estimator evidence submission is sealed'); END;
CREATE TRIGGER estimator_evidence_adjudication_judgments_authorized BEFORE INSERT ON estimator_evidence_adjudication_judgments WHEN NOT EXISTS (SELECT 1 FROM estimator_evidence_append_authorizations AS auth WHERE auth.submission_id=NEW.submission_id AND auth.campaign_id=NEW.campaign_id AND auth.authorization_tag=estimator_evidence_authorization_tag(auth.authorization_id,auth.submission_id,auth.campaign_id)) BEGIN SELECT RAISE(ABORT,'estimator evidence append is not authorized'); END;
CREATE TRIGGER estimator_evidence_adjudication_judgments_final_sealed BEFORE INSERT ON estimator_evidence_adjudication_judgments WHEN EXISTS (SELECT 1 FROM estimator_evidence_submissions WHERE submission_id=NEW.submission_id) BEGIN SELECT RAISE(ABORT,'estimator evidence submission is sealed'); END;
CREATE TRIGGER estimator_evidence_blind_adjudications_authorized BEFORE INSERT ON estimator_evidence_blind_adjudications WHEN NOT EXISTS (SELECT 1 FROM estimator_evidence_append_authorizations AS auth WHERE auth.submission_id=NEW.submission_id AND auth.campaign_id=NEW.campaign_id AND auth.authorization_tag=estimator_evidence_authorization_tag(auth.authorization_id,auth.submission_id,auth.campaign_id)) BEGIN SELECT RAISE(ABORT,'estimator evidence append is not authorized'); END;
CREATE TRIGGER estimator_evidence_blind_adjudications_final_sealed BEFORE INSERT ON estimator_evidence_blind_adjudications WHEN EXISTS (SELECT 1 FROM estimator_evidence_submissions WHERE submission_id=NEW.submission_id) BEGIN SELECT RAISE(ABORT,'estimator evidence submission is sealed'); END;
CREATE TRIGGER estimator_evidence_stability_trials_authorized BEFORE INSERT ON estimator_evidence_stability_trials WHEN NOT EXISTS (SELECT 1 FROM estimator_evidence_append_authorizations AS auth WHERE auth.submission_id=NEW.submission_id AND auth.campaign_id=NEW.campaign_id AND auth.authorization_tag=estimator_evidence_authorization_tag(auth.authorization_id,auth.submission_id,auth.campaign_id)) BEGIN SELECT RAISE(ABORT,'estimator evidence append is not authorized'); END;
CREATE TRIGGER estimator_evidence_stability_trials_final_sealed BEFORE INSERT ON estimator_evidence_stability_trials WHEN EXISTS (SELECT 1 FROM estimator_evidence_submissions WHERE submission_id=NEW.submission_id) BEGIN SELECT RAISE(ABORT,'estimator evidence submission is sealed'); END;
CREATE TRIGGER estimator_evidence_stability_series_authorized BEFORE INSERT ON estimator_evidence_stability_series WHEN NOT EXISTS (SELECT 1 FROM estimator_evidence_append_authorizations AS auth WHERE auth.submission_id=NEW.submission_id AND auth.campaign_id=NEW.campaign_id AND auth.authorization_tag=estimator_evidence_authorization_tag(auth.authorization_id,auth.submission_id,auth.campaign_id)) BEGIN SELECT RAISE(ABORT,'estimator evidence append is not authorized'); END;
CREATE TRIGGER estimator_evidence_stability_series_final_sealed BEFORE INSERT ON estimator_evidence_stability_series WHEN EXISTS (SELECT 1 FROM estimator_evidence_submissions WHERE submission_id=NEW.submission_id) BEGIN SELECT RAISE(ABORT,'estimator evidence submission is sealed'); END;
CREATE TRIGGER estimator_evidence_submission_holdout_cases_authorized BEFORE INSERT ON estimator_evidence_submission_holdout_cases WHEN NOT EXISTS (SELECT 1 FROM estimator_evidence_append_authorizations AS auth WHERE auth.submission_id=NEW.submission_id AND auth.campaign_id=NEW.campaign_id AND auth.authorization_tag=estimator_evidence_authorization_tag(auth.authorization_id,auth.submission_id,auth.campaign_id)) BEGIN SELECT RAISE(ABORT,'estimator evidence append is not authorized'); END;
CREATE TRIGGER estimator_evidence_submission_holdout_cases_final_sealed BEFORE INSERT ON estimator_evidence_submission_holdout_cases WHEN EXISTS (SELECT 1 FROM estimator_evidence_submissions WHERE submission_id=NEW.submission_id) BEGIN SELECT RAISE(ABORT,'estimator evidence submission is sealed'); END;
CREATE TRIGGER estimator_evidence_submissions_authorized BEFORE INSERT ON estimator_evidence_submissions WHEN NOT EXISTS (SELECT 1 FROM estimator_evidence_append_authorizations AS auth WHERE auth.submission_id=NEW.submission_id AND auth.campaign_id=NEW.campaign_id AND auth.authorization_tag=estimator_evidence_authorization_tag(auth.authorization_id,auth.submission_id,auth.campaign_id)) BEGIN SELECT RAISE(ABORT,'estimator evidence append is not authorized'); END;

CREATE TRIGGER estimator_evidence_expected_attempt_sealed BEFORE INSERT ON estimator_evidence_expected_attempts WHEN EXISTS (SELECT 1 FROM estimator_evidence_expected_manifests WHERE submission_id=NEW.submission_id) BEGIN SELECT RAISE(ABORT,'expected attempt manifest is sealed'); END;
CREATE TRIGGER estimator_evidence_access_event_sealed BEFORE INSERT ON estimator_evidence_access_events WHEN EXISTS (SELECT 1 FROM estimator_evidence_access_manifests WHERE submission_id=NEW.submission_id) BEGIN SELECT RAISE(ABORT,'access manifest is sealed'); END;
CREATE TRIGGER estimator_evidence_access_gap_sealed BEFORE INSERT ON estimator_evidence_access_gaps WHEN EXISTS (SELECT 1 FROM estimator_evidence_access_manifests WHERE submission_id=NEW.submission_id) BEGIN SELECT RAISE(ABORT,'access manifest is sealed'); END;
CREATE TRIGGER estimator_evidence_privacy_artifact_sealed BEFORE INSERT ON estimator_evidence_privacy_artifacts WHEN EXISTS (SELECT 1 FROM estimator_evidence_privacy_manifests WHERE submission_id=NEW.submission_id) BEGIN SELECT RAISE(ABORT,'privacy manifest is sealed'); END;
CREATE TRIGGER estimator_evidence_privacy_finding_sealed BEFORE INSERT ON estimator_evidence_privacy_findings WHEN EXISTS (SELECT 1 FROM estimator_evidence_privacy_manifests WHERE submission_id=NEW.submission_id) BEGIN SELECT RAISE(ABORT,'privacy manifest is sealed'); END;
CREATE TRIGGER estimator_evidence_adjudication_link_sealed BEFORE INSERT ON estimator_evidence_adjudication_judgments WHEN EXISTS (SELECT 1 FROM estimator_evidence_blind_adjudications WHERE submission_id=NEW.submission_id AND adjudication_id=NEW.adjudication_id) BEGIN SELECT RAISE(ABORT,'adjudication is sealed'); END;
CREATE TRIGGER estimator_evidence_trial_sealed BEFORE INSERT ON estimator_evidence_stability_trials WHEN EXISTS (SELECT 1 FROM estimator_evidence_stability_series WHERE submission_id=NEW.submission_id AND series_id=NEW.series_id) BEGIN SELECT RAISE(ABORT,'stability series is sealed'); END;

-- SQLite string length/pattern functions stop at embedded NUL. A printable
-- ASCII projection plus an explicit NUL test closes that bypass for every V17
-- TEXT surface, including nullable provenance fields.
CREATE TRIGGER estimator_evidence_launch_no_controls BEFORE INSERT ON estimator_evidence_attempt_launches WHEN instr(NEW.submission_id||NEW.launch_id||NEW.campaign_id||NEW.attempt_id||NEW.execution_id||NEW.case_id||NEW.plan_fingerprint||NEW.metric_question_fingerprint||NEW.evidence_packet_fingerprint||NEW.constellation_stage_fingerprint||NEW.stage_kind||NEW.stage_configuration_sha256||NEW.model_artifact_fingerprint||NEW.requested_source||NEW.requested_model_id||NEW.requested_revision||NEW.requested_execution_mode||NEW.runner_adapter_key||NEW.runner_adapter_version||NEW.runner_configuration_sha256||NEW.response_schema_version||NEW.destination||NEW.retention_class||NEW.approval_kind||coalesce(NEW.approval_id,'')||coalesce(NEW.redaction_preview_fingerprint,'')||NEW.launch_fingerprint,char(0))>0 OR (NEW.submission_id||NEW.launch_id||NEW.campaign_id||NEW.attempt_id||NEW.execution_id||NEW.case_id||NEW.plan_fingerprint||NEW.metric_question_fingerprint||NEW.evidence_packet_fingerprint||NEW.constellation_stage_fingerprint||NEW.stage_kind||NEW.stage_configuration_sha256||NEW.model_artifact_fingerprint||NEW.requested_source||NEW.requested_model_id||NEW.requested_revision||NEW.requested_execution_mode||NEW.runner_adapter_key||NEW.runner_adapter_version||NEW.runner_configuration_sha256||NEW.response_schema_version||NEW.destination||NEW.retention_class||NEW.approval_kind||coalesce(NEW.approval_id,'')||coalesce(NEW.redaction_preview_fingerprint,'')||NEW.launch_fingerprint) GLOB '*[^ -~]*' BEGIN SELECT RAISE(ABORT,'estimator evidence text contains a control'); END;
CREATE TRIGGER estimator_evidence_outcome_no_controls BEFORE INSERT ON estimator_evidence_attempt_outcomes WHEN instr(NEW.submission_id||NEW.outcome_id||NEW.outcome_fingerprint||NEW.campaign_id||NEW.attempt_id||NEW.execution_id||NEW.case_id||NEW.plan_fingerprint||NEW.metric_question_fingerprint||NEW.evidence_packet_fingerprint||NEW.terminal_state||coalesce(NEW.structured_output_fingerprint,'')||coalesce(NEW.terminal_reason_code,'')||NEW.served_state||coalesce(NEW.served_source,'')||coalesce(NEW.served_model_id,'')||coalesce(NEW.served_revision,'')||coalesce(NEW.served_execution_mode,'')||coalesce(NEW.fallback_reason_code,'')||coalesce(NEW.served_unavailable_reason_code,'')||NEW.token_state||NEW.token_collector_version||coalesce(NEW.token_reason_code,'')||NEW.resource_state||NEW.resource_collector_version||coalesce(NEW.resource_reason_code,'')||NEW.cost_state||NEW.cost_collector_version||coalesce(NEW.cost_reason_code,'')||NEW.queue_key||NEW.queue_version||NEW.worker_id,char(0))>0 OR (NEW.submission_id||NEW.outcome_id||NEW.outcome_fingerprint||NEW.campaign_id||NEW.attempt_id||NEW.execution_id||NEW.case_id||NEW.plan_fingerprint||NEW.metric_question_fingerprint||NEW.evidence_packet_fingerprint||NEW.terminal_state||coalesce(NEW.structured_output_fingerprint,'')||coalesce(NEW.terminal_reason_code,'')||NEW.served_state||coalesce(NEW.served_source,'')||coalesce(NEW.served_model_id,'')||coalesce(NEW.served_revision,'')||coalesce(NEW.served_execution_mode,'')||coalesce(NEW.fallback_reason_code,'')||coalesce(NEW.served_unavailable_reason_code,'')||NEW.token_state||NEW.token_collector_version||coalesce(NEW.token_reason_code,'')||NEW.resource_state||NEW.resource_collector_version||coalesce(NEW.resource_reason_code,'')||NEW.cost_state||NEW.cost_collector_version||coalesce(NEW.cost_reason_code,'')||NEW.queue_key||NEW.queue_version||NEW.worker_id) GLOB '*[^ -~]*' BEGIN SELECT RAISE(ABORT,'estimator evidence text contains a control'); END;
CREATE TRIGGER estimator_evidence_expected_attempt_no_controls BEFORE INSERT ON estimator_evidence_expected_attempts WHEN instr(NEW.submission_id||NEW.manifest_id||NEW.attempt_id||NEW.execution_id||NEW.case_id||NEW.plan_fingerprint||NEW.metric_question_fingerprint||NEW.evidence_packet_fingerprint||NEW.constellation_stage_fingerprint||NEW.stage_configuration_sha256||NEW.stage_kind||NEW.attempt_fingerprint||NEW.campaign_id,char(0))>0 OR (NEW.submission_id||NEW.manifest_id||NEW.attempt_id||NEW.execution_id||NEW.case_id||NEW.plan_fingerprint||NEW.metric_question_fingerprint||NEW.evidence_packet_fingerprint||NEW.constellation_stage_fingerprint||NEW.stage_configuration_sha256||NEW.stage_kind||NEW.attempt_fingerprint||NEW.campaign_id) GLOB '*[^ -~]*' BEGIN SELECT RAISE(ABORT,'estimator evidence text contains a control'); END;
CREATE TRIGGER estimator_evidence_expected_manifest_no_controls BEFORE INSERT ON estimator_evidence_expected_manifests WHEN instr(NEW.submission_id||NEW.manifest_id||NEW.manifest_fingerprint||NEW.execution_set_fingerprint||NEW.campaign_id||NEW.plan_fingerprint,char(0))>0 OR (NEW.submission_id||NEW.manifest_id||NEW.manifest_fingerprint||NEW.execution_set_fingerprint||NEW.campaign_id||NEW.plan_fingerprint) GLOB '*[^ -~]*' BEGIN SELECT RAISE(ABORT,'estimator evidence text contains a control'); END;
CREATE TRIGGER estimator_evidence_access_event_no_controls BEFORE INSERT ON estimator_evidence_access_events WHEN instr(NEW.submission_id||NEW.manifest_id||NEW.event_id||NEW.event_fingerprint||NEW.campaign_id||NEW.case_id||NEW.actor_id||NEW.actor_kind||NEW.access_kind,char(0))>0 OR (NEW.submission_id||NEW.manifest_id||NEW.event_id||NEW.event_fingerprint||NEW.campaign_id||NEW.case_id||NEW.actor_id||NEW.actor_kind||NEW.access_kind) GLOB '*[^ -~]*' BEGIN SELECT RAISE(ABORT,'estimator evidence text contains a control'); END;
CREATE TRIGGER estimator_evidence_access_gap_no_controls BEFORE INSERT ON estimator_evidence_access_gaps WHEN instr(NEW.submission_id||NEW.manifest_id||NEW.gap_id||NEW.campaign_id||NEW.reason_code,char(0))>0 OR (NEW.submission_id||NEW.manifest_id||NEW.gap_id||NEW.campaign_id||NEW.reason_code) GLOB '*[^ -~]*' BEGIN SELECT RAISE(ABORT,'estimator evidence text contains a control'); END;
CREATE TRIGGER estimator_evidence_access_manifest_no_controls BEFORE INSERT ON estimator_evidence_access_manifests WHEN instr(NEW.submission_id||NEW.manifest_id||NEW.manifest_fingerprint||NEW.event_set_fingerprint||NEW.gap_set_fingerprint||NEW.campaign_id||NEW.auditor_version,char(0))>0 OR (NEW.submission_id||NEW.manifest_id||NEW.manifest_fingerprint||NEW.event_set_fingerprint||NEW.gap_set_fingerprint||NEW.campaign_id||NEW.auditor_version) GLOB '*[^ -~]*' BEGIN SELECT RAISE(ABORT,'estimator evidence text contains a control'); END;
CREATE TRIGGER estimator_evidence_access_audit_case_no_controls BEFORE INSERT ON estimator_evidence_access_audit_cases WHEN instr(NEW.submission_id||NEW.audit_id||NEW.case_id||NEW.campaign_id,char(0))>0 OR (NEW.submission_id||NEW.audit_id||NEW.case_id||NEW.campaign_id) GLOB '*[^ -~]*' BEGIN SELECT RAISE(ABORT,'estimator evidence text contains a control'); END;
CREATE TRIGGER estimator_evidence_access_audit_no_controls BEFORE INSERT ON estimator_evidence_access_audits WHEN instr(NEW.submission_id||NEW.audit_id||NEW.audit_fingerprint||NEW.campaign_id||NEW.manifest_id,char(0))>0 OR (NEW.submission_id||NEW.audit_id||NEW.audit_fingerprint||NEW.campaign_id||NEW.manifest_id) GLOB '*[^ -~]*' BEGIN SELECT RAISE(ABORT,'estimator evidence text contains a control'); END;
CREATE TRIGGER estimator_evidence_privacy_artifact_no_controls BEFORE INSERT ON estimator_evidence_privacy_artifacts WHEN instr(NEW.submission_id||NEW.manifest_id||NEW.set_kind||NEW.artifact_fingerprint||NEW.campaign_id,char(0))>0 OR (NEW.submission_id||NEW.manifest_id||NEW.set_kind||NEW.artifact_fingerprint||NEW.campaign_id) GLOB '*[^ -~]*' BEGIN SELECT RAISE(ABORT,'estimator evidence text contains a control'); END;
CREATE TRIGGER estimator_evidence_privacy_finding_no_controls BEFORE INSERT ON estimator_evidence_privacy_findings WHEN instr(NEW.submission_id||NEW.manifest_id||NEW.finding_id||NEW.finding_fingerprint||NEW.campaign_id||NEW.artifact_fingerprint||NEW.detector_key||NEW.detector_version||NEW.category,char(0))>0 OR (NEW.submission_id||NEW.manifest_id||NEW.finding_id||NEW.finding_fingerprint||NEW.campaign_id||NEW.artifact_fingerprint||NEW.detector_key||NEW.detector_version||NEW.category) GLOB '*[^ -~]*' BEGIN SELECT RAISE(ABORT,'estimator evidence text contains a control'); END;
CREATE TRIGGER estimator_evidence_privacy_manifest_no_controls BEFORE INSERT ON estimator_evidence_privacy_manifests WHEN instr(NEW.submission_id||NEW.manifest_id||NEW.manifest_fingerprint||NEW.finding_set_fingerprint||NEW.campaign_id,char(0))>0 OR (NEW.submission_id||NEW.manifest_id||NEW.manifest_fingerprint||NEW.finding_set_fingerprint||NEW.campaign_id) GLOB '*[^ -~]*' BEGIN SELECT RAISE(ABORT,'estimator evidence text contains a control'); END;
CREATE TRIGGER estimator_evidence_privacy_scan_no_controls BEFORE INSERT ON estimator_evidence_privacy_scans WHEN instr(NEW.submission_id||NEW.scan_id||NEW.scan_fingerprint||NEW.campaign_id||NEW.manifest_id||NEW.scanner_version,char(0))>0 OR (NEW.submission_id||NEW.scan_id||NEW.scan_fingerprint||NEW.campaign_id||NEW.manifest_id||NEW.scanner_version) GLOB '*[^ -~]*' BEGIN SELECT RAISE(ABORT,'estimator evidence text contains a control'); END;
CREATE TRIGGER estimator_evidence_estimate_no_controls BEFORE INSERT ON estimator_evidence_structured_estimates WHEN instr(NEW.submission_id||NEW.receipt_id||NEW.receipt_fingerprint||NEW.campaign_id||NEW.case_id||NEW.plan_fingerprint||NEW.metric_question_fingerprint||NEW.evidence_packet_fingerprint||NEW.attempt_id||NEW.outcome_id||NEW.outcome_fingerprint||NEW.structured_output_fingerprint||NEW.value_kind||NEW.value_state||coalesce(NEW.label_code,'')||coalesce(NEW.reason_code,''),char(0))>0 OR (NEW.submission_id||NEW.receipt_id||NEW.receipt_fingerprint||NEW.campaign_id||NEW.case_id||NEW.plan_fingerprint||NEW.metric_question_fingerprint||NEW.evidence_packet_fingerprint||NEW.attempt_id||NEW.outcome_id||NEW.outcome_fingerprint||NEW.structured_output_fingerprint||NEW.value_kind||NEW.value_state||coalesce(NEW.label_code,'')||coalesce(NEW.reason_code,'')) GLOB '*[^ -~]*' BEGIN SELECT RAISE(ABORT,'estimator evidence text contains a control'); END;
CREATE TRIGGER estimator_evidence_candidate_no_controls BEFORE INSERT ON estimator_evidence_candidate_projections WHEN instr(NEW.submission_id||NEW.projection_id||NEW.projection_fingerprint||NEW.campaign_id||NEW.case_id||NEW.plan_fingerprint||NEW.metric_question_fingerprint||NEW.evidence_packet_fingerprint||NEW.attempt_id||NEW.outcome_id||NEW.outcome_fingerprint||NEW.estimate_receipt_id||NEW.estimate_receipt_fingerprint||NEW.stage_kind,char(0))>0 OR (NEW.submission_id||NEW.projection_id||NEW.projection_fingerprint||NEW.campaign_id||NEW.case_id||NEW.plan_fingerprint||NEW.metric_question_fingerprint||NEW.evidence_packet_fingerprint||NEW.attempt_id||NEW.outcome_id||NEW.outcome_fingerprint||NEW.estimate_receipt_id||NEW.estimate_receipt_fingerprint||NEW.stage_kind) GLOB '*[^ -~]*' BEGIN SELECT RAISE(ABORT,'estimator evidence text contains a control'); END;
CREATE TRIGGER estimator_evidence_baseline_no_controls BEFORE INSERT ON estimator_evidence_baseline_projections WHEN instr(NEW.submission_id||NEW.projection_id||NEW.projection_fingerprint||NEW.campaign_id||NEW.case_id||NEW.plan_fingerprint||NEW.metric_question_fingerprint||NEW.evidence_packet_fingerprint||NEW.baseline_id||NEW.baseline_version||NEW.baseline_configuration_sha256||NEW.final_estimate_fingerprint||NEW.value_kind||NEW.value_state||coalesce(NEW.label_code,'')||coalesce(NEW.reason_code,''),char(0))>0 OR (NEW.submission_id||NEW.projection_id||NEW.projection_fingerprint||NEW.campaign_id||NEW.case_id||NEW.plan_fingerprint||NEW.metric_question_fingerprint||NEW.evidence_packet_fingerprint||NEW.baseline_id||NEW.baseline_version||NEW.baseline_configuration_sha256||NEW.final_estimate_fingerprint||NEW.value_kind||NEW.value_state||coalesce(NEW.label_code,'')||coalesce(NEW.reason_code,'')) GLOB '*[^ -~]*' BEGIN SELECT RAISE(ABORT,'estimator evidence text contains a control'); END;
CREATE TRIGGER estimator_evidence_objective_no_controls BEFORE INSERT ON estimator_evidence_objective_projections WHEN instr(NEW.submission_id||NEW.projection_id||NEW.projection_fingerprint||NEW.campaign_id||NEW.case_id||NEW.plan_fingerprint||NEW.metric_question_fingerprint||NEW.evidence_packet_fingerprint||NEW.truth_kind||NEW.objective_evidence_fingerprint||NEW.verification_adapter_version||NEW.value_kind||NEW.value_state||coalesce(NEW.label_code,'')||coalesce(NEW.reason_code,''),char(0))>0 OR (NEW.submission_id||NEW.projection_id||NEW.projection_fingerprint||NEW.campaign_id||NEW.case_id||NEW.plan_fingerprint||NEW.metric_question_fingerprint||NEW.evidence_packet_fingerprint||NEW.truth_kind||NEW.objective_evidence_fingerprint||NEW.verification_adapter_version||NEW.value_kind||NEW.value_state||coalesce(NEW.label_code,'')||coalesce(NEW.reason_code,'')) GLOB '*[^ -~]*' BEGIN SELECT RAISE(ABORT,'estimator evidence text contains a control'); END;
CREATE TRIGGER estimator_evidence_judgment_no_controls BEFORE INSERT ON estimator_evidence_blind_judgments WHEN instr(NEW.submission_id||NEW.judgment_id||NEW.judgment_fingerprint||NEW.campaign_id||NEW.case_id||NEW.plan_fingerprint||NEW.metric_question_fingerprint||NEW.evidence_packet_fingerprint||NEW.participant_id||NEW.participant_kind||NEW.annotation_protocol_version||NEW.value_kind||NEW.value_state||coalesce(NEW.label_code,'')||coalesce(NEW.reason_code,''),char(0))>0 OR (NEW.submission_id||NEW.judgment_id||NEW.judgment_fingerprint||NEW.campaign_id||NEW.case_id||NEW.plan_fingerprint||NEW.metric_question_fingerprint||NEW.evidence_packet_fingerprint||NEW.participant_id||NEW.participant_kind||NEW.annotation_protocol_version||NEW.value_kind||NEW.value_state||coalesce(NEW.label_code,'')||coalesce(NEW.reason_code,'')) GLOB '*[^ -~]*' BEGIN SELECT RAISE(ABORT,'estimator evidence text contains a control'); END;
CREATE TRIGGER estimator_evidence_adjudication_link_no_controls BEFORE INSERT ON estimator_evidence_adjudication_judgments WHEN instr(NEW.submission_id||NEW.adjudication_id||NEW.judgment_id||NEW.campaign_id,char(0))>0 OR (NEW.submission_id||NEW.adjudication_id||NEW.judgment_id||NEW.campaign_id) GLOB '*[^ -~]*' BEGIN SELECT RAISE(ABORT,'estimator evidence text contains a control'); END;
CREATE TRIGGER estimator_evidence_adjudication_no_controls BEFORE INSERT ON estimator_evidence_blind_adjudications WHEN instr(NEW.submission_id||NEW.adjudication_id||NEW.adjudication_fingerprint||NEW.campaign_id||NEW.case_id||NEW.plan_fingerprint||NEW.metric_question_fingerprint||NEW.evidence_packet_fingerprint||NEW.resolver_id||NEW.resolution||NEW.annotation_protocol_version||NEW.value_kind||NEW.value_state||coalesce(NEW.label_code,'')||coalesce(NEW.reason_code,''),char(0))>0 OR (NEW.submission_id||NEW.adjudication_id||NEW.adjudication_fingerprint||NEW.campaign_id||NEW.case_id||NEW.plan_fingerprint||NEW.metric_question_fingerprint||NEW.evidence_packet_fingerprint||NEW.resolver_id||NEW.resolution||NEW.annotation_protocol_version||NEW.value_kind||NEW.value_state||coalesce(NEW.label_code,'')||coalesce(NEW.reason_code,'')) GLOB '*[^ -~]*' BEGIN SELECT RAISE(ABORT,'estimator evidence text contains a control'); END;
CREATE TRIGGER estimator_evidence_trial_no_controls BEFORE INSERT ON estimator_evidence_stability_trials WHEN instr(NEW.submission_id||NEW.series_id||NEW.receipt_id||NEW.receipt_fingerprint||NEW.campaign_id||NEW.case_id||NEW.plan_fingerprint||NEW.metric_question_fingerprint||NEW.evidence_packet_fingerprint||NEW.condition_code||NEW.attempt_id||NEW.outcome_id||NEW.outcome_fingerprint||NEW.estimate_receipt_id||NEW.estimate_receipt_fingerprint,char(0))>0 OR (NEW.submission_id||NEW.series_id||NEW.receipt_id||NEW.receipt_fingerprint||NEW.campaign_id||NEW.case_id||NEW.plan_fingerprint||NEW.metric_question_fingerprint||NEW.evidence_packet_fingerprint||NEW.condition_code||NEW.attempt_id||NEW.outcome_id||NEW.outcome_fingerprint||NEW.estimate_receipt_id||NEW.estimate_receipt_fingerprint) GLOB '*[^ -~]*' BEGIN SELECT RAISE(ABORT,'estimator evidence text contains a control'); END;
CREATE TRIGGER estimator_evidence_series_no_controls BEFORE INSERT ON estimator_evidence_stability_series WHEN instr(NEW.submission_id||NEW.series_id||NEW.series_fingerprint||NEW.trial_set_fingerprint||NEW.campaign_id||NEW.case_id||NEW.plan_fingerprint||NEW.metric_question_fingerprint||NEW.evidence_packet_fingerprint||NEW.condition_code,char(0))>0 OR (NEW.submission_id||NEW.series_id||NEW.series_fingerprint||NEW.trial_set_fingerprint||NEW.campaign_id||NEW.case_id||NEW.plan_fingerprint||NEW.metric_question_fingerprint||NEW.evidence_packet_fingerprint||NEW.condition_code) GLOB '*[^ -~]*' BEGIN SELECT RAISE(ABORT,'estimator evidence text contains a control'); END;
CREATE TRIGGER estimator_evidence_holdout_no_controls BEFORE INSERT ON estimator_evidence_submission_holdout_cases WHEN instr(NEW.submission_id||NEW.case_id||NEW.campaign_id,char(0))>0 OR (NEW.submission_id||NEW.case_id||NEW.campaign_id) GLOB '*[^ -~]*' BEGIN SELECT RAISE(ABORT,'estimator evidence text contains a control'); END;
CREATE TRIGGER estimator_evidence_submission_no_controls BEFORE INSERT ON estimator_evidence_submissions WHEN instr(NEW.submission_id||NEW.submission_fingerprint||NEW.campaign_id||NEW.expected_manifest_id||NEW.access_audit_id||NEW.privacy_scan_id,char(0))>0 OR (NEW.submission_id||NEW.submission_fingerprint||NEW.campaign_id||NEW.expected_manifest_id||NEW.access_audit_id||NEW.privacy_scan_id) GLOB '*[^ -~]*' BEGIN SELECT RAISE(ABORT,'estimator evidence text contains a control'); END;

CREATE TRIGGER estimator_evidence_access_event_safe_ids BEFORE INSERT ON estimator_evidence_access_events WHEN length(NEW.submission_id)<>64 OR NEW.submission_id GLOB '*[^0-9a-f]*' OR length(NEW.manifest_id)<>64 OR NEW.manifest_id GLOB '*[^0-9a-f]*' OR length(NEW.campaign_id)<>64 OR NEW.campaign_id GLOB '*[^0-9a-f]*' BEGIN SELECT RAISE(ABORT,'estimator evidence identifier is invalid'); END;
CREATE TRIGGER estimator_evidence_access_gap_safe_ids BEFORE INSERT ON estimator_evidence_access_gaps WHEN length(NEW.submission_id)<>64 OR NEW.submission_id GLOB '*[^0-9a-f]*' OR length(NEW.manifest_id)<>64 OR NEW.manifest_id GLOB '*[^0-9a-f]*' OR length(NEW.campaign_id)<>64 OR NEW.campaign_id GLOB '*[^0-9a-f]*' BEGIN SELECT RAISE(ABORT,'estimator evidence identifier is invalid'); END;
CREATE TRIGGER estimator_evidence_access_manifest_safe_ids BEFORE INSERT ON estimator_evidence_access_manifests WHEN length(NEW.submission_id)<>64 OR NEW.submission_id GLOB '*[^0-9a-f]*' OR length(NEW.campaign_id)<>64 OR NEW.campaign_id GLOB '*[^0-9a-f]*' BEGIN SELECT RAISE(ABORT,'estimator evidence identifier is invalid'); END;
CREATE TRIGGER estimator_evidence_access_audit_case_safe_ids BEFORE INSERT ON estimator_evidence_access_audit_cases WHEN length(NEW.submission_id)<>64 OR NEW.submission_id GLOB '*[^0-9a-f]*' OR length(NEW.campaign_id)<>64 OR NEW.campaign_id GLOB '*[^0-9a-f]*' BEGIN SELECT RAISE(ABORT,'estimator evidence identifier is invalid'); END;
CREATE TRIGGER estimator_evidence_access_audit_safe_ids BEFORE INSERT ON estimator_evidence_access_audits WHEN length(NEW.submission_id)<>64 OR NEW.submission_id GLOB '*[^0-9a-f]*' OR length(NEW.campaign_id)<>64 OR NEW.campaign_id GLOB '*[^0-9a-f]*' OR length(NEW.manifest_id)<>64 OR NEW.manifest_id GLOB '*[^0-9a-f]*' BEGIN SELECT RAISE(ABORT,'estimator evidence identifier is invalid'); END;
CREATE TRIGGER estimator_evidence_privacy_artifact_safe_ids BEFORE INSERT ON estimator_evidence_privacy_artifacts WHEN length(NEW.submission_id)<>64 OR NEW.submission_id GLOB '*[^0-9a-f]*' OR length(NEW.manifest_id)<>64 OR NEW.manifest_id GLOB '*[^0-9a-f]*' OR length(NEW.campaign_id)<>64 OR NEW.campaign_id GLOB '*[^0-9a-f]*' BEGIN SELECT RAISE(ABORT,'estimator evidence identifier is invalid'); END;
CREATE TRIGGER estimator_evidence_privacy_finding_safe_ids BEFORE INSERT ON estimator_evidence_privacy_findings WHEN length(NEW.submission_id)<>64 OR NEW.submission_id GLOB '*[^0-9a-f]*' OR length(NEW.manifest_id)<>64 OR NEW.manifest_id GLOB '*[^0-9a-f]*' OR length(NEW.campaign_id)<>64 OR NEW.campaign_id GLOB '*[^0-9a-f]*' BEGIN SELECT RAISE(ABORT,'estimator evidence identifier is invalid'); END;
CREATE TRIGGER estimator_evidence_privacy_manifest_safe_ids BEFORE INSERT ON estimator_evidence_privacy_manifests WHEN length(NEW.submission_id)<>64 OR NEW.submission_id GLOB '*[^0-9a-f]*' OR length(NEW.campaign_id)<>64 OR NEW.campaign_id GLOB '*[^0-9a-f]*' BEGIN SELECT RAISE(ABORT,'estimator evidence identifier is invalid'); END;
CREATE TRIGGER estimator_evidence_privacy_scan_safe_ids BEFORE INSERT ON estimator_evidence_privacy_scans WHEN length(NEW.submission_id)<>64 OR NEW.submission_id GLOB '*[^0-9a-f]*' OR length(NEW.campaign_id)<>64 OR NEW.campaign_id GLOB '*[^0-9a-f]*' OR length(NEW.manifest_id)<>64 OR NEW.manifest_id GLOB '*[^0-9a-f]*' BEGIN SELECT RAISE(ABORT,'estimator evidence identifier is invalid'); END;
CREATE TRIGGER estimator_evidence_estimate_safe_ids BEFORE INSERT ON estimator_evidence_structured_estimates WHEN length(NEW.submission_id)<>64 OR NEW.submission_id GLOB '*[^0-9a-f]*' OR length(NEW.campaign_id)<>64 OR NEW.campaign_id GLOB '*[^0-9a-f]*' OR length(NEW.case_id)<>64 OR NEW.case_id GLOB '*[^0-9a-f]*' OR length(NEW.plan_fingerprint)<>64 OR NEW.plan_fingerprint GLOB '*[^0-9a-f]*' OR length(NEW.metric_question_fingerprint)<>64 OR NEW.metric_question_fingerprint GLOB '*[^0-9a-f]*' OR length(NEW.evidence_packet_fingerprint)<>64 OR NEW.evidence_packet_fingerprint GLOB '*[^0-9a-f]*' OR length(NEW.attempt_id)<>64 OR NEW.attempt_id GLOB '*[^0-9a-f]*' OR length(NEW.outcome_id)<>64 OR NEW.outcome_id GLOB '*[^0-9a-f]*' OR length(NEW.outcome_fingerprint)<>64 OR NEW.outcome_fingerprint GLOB '*[^0-9a-f]*' OR length(NEW.structured_output_fingerprint)<>64 OR NEW.structured_output_fingerprint GLOB '*[^0-9a-f]*' BEGIN SELECT RAISE(ABORT,'estimator evidence identifier is invalid'); END;
CREATE TRIGGER estimator_evidence_candidate_safe_ids BEFORE INSERT ON estimator_evidence_candidate_projections WHEN length(NEW.submission_id)<>64 OR NEW.submission_id GLOB '*[^0-9a-f]*' OR length(NEW.campaign_id)<>64 OR NEW.campaign_id GLOB '*[^0-9a-f]*' OR length(NEW.case_id)<>64 OR NEW.case_id GLOB '*[^0-9a-f]*' OR length(NEW.plan_fingerprint)<>64 OR NEW.plan_fingerprint GLOB '*[^0-9a-f]*' OR length(NEW.metric_question_fingerprint)<>64 OR NEW.metric_question_fingerprint GLOB '*[^0-9a-f]*' OR length(NEW.evidence_packet_fingerprint)<>64 OR NEW.evidence_packet_fingerprint GLOB '*[^0-9a-f]*' OR length(NEW.attempt_id)<>64 OR NEW.attempt_id GLOB '*[^0-9a-f]*' OR length(NEW.outcome_id)<>64 OR NEW.outcome_id GLOB '*[^0-9a-f]*' OR length(NEW.outcome_fingerprint)<>64 OR NEW.outcome_fingerprint GLOB '*[^0-9a-f]*' OR length(NEW.estimate_receipt_id)<>64 OR NEW.estimate_receipt_id GLOB '*[^0-9a-f]*' OR length(NEW.estimate_receipt_fingerprint)<>64 OR NEW.estimate_receipt_fingerprint GLOB '*[^0-9a-f]*' BEGIN SELECT RAISE(ABORT,'estimator evidence identifier is invalid'); END;
CREATE TRIGGER estimator_evidence_baseline_safe_ids BEFORE INSERT ON estimator_evidence_baseline_projections WHEN length(NEW.submission_id)<>64 OR NEW.submission_id GLOB '*[^0-9a-f]*' OR length(NEW.campaign_id)<>64 OR NEW.campaign_id GLOB '*[^0-9a-f]*' OR length(NEW.case_id)<>64 OR NEW.case_id GLOB '*[^0-9a-f]*' OR length(NEW.plan_fingerprint)<>64 OR NEW.plan_fingerprint GLOB '*[^0-9a-f]*' OR length(NEW.metric_question_fingerprint)<>64 OR NEW.metric_question_fingerprint GLOB '*[^0-9a-f]*' OR length(NEW.evidence_packet_fingerprint)<>64 OR NEW.evidence_packet_fingerprint GLOB '*[^0-9a-f]*' OR length(NEW.baseline_configuration_sha256)<>64 OR NEW.baseline_configuration_sha256 GLOB '*[^0-9a-f]*' OR length(NEW.final_estimate_fingerprint)<>64 OR NEW.final_estimate_fingerprint GLOB '*[^0-9a-f]*' BEGIN SELECT RAISE(ABORT,'estimator evidence identifier is invalid'); END;
CREATE TRIGGER estimator_evidence_objective_safe_ids BEFORE INSERT ON estimator_evidence_objective_projections WHEN length(NEW.submission_id)<>64 OR NEW.submission_id GLOB '*[^0-9a-f]*' OR length(NEW.campaign_id)<>64 OR NEW.campaign_id GLOB '*[^0-9a-f]*' OR length(NEW.case_id)<>64 OR NEW.case_id GLOB '*[^0-9a-f]*' OR length(NEW.plan_fingerprint)<>64 OR NEW.plan_fingerprint GLOB '*[^0-9a-f]*' OR length(NEW.metric_question_fingerprint)<>64 OR NEW.metric_question_fingerprint GLOB '*[^0-9a-f]*' OR length(NEW.evidence_packet_fingerprint)<>64 OR NEW.evidence_packet_fingerprint GLOB '*[^0-9a-f]*' BEGIN SELECT RAISE(ABORT,'estimator evidence identifier is invalid'); END;
CREATE TRIGGER estimator_evidence_judgment_safe_ids BEFORE INSERT ON estimator_evidence_blind_judgments WHEN length(NEW.submission_id)<>64 OR NEW.submission_id GLOB '*[^0-9a-f]*' OR length(NEW.campaign_id)<>64 OR NEW.campaign_id GLOB '*[^0-9a-f]*' OR length(NEW.case_id)<>64 OR NEW.case_id GLOB '*[^0-9a-f]*' OR length(NEW.plan_fingerprint)<>64 OR NEW.plan_fingerprint GLOB '*[^0-9a-f]*' OR length(NEW.metric_question_fingerprint)<>64 OR NEW.metric_question_fingerprint GLOB '*[^0-9a-f]*' OR length(NEW.evidence_packet_fingerprint)<>64 OR NEW.evidence_packet_fingerprint GLOB '*[^0-9a-f]*' BEGIN SELECT RAISE(ABORT,'estimator evidence identifier is invalid'); END;
CREATE TRIGGER estimator_evidence_adjudication_link_safe_ids BEFORE INSERT ON estimator_evidence_adjudication_judgments WHEN length(NEW.submission_id)<>64 OR NEW.submission_id GLOB '*[^0-9a-f]*' OR length(NEW.adjudication_id)<>64 OR NEW.adjudication_id GLOB '*[^0-9a-f]*' OR length(NEW.judgment_id)<>64 OR NEW.judgment_id GLOB '*[^0-9a-f]*' OR length(NEW.campaign_id)<>64 OR NEW.campaign_id GLOB '*[^0-9a-f]*' BEGIN SELECT RAISE(ABORT,'estimator evidence identifier is invalid'); END;
CREATE TRIGGER estimator_evidence_adjudication_safe_ids BEFORE INSERT ON estimator_evidence_blind_adjudications WHEN length(NEW.submission_id)<>64 OR NEW.submission_id GLOB '*[^0-9a-f]*' OR length(NEW.campaign_id)<>64 OR NEW.campaign_id GLOB '*[^0-9a-f]*' OR length(NEW.case_id)<>64 OR NEW.case_id GLOB '*[^0-9a-f]*' OR length(NEW.plan_fingerprint)<>64 OR NEW.plan_fingerprint GLOB '*[^0-9a-f]*' OR length(NEW.metric_question_fingerprint)<>64 OR NEW.metric_question_fingerprint GLOB '*[^0-9a-f]*' OR length(NEW.evidence_packet_fingerprint)<>64 OR NEW.evidence_packet_fingerprint GLOB '*[^0-9a-f]*' BEGIN SELECT RAISE(ABORT,'estimator evidence identifier is invalid'); END;
CREATE TRIGGER estimator_evidence_trial_safe_ids BEFORE INSERT ON estimator_evidence_stability_trials WHEN length(NEW.submission_id)<>64 OR NEW.submission_id GLOB '*[^0-9a-f]*' OR length(NEW.campaign_id)<>64 OR NEW.campaign_id GLOB '*[^0-9a-f]*' OR length(NEW.case_id)<>64 OR NEW.case_id GLOB '*[^0-9a-f]*' OR length(NEW.plan_fingerprint)<>64 OR NEW.plan_fingerprint GLOB '*[^0-9a-f]*' OR length(NEW.metric_question_fingerprint)<>64 OR NEW.metric_question_fingerprint GLOB '*[^0-9a-f]*' OR length(NEW.evidence_packet_fingerprint)<>64 OR NEW.evidence_packet_fingerprint GLOB '*[^0-9a-f]*' OR length(NEW.attempt_id)<>64 OR NEW.attempt_id GLOB '*[^0-9a-f]*' OR length(NEW.outcome_id)<>64 OR NEW.outcome_id GLOB '*[^0-9a-f]*' OR length(NEW.outcome_fingerprint)<>64 OR NEW.outcome_fingerprint GLOB '*[^0-9a-f]*' OR length(NEW.estimate_receipt_id)<>64 OR NEW.estimate_receipt_id GLOB '*[^0-9a-f]*' OR length(NEW.estimate_receipt_fingerprint)<>64 OR NEW.estimate_receipt_fingerprint GLOB '*[^0-9a-f]*' BEGIN SELECT RAISE(ABORT,'estimator evidence identifier is invalid'); END;
CREATE TRIGGER estimator_evidence_series_safe_ids BEFORE INSERT ON estimator_evidence_stability_series WHEN length(NEW.submission_id)<>64 OR NEW.submission_id GLOB '*[^0-9a-f]*' OR length(NEW.campaign_id)<>64 OR NEW.campaign_id GLOB '*[^0-9a-f]*' OR length(NEW.case_id)<>64 OR NEW.case_id GLOB '*[^0-9a-f]*' OR length(NEW.plan_fingerprint)<>64 OR NEW.plan_fingerprint GLOB '*[^0-9a-f]*' OR length(NEW.metric_question_fingerprint)<>64 OR NEW.metric_question_fingerprint GLOB '*[^0-9a-f]*' OR length(NEW.evidence_packet_fingerprint)<>64 OR NEW.evidence_packet_fingerprint GLOB '*[^0-9a-f]*' BEGIN SELECT RAISE(ABORT,'estimator evidence identifier is invalid'); END;
CREATE TRIGGER estimator_evidence_holdout_safe_ids BEFORE INSERT ON estimator_evidence_submission_holdout_cases WHEN length(NEW.campaign_id)<>64 OR NEW.campaign_id GLOB '*[^0-9a-f]*' BEGIN SELECT RAISE(ABORT,'estimator evidence identifier is invalid'); END;
CREATE TRIGGER estimator_evidence_submission_safe_ids BEFORE INSERT ON estimator_evidence_submissions WHEN length(NEW.campaign_id)<>64 OR NEW.campaign_id GLOB '*[^0-9a-f]*' OR length(NEW.expected_manifest_id)<>64 OR NEW.expected_manifest_id GLOB '*[^0-9a-f]*' OR length(NEW.access_audit_id)<>64 OR NEW.access_audit_id GLOB '*[^0-9a-f]*' OR length(NEW.privacy_scan_id)<>64 OR NEW.privacy_scan_id GLOB '*[^0-9a-f]*' BEGIN SELECT RAISE(ABORT,'estimator evidence identifier is invalid'); END;

CREATE TRIGGER estimator_evidence_attempt_launches_time_bounds BEFORE INSERT ON estimator_evidence_attempt_launches WHEN (NEW.approved_at_us IS NOT NULL AND (typeof(NEW.approved_at_us)<>'integer' OR NEW.approved_at_us NOT BETWEEN -62135596800000000 AND 253402300799999999)) OR typeof(NEW.launched_at_us)<>'integer' OR NEW.launched_at_us NOT BETWEEN -62135596800000000 AND 253402300799999999 BEGIN SELECT RAISE(ABORT,'estimator evidence timestamp is out of range'); END;
CREATE TRIGGER estimator_evidence_attempt_outcomes_time_bounds BEFORE INSERT ON estimator_evidence_attempt_outcomes WHEN typeof(NEW.enqueued_at_us)<>'integer' OR NEW.enqueued_at_us NOT BETWEEN -62135596800000000 AND 253402300799999999 OR typeof(NEW.dequeued_at_us)<>'integer' OR NEW.dequeued_at_us NOT BETWEEN -62135596800000000 AND 253402300799999999 OR typeof(NEW.started_at_us)<>'integer' OR NEW.started_at_us NOT BETWEEN -62135596800000000 AND 253402300799999999 OR typeof(NEW.finished_at_us)<>'integer' OR NEW.finished_at_us NOT BETWEEN -62135596800000000 AND 253402300799999999 BEGIN SELECT RAISE(ABORT,'estimator evidence timestamp is out of range'); END;
CREATE TRIGGER estimator_evidence_expected_manifests_time_bounds BEFORE INSERT ON estimator_evidence_expected_manifests WHEN typeof(NEW.frozen_at_us)<>'integer' OR NEW.frozen_at_us NOT BETWEEN -62135596800000000 AND 253402300799999999 BEGIN SELECT RAISE(ABORT,'estimator evidence timestamp is out of range'); END;
CREATE TRIGGER estimator_evidence_access_events_time_bounds BEFORE INSERT ON estimator_evidence_access_events WHEN typeof(NEW.occurred_at_us)<>'integer' OR NEW.occurred_at_us NOT BETWEEN -62135596800000000 AND 253402300799999999 BEGIN SELECT RAISE(ABORT,'estimator evidence timestamp is out of range'); END;
CREATE TRIGGER estimator_evidence_access_gaps_time_bounds BEFORE INSERT ON estimator_evidence_access_gaps WHEN typeof(NEW.started_at_us)<>'integer' OR NEW.started_at_us NOT BETWEEN -62135596800000000 AND 253402300799999999 OR typeof(NEW.ended_at_us)<>'integer' OR NEW.ended_at_us NOT BETWEEN -62135596800000000 AND 253402300799999999 BEGIN SELECT RAISE(ABORT,'estimator evidence timestamp is out of range'); END;
CREATE TRIGGER estimator_evidence_access_manifests_time_bounds BEFORE INSERT ON estimator_evidence_access_manifests WHEN typeof(NEW.coverage_started_at_us)<>'integer' OR NEW.coverage_started_at_us NOT BETWEEN -62135596800000000 AND 253402300799999999 OR typeof(NEW.coverage_ended_at_us)<>'integer' OR NEW.coverage_ended_at_us NOT BETWEEN -62135596800000000 AND 253402300799999999 OR typeof(NEW.frozen_at_us)<>'integer' OR NEW.frozen_at_us NOT BETWEEN -62135596800000000 AND 253402300799999999 BEGIN SELECT RAISE(ABORT,'estimator evidence timestamp is out of range'); END;
CREATE TRIGGER estimator_evidence_access_audits_time_bounds BEFORE INSERT ON estimator_evidence_access_audits WHEN typeof(NEW.holdout_unsealed_at_us)<>'integer' OR NEW.holdout_unsealed_at_us NOT BETWEEN -62135596800000000 AND 253402300799999999 OR typeof(NEW.completed_at_us)<>'integer' OR NEW.completed_at_us NOT BETWEEN -62135596800000000 AND 253402300799999999 BEGIN SELECT RAISE(ABORT,'estimator evidence timestamp is out of range'); END;
CREATE TRIGGER estimator_evidence_privacy_findings_time_bounds BEFORE INSERT ON estimator_evidence_privacy_findings WHEN typeof(NEW.detected_at_us)<>'integer' OR NEW.detected_at_us NOT BETWEEN -62135596800000000 AND 253402300799999999 BEGIN SELECT RAISE(ABORT,'estimator evidence timestamp is out of range'); END;
CREATE TRIGGER estimator_evidence_privacy_manifests_time_bounds BEFORE INSERT ON estimator_evidence_privacy_manifests WHEN typeof(NEW.frozen_at_us)<>'integer' OR NEW.frozen_at_us NOT BETWEEN -62135596800000000 AND 253402300799999999 BEGIN SELECT RAISE(ABORT,'estimator evidence timestamp is out of range'); END;
CREATE TRIGGER estimator_evidence_privacy_scans_time_bounds BEFORE INSERT ON estimator_evidence_privacy_scans WHEN typeof(NEW.started_at_us)<>'integer' OR NEW.started_at_us NOT BETWEEN -62135596800000000 AND 253402300799999999 OR typeof(NEW.completed_at_us)<>'integer' OR NEW.completed_at_us NOT BETWEEN -62135596800000000 AND 253402300799999999 BEGIN SELECT RAISE(ABORT,'estimator evidence timestamp is out of range'); END;
CREATE TRIGGER estimator_evidence_structured_estimates_time_bounds BEFORE INSERT ON estimator_evidence_structured_estimates WHEN typeof(NEW.recorded_at_us)<>'integer' OR NEW.recorded_at_us NOT BETWEEN -62135596800000000 AND 253402300799999999 BEGIN SELECT RAISE(ABORT,'estimator evidence timestamp is out of range'); END;
CREATE TRIGGER estimator_evidence_candidate_projections_time_bounds BEFORE INSERT ON estimator_evidence_candidate_projections WHEN typeof(NEW.selected_at_us)<>'integer' OR NEW.selected_at_us NOT BETWEEN -62135596800000000 AND 253402300799999999 BEGIN SELECT RAISE(ABORT,'estimator evidence timestamp is out of range'); END;
CREATE TRIGGER estimator_evidence_baseline_projections_time_bounds BEFORE INSERT ON estimator_evidence_baseline_projections WHEN typeof(NEW.evaluated_at_us)<>'integer' OR NEW.evaluated_at_us NOT BETWEEN -62135596800000000 AND 253402300799999999 BEGIN SELECT RAISE(ABORT,'estimator evidence timestamp is out of range'); END;
CREATE TRIGGER estimator_evidence_objective_projections_time_bounds BEFORE INSERT ON estimator_evidence_objective_projections WHEN typeof(NEW.observed_at_us)<>'integer' OR NEW.observed_at_us NOT BETWEEN -62135596800000000 AND 253402300799999999 BEGIN SELECT RAISE(ABORT,'estimator evidence timestamp is out of range'); END;
CREATE TRIGGER estimator_evidence_blind_judgments_time_bounds BEFORE INSERT ON estimator_evidence_blind_judgments WHEN typeof(NEW.created_at_us)<>'integer' OR NEW.created_at_us NOT BETWEEN -62135596800000000 AND 253402300799999999 BEGIN SELECT RAISE(ABORT,'estimator evidence timestamp is out of range'); END;
CREATE TRIGGER estimator_evidence_blind_adjudications_time_bounds BEFORE INSERT ON estimator_evidence_blind_adjudications WHEN typeof(NEW.completed_at_us)<>'integer' OR NEW.completed_at_us NOT BETWEEN -62135596800000000 AND 253402300799999999 BEGIN SELECT RAISE(ABORT,'estimator evidence timestamp is out of range'); END;
CREATE TRIGGER estimator_evidence_stability_trials_time_bounds BEFORE INSERT ON estimator_evidence_stability_trials WHEN typeof(NEW.recorded_at_us)<>'integer' OR NEW.recorded_at_us NOT BETWEEN -62135596800000000 AND 253402300799999999 BEGIN SELECT RAISE(ABORT,'estimator evidence timestamp is out of range'); END;
CREATE TRIGGER estimator_evidence_stability_series_time_bounds BEFORE INSERT ON estimator_evidence_stability_series WHEN typeof(NEW.frozen_at_us)<>'integer' OR NEW.frozen_at_us NOT BETWEEN -62135596800000000 AND 253402300799999999 BEGIN SELECT RAISE(ABORT,'estimator evidence timestamp is out of range'); END;
CREATE TRIGGER estimator_evidence_submissions_time_bounds BEFORE INSERT ON estimator_evidence_submissions WHEN typeof(NEW.submitted_at_us)<>'integer' OR NEW.submitted_at_us NOT BETWEEN -62135596800000000 AND 253402300799999999 BEGIN SELECT RAISE(ABORT,'estimator evidence timestamp is out of range'); END;

CREATE INDEX estimator_evidence_campaign_idx ON estimator_evidence_attempt_launches(campaign_id, submission_id);
CREATE INDEX estimator_evidence_outcome_idx ON estimator_evidence_attempt_outcomes(submission_id, outcome_id);
CREATE INDEX estimator_evidence_estimate_idx ON estimator_evidence_structured_estimates(submission_id, attempt_id);

COMMIT;
"""


MIGRATION_18 = r"""
BEGIN IMMEDIATE;

-- Rebuild the v11 queue with the same closed state machine and one additional
-- reviewed kind. SQLite cannot extend a CHECK constraint in place.
DROP TRIGGER analysis_jobs_identity_immutable;
DROP TRIGGER analysis_jobs_closed_transitions;
DROP TRIGGER analysis_jobs_terminal_immutable;
DROP TRIGGER analysis_job_metrics_no_update;
DROP INDEX analysis_jobs_claim_idx;
DROP INDEX analysis_jobs_session_idx;
DROP INDEX analysis_jobs_grant_idx;
DROP INDEX analysis_jobs_lease_idx;
ALTER TABLE analysis_job_metrics RENAME TO analysis_job_metrics_v11;
ALTER TABLE analysis_jobs RENAME TO analysis_jobs_v11;

CREATE TABLE analysis_jobs (
    job_id TEXT PRIMARY KEY CHECK(length(job_id)=64 AND job_id NOT GLOB '*[^0-9a-f]*'),
    dedupe_key TEXT NOT NULL UNIQUE CHECK(length(dedupe_key)=64 AND dedupe_key NOT GLOB '*[^0-9a-f]*'),
    kind TEXT NOT NULL CHECK(kind IN ('session_quality','synthetic_validation','estimator_execution')),
    provider TEXT NOT NULL CHECK(provider IN ('codex','claude_code','synthetic')),
    project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    input_fingerprint TEXT NOT NULL CHECK(length(input_fingerprint)=64 AND input_fingerprint NOT GLOB '*[^0-9a-f]*'),
    provenance_fingerprint TEXT NOT NULL CHECK(length(provenance_fingerprint)=64 AND provenance_fingerprint NOT GLOB '*[^0-9a-f]*'),
    estimator_plan_version TEXT NOT NULL CHECK(length(estimator_plan_version) BETWEEN 1 AND 128 AND estimator_plan_version GLOB '[A-Za-z0-9]*' AND estimator_plan_version NOT GLOB '*[^A-Za-z0-9._+:/-]*'),
    redactor_version TEXT NOT NULL CHECK(length(redactor_version) BETWEEN 1 AND 128 AND redactor_version GLOB '[A-Za-z0-9]*' AND redactor_version NOT GLOB '*[^A-Za-z0-9._+:/-]*'),
    provider_schema_version TEXT NOT NULL CHECK(length(provider_schema_version) BETWEEN 1 AND 128 AND provider_schema_version GLOB '[A-Za-z0-9]*' AND provider_schema_version NOT GLOB '*[^A-Za-z0-9._+:/-]*'),
    automation_grant_id TEXT CHECK(automation_grant_id IS NULL OR (length(automation_grant_id)=64 AND automation_grant_id NOT GLOB '*[^0-9a-f]*')),
    local_only INTEGER NOT NULL CHECK(local_only=1),
    state TEXT NOT NULL CHECK(state IN ('queued','preprocessing','stage_n','awaiting_approval','completed','partial','failed','cancelled','superseded')),
    stage_number INTEGER CHECK(stage_number BETWEEN 1 AND 32),
    progress_completed INTEGER NOT NULL CHECK(progress_completed BETWEEN 0 AND 1000000),
    progress_total INTEGER NOT NULL CHECK(progress_total BETWEEN 1 AND 1000000),
    attempt_count INTEGER NOT NULL CHECK(attempt_count BETWEEN 0 AND 5),
    max_attempts INTEGER NOT NULL CHECK(max_attempts BETWEEN 1 AND 5),
    available_at TEXT NOT NULL,
    cancel_requested INTEGER NOT NULL CHECK(cancel_requested IN (0,1)),
    lease_owner TEXT CHECK(lease_owner IS NULL OR (length(lease_owner)=64 AND lease_owner NOT GLOB '*[^0-9a-f]*')),
    lease_token TEXT CHECK(lease_token IS NULL OR (length(lease_token)=64 AND lease_token NOT GLOB '*[^0-9a-f]*')),
    lease_expires_at TEXT,
    last_error_code TEXT CHECK(last_error_code IS NULL OR (length(last_error_code) BETWEEN 1 AND 128 AND last_error_code GLOB '[A-Za-z0-9]*' AND last_error_code NOT GLOB '*[^A-Za-z0-9._+:/-]*')),
    terminal_reason_code TEXT CHECK(terminal_reason_code IS NULL OR (length(terminal_reason_code) BETWEEN 1 AND 128 AND terminal_reason_code GLOB '[A-Za-z0-9]*' AND terminal_reason_code NOT GLOB '*[^A-Za-z0-9._+:/-]*')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    terminal_at TEXT,
    CHECK(attempt_count<=max_attempts),
    CHECK(progress_completed<=progress_total),
    CHECK((state='stage_n')=(stage_number IS NOT NULL)),
    CHECK((state IN ('preprocessing','stage_n') AND lease_owner IS NOT NULL AND lease_token IS NOT NULL AND lease_expires_at IS NOT NULL) OR (state NOT IN ('preprocessing','stage_n') AND lease_owner IS NULL AND lease_token IS NULL AND lease_expires_at IS NULL)),
    CHECK((state IN ('completed','partial','failed','cancelled','superseded') AND terminal_at IS NOT NULL AND terminal_reason_code IS NOT NULL) OR (state NOT IN ('completed','partial','failed','cancelled','superseded') AND terminal_at IS NULL AND terminal_reason_code IS NULL))
);
INSERT INTO analysis_jobs SELECT * FROM analysis_jobs_v11;

CREATE TABLE analysis_job_metrics (
    job_id TEXT NOT NULL REFERENCES analysis_jobs(job_id) ON DELETE CASCADE,
    metric_key TEXT NOT NULL CHECK(length(metric_key) BETWEEN 1 AND 128 AND metric_key GLOB '[A-Za-z0-9]*' AND metric_key NOT GLOB '*[^A-Za-z0-9._+:/-]*'),
    ordinal INTEGER NOT NULL CHECK(ordinal BETWEEN 0 AND 99),
    PRIMARY KEY(job_id,metric_key), UNIQUE(job_id,ordinal)
);
INSERT INTO analysis_job_metrics SELECT * FROM analysis_job_metrics_v11;
DROP TABLE analysis_job_metrics_v11;
DROP TABLE analysis_jobs_v11;

CREATE INDEX analysis_jobs_claim_idx ON analysis_jobs(state,available_at,created_at,job_id);
CREATE INDEX analysis_jobs_session_idx ON analysis_jobs(session_id,created_at DESC,job_id DESC);
CREATE INDEX analysis_jobs_grant_idx ON analysis_jobs(automation_grant_id,state,created_at) WHERE automation_grant_id IS NOT NULL;
CREATE INDEX analysis_jobs_lease_idx ON analysis_jobs(state,lease_expires_at) WHERE state IN ('preprocessing','stage_n');
CREATE TRIGGER analysis_jobs_identity_immutable BEFORE UPDATE ON analysis_jobs
WHEN NEW.job_id IS NOT OLD.job_id OR NEW.dedupe_key IS NOT OLD.dedupe_key OR NEW.kind IS NOT OLD.kind OR NEW.provider IS NOT OLD.provider OR NEW.project_id IS NOT OLD.project_id OR NEW.session_id IS NOT OLD.session_id OR NEW.input_fingerprint IS NOT OLD.input_fingerprint OR NEW.provenance_fingerprint IS NOT OLD.provenance_fingerprint OR NEW.estimator_plan_version IS NOT OLD.estimator_plan_version OR NEW.redactor_version IS NOT OLD.redactor_version OR NEW.provider_schema_version IS NOT OLD.provider_schema_version OR NEW.automation_grant_id IS NOT OLD.automation_grant_id OR NEW.local_only IS NOT OLD.local_only OR NEW.max_attempts IS NOT OLD.max_attempts OR NEW.created_at IS NOT OLD.created_at
BEGIN SELECT RAISE(ABORT,'analysis job identity is immutable'); END;
CREATE TRIGGER analysis_jobs_closed_transitions BEFORE UPDATE ON analysis_jobs
WHEN NEW.state<>OLD.state AND NOT ((OLD.state='queued' AND NEW.state IN ('preprocessing','cancelled','superseded')) OR (OLD.state='preprocessing' AND NEW.state IN ('queued','stage_n','awaiting_approval','completed','partial','failed','cancelled','superseded')) OR (OLD.state='stage_n' AND NEW.state IN ('queued','awaiting_approval','completed','partial','failed','cancelled','superseded')) OR (OLD.state='awaiting_approval' AND NEW.state IN ('queued','failed','cancelled','superseded')))
BEGIN SELECT RAISE(ABORT,'analysis job state transition is invalid'); END;
CREATE TRIGGER analysis_jobs_terminal_immutable BEFORE UPDATE ON analysis_jobs WHEN OLD.state IN ('completed','partial','failed','cancelled','superseded') BEGIN SELECT RAISE(ABORT,'terminal analysis jobs are immutable'); END;
CREATE TRIGGER analysis_job_metrics_no_update BEFORE UPDATE ON analysis_job_metrics BEGIN SELECT RAISE(ABORT,'analysis job metric selections are immutable'); END;

-- The transient authorization row is accepted only when the application-held
-- HMAC capability is active. It is deleted before every repository call returns.
CREATE TABLE estimator_runtime_write_authorizations (
    operation_id TEXT PRIMARY KEY CHECK(length(operation_id)=64 AND operation_id NOT GLOB '*[^0-9a-f]*'),
    authorization_id TEXT NOT NULL CHECK(length(authorization_id)=64 AND authorization_id NOT GLOB '*[^0-9a-f]*'),
    execution_id TEXT NOT NULL CHECK(length(execution_id)=64 AND execution_id NOT GLOB '*[^0-9a-f]*'),
    job_id TEXT NOT NULL CHECK(length(job_id)=64 AND job_id NOT GLOB '*[^0-9a-f]*'),
    authorization_tag TEXT NOT NULL CHECK(length(authorization_tag)=64 AND authorization_tag NOT GLOB '*[^0-9a-f]*'),
    UNIQUE(authorization_id,execution_id,job_id)
);
CREATE TRIGGER estimator_runtime_write_authorization_validate BEFORE INSERT ON estimator_runtime_write_authorizations
WHEN NEW.authorization_tag<>estimator_runtime_authorization_tag(NEW.operation_id,NEW.authorization_id,NEW.execution_id,NEW.job_id)
BEGIN SELECT RAISE(ABORT,'estimator runtime write authorization is invalid'); END;
CREATE TRIGGER estimator_runtime_write_authorization_no_update BEFORE UPDATE ON estimator_runtime_write_authorizations BEGIN SELECT RAISE(ABORT,'estimator runtime write authorization is immutable'); END;
CREATE TRIGGER estimator_runtime_write_authorization_delete_validate BEFORE DELETE ON estimator_runtime_write_authorizations
WHEN OLD.authorization_tag<>estimator_runtime_authorization_tag(OLD.operation_id,OLD.authorization_id,OLD.execution_id,OLD.job_id)
BEGIN SELECT RAISE(ABORT,'estimator runtime write authorization is invalid'); END;

CREATE TABLE estimator_runtime_authorizations (
    authorization_id TEXT PRIMARY KEY CHECK(length(authorization_id)=64 AND authorization_id NOT GLOB '*[^0-9a-f]*'),
    authorization_fingerprint TEXT NOT NULL UNIQUE CHECK(length(authorization_fingerprint)=64 AND authorization_fingerprint NOT GLOB '*[^0-9a-f]*'),
    contract_version TEXT NOT NULL CHECK(length(contract_version) BETWEEN 1 AND 128 AND contract_version NOT GLOB '*[^A-Za-z0-9._+-]*'),
    job_id TEXT NOT NULL UNIQUE REFERENCES analysis_jobs(job_id) ON DELETE CASCADE,
    execution_id TEXT NOT NULL UNIQUE CHECK(length(execution_id)=64 AND execution_id NOT GLOB '*[^0-9a-f]*'),
    kind TEXT NOT NULL CHECK(kind IN ('manual_once','automation_once','synthetic_test')),
    provider TEXT NOT NULL CHECK(provider IN ('codex','claude_code','synthetic')),
    destination TEXT NOT NULL CHECK(destination IN ('local_device','openai_api','anthropic_api','codex_cli','claude_api','manual_import','synthetic_test')),
    retention_class TEXT NOT NULL CHECK(retention_class IN ('local_ephemeral','provider_zero_day','provider_30_day','provider_disclosed_other','manual_export','synthetic')),
    project_id TEXT NOT NULL REFERENCES projects(project_id),
    session_id TEXT NOT NULL REFERENCES sessions(session_id),
    session_revision_id TEXT NOT NULL CHECK(length(session_revision_id)=64 AND session_revision_id NOT GLOB '*[^0-9a-f]*'),
    window_fingerprint TEXT NOT NULL CHECK(length(window_fingerprint)=64 AND window_fingerprint NOT GLOB '*[^0-9a-f]*'),
    input_fingerprint TEXT NOT NULL CHECK(length(input_fingerprint)=64 AND input_fingerprint NOT GLOB '*[^0-9a-f]*'),
    provenance_fingerprint TEXT NOT NULL CHECK(length(provenance_fingerprint)=64 AND provenance_fingerprint NOT GLOB '*[^0-9a-f]*'),
    plan_fingerprint TEXT NOT NULL REFERENCES estimator_plans(plan_fingerprint),
    route TEXT NOT NULL CHECK(route IN ('fast','balanced','deep')),
    provider_schema_version TEXT NOT NULL CHECK(length(provider_schema_version) BETWEEN 1 AND 128 AND provider_schema_version GLOB '[A-Za-z0-9]*' AND provider_schema_version NOT GLOB '*[^A-Za-z0-9._+-]*' AND instr(provider_schema_version,'..')=0),
    redactor_version TEXT NOT NULL CHECK(length(redactor_version) BETWEEN 1 AND 128 AND redactor_version GLOB '[A-Za-z0-9]*' AND redactor_version NOT GLOB '*[^A-Za-z0-9._+-]*' AND instr(redactor_version,'..')=0),
    redactor_sha256 TEXT NOT NULL CHECK(length(redactor_sha256)=64 AND redactor_sha256 NOT GLOB '*[^0-9a-f]*'),
    automation_grant_id TEXT CHECK(automation_grant_id IS NULL OR (length(automation_grant_id)=64 AND automation_grant_id NOT GLOB '*[^0-9a-f]*')),
    issued_at_us INTEGER NOT NULL CHECK(typeof(issued_at_us)='integer' AND issued_at_us BETWEEN -62135596800000000 AND 253402300799999999),
    expires_at_us INTEGER NOT NULL CHECK(typeof(expires_at_us)='integer' AND expires_at_us BETWEEN -62135596800000000 AND 253402300799999999 AND expires_at_us>issued_at_us AND expires_at_us-issued_at_us<=600000000),
    packet_count INTEGER NOT NULL CHECK(packet_count BETWEEN 1 AND 100),
    one_shot INTEGER NOT NULL CHECK(one_shot=1),
    preview_text_retained INTEGER NOT NULL CHECK(preview_text_retained=0),
    execution_only INTEGER NOT NULL CHECK(execution_only=1),
    activation_allowed INTEGER NOT NULL CHECK(activation_allowed=0),
    product_metric_write_allowed INTEGER NOT NULL CHECK(product_metric_write_allowed=0),
    private_export_allowed INTEGER NOT NULL CHECK(private_export_allowed=0),
    team_share_allowed INTEGER NOT NULL CHECK(team_share_allowed=0),
    CHECK((kind='automation_once')=(automation_grant_id IS NOT NULL)),
    CHECK(kind<>'automation_once' OR destination NOT IN ('openai_api','anthropic_api','codex_cli','claude_api')),
    CHECK((destination='local_device' AND retention_class='local_ephemeral') OR (destination='synthetic_test' AND provider='synthetic' AND retention_class='synthetic') OR (destination='manual_import' AND retention_class='manual_export') OR (destination IN ('openai_api','anthropic_api','codex_cli','claude_api') AND retention_class IN ('provider_zero_day','provider_30_day','provider_disclosed_other')))
);

CREATE TABLE estimator_runtime_authorization_packets (
    authorization_id TEXT NOT NULL REFERENCES estimator_runtime_authorizations(authorization_id) ON DELETE CASCADE,
    execution_id TEXT NOT NULL,
    ordinal INTEGER NOT NULL CHECK(ordinal BETWEEN 0 AND 99),
    metric_key TEXT NOT NULL CHECK(length(metric_key) BETWEEN 1 AND 128 AND metric_key GLOB '[a-z]*' AND metric_key NOT GLOB '*[^a-z0-9_.:-]*'),
    metric_question_fingerprint TEXT NOT NULL REFERENCES estimator_metric_questions(question_fingerprint),
    evidence_packet_fingerprint TEXT NOT NULL CHECK(length(evidence_packet_fingerprint)=64 AND evidence_packet_fingerprint NOT GLOB '*[^0-9a-f]*'),
    PRIMARY KEY(authorization_id,metric_key), UNIQUE(authorization_id,ordinal), UNIQUE(authorization_id,evidence_packet_fingerprint)
);

CREATE TABLE estimator_runtime_authorization_consumptions (
    authorization_id TEXT PRIMARY KEY REFERENCES estimator_runtime_authorizations(authorization_id) ON DELETE CASCADE,
    execution_id TEXT NOT NULL UNIQUE,
    job_id TEXT NOT NULL UNIQUE REFERENCES analysis_jobs(job_id) ON DELETE CASCADE,
    consumed_at_us INTEGER NOT NULL CHECK(typeof(consumed_at_us)='integer' AND consumed_at_us BETWEEN -62135596800000000 AND 253402300799999999)
);

CREATE TABLE estimator_runtime_authorization_revocations (
    authorization_id TEXT PRIMARY KEY REFERENCES estimator_runtime_authorizations(authorization_id) ON DELETE CASCADE,
    execution_id TEXT NOT NULL UNIQUE,
    revoked_at_us INTEGER NOT NULL CHECK(typeof(revoked_at_us)='integer' AND revoked_at_us BETWEEN -62135596800000000 AND 253402300799999999)
);

CREATE TABLE estimator_runtime_executions (
    execution_id TEXT PRIMARY KEY CHECK(length(execution_id)=64 AND execution_id NOT GLOB '*[^0-9a-f]*'),
    authorization_id TEXT NOT NULL UNIQUE REFERENCES estimator_runtime_authorizations(authorization_id) ON DELETE CASCADE,
    job_id TEXT NOT NULL UNIQUE REFERENCES analysis_jobs(job_id) ON DELETE CASCADE,
    plan_fingerprint TEXT NOT NULL REFERENCES estimator_plans(plan_fingerprint),
    route TEXT NOT NULL CHECK(route IN ('fast','balanced','deep')),
    provider TEXT NOT NULL CHECK(provider IN ('codex','claude_code','synthetic')),
    project_id TEXT NOT NULL REFERENCES projects(project_id),
    session_id TEXT NOT NULL REFERENCES sessions(session_id),
    session_revision_id TEXT NOT NULL CHECK(length(session_revision_id)=64 AND session_revision_id NOT GLOB '*[^0-9a-f]*'),
    window_fingerprint TEXT NOT NULL CHECK(length(window_fingerprint)=64 AND window_fingerprint NOT GLOB '*[^0-9a-f]*'),
    input_fingerprint TEXT NOT NULL CHECK(length(input_fingerprint)=64 AND input_fingerprint NOT GLOB '*[^0-9a-f]*'),
    provenance_fingerprint TEXT NOT NULL CHECK(length(provenance_fingerprint)=64 AND provenance_fingerprint NOT GLOB '*[^0-9a-f]*'),
    created_at_us INTEGER NOT NULL CHECK(typeof(created_at_us)='integer' AND created_at_us BETWEEN -62135596800000000 AND 253402300799999999),
    execution_only INTEGER NOT NULL CHECK(execution_only=1), activation_allowed INTEGER NOT NULL CHECK(activation_allowed=0), product_metric_write_allowed INTEGER NOT NULL CHECK(product_metric_write_allowed=0), private_export_allowed INTEGER NOT NULL CHECK(private_export_allowed=0), team_share_allowed INTEGER NOT NULL CHECK(team_share_allowed=0)
);

CREATE TABLE estimator_runtime_job_bindings (
    job_id TEXT PRIMARY KEY REFERENCES analysis_jobs(job_id) ON DELETE CASCADE,
    execution_id TEXT NOT NULL UNIQUE REFERENCES estimator_runtime_executions(execution_id) ON DELETE CASCADE,
    authorization_id TEXT NOT NULL UNIQUE REFERENCES estimator_runtime_authorizations(authorization_id) ON DELETE CASCADE,
    authorization_fingerprint TEXT NOT NULL CHECK(length(authorization_fingerprint)=64 AND authorization_fingerprint NOT GLOB '*[^0-9a-f]*'),
    plan_fingerprint TEXT NOT NULL REFERENCES estimator_plans(plan_fingerprint),
    route TEXT NOT NULL CHECK(route IN ('fast','balanced','deep')),
    provider TEXT NOT NULL CHECK(provider IN ('codex','claude_code','synthetic')),
    project_id TEXT NOT NULL REFERENCES projects(project_id), session_id TEXT NOT NULL REFERENCES sessions(session_id),
    session_revision_id TEXT NOT NULL CHECK(length(session_revision_id)=64 AND session_revision_id NOT GLOB '*[^0-9a-f]*'),
    window_fingerprint TEXT NOT NULL CHECK(length(window_fingerprint)=64 AND window_fingerprint NOT GLOB '*[^0-9a-f]*'),
    input_fingerprint TEXT NOT NULL CHECK(length(input_fingerprint)=64 AND input_fingerprint NOT GLOB '*[^0-9a-f]*'),
    provenance_fingerprint TEXT NOT NULL CHECK(length(provenance_fingerprint)=64 AND provenance_fingerprint NOT GLOB '*[^0-9a-f]*'),
    created_at_us INTEGER NOT NULL CHECK(typeof(created_at_us)='integer' AND created_at_us BETWEEN -62135596800000000 AND 253402300799999999)
);

CREATE TABLE estimator_runtime_packet_receipts (
    execution_id TEXT NOT NULL REFERENCES estimator_runtime_executions(execution_id) ON DELETE CASCADE,
    authorization_id TEXT NOT NULL REFERENCES estimator_runtime_authorizations(authorization_id) ON DELETE CASCADE,
    ordinal INTEGER NOT NULL CHECK(ordinal BETWEEN 0 AND 99),
    packet_fingerprint TEXT NOT NULL CHECK(length(packet_fingerprint)=64 AND packet_fingerprint NOT GLOB '*[^0-9a-f]*'),
    packet_schema_version TEXT NOT NULL CHECK(length(packet_schema_version) BETWEEN 1 AND 128 AND packet_schema_version NOT GLOB '*[^A-Za-z0-9._+-]*'),
    plan_fingerprint TEXT NOT NULL REFERENCES estimator_plans(plan_fingerprint), metric_key TEXT NOT NULL, metric_question_fingerprint TEXT NOT NULL REFERENCES estimator_metric_questions(question_fingerprint),
    route TEXT NOT NULL CHECK(route IN ('fast','balanced','deep')),
    scope_projection_fingerprint TEXT NOT NULL, scope_router_output_fingerprint TEXT NOT NULL, retrieval_query_fingerprint TEXT NOT NULL, requirements_sha256 TEXT NOT NULL, chronology_sha256 TEXT NOT NULL, retrieval_index_sha256 TEXT NOT NULL,
    provider TEXT NOT NULL CHECK(provider IN ('codex','claude_code','synthetic')),
    adapter_version TEXT NOT NULL, provider_schema_version TEXT NOT NULL, preprocessing_version TEXT NOT NULL, preprocessing_sha256 TEXT NOT NULL, router_version TEXT NOT NULL, router_sha256 TEXT NOT NULL, redactor_version TEXT NOT NULL, redactor_sha256 TEXT NOT NULL,
    source_record_count INTEGER NOT NULL CHECK(source_record_count BETWEEN 0 AND 10000000), requirement_count INTEGER NOT NULL CHECK(requirement_count BETWEEN 0 AND 1000000), chronology_count INTEGER NOT NULL CHECK(chronology_count BETWEEN 0 AND 10000000), action_count INTEGER NOT NULL CHECK(action_count BETWEEN 0 AND 1000000), decision_count INTEGER NOT NULL CHECK(decision_count BETWEEN 0 AND 1000000), feedback_count INTEGER NOT NULL CHECK(feedback_count BETWEEN 0 AND 1000000), verification_count INTEGER NOT NULL CHECK(verification_count BETWEEN 0 AND 1000000), evidence_ref_count INTEGER NOT NULL CHECK(evidence_ref_count BETWEEN 0 AND 512),
    created_at_us INTEGER NOT NULL CHECK(typeof(created_at_us)='integer' AND created_at_us BETWEEN -62135596800000000 AND 253402300799999999),
    ephemeral_payload_retained INTEGER NOT NULL CHECK(ephemeral_payload_retained=0), execution_only INTEGER NOT NULL CHECK(execution_only=1), activation_allowed INTEGER NOT NULL CHECK(activation_allowed=0), private_export_allowed INTEGER NOT NULL CHECK(private_export_allowed=0), team_share_allowed INTEGER NOT NULL CHECK(team_share_allowed=0),
    PRIMARY KEY(execution_id,packet_fingerprint), UNIQUE(execution_id,ordinal), UNIQUE(execution_id,metric_key),
    CHECK(length(metric_key) BETWEEN 1 AND 128 AND metric_key GLOB '[a-z]*' AND metric_key NOT GLOB '*[^a-z0-9_.:-]*'),
    CHECK(length(scope_projection_fingerprint)=64 AND scope_projection_fingerprint NOT GLOB '*[^0-9a-f]*'), CHECK(length(scope_router_output_fingerprint)=64 AND scope_router_output_fingerprint NOT GLOB '*[^0-9a-f]*'), CHECK(length(retrieval_query_fingerprint)=64 AND retrieval_query_fingerprint NOT GLOB '*[^0-9a-f]*'), CHECK(length(requirements_sha256)=64 AND requirements_sha256 NOT GLOB '*[^0-9a-f]*'), CHECK(length(chronology_sha256)=64 AND chronology_sha256 NOT GLOB '*[^0-9a-f]*'), CHECK(length(retrieval_index_sha256)=64 AND retrieval_index_sha256 NOT GLOB '*[^0-9a-f]*'), CHECK(length(preprocessing_sha256)=64 AND preprocessing_sha256 NOT GLOB '*[^0-9a-f]*'), CHECK(length(router_sha256)=64 AND router_sha256 NOT GLOB '*[^0-9a-f]*'), CHECK(length(redactor_sha256)=64 AND redactor_sha256 NOT GLOB '*[^0-9a-f]*')
);
CREATE TABLE estimator_runtime_packet_refs (
    execution_id TEXT NOT NULL, packet_fingerprint TEXT NOT NULL, authorization_id TEXT NOT NULL, ordinal INTEGER NOT NULL CHECK(ordinal BETWEEN 0 AND 511), evidence_reference_id TEXT NOT NULL CHECK(length(evidence_reference_id)=64 AND evidence_reference_id NOT GLOB '*[^0-9a-f]*'),
    PRIMARY KEY(execution_id,packet_fingerprint,ordinal), UNIQUE(execution_id,packet_fingerprint,evidence_reference_id),
    FOREIGN KEY(execution_id,packet_fingerprint) REFERENCES estimator_runtime_packet_receipts(execution_id,packet_fingerprint) ON DELETE CASCADE
);

CREATE TABLE estimator_runtime_state_receipts (
    state_receipt_id TEXT PRIMARY KEY CHECK(length(state_receipt_id)=64 AND state_receipt_id NOT GLOB '*[^0-9a-f]*'), execution_id TEXT NOT NULL REFERENCES estimator_runtime_executions(execution_id) ON DELETE CASCADE, authorization_id TEXT NOT NULL, sequence INTEGER NOT NULL CHECK(sequence BETWEEN 0 AND 1000000), previous_state_receipt_fingerprint TEXT, state TEXT NOT NULL CHECK(state IN ('created','running','partial','failed','cancelled','superseded')), reason_code TEXT NOT NULL CHECK(length(reason_code) BETWEEN 1 AND 128 AND reason_code GLOB '[a-z]*' AND reason_code NOT GLOB '*[^a-z0-9_.:-]*'), recorded_at_us INTEGER NOT NULL CHECK(typeof(recorded_at_us)='integer' AND recorded_at_us BETWEEN -62135596800000000 AND 253402300799999999), receipt_fingerprint TEXT NOT NULL UNIQUE CHECK(length(receipt_fingerprint)=64 AND receipt_fingerprint NOT GLOB '*[^0-9a-f]*'), UNIQUE(execution_id,sequence), CHECK((sequence=0)=(previous_state_receipt_fingerprint IS NULL)), CHECK(previous_state_receipt_fingerprint IS NULL OR (length(previous_state_receipt_fingerprint)=64 AND previous_state_receipt_fingerprint NOT GLOB '*[^0-9a-f]*'))
);
CREATE TABLE estimator_runtime_stage_attempts (
    attempt_id TEXT PRIMARY KEY CHECK(length(attempt_id)=64 AND attempt_id NOT GLOB '*[^0-9a-f]*'), execution_id TEXT NOT NULL REFERENCES estimator_runtime_executions(execution_id) ON DELETE CASCADE, authorization_id TEXT NOT NULL, metric_key TEXT NOT NULL, metric_question_fingerprint TEXT NOT NULL, evidence_packet_fingerprint TEXT NOT NULL, stage_ordinal INTEGER NOT NULL CHECK(stage_ordinal BETWEEN 1 AND 7), stage_kind TEXT NOT NULL CHECK(stage_kind IN ('objective_evidence','bm25_retrieval','embedding_retrieval','reranker','specialist','second_opinion','human_adjudication')), stage_fingerprint TEXT NOT NULL, attempt_ordinal INTEGER NOT NULL CHECK(attempt_ordinal BETWEEN 1 AND 100), started_at_us INTEGER NOT NULL CHECK(typeof(started_at_us)='integer' AND started_at_us BETWEEN -62135596800000000 AND 253402300799999999), UNIQUE(execution_id,metric_key,stage_ordinal,attempt_ordinal), CHECK(length(metric_question_fingerprint)=64 AND metric_question_fingerprint NOT GLOB '*[^0-9a-f]*'), CHECK(length(evidence_packet_fingerprint)=64 AND evidence_packet_fingerprint NOT GLOB '*[^0-9a-f]*'), CHECK(length(stage_fingerprint)=64 AND stage_fingerprint NOT GLOB '*[^0-9a-f]*'), CHECK((stage_ordinal=1 AND stage_kind='objective_evidence') OR (stage_ordinal=2 AND stage_kind='bm25_retrieval') OR (stage_ordinal=3 AND stage_kind='embedding_retrieval') OR (stage_ordinal=4 AND stage_kind='reranker') OR (stage_ordinal=5 AND stage_kind='specialist') OR (stage_ordinal=6 AND stage_kind='second_opinion') OR (stage_ordinal=7 AND stage_kind='human_adjudication'))
);
CREATE TABLE estimator_runtime_metric_observations (
    observation_id TEXT PRIMARY KEY CHECK(length(observation_id)=64 AND observation_id NOT GLOB '*[^0-9a-f]*'), execution_id TEXT NOT NULL REFERENCES estimator_runtime_executions(execution_id) ON DELETE CASCADE, authorization_id TEXT NOT NULL, attempt_id TEXT NOT NULL UNIQUE REFERENCES estimator_runtime_stage_attempts(attempt_id) ON DELETE CASCADE, metric_key TEXT NOT NULL, metric_question_fingerprint TEXT NOT NULL, evidence_packet_fingerprint TEXT NOT NULL, stage_ordinal INTEGER NOT NULL CHECK(stage_ordinal=1), state TEXT NOT NULL CHECK(state IN ('known','unknown','abstained','not_applicable','failed')), value_kind TEXT NOT NULL CHECK(value_kind IN ('continuous','fraction','binary','categorical')), numeric_value REAL CHECK(numeric_value IS NULL OR (typeof(numeric_value) IN ('real','integer') AND numeric_value BETWEEN -1.0e308 AND 1.0e308)), label_code TEXT, numerator INTEGER CHECK(numerator IS NULL OR (typeof(numerator)='integer' AND numerator>=0)), denominator INTEGER CHECK(denominator IS NULL OR (typeof(denominator)='integer' AND denominator>0)), reason_code TEXT, ref_count INTEGER NOT NULL CHECK(ref_count BETWEEN 0 AND 512), observed_at_us INTEGER NOT NULL CHECK(typeof(observed_at_us)='integer' AND observed_at_us BETWEEN -62135596800000000 AND 253402300799999999), observation_fingerprint TEXT NOT NULL UNIQUE, calibration_state TEXT NOT NULL CHECK(calibration_state='not_assessed'), execution_only INTEGER NOT NULL CHECK(execution_only=1), activation_allowed INTEGER NOT NULL CHECK(activation_allowed=0), product_metric_write_allowed INTEGER NOT NULL CHECK(product_metric_write_allowed=0), CHECK((state='known' AND reason_code IS NULL AND ((value_kind IN ('continuous','fraction') AND numeric_value IS NOT NULL AND label_code IS NULL) OR (value_kind IN ('binary','categorical') AND numeric_value IS NULL AND label_code IS NOT NULL))) OR (state<>'known' AND numeric_value IS NULL AND label_code IS NULL AND numerator IS NULL AND denominator IS NULL AND reason_code IS NOT NULL)), CHECK((numerator IS NULL)=(denominator IS NULL)), CHECK(numerator IS NULL OR (value_kind='fraction' AND numerator<=denominator AND abs(numeric_value-(1.0*numerator/denominator))<=0.000000001))
);
CREATE TABLE estimator_runtime_observation_refs (
    observation_id TEXT NOT NULL REFERENCES estimator_runtime_metric_observations(observation_id) ON DELETE CASCADE, execution_id TEXT NOT NULL, authorization_id TEXT NOT NULL, ordinal INTEGER NOT NULL CHECK(ordinal BETWEEN 0 AND 511), evidence_reference_id TEXT NOT NULL CHECK(length(evidence_reference_id)=64 AND evidence_reference_id NOT GLOB '*[^0-9a-f]*'), PRIMARY KEY(observation_id,ordinal), UNIQUE(observation_id,evidence_reference_id)
);
CREATE TABLE estimator_runtime_retrievals (
    retrieval_id TEXT PRIMARY KEY CHECK(length(retrieval_id)=64 AND retrieval_id NOT GLOB '*[^0-9a-f]*'), execution_id TEXT NOT NULL REFERENCES estimator_runtime_executions(execution_id) ON DELETE CASCADE, authorization_id TEXT NOT NULL, attempt_id TEXT NOT NULL UNIQUE REFERENCES estimator_runtime_stage_attempts(attempt_id) ON DELETE CASCADE, metric_key TEXT NOT NULL, metric_question_fingerprint TEXT NOT NULL, evidence_packet_fingerprint TEXT NOT NULL, stage_ordinal INTEGER NOT NULL CHECK(stage_ordinal=2), stage_kind TEXT NOT NULL CHECK(stage_kind='bm25_retrieval'), score_kind TEXT NOT NULL CHECK(score_kind='bm25_raw'), query_fingerprint TEXT NOT NULL, candidate_index_fingerprint TEXT NOT NULL, candidate_count INTEGER NOT NULL CHECK(candidate_count BETWEEN 0 AND 512), hit_count INTEGER NOT NULL CHECK(hit_count BETWEEN 0 AND 512 AND hit_count<=candidate_count), created_at_us INTEGER NOT NULL CHECK(typeof(created_at_us)='integer' AND created_at_us BETWEEN -62135596800000000 AND 253402300799999999), retrieval_fingerprint TEXT NOT NULL UNIQUE, calibration_state TEXT NOT NULL CHECK(calibration_state='not_assessed'), execution_only INTEGER NOT NULL CHECK(execution_only=1), activation_allowed INTEGER NOT NULL CHECK(activation_allowed=0)
);
CREATE TABLE estimator_runtime_retrieval_candidates (
    retrieval_id TEXT NOT NULL REFERENCES estimator_runtime_retrievals(retrieval_id) ON DELETE CASCADE, execution_id TEXT NOT NULL, authorization_id TEXT NOT NULL, ordinal INTEGER NOT NULL CHECK(ordinal BETWEEN 0 AND 511), evidence_reference_id TEXT NOT NULL CHECK(length(evidence_reference_id)=64 AND evidence_reference_id NOT GLOB '*[^0-9a-f]*'), PRIMARY KEY(retrieval_id,ordinal), UNIQUE(retrieval_id,evidence_reference_id)
);
CREATE TABLE estimator_runtime_retrieval_hits (
    retrieval_id TEXT NOT NULL REFERENCES estimator_runtime_retrievals(retrieval_id) ON DELETE CASCADE, execution_id TEXT NOT NULL, authorization_id TEXT NOT NULL, rank INTEGER NOT NULL CHECK(rank BETWEEN 1 AND 512), evidence_reference_id TEXT NOT NULL, raw_score REAL NOT NULL CHECK(typeof(raw_score) IN ('real','integer') AND raw_score BETWEEN -1.0e308 AND 1.0e308), PRIMARY KEY(retrieval_id,rank), UNIQUE(retrieval_id,evidence_reference_id)
);
CREATE TABLE estimator_runtime_stage_outcomes (
    outcome_id TEXT PRIMARY KEY CHECK(length(outcome_id)=64 AND outcome_id NOT GLOB '*[^0-9a-f]*'), attempt_id TEXT NOT NULL UNIQUE REFERENCES estimator_runtime_stage_attempts(attempt_id) ON DELETE CASCADE, execution_id TEXT NOT NULL REFERENCES estimator_runtime_executions(execution_id) ON DELETE CASCADE, authorization_id TEXT NOT NULL, state TEXT NOT NULL CHECK(state IN ('completed','failed','cancelled','interrupted')), reason_code TEXT NOT NULL CHECK(length(reason_code) BETWEEN 1 AND 128 AND reason_code GLOB '[a-z]*' AND reason_code NOT GLOB '*[^a-z0-9_.:-]*'), output_fingerprint TEXT, finished_at_us INTEGER NOT NULL CHECK(typeof(finished_at_us)='integer' AND finished_at_us BETWEEN -62135596800000000 AND 253402300799999999), CHECK((state='completed')=(output_fingerprint IS NOT NULL)), CHECK(output_fingerprint IS NULL OR (length(output_fingerprint)=64 AND output_fingerprint NOT GLOB '*[^0-9a-f]*'))
);
CREATE TABLE estimator_runtime_checkpoints (
    checkpoint_id TEXT PRIMARY KEY CHECK(length(checkpoint_id)=64 AND checkpoint_id NOT GLOB '*[^0-9a-f]*'), execution_id TEXT NOT NULL REFERENCES estimator_runtime_executions(execution_id) ON DELETE CASCADE, authorization_id TEXT NOT NULL, metric_key TEXT NOT NULL, sequence INTEGER NOT NULL CHECK(sequence BETWEEN 0 AND 1000000), previous_checkpoint_fingerprint TEXT, last_completed_stage_ordinal INTEGER NOT NULL CHECK(last_completed_stage_ordinal BETWEEN 0 AND 7), next_stage_ordinal INTEGER CHECK(next_stage_ordinal BETWEEN 1 AND 7), restart_generation INTEGER NOT NULL CHECK(restart_generation BETWEEN 0 AND 1000000), state TEXT NOT NULL CHECK(state IN ('created','running','partial','failed','cancelled','superseded')), reason_code TEXT NOT NULL CHECK(length(reason_code) BETWEEN 1 AND 128 AND reason_code GLOB '[a-z]*' AND reason_code NOT GLOB '*[^a-z0-9_.:-]*'), recorded_at_us INTEGER NOT NULL CHECK(typeof(recorded_at_us)='integer' AND recorded_at_us BETWEEN -62135596800000000 AND 253402300799999999), checkpoint_fingerprint TEXT NOT NULL UNIQUE, UNIQUE(execution_id,metric_key,sequence), CHECK((sequence=0)=(previous_checkpoint_fingerprint IS NULL)), CHECK((state IN ('partial','failed','cancelled','superseded'))=(next_stage_ordinal IS NULL)), CHECK(next_stage_ordinal IS NULL OR next_stage_ordinal=last_completed_stage_ordinal+1)
);
CREATE TABLE estimator_runtime_deletion_tombstones (
    revocation_key TEXT PRIMARY KEY CHECK(length(revocation_key)=64 AND revocation_key NOT GLOB '*[^0-9a-f]*'),
    retained_plan_fingerprint TEXT NOT NULL REFERENCES estimator_plans(plan_fingerprint),
    deleted_at_us INTEGER NOT NULL CHECK(typeof(deleted_at_us)='integer' AND deleted_at_us BETWEEN -62135596800000000 AND 253402300799999999)
);

-- Every runtime insert/delete requires the transient application HMAC row.
CREATE TRIGGER estimator_runtime_authorizations_insert_guard BEFORE INSERT ON estimator_runtime_authorizations WHEN NOT EXISTS (SELECT 1 FROM estimator_runtime_write_authorizations a WHERE a.authorization_id=NEW.authorization_id AND a.execution_id=NEW.execution_id AND a.authorization_tag=estimator_runtime_authorization_tag(a.operation_id,a.authorization_id,a.execution_id,a.job_id)) BEGIN SELECT RAISE(ABORT,'estimator runtime append is not authorized'); END;
CREATE TRIGGER estimator_runtime_authorizations_update_guard BEFORE UPDATE ON estimator_runtime_authorizations BEGIN SELECT RAISE(ABORT,'estimator runtime authorization is immutable'); END;
CREATE TRIGGER estimator_runtime_authorizations_delete_guard BEFORE DELETE ON estimator_runtime_authorizations WHEN NOT EXISTS (SELECT 1 FROM estimator_runtime_write_authorizations a WHERE a.authorization_id=OLD.authorization_id AND a.execution_id=OLD.execution_id AND a.authorization_tag=estimator_runtime_authorization_tag(a.operation_id,a.authorization_id,a.execution_id,a.job_id)) BEGIN SELECT RAISE(ABORT,'estimator runtime delete is not authorized'); END;
CREATE TRIGGER estimator_runtime_packets_insert_guard BEFORE INSERT ON estimator_runtime_authorization_packets WHEN NOT EXISTS (SELECT 1 FROM estimator_runtime_write_authorizations a WHERE a.authorization_id=NEW.authorization_id AND a.execution_id=NEW.execution_id AND a.authorization_tag=estimator_runtime_authorization_tag(a.operation_id,a.authorization_id,a.execution_id,a.job_id)) BEGIN SELECT RAISE(ABORT,'estimator runtime append is not authorized'); END;
CREATE TRIGGER estimator_runtime_consumption_insert_guard BEFORE INSERT ON estimator_runtime_authorization_consumptions WHEN NOT EXISTS (SELECT 1 FROM estimator_runtime_write_authorizations a WHERE a.authorization_id=NEW.authorization_id AND a.execution_id=NEW.execution_id AND a.authorization_tag=estimator_runtime_authorization_tag(a.operation_id,a.authorization_id,a.execution_id,a.job_id)) BEGIN SELECT RAISE(ABORT,'estimator runtime append is not authorized'); END;
CREATE TRIGGER estimator_runtime_revocation_insert_guard BEFORE INSERT ON estimator_runtime_authorization_revocations WHEN NOT EXISTS (SELECT 1 FROM estimator_runtime_write_authorizations a WHERE a.authorization_id=NEW.authorization_id AND a.execution_id=NEW.execution_id AND a.authorization_tag=estimator_runtime_authorization_tag(a.operation_id,a.authorization_id,a.execution_id,a.job_id)) BEGIN SELECT RAISE(ABORT,'estimator runtime append is not authorized'); END;
CREATE TRIGGER estimator_runtime_executions_insert_guard BEFORE INSERT ON estimator_runtime_executions WHEN NOT EXISTS (SELECT 1 FROM estimator_runtime_write_authorizations a WHERE a.authorization_id=NEW.authorization_id AND a.execution_id=NEW.execution_id AND a.authorization_tag=estimator_runtime_authorization_tag(a.operation_id,a.authorization_id,a.execution_id,a.job_id)) BEGIN SELECT RAISE(ABORT,'estimator runtime append is not authorized'); END;
CREATE TRIGGER estimator_runtime_bindings_insert_guard BEFORE INSERT ON estimator_runtime_job_bindings WHEN NOT EXISTS (SELECT 1 FROM estimator_runtime_write_authorizations a WHERE a.authorization_id=NEW.authorization_id AND a.execution_id=NEW.execution_id AND a.authorization_tag=estimator_runtime_authorization_tag(a.operation_id,a.authorization_id,a.execution_id,a.job_id)) BEGIN SELECT RAISE(ABORT,'estimator runtime append is not authorized'); END;
CREATE TRIGGER estimator_runtime_bindings_validate_seal BEFORE INSERT ON estimator_runtime_job_bindings WHEN
    NOT EXISTS (SELECT 1 FROM estimator_runtime_authorizations a WHERE a.authorization_id=NEW.authorization_id AND a.execution_id=NEW.execution_id AND a.job_id=NEW.job_id AND a.authorization_fingerprint=NEW.authorization_fingerprint AND a.plan_fingerprint=NEW.plan_fingerprint AND a.route=NEW.route AND a.provider=NEW.provider AND a.project_id=NEW.project_id AND a.session_id=NEW.session_id AND a.session_revision_id=NEW.session_revision_id AND a.window_fingerprint=NEW.window_fingerprint AND a.input_fingerprint=NEW.input_fingerprint AND a.provenance_fingerprint=NEW.provenance_fingerprint)
    OR NOT EXISTS (SELECT 1 FROM estimator_runtime_executions e WHERE e.execution_id=NEW.execution_id AND e.authorization_id=NEW.authorization_id AND e.job_id=NEW.job_id AND e.plan_fingerprint=NEW.plan_fingerprint)
    OR (SELECT packet_count FROM estimator_runtime_authorizations WHERE authorization_id=NEW.authorization_id)<>(SELECT COUNT(*) FROM estimator_runtime_packet_receipts WHERE execution_id=NEW.execution_id)
    OR (SELECT packet_count FROM estimator_runtime_authorizations WHERE authorization_id=NEW.authorization_id)<>(SELECT COUNT(*) FROM analysis_job_metrics WHERE job_id=NEW.job_id)
    OR EXISTS (SELECT 1 FROM estimator_runtime_authorization_packets ap WHERE ap.authorization_id=NEW.authorization_id AND NOT EXISTS (SELECT 1 FROM estimator_runtime_packet_receipts p WHERE p.execution_id=NEW.execution_id AND p.metric_key=ap.metric_key AND p.metric_question_fingerprint=ap.metric_question_fingerprint AND p.packet_fingerprint=ap.evidence_packet_fingerprint))
    OR EXISTS (SELECT 1 FROM estimator_runtime_authorization_packets ap WHERE ap.authorization_id=NEW.authorization_id AND NOT EXISTS (SELECT 1 FROM analysis_job_metrics jm WHERE jm.job_id=NEW.job_id AND jm.metric_key=ap.metric_key AND jm.ordinal=ap.ordinal))
    OR EXISTS (SELECT 1 FROM analysis_job_metrics jm WHERE jm.job_id=NEW.job_id AND NOT EXISTS (SELECT 1 FROM estimator_runtime_authorization_packets ap WHERE ap.authorization_id=NEW.authorization_id AND ap.metric_key=jm.metric_key AND ap.ordinal=jm.ordinal))
    OR EXISTS (SELECT 1 FROM estimator_runtime_packet_receipts p WHERE p.execution_id=NEW.execution_id AND p.evidence_ref_count<>(SELECT COUNT(*) FROM estimator_runtime_packet_refs r WHERE r.execution_id=p.execution_id AND r.packet_fingerprint=p.packet_fingerprint))
BEGIN SELECT RAISE(ABORT,'estimator runtime launch seal is inconsistent'); END;
CREATE TRIGGER estimator_runtime_receipts_insert_guard BEFORE INSERT ON estimator_runtime_packet_receipts WHEN NOT EXISTS (SELECT 1 FROM estimator_runtime_write_authorizations a WHERE a.authorization_id=NEW.authorization_id AND a.execution_id=NEW.execution_id AND a.authorization_tag=estimator_runtime_authorization_tag(a.operation_id,a.authorization_id,a.execution_id,a.job_id)) BEGIN SELECT RAISE(ABORT,'estimator runtime append is not authorized'); END;
CREATE TRIGGER estimator_runtime_refs_insert_guard BEFORE INSERT ON estimator_runtime_packet_refs WHEN NOT EXISTS (SELECT 1 FROM estimator_runtime_write_authorizations a WHERE a.authorization_id=NEW.authorization_id AND a.execution_id=NEW.execution_id AND a.authorization_tag=estimator_runtime_authorization_tag(a.operation_id,a.authorization_id,a.execution_id,a.job_id)) BEGIN SELECT RAISE(ABORT,'estimator runtime append is not authorized'); END;
CREATE TRIGGER estimator_runtime_states_insert_guard BEFORE INSERT ON estimator_runtime_state_receipts WHEN NOT EXISTS (SELECT 1 FROM estimator_runtime_write_authorizations a WHERE a.authorization_id=NEW.authorization_id AND a.execution_id=NEW.execution_id AND a.authorization_tag=estimator_runtime_authorization_tag(a.operation_id,a.authorization_id,a.execution_id,a.job_id)) BEGIN SELECT RAISE(ABORT,'estimator runtime append is not authorized'); END;
CREATE TRIGGER estimator_runtime_attempts_insert_guard BEFORE INSERT ON estimator_runtime_stage_attempts WHEN NOT EXISTS (SELECT 1 FROM estimator_runtime_write_authorizations a WHERE a.authorization_id=NEW.authorization_id AND a.execution_id=NEW.execution_id AND a.authorization_tag=estimator_runtime_authorization_tag(a.operation_id,a.authorization_id,a.execution_id,a.job_id)) BEGIN SELECT RAISE(ABORT,'estimator runtime append is not authorized'); END;
CREATE TRIGGER estimator_runtime_observations_insert_guard BEFORE INSERT ON estimator_runtime_metric_observations WHEN NOT EXISTS (SELECT 1 FROM estimator_runtime_write_authorizations a WHERE a.authorization_id=NEW.authorization_id AND a.execution_id=NEW.execution_id AND a.authorization_tag=estimator_runtime_authorization_tag(a.operation_id,a.authorization_id,a.execution_id,a.job_id)) BEGIN SELECT RAISE(ABORT,'estimator runtime append is not authorized'); END;
CREATE TRIGGER estimator_runtime_observation_refs_insert_guard BEFORE INSERT ON estimator_runtime_observation_refs WHEN NOT EXISTS (SELECT 1 FROM estimator_runtime_write_authorizations a WHERE a.authorization_id=NEW.authorization_id AND a.execution_id=NEW.execution_id AND a.authorization_tag=estimator_runtime_authorization_tag(a.operation_id,a.authorization_id,a.execution_id,a.job_id)) BEGIN SELECT RAISE(ABORT,'estimator runtime append is not authorized'); END;
CREATE TRIGGER estimator_runtime_retrievals_insert_guard BEFORE INSERT ON estimator_runtime_retrievals WHEN NOT EXISTS (SELECT 1 FROM estimator_runtime_write_authorizations a WHERE a.authorization_id=NEW.authorization_id AND a.execution_id=NEW.execution_id AND a.authorization_tag=estimator_runtime_authorization_tag(a.operation_id,a.authorization_id,a.execution_id,a.job_id)) BEGIN SELECT RAISE(ABORT,'estimator runtime append is not authorized'); END;
CREATE TRIGGER estimator_runtime_candidates_insert_guard BEFORE INSERT ON estimator_runtime_retrieval_candidates WHEN NOT EXISTS (SELECT 1 FROM estimator_runtime_write_authorizations a WHERE a.authorization_id=NEW.authorization_id AND a.execution_id=NEW.execution_id AND a.authorization_tag=estimator_runtime_authorization_tag(a.operation_id,a.authorization_id,a.execution_id,a.job_id)) BEGIN SELECT RAISE(ABORT,'estimator runtime append is not authorized'); END;
CREATE TRIGGER estimator_runtime_hits_insert_guard BEFORE INSERT ON estimator_runtime_retrieval_hits WHEN NOT EXISTS (SELECT 1 FROM estimator_runtime_write_authorizations a WHERE a.authorization_id=NEW.authorization_id AND a.execution_id=NEW.execution_id AND a.authorization_tag=estimator_runtime_authorization_tag(a.operation_id,a.authorization_id,a.execution_id,a.job_id)) BEGIN SELECT RAISE(ABORT,'estimator runtime append is not authorized'); END;
CREATE TRIGGER estimator_runtime_outcomes_insert_guard BEFORE INSERT ON estimator_runtime_stage_outcomes WHEN NOT EXISTS (SELECT 1 FROM estimator_runtime_write_authorizations a WHERE a.authorization_id=NEW.authorization_id AND a.execution_id=NEW.execution_id AND a.authorization_tag=estimator_runtime_authorization_tag(a.operation_id,a.authorization_id,a.execution_id,a.job_id)) BEGIN SELECT RAISE(ABORT,'estimator runtime append is not authorized'); END;
CREATE TRIGGER estimator_runtime_checkpoints_insert_guard BEFORE INSERT ON estimator_runtime_checkpoints WHEN NOT EXISTS (SELECT 1 FROM estimator_runtime_write_authorizations a WHERE a.authorization_id=NEW.authorization_id AND a.execution_id=NEW.execution_id AND a.authorization_tag=estimator_runtime_authorization_tag(a.operation_id,a.authorization_id,a.execution_id,a.job_id)) BEGIN SELECT RAISE(ABORT,'estimator runtime append is not authorized'); END;
CREATE TRIGGER estimator_runtime_packet_receipts_sealed BEFORE INSERT ON estimator_runtime_packet_receipts WHEN EXISTS (SELECT 1 FROM estimator_runtime_job_bindings b WHERE b.execution_id=NEW.execution_id) BEGIN SELECT RAISE(ABORT,'estimator runtime packet set is sealed'); END;
CREATE TRIGGER estimator_runtime_packet_refs_sealed BEFORE INSERT ON estimator_runtime_packet_refs WHEN EXISTS (SELECT 1 FROM estimator_runtime_job_bindings b WHERE b.execution_id=NEW.execution_id) BEGIN SELECT RAISE(ABORT,'estimator runtime packet set is sealed'); END;
CREATE TRIGGER estimator_runtime_tombstone_insert_guard BEFORE INSERT ON estimator_runtime_deletion_tombstones WHEN NOT EXISTS (SELECT 1 FROM estimator_runtime_write_authorizations a WHERE a.authorization_tag=estimator_runtime_authorization_tag(a.operation_id,a.authorization_id,a.execution_id,a.job_id)) BEGIN SELECT RAISE(ABORT,'estimator runtime deletion is not authorized'); END;

-- Repository capabilities authorize a write, while these relational seals
-- independently prove that every normalized child belongs to the same exact
-- execution/authorization/packet lineage.
CREATE TRIGGER estimator_runtime_states_validate_lineage BEFORE INSERT ON estimator_runtime_state_receipts
WHEN NOT EXISTS (SELECT 1 FROM estimator_runtime_executions e WHERE e.execution_id=NEW.execution_id AND e.authorization_id=NEW.authorization_id)
BEGIN SELECT RAISE(ABORT,'estimator runtime state lineage is inconsistent'); END;
CREATE TRIGGER estimator_runtime_attempts_validate_lineage BEFORE INSERT ON estimator_runtime_stage_attempts
WHEN NOT EXISTS (SELECT 1 FROM estimator_runtime_executions e WHERE e.execution_id=NEW.execution_id AND e.authorization_id=NEW.authorization_id)
 OR NOT EXISTS (SELECT 1 FROM estimator_runtime_packet_receipts p WHERE p.execution_id=NEW.execution_id AND p.authorization_id=NEW.authorization_id AND p.metric_key=NEW.metric_key AND p.metric_question_fingerprint=NEW.metric_question_fingerprint AND p.packet_fingerprint=NEW.evidence_packet_fingerprint)
BEGIN SELECT RAISE(ABORT,'estimator runtime attempt lineage is inconsistent'); END;
CREATE TRIGGER estimator_runtime_observations_validate_lineage BEFORE INSERT ON estimator_runtime_metric_observations
WHEN NOT EXISTS (SELECT 1 FROM estimator_runtime_stage_attempts a WHERE a.attempt_id=NEW.attempt_id AND a.execution_id=NEW.execution_id AND a.authorization_id=NEW.authorization_id AND a.metric_key=NEW.metric_key AND a.metric_question_fingerprint=NEW.metric_question_fingerprint AND a.evidence_packet_fingerprint=NEW.evidence_packet_fingerprint AND a.stage_ordinal=1)
BEGIN SELECT RAISE(ABORT,'estimator runtime observation lineage is inconsistent'); END;
CREATE TRIGGER estimator_runtime_observation_refs_validate_lineage BEFORE INSERT ON estimator_runtime_observation_refs
WHEN NOT EXISTS (SELECT 1 FROM estimator_runtime_metric_observations o WHERE o.observation_id=NEW.observation_id AND o.execution_id=NEW.execution_id AND o.authorization_id=NEW.authorization_id)
BEGIN SELECT RAISE(ABORT,'estimator runtime observation reference lineage is inconsistent'); END;
CREATE TRIGGER estimator_runtime_retrievals_validate_lineage BEFORE INSERT ON estimator_runtime_retrievals
WHEN NOT EXISTS (SELECT 1 FROM estimator_runtime_stage_attempts a WHERE a.attempt_id=NEW.attempt_id AND a.execution_id=NEW.execution_id AND a.authorization_id=NEW.authorization_id AND a.metric_key=NEW.metric_key AND a.metric_question_fingerprint=NEW.metric_question_fingerprint AND a.evidence_packet_fingerprint=NEW.evidence_packet_fingerprint AND a.stage_ordinal=2)
BEGIN SELECT RAISE(ABORT,'estimator runtime retrieval lineage is inconsistent'); END;
CREATE TRIGGER estimator_runtime_candidates_validate_lineage BEFORE INSERT ON estimator_runtime_retrieval_candidates
WHEN NOT EXISTS (SELECT 1 FROM estimator_runtime_retrievals r WHERE r.retrieval_id=NEW.retrieval_id AND r.execution_id=NEW.execution_id AND r.authorization_id=NEW.authorization_id)
BEGIN SELECT RAISE(ABORT,'estimator runtime candidate lineage is inconsistent'); END;
CREATE TRIGGER estimator_runtime_hits_validate_lineage BEFORE INSERT ON estimator_runtime_retrieval_hits
WHEN NOT EXISTS (SELECT 1 FROM estimator_runtime_retrievals r WHERE r.retrieval_id=NEW.retrieval_id AND r.execution_id=NEW.execution_id AND r.authorization_id=NEW.authorization_id)
 OR NOT EXISTS (SELECT 1 FROM estimator_runtime_retrieval_candidates c WHERE c.retrieval_id=NEW.retrieval_id AND c.execution_id=NEW.execution_id AND c.authorization_id=NEW.authorization_id AND c.evidence_reference_id=NEW.evidence_reference_id)
BEGIN SELECT RAISE(ABORT,'estimator runtime hit lineage is inconsistent'); END;
CREATE TRIGGER estimator_runtime_outcomes_validate_lineage BEFORE INSERT ON estimator_runtime_stage_outcomes
WHEN NOT EXISTS (SELECT 1 FROM estimator_runtime_stage_attempts a WHERE a.attempt_id=NEW.attempt_id AND a.execution_id=NEW.execution_id AND a.authorization_id=NEW.authorization_id)
 OR (NEW.state='completed' AND NOT EXISTS (
      SELECT 1 FROM estimator_runtime_metric_observations o
      WHERE o.attempt_id=NEW.attempt_id AND o.observation_fingerprint=NEW.output_fingerprint
        AND o.ref_count=(SELECT COUNT(*) FROM estimator_runtime_observation_refs x WHERE x.observation_id=o.observation_id)
      UNION ALL
      SELECT 1 FROM estimator_runtime_retrievals r
      WHERE r.attempt_id=NEW.attempt_id AND r.retrieval_fingerprint=NEW.output_fingerprint
        AND r.candidate_count=(SELECT COUNT(*) FROM estimator_runtime_retrieval_candidates c WHERE c.retrieval_id=r.retrieval_id)
        AND r.hit_count=(SELECT COUNT(*) FROM estimator_runtime_retrieval_hits h WHERE h.retrieval_id=r.retrieval_id)))
BEGIN SELECT RAISE(ABORT,'estimator runtime outcome lineage or child counts are inconsistent'); END;
CREATE TRIGGER estimator_runtime_checkpoints_validate_lineage BEFORE INSERT ON estimator_runtime_checkpoints
WHEN NOT EXISTS (SELECT 1 FROM estimator_runtime_executions e WHERE e.execution_id=NEW.execution_id AND e.authorization_id=NEW.authorization_id)
 OR NOT EXISTS (SELECT 1 FROM estimator_runtime_packet_receipts p WHERE p.execution_id=NEW.execution_id AND p.authorization_id=NEW.authorization_id AND p.metric_key=NEW.metric_key)
BEGIN SELECT RAISE(ABORT,'estimator runtime checkpoint lineage is inconsistent'); END;

CREATE TRIGGER estimator_runtime_receipts_safe_metadata BEFORE INSERT ON estimator_runtime_packet_receipts
WHEN NEW.packet_schema_version NOT GLOB '[A-Za-z0-9]*' OR NEW.packet_schema_version GLOB '*[^A-Za-z0-9._+-]*'
 OR NEW.adapter_version NOT GLOB '[A-Za-z0-9]*' OR NEW.adapter_version GLOB '*[^A-Za-z0-9._+-]*'
 OR NEW.provider_schema_version NOT GLOB '[A-Za-z0-9]*' OR NEW.provider_schema_version GLOB '*[^A-Za-z0-9._+-]*'
 OR NEW.preprocessing_version NOT GLOB '[A-Za-z0-9]*' OR NEW.preprocessing_version GLOB '*[^A-Za-z0-9._+-]*'
 OR NEW.router_version NOT GLOB '[A-Za-z0-9]*' OR NEW.router_version GLOB '*[^A-Za-z0-9._+-]*'
 OR NEW.redactor_version NOT GLOB '[A-Za-z0-9]*' OR NEW.redactor_version GLOB '*[^A-Za-z0-9._+-]*'
 OR instr(NEW.packet_schema_version,'..')>0 OR instr(NEW.adapter_version,'..')>0
 OR instr(NEW.provider_schema_version,'..')>0 OR instr(NEW.preprocessing_version,'..')>0
 OR instr(NEW.router_version,'..')>0 OR instr(NEW.redactor_version,'..')>0
 OR instr(NEW.packet_schema_version,'://')>0 OR instr(NEW.adapter_version,'://')>0
 OR instr(NEW.provider_schema_version,'://')>0 OR instr(NEW.preprocessing_version,'://')>0
 OR instr(NEW.router_version,'://')>0 OR instr(NEW.redactor_version,'://')>0
 OR NEW.packet_schema_version GLOB '[A-Za-z]:*' OR NEW.adapter_version GLOB '[A-Za-z]:*'
 OR NEW.provider_schema_version GLOB '[A-Za-z]:*' OR NEW.preprocessing_version GLOB '[A-Za-z]:*'
 OR NEW.router_version GLOB '[A-Za-z]:*' OR NEW.redactor_version GLOB '[A-Za-z]:*'
BEGIN SELECT RAISE(ABORT,'estimator runtime metadata must be content-free'); END;
CREATE TRIGGER estimator_runtime_observations_safe_codes BEFORE INSERT ON estimator_runtime_metric_observations
WHEN NEW.observation_fingerprint IS NULL OR length(NEW.observation_fingerprint)<>64 OR NEW.observation_fingerprint GLOB '*[^0-9a-f]*'
 OR (NEW.label_code IS NOT NULL AND (length(NEW.label_code) NOT BETWEEN 1 AND 128 OR NEW.label_code NOT GLOB '[a-z]*' OR NEW.label_code GLOB '*[^a-z0-9_.:-]*'))
 OR (NEW.reason_code IS NOT NULL AND (length(NEW.reason_code) NOT BETWEEN 1 AND 128 OR NEW.reason_code NOT GLOB '[a-z]*' OR NEW.reason_code GLOB '*[^a-z0-9_.:-]*'))
BEGIN SELECT RAISE(ABORT,'estimator runtime observation codes are invalid'); END;
CREATE TRIGGER estimator_runtime_retrievals_safe_digests BEFORE INSERT ON estimator_runtime_retrievals
WHEN length(NEW.query_fingerprint)<>64 OR NEW.query_fingerprint GLOB '*[^0-9a-f]*'
 OR length(NEW.candidate_index_fingerprint)<>64 OR NEW.candidate_index_fingerprint GLOB '*[^0-9a-f]*'
 OR length(NEW.retrieval_fingerprint)<>64 OR NEW.retrieval_fingerprint GLOB '*[^0-9a-f]*'
BEGIN SELECT RAISE(ABORT,'estimator runtime retrieval digests are invalid'); END;

CREATE TRIGGER estimator_runtime_packets_no_mutation BEFORE UPDATE ON estimator_runtime_authorization_packets BEGIN SELECT RAISE(ABORT,'estimator runtime receipt is immutable'); END;
CREATE TRIGGER estimator_runtime_consumptions_no_mutation BEFORE UPDATE ON estimator_runtime_authorization_consumptions BEGIN SELECT RAISE(ABORT,'estimator runtime receipt is immutable'); END;
CREATE TRIGGER estimator_runtime_revocations_no_mutation BEFORE UPDATE ON estimator_runtime_authorization_revocations BEGIN SELECT RAISE(ABORT,'estimator runtime receipt is immutable'); END;
CREATE TRIGGER estimator_runtime_executions_no_mutation BEFORE UPDATE ON estimator_runtime_executions BEGIN SELECT RAISE(ABORT,'estimator runtime receipt is immutable'); END;
CREATE TRIGGER estimator_runtime_bindings_no_mutation BEFORE UPDATE ON estimator_runtime_job_bindings BEGIN SELECT RAISE(ABORT,'estimator runtime receipt is immutable'); END;
CREATE TRIGGER estimator_runtime_packet_receipts_no_mutation BEFORE UPDATE ON estimator_runtime_packet_receipts BEGIN SELECT RAISE(ABORT,'estimator runtime receipt is immutable'); END;
CREATE TRIGGER estimator_runtime_packet_refs_no_mutation BEFORE UPDATE ON estimator_runtime_packet_refs BEGIN SELECT RAISE(ABORT,'estimator runtime receipt is immutable'); END;
CREATE TRIGGER estimator_runtime_states_no_mutation BEFORE UPDATE ON estimator_runtime_state_receipts BEGIN SELECT RAISE(ABORT,'estimator runtime receipt is immutable'); END;
CREATE TRIGGER estimator_runtime_attempts_no_mutation BEFORE UPDATE ON estimator_runtime_stage_attempts BEGIN SELECT RAISE(ABORT,'estimator runtime receipt is immutable'); END;
CREATE TRIGGER estimator_runtime_observations_no_mutation BEFORE UPDATE ON estimator_runtime_metric_observations BEGIN SELECT RAISE(ABORT,'estimator runtime receipt is immutable'); END;
CREATE TRIGGER estimator_runtime_observation_refs_no_mutation BEFORE UPDATE ON estimator_runtime_observation_refs BEGIN SELECT RAISE(ABORT,'estimator runtime receipt is immutable'); END;
CREATE TRIGGER estimator_runtime_retrievals_no_mutation BEFORE UPDATE ON estimator_runtime_retrievals BEGIN SELECT RAISE(ABORT,'estimator runtime receipt is immutable'); END;
CREATE TRIGGER estimator_runtime_candidates_no_mutation BEFORE UPDATE ON estimator_runtime_retrieval_candidates BEGIN SELECT RAISE(ABORT,'estimator runtime receipt is immutable'); END;
CREATE TRIGGER estimator_runtime_hits_no_mutation BEFORE UPDATE ON estimator_runtime_retrieval_hits BEGIN SELECT RAISE(ABORT,'estimator runtime receipt is immutable'); END;
CREATE TRIGGER estimator_runtime_outcomes_no_mutation BEFORE UPDATE ON estimator_runtime_stage_outcomes BEGIN SELECT RAISE(ABORT,'estimator runtime receipt is immutable'); END;
CREATE TRIGGER estimator_runtime_checkpoints_no_mutation BEFORE UPDATE ON estimator_runtime_checkpoints BEGIN SELECT RAISE(ABORT,'estimator runtime receipt is immutable'); END;
CREATE TRIGGER estimator_runtime_tombstones_no_mutation BEFORE UPDATE ON estimator_runtime_deletion_tombstones BEGIN SELECT RAISE(ABORT,'estimator runtime tombstone is immutable'); END;
CREATE TRIGGER estimator_runtime_tombstones_no_delete BEFORE DELETE ON estimator_runtime_deletion_tombstones BEGIN SELECT RAISE(ABORT,'estimator runtime tombstone cannot be deleted'); END;

-- Estimator queue roots and their selected metric set are writable only while
-- the private runtime capability is live.  Public/generic queue paths never
-- obtain this capability, and a binding seals the exact metric set forever.
CREATE TRIGGER analysis_jobs_runtime_insert_guard BEFORE INSERT ON analysis_jobs
WHEN NEW.kind='estimator_execution' AND NOT EXISTS (
    SELECT 1 FROM estimator_runtime_write_authorizations a
    WHERE a.job_id=NEW.job_id)
BEGIN SELECT RAISE(ABORT,'estimator execution requires atomic runtime launch'); END;
CREATE TRIGGER analysis_jobs_runtime_delete_guard BEFORE DELETE ON analysis_jobs
WHEN OLD.kind='estimator_execution' AND NOT EXISTS (
    SELECT 1 FROM estimator_runtime_write_authorizations a
    JOIN estimator_runtime_authorizations r
      ON r.authorization_id=a.authorization_id AND r.execution_id=a.execution_id
    WHERE a.job_id=OLD.job_id AND r.job_id=OLD.job_id)
BEGIN SELECT RAISE(ABORT,'estimator execution delete is not authorized'); END;
CREATE TRIGGER analysis_job_metrics_runtime_insert_guard BEFORE INSERT ON analysis_job_metrics
WHEN (SELECT kind FROM analysis_jobs WHERE job_id=NEW.job_id)='estimator_execution'
 AND (EXISTS (SELECT 1 FROM estimator_runtime_job_bindings WHERE job_id=NEW.job_id)
      OR NOT EXISTS (
        SELECT 1 FROM estimator_runtime_authorizations r
        JOIN estimator_runtime_write_authorizations a
          ON a.authorization_id=r.authorization_id AND a.execution_id=r.execution_id
        WHERE a.job_id=NEW.job_id AND r.job_id=NEW.job_id))
BEGIN SELECT RAISE(ABORT,'estimator execution metric set is sealed'); END;
CREATE TRIGGER analysis_job_metrics_runtime_delete_guard BEFORE DELETE ON analysis_job_metrics
WHEN (SELECT kind FROM analysis_jobs WHERE job_id=OLD.job_id)='estimator_execution'
 AND NOT EXISTS (
    SELECT 1 FROM estimator_runtime_authorizations r
    JOIN estimator_runtime_write_authorizations a
      ON a.authorization_id=r.authorization_id AND a.execution_id=r.execution_id
    WHERE a.job_id=OLD.job_id AND r.job_id=OLD.job_id)
BEGIN SELECT RAISE(ABORT,'estimator execution metric delete is not authorized'); END;
CREATE TRIGGER analysis_jobs_runtime_terminal_seal BEFORE UPDATE OF state ON analysis_jobs
WHEN OLD.kind='estimator_execution'
 AND NEW.state IN ('partial','failed','cancelled','superseded')
 AND NOT EXISTS (
    SELECT 1 FROM estimator_runtime_job_bindings b
    JOIN estimator_runtime_state_receipts s ON s.execution_id=b.execution_id
    WHERE b.job_id=OLD.job_id AND s.sequence=(
        SELECT MAX(latest.sequence) FROM estimator_runtime_state_receipts latest
        WHERE latest.execution_id=b.execution_id)
      AND s.state=NEW.state AND s.reason_code=NEW.terminal_reason_code)
BEGIN SELECT RAISE(ABORT,'estimator queue terminal state lacks exact runtime receipt'); END;

CREATE TRIGGER estimator_runtime_packets_delete_guard BEFORE DELETE ON estimator_runtime_authorization_packets WHEN NOT EXISTS (SELECT 1 FROM estimator_runtime_write_authorizations a WHERE a.authorization_id=OLD.authorization_id AND a.execution_id=OLD.execution_id AND a.authorization_tag=estimator_runtime_authorization_tag(a.operation_id,a.authorization_id,a.execution_id,a.job_id)) BEGIN SELECT RAISE(ABORT,'estimator runtime delete is not authorized'); END;
CREATE TRIGGER estimator_runtime_consumptions_delete_guard BEFORE DELETE ON estimator_runtime_authorization_consumptions WHEN NOT EXISTS (SELECT 1 FROM estimator_runtime_write_authorizations a WHERE a.authorization_id=OLD.authorization_id AND a.execution_id=OLD.execution_id AND a.authorization_tag=estimator_runtime_authorization_tag(a.operation_id,a.authorization_id,a.execution_id,a.job_id)) BEGIN SELECT RAISE(ABORT,'estimator runtime delete is not authorized'); END;
CREATE TRIGGER estimator_runtime_revocations_delete_guard BEFORE DELETE ON estimator_runtime_authorization_revocations WHEN NOT EXISTS (SELECT 1 FROM estimator_runtime_write_authorizations a WHERE a.authorization_id=OLD.authorization_id AND a.execution_id=OLD.execution_id AND a.authorization_tag=estimator_runtime_authorization_tag(a.operation_id,a.authorization_id,a.execution_id,a.job_id)) BEGIN SELECT RAISE(ABORT,'estimator runtime delete is not authorized'); END;
CREATE TRIGGER estimator_runtime_executions_delete_guard BEFORE DELETE ON estimator_runtime_executions WHEN NOT EXISTS (SELECT 1 FROM estimator_runtime_write_authorizations a WHERE a.authorization_id=OLD.authorization_id AND a.execution_id=OLD.execution_id AND a.authorization_tag=estimator_runtime_authorization_tag(a.operation_id,a.authorization_id,a.execution_id,a.job_id)) BEGIN SELECT RAISE(ABORT,'estimator runtime delete is not authorized'); END;
CREATE TRIGGER estimator_runtime_bindings_delete_guard BEFORE DELETE ON estimator_runtime_job_bindings WHEN NOT EXISTS (SELECT 1 FROM estimator_runtime_write_authorizations a WHERE a.authorization_id=OLD.authorization_id AND a.execution_id=OLD.execution_id AND a.authorization_tag=estimator_runtime_authorization_tag(a.operation_id,a.authorization_id,a.execution_id,a.job_id)) BEGIN SELECT RAISE(ABORT,'estimator runtime delete is not authorized'); END;
CREATE TRIGGER estimator_runtime_receipts_delete_guard BEFORE DELETE ON estimator_runtime_packet_receipts WHEN NOT EXISTS (SELECT 1 FROM estimator_runtime_write_authorizations a WHERE a.authorization_id=OLD.authorization_id AND a.execution_id=OLD.execution_id AND a.authorization_tag=estimator_runtime_authorization_tag(a.operation_id,a.authorization_id,a.execution_id,a.job_id)) BEGIN SELECT RAISE(ABORT,'estimator runtime delete is not authorized'); END;
CREATE TRIGGER estimator_runtime_refs_delete_guard BEFORE DELETE ON estimator_runtime_packet_refs WHEN NOT EXISTS (SELECT 1 FROM estimator_runtime_write_authorizations a WHERE a.authorization_id=OLD.authorization_id AND a.execution_id=OLD.execution_id AND a.authorization_tag=estimator_runtime_authorization_tag(a.operation_id,a.authorization_id,a.execution_id,a.job_id)) BEGIN SELECT RAISE(ABORT,'estimator runtime delete is not authorized'); END;
CREATE TRIGGER estimator_runtime_states_delete_guard BEFORE DELETE ON estimator_runtime_state_receipts WHEN NOT EXISTS (SELECT 1 FROM estimator_runtime_write_authorizations a WHERE a.authorization_id=OLD.authorization_id AND a.execution_id=OLD.execution_id AND a.authorization_tag=estimator_runtime_authorization_tag(a.operation_id,a.authorization_id,a.execution_id,a.job_id)) BEGIN SELECT RAISE(ABORT,'estimator runtime delete is not authorized'); END;
CREATE TRIGGER estimator_runtime_attempts_delete_guard BEFORE DELETE ON estimator_runtime_stage_attempts WHEN NOT EXISTS (SELECT 1 FROM estimator_runtime_write_authorizations a WHERE a.authorization_id=OLD.authorization_id AND a.execution_id=OLD.execution_id AND a.authorization_tag=estimator_runtime_authorization_tag(a.operation_id,a.authorization_id,a.execution_id,a.job_id)) BEGIN SELECT RAISE(ABORT,'estimator runtime delete is not authorized'); END;
CREATE TRIGGER estimator_runtime_observations_delete_guard BEFORE DELETE ON estimator_runtime_metric_observations WHEN NOT EXISTS (SELECT 1 FROM estimator_runtime_write_authorizations a WHERE a.authorization_id=OLD.authorization_id AND a.execution_id=OLD.execution_id AND a.authorization_tag=estimator_runtime_authorization_tag(a.operation_id,a.authorization_id,a.execution_id,a.job_id)) BEGIN SELECT RAISE(ABORT,'estimator runtime delete is not authorized'); END;
CREATE TRIGGER estimator_runtime_observation_refs_delete_guard BEFORE DELETE ON estimator_runtime_observation_refs WHEN NOT EXISTS (SELECT 1 FROM estimator_runtime_write_authorizations a WHERE a.authorization_id=OLD.authorization_id AND a.execution_id=OLD.execution_id AND a.authorization_tag=estimator_runtime_authorization_tag(a.operation_id,a.authorization_id,a.execution_id,a.job_id)) BEGIN SELECT RAISE(ABORT,'estimator runtime delete is not authorized'); END;
CREATE TRIGGER estimator_runtime_retrievals_delete_guard BEFORE DELETE ON estimator_runtime_retrievals WHEN NOT EXISTS (SELECT 1 FROM estimator_runtime_write_authorizations a WHERE a.authorization_id=OLD.authorization_id AND a.execution_id=OLD.execution_id AND a.authorization_tag=estimator_runtime_authorization_tag(a.operation_id,a.authorization_id,a.execution_id,a.job_id)) BEGIN SELECT RAISE(ABORT,'estimator runtime delete is not authorized'); END;
CREATE TRIGGER estimator_runtime_candidates_delete_guard BEFORE DELETE ON estimator_runtime_retrieval_candidates WHEN NOT EXISTS (SELECT 1 FROM estimator_runtime_write_authorizations a WHERE a.authorization_id=OLD.authorization_id AND a.execution_id=OLD.execution_id AND a.authorization_tag=estimator_runtime_authorization_tag(a.operation_id,a.authorization_id,a.execution_id,a.job_id)) BEGIN SELECT RAISE(ABORT,'estimator runtime delete is not authorized'); END;
CREATE TRIGGER estimator_runtime_hits_delete_guard BEFORE DELETE ON estimator_runtime_retrieval_hits WHEN NOT EXISTS (SELECT 1 FROM estimator_runtime_write_authorizations a WHERE a.authorization_id=OLD.authorization_id AND a.execution_id=OLD.execution_id AND a.authorization_tag=estimator_runtime_authorization_tag(a.operation_id,a.authorization_id,a.execution_id,a.job_id)) BEGIN SELECT RAISE(ABORT,'estimator runtime delete is not authorized'); END;
CREATE TRIGGER estimator_runtime_outcomes_delete_guard BEFORE DELETE ON estimator_runtime_stage_outcomes WHEN NOT EXISTS (SELECT 1 FROM estimator_runtime_write_authorizations a WHERE a.authorization_id=OLD.authorization_id AND a.execution_id=OLD.execution_id AND a.authorization_tag=estimator_runtime_authorization_tag(a.operation_id,a.authorization_id,a.execution_id,a.job_id)) BEGIN SELECT RAISE(ABORT,'estimator runtime delete is not authorized'); END;
CREATE TRIGGER estimator_runtime_checkpoints_delete_guard BEFORE DELETE ON estimator_runtime_checkpoints WHEN NOT EXISTS (SELECT 1 FROM estimator_runtime_write_authorizations a WHERE a.authorization_id=OLD.authorization_id AND a.execution_id=OLD.execution_id AND a.authorization_tag=estimator_runtime_authorization_tag(a.operation_id,a.authorization_id,a.execution_id,a.job_id)) BEGIN SELECT RAISE(ABORT,'estimator runtime delete is not authorized'); END;

CREATE INDEX estimator_runtime_session_idx ON estimator_runtime_executions(session_id,created_at_us DESC);
CREATE INDEX estimator_runtime_attempt_idx ON estimator_runtime_stage_attempts(execution_id,metric_key,stage_ordinal);
COMMIT;
"""


# The v19 report vocabulary is duplicated here intentionally.  Migrations are
# immutable compatibility artifacts and must not import the live application
# model when reproducing an historical checksum.
_CALIBRATION_MEASUREMENT_SPECS_19 = (
    ("agreement.human_human_kappa", "agreement", "scalar", "score"),
    ("agreement.human_human_observed", "agreement", "rate", "ratio"),
    ("agreement.model_human_kappa", "agreement", "scalar", "score"),
    ("agreement.model_human_observed", "agreement", "rate", "ratio"),
    ("calibration.brier_score", "calibration", "scalar", "score"),
    ("calibration.false_confident_error_rate", "calibration", "rate", "ratio"),
    ("calibration.log_loss", "calibration", "scalar", "score"),
    ("calibration.selected_confidence_ece", "calibration", "scalar", "ratio"),
    ("calibration.slope", "calibration", "scalar", "slope"),
    ("cascade.incremental_value", "cascade", "scalar", "score"),
    ("cascade.stop_rate", "cascade", "rate", "ratio"),
    ("classification.accuracy", "classification", "rate", "ratio"),
    ("classification.macro_f1", "classification", "scalar", "ratio"),
    ("classification.macro_precision", "classification", "scalar", "ratio"),
    ("classification.macro_recall", "classification", "scalar", "ratio"),
    ("coverage.access_gaps", "coverage", "count", "gaps"),
    ("coverage.baseline_known", "coverage", "count", "cases"),
    ("coverage.candidate_known", "coverage", "count", "cases"),
    ("coverage.fallback_attempts", "coverage", "count", "attempts"),
    ("coverage.holdout_cases", "coverage", "count", "cases"),
    ("coverage.human_adjudicated", "coverage", "count", "cases"),
    ("coverage.objective_truth", "coverage", "count", "cases"),
    ("coverage.privacy_findings", "coverage", "count", "findings"),
    ("coverage.private_holdout_cases", "coverage", "count", "cases"),
    ("coverage.resolved_human_truth", "coverage", "count", "cases"),
    ("coverage.served_identity_unavailable", "coverage", "count", "attempts"),
    ("coverage.truth_known", "coverage", "count", "cases"),
    ("coverage.unauthorized_access", "coverage", "count", "events"),
    ("coverage.unscanned_artifacts", "coverage", "count", "artifacts"),
    ("numeric.mean_absolute_error", "numeric", "scalar", "error"),
    ("numeric.root_mean_squared_error", "numeric", "scalar", "error"),
    ("numeric.within_tolerance_rate", "numeric", "rate", "ratio"),
    ("resource.attempt_count", "resource", "count", "attempts"),
    ("resource.cancelled_rate", "resource", "rate", "ratio"),
    ("resource.cold_latency_p95_ms", "resource", "scalar", "milliseconds"),
    ("resource.cost_total_microusd", "resource", "scalar", "microusd"),
    ("resource.disk_bytes", "resource", "scalar", "bytes"),
    ("resource.energy_total_millijoules", "resource", "scalar", "millijoules"),
    ("resource.error_rate", "resource", "rate", "ratio"),
    ("resource.latency_p50_ms", "resource", "scalar", "milliseconds"),
    ("resource.latency_p95_ms", "resource", "scalar", "milliseconds"),
    ("resource.oom_rate", "resource", "rate", "ratio"),
    ("resource.peak_ram_bytes", "resource", "scalar", "bytes"),
    ("resource.peak_vram_bytes", "resource", "scalar", "bytes"),
    ("resource.queue_p50_ms", "resource", "scalar", "milliseconds"),
    ("resource.queue_p95_ms", "resource", "scalar", "milliseconds"),
    ("resource.refusal_rate", "resource", "rate", "ratio"),
    ("resource.throughput_per_second", "resource", "scalar", "items_per_second"),
    ("resource.timeout_rate", "resource", "rate", "ratio"),
    ("resource.token_total", "resource", "scalar", "tokens"),
    ("resource.warm_latency_p95_ms", "resource", "scalar", "milliseconds"),
    ("resource.worker_lost_rate", "resource", "rate", "ratio"),
    ("retrieval.link_precision", "retrieval", "rate", "ratio"),
    ("retrieval.mean_reciprocal_rank", "retrieval", "scalar", "score"),
    ("retrieval.ndcg_at_k", "retrieval", "scalar", "score"),
    ("retrieval.recall_at_k", "retrieval", "scalar", "ratio"),
    ("stability.format", "stability", "rate", "ratio"),
    ("stability.injection", "stability", "rate", "ratio"),
    ("stability.order", "stability", "rate", "ratio"),
    ("stability.repeat", "stability", "rate", "ratio"),
)


def _calibration_measurement_seed_rows_19() -> str:
    rows: list[str] = []
    definition_fingerprint = (
        "a3cdde9764d7a7925843dd99168a5eb4161ce08adbc18c4aaf03a7d6c19c17e0"
    )
    for ordinal, (key, family, shape, unit) in enumerate(
        _CALIBRATION_MEASUREMENT_SPECS_19
    ):
        payload = {
            "contract_version": "calibration-measurement-spec-v1",
            "family": family,
            "measurement_key": key,
            "shape": shape,
            "unit_code": unit,
        }
        fingerprint = hashlib.sha256(
            json.dumps(
                payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True
            ).encode("utf-8")
        ).hexdigest()
        rows.append(
            "(" + ",".join(
                (
                    f"'{definition_fingerprint}'",
                    str(ordinal),
                    "'calibration-measurement-spec-v1'",
                    f"'{key}'",
                    f"'{family}'",
                    f"'{shape}'",
                    f"'{unit}'",
                    f"'{fingerprint}'",
                )
            ) + ")"
        )
    return ",\n".join(rows)


_CALIBRATION_REPORT_GUARDED_TABLES_19 = (
    "estimator_calibration_report_metric_drafts",
    "estimator_calibration_report_comparison_identities",
    "estimator_calibration_report_label_vocabulary",
    "estimator_calibration_report_scopes",
    "estimator_calibration_report_measurements",
    "estimator_calibration_report_confusion_cells",
    "estimator_calibration_report_class_receipts",
    "estimator_calibration_report_reliability_bins",
    "estimator_calibration_report_selective_points",
    "estimator_calibration_report_agreement_receipts",
    "estimator_calibration_report_stability_receipts",
    "estimator_calibration_report_resource_receipts",
    "estimator_calibration_report_resource_keys",
    "estimator_calibration_report_missingness",
    "estimator_calibration_report_metric_roots",
)


def _calibration_report_guards_19() -> str:
    statements: list[str] = []
    for table in _CALIBRATION_REPORT_GUARDED_TABLES_19:
        name = table.removeprefix("estimator_calibration_report_")
        statements.extend(
            (
                f"""CREATE TRIGGER estimator_calibration_report_{name}_insert_guard BEFORE INSERT ON {table}
WHEN EXISTS (SELECT 1 FROM estimator_calibration_report_roots WHERE report_id=NEW.report_id)
 OR NOT EXISTS (
    SELECT 1 FROM estimator_calibration_report_append_authorizations a
    JOIN estimator_calibration_report_drafts d
      ON d.report_id=a.report_id AND d.submission_id=a.submission_id AND d.campaign_id=a.campaign_id
    WHERE d.report_id=NEW.report_id
      AND a.authorization_tag=estimator_calibration_report_authorization_tag(a.operation_id,a.report_id,a.submission_id,a.campaign_id))
BEGIN SELECT RAISE(ABORT,'estimator calibration report append is not authorized or is sealed'); END;""",
                f"CREATE TRIGGER estimator_calibration_report_{name}_no_update BEFORE UPDATE ON {table} BEGIN SELECT RAISE(ABORT,'estimator calibration report is immutable'); END;",
                f"""CREATE TRIGGER estimator_calibration_report_{name}_no_delete BEFORE DELETE ON {table}
WHEN EXISTS (
    SELECT 1 FROM estimator_calibration_report_drafts d
    JOIN estimator_gate_campaigns c ON c.campaign_id=d.campaign_id
    WHERE d.report_id=OLD.report_id)
BEGIN SELECT RAISE(ABORT,'estimator calibration report requires campaign privacy deletion'); END;""",
            )
        )
    return "\n".join(statements)


MIGRATION_19 = r"""
BEGIN IMMEDIATE;

-- V19 persists only normalized scalar aggregates derived inside the repository
-- from sealed v16/v17 rows.  No JSON, BLOB, prose, raw evidence, path, or URI
-- column exists in this schema.
CREATE TABLE estimator_calibration_report_definitions (
    definition_fingerprint TEXT PRIMARY KEY CHECK(definition_fingerprint='a3cdde9764d7a7925843dd99168a5eb4161ce08adbc18c4aaf03a7d6c19c17e0'),
    contract_version TEXT NOT NULL CHECK(contract_version='calibration-report-definition-v1'),
    definition_version TEXT NOT NULL CHECK(definition_version='calibration-report-math-v1'),
    classification_version TEXT NOT NULL CHECK(classification_version='registered-vocabulary-classification-v1'),
    confidence_calibration_version TEXT NOT NULL CHECK(confidence_calibration_version='selected-confidence-calibration-v1'),
    truth_resolution_version TEXT NOT NULL CHECK(truth_resolution_version='objective-then-independent-human-v1'),
    human_pairing_version TEXT NOT NULL CHECK(human_pairing_version='all-unordered-independent-pairs-v1'),
    slice_version TEXT NOT NULL CHECK(slice_version='frozen-assignment-slices-v1'),
    time_bucket_version TEXT NOT NULL CHECK(time_bucket_version='utc-calendar-month-v1'),
    quantile_version TEXT NOT NULL CHECK(quantile_version='linear-interpolation-v1'),
    reliability_bin_count INTEGER NOT NULL CHECK(reliability_bin_count=10),
    selective_threshold_count INTEGER NOT NULL CHECK(selective_threshold_count=5),
    retrieval_k_count INTEGER NOT NULL CHECK(retrieval_k_count=4),
    full_probability_vector_required INTEGER NOT NULL CHECK(full_probability_vector_required=1),
    false_confidence_threshold_source TEXT NOT NULL CHECK(false_confidence_threshold_source='campaign_policy'),
    minimum_slice_size_source TEXT NOT NULL CHECK(minimum_slice_size_source='campaign_policy'),
    activation_allowed INTEGER NOT NULL CHECK(activation_allowed=0)
);
CREATE TABLE estimator_calibration_report_selective_thresholds (
    definition_fingerprint TEXT NOT NULL REFERENCES estimator_calibration_report_definitions(definition_fingerprint),
    ordinal INTEGER NOT NULL CHECK(ordinal BETWEEN 0 AND 4),
    threshold REAL NOT NULL CHECK(typeof(threshold)='real' AND threshold BETWEEN 0.0 AND 1.0),
    PRIMARY KEY(definition_fingerprint,ordinal), UNIQUE(definition_fingerprint,threshold)
);
CREATE TABLE estimator_calibration_report_retrieval_ks (
    definition_fingerprint TEXT NOT NULL REFERENCES estimator_calibration_report_definitions(definition_fingerprint),
    ordinal INTEGER NOT NULL CHECK(ordinal BETWEEN 0 AND 3),
    retrieval_k INTEGER NOT NULL CHECK(retrieval_k IN (1,3,5,10)),
    PRIMARY KEY(definition_fingerprint,ordinal), UNIQUE(definition_fingerprint,retrieval_k)
);
CREATE TABLE estimator_calibration_report_measurement_specs (
    definition_fingerprint TEXT NOT NULL REFERENCES estimator_calibration_report_definitions(definition_fingerprint),
    ordinal INTEGER NOT NULL CHECK(ordinal BETWEEN 0 AND 59),
    contract_version TEXT NOT NULL CHECK(contract_version='calibration-measurement-spec-v1'),
    measurement_key TEXT NOT NULL CHECK(length(measurement_key) BETWEEN 1 AND 128 AND measurement_key NOT GLOB '*[^a-z0-9._-]*'),
    family TEXT NOT NULL CHECK(family IN ('coverage','classification','calibration','agreement','stability','resource','retrieval','cascade','numeric')),
    shape TEXT NOT NULL CHECK(shape IN ('count','scalar','rate')),
    unit_code TEXT NOT NULL CHECK(length(unit_code) BETWEEN 1 AND 128 AND unit_code NOT GLOB '*[^a-z0-9._-]*'),
    spec_fingerprint TEXT NOT NULL CHECK(length(spec_fingerprint)=64 AND spec_fingerprint NOT GLOB '*[^0-9a-f]*'),
    PRIMARY KEY(definition_fingerprint,measurement_key), UNIQUE(definition_fingerprint,ordinal), UNIQUE(measurement_key), UNIQUE(spec_fingerprint)
);
INSERT INTO estimator_calibration_report_definitions VALUES (
    'a3cdde9764d7a7925843dd99168a5eb4161ce08adbc18c4aaf03a7d6c19c17e0',
    'calibration-report-definition-v1','calibration-report-math-v1',
    'registered-vocabulary-classification-v1','selected-confidence-calibration-v1',
    'objective-then-independent-human-v1','all-unordered-independent-pairs-v1',
    'frozen-assignment-slices-v1','utc-calendar-month-v1','linear-interpolation-v1',
    10,5,4,1,'campaign_policy','campaign_policy',0
);
INSERT INTO estimator_calibration_report_selective_thresholds VALUES
('a3cdde9764d7a7925843dd99168a5eb4161ce08adbc18c4aaf03a7d6c19c17e0',0,0.0),
('a3cdde9764d7a7925843dd99168a5eb4161ce08adbc18c4aaf03a7d6c19c17e0',1,0.5),
('a3cdde9764d7a7925843dd99168a5eb4161ce08adbc18c4aaf03a7d6c19c17e0',2,0.75),
('a3cdde9764d7a7925843dd99168a5eb4161ce08adbc18c4aaf03a7d6c19c17e0',3,0.9),
('a3cdde9764d7a7925843dd99168a5eb4161ce08adbc18c4aaf03a7d6c19c17e0',4,0.95);
INSERT INTO estimator_calibration_report_retrieval_ks VALUES
('a3cdde9764d7a7925843dd99168a5eb4161ce08adbc18c4aaf03a7d6c19c17e0',0,1),
('a3cdde9764d7a7925843dd99168a5eb4161ce08adbc18c4aaf03a7d6c19c17e0',1,3),
('a3cdde9764d7a7925843dd99168a5eb4161ce08adbc18c4aaf03a7d6c19c17e0',2,5),
('a3cdde9764d7a7925843dd99168a5eb4161ce08adbc18c4aaf03a7d6c19c17e0',3,10);
INSERT INTO estimator_calibration_report_measurement_specs VALUES
""" + _calibration_measurement_seed_rows_19() + r""";

CREATE TRIGGER estimator_calibration_report_definitions_no_insert BEFORE INSERT ON estimator_calibration_report_definitions BEGIN SELECT RAISE(ABORT,'calibration report definition is sealed'); END;
CREATE TRIGGER estimator_calibration_report_definitions_no_update BEFORE UPDATE ON estimator_calibration_report_definitions BEGIN SELECT RAISE(ABORT,'calibration report definition is immutable'); END;
CREATE TRIGGER estimator_calibration_report_definitions_no_delete BEFORE DELETE ON estimator_calibration_report_definitions BEGIN SELECT RAISE(ABORT,'calibration report definition is retained'); END;
CREATE TRIGGER estimator_calibration_report_thresholds_no_insert BEFORE INSERT ON estimator_calibration_report_selective_thresholds BEGIN SELECT RAISE(ABORT,'calibration report definition is sealed'); END;
CREATE TRIGGER estimator_calibration_report_thresholds_no_update BEFORE UPDATE ON estimator_calibration_report_selective_thresholds BEGIN SELECT RAISE(ABORT,'calibration report definition is immutable'); END;
CREATE TRIGGER estimator_calibration_report_thresholds_no_delete BEFORE DELETE ON estimator_calibration_report_selective_thresholds BEGIN SELECT RAISE(ABORT,'calibration report definition is retained'); END;
CREATE TRIGGER estimator_calibration_report_ks_no_insert BEFORE INSERT ON estimator_calibration_report_retrieval_ks BEGIN SELECT RAISE(ABORT,'calibration report definition is sealed'); END;
CREATE TRIGGER estimator_calibration_report_ks_no_update BEFORE UPDATE ON estimator_calibration_report_retrieval_ks BEGIN SELECT RAISE(ABORT,'calibration report definition is immutable'); END;
CREATE TRIGGER estimator_calibration_report_ks_no_delete BEFORE DELETE ON estimator_calibration_report_retrieval_ks BEGIN SELECT RAISE(ABORT,'calibration report definition is retained'); END;
CREATE TRIGGER estimator_calibration_report_specs_no_insert BEFORE INSERT ON estimator_calibration_report_measurement_specs BEGIN SELECT RAISE(ABORT,'calibration report vocabulary is sealed'); END;
CREATE TRIGGER estimator_calibration_report_specs_no_update BEFORE UPDATE ON estimator_calibration_report_measurement_specs BEGIN SELECT RAISE(ABORT,'calibration report vocabulary is immutable'); END;
CREATE TRIGGER estimator_calibration_report_specs_no_delete BEFORE DELETE ON estimator_calibration_report_measurement_specs BEGIN SELECT RAISE(ABORT,'calibration report vocabulary is retained'); END;

CREATE TABLE estimator_calibration_report_append_authorizations (
    operation_id TEXT PRIMARY KEY CHECK(length(operation_id)=64 AND operation_id NOT GLOB '*[^0-9a-f]*'),
    report_id TEXT NOT NULL CHECK(length(report_id)=64 AND report_id NOT GLOB '*[^0-9a-f]*'),
    submission_id TEXT NOT NULL CHECK(length(submission_id)=64 AND submission_id NOT GLOB '*[^0-9a-f]*'),
    campaign_id TEXT NOT NULL REFERENCES estimator_gate_campaigns(campaign_id) ON DELETE CASCADE,
    authorization_tag TEXT NOT NULL CHECK(length(authorization_tag)=64 AND authorization_tag NOT GLOB '*[^0-9a-f]*'),
    UNIQUE(report_id,submission_id,campaign_id)
);
CREATE TRIGGER estimator_calibration_report_authorization_validate BEFORE INSERT ON estimator_calibration_report_append_authorizations
WHEN NEW.authorization_tag<>estimator_calibration_report_authorization_tag(NEW.operation_id,NEW.report_id,NEW.submission_id,NEW.campaign_id)
 OR NOT EXISTS (SELECT 1 FROM estimator_evidence_submissions WHERE submission_id=NEW.submission_id AND campaign_id=NEW.campaign_id)
BEGIN SELECT RAISE(ABORT,'estimator calibration report authorization is invalid'); END;
CREATE TRIGGER estimator_calibration_report_authorization_no_update BEFORE UPDATE ON estimator_calibration_report_append_authorizations BEGIN SELECT RAISE(ABORT,'estimator calibration report authorization is immutable'); END;
CREATE TRIGGER estimator_calibration_report_authorization_no_delete BEFORE DELETE ON estimator_calibration_report_append_authorizations
WHEN OLD.authorization_tag<>estimator_calibration_report_authorization_tag(OLD.operation_id,OLD.report_id,OLD.submission_id,OLD.campaign_id)
BEGIN SELECT RAISE(ABORT,'estimator calibration report authorization is invalid'); END;

CREATE TABLE estimator_calibration_report_drafts (
    report_id TEXT PRIMARY KEY CHECK(length(report_id)=64 AND report_id NOT GLOB '*[^0-9a-f]*'),
    contract_version TEXT NOT NULL CHECK(contract_version='untrusted-calibration-report-v1'),
    campaign_id TEXT NOT NULL REFERENCES estimator_gate_campaigns(campaign_id) ON DELETE CASCADE,
    campaign_fingerprint TEXT NOT NULL CHECK(length(campaign_fingerprint)=64 AND campaign_fingerprint NOT GLOB '*[^0-9a-f]*'),
    submission_id TEXT NOT NULL UNIQUE REFERENCES estimator_evidence_submissions(submission_id) ON DELETE CASCADE,
    submission_fingerprint TEXT NOT NULL CHECK(length(submission_fingerprint)=64 AND submission_fingerprint NOT GLOB '*[^0-9a-f]*'),
    stored_plan_fingerprint TEXT NOT NULL CHECK(length(stored_plan_fingerprint)=64 AND stored_plan_fingerprint NOT GLOB '*[^0-9a-f]*'),
    policy_fingerprint TEXT NOT NULL CHECK(length(policy_fingerprint)=64 AND policy_fingerprint NOT GLOB '*[^0-9a-f]*'),
    assignment_manifest_fingerprint TEXT NOT NULL CHECK(length(assignment_manifest_fingerprint)=64 AND assignment_manifest_fingerprint NOT GLOB '*[^0-9a-f]*'),
    split_fingerprint TEXT NOT NULL CHECK(length(split_fingerprint)=64 AND split_fingerprint NOT GLOB '*[^0-9a-f]*'),
    preregistration_fingerprint TEXT NOT NULL CHECK(length(preregistration_fingerprint)=64 AND preregistration_fingerprint NOT GLOB '*[^0-9a-f]*'),
    preregistration_v2_fingerprint TEXT NOT NULL CHECK(length(preregistration_v2_fingerprint)=64 AND preregistration_v2_fingerprint NOT GLOB '*[^0-9a-f]*'),
    constellation_fingerprint TEXT NOT NULL CHECK(length(constellation_fingerprint)=64 AND constellation_fingerprint NOT GLOB '*[^0-9a-f]*'),
    source_bundle_fingerprint TEXT NOT NULL CHECK(length(source_bundle_fingerprint)=64 AND source_bundle_fingerprint NOT GLOB '*[^0-9a-f]*'),
    definition_fingerprint TEXT NOT NULL REFERENCES estimator_calibration_report_definitions(definition_fingerprint),
    state TEXT NOT NULL CHECK(state IN ('ready','partial','insufficient_data')),
    source_observed_at_us INTEGER NOT NULL CHECK(typeof(source_observed_at_us)='integer' AND source_observed_at_us BETWEEN -62135596800000000 AND 253402300799999999),
    derived_at_us INTEGER CHECK(derived_at_us IS NULL),
    report_fingerprint TEXT NOT NULL CHECK(length(report_fingerprint)=64 AND report_fingerprint NOT GLOB '*[^0-9a-f]*'),
    metric_count INTEGER NOT NULL CHECK(metric_count BETWEEN 1 AND 1024),
    repository_owned INTEGER NOT NULL CHECK(repository_owned=0),
    persistence_state TEXT NOT NULL CHECK(persistence_state='untrusted_projection'),
    comparison_allowed INTEGER NOT NULL CHECK(comparison_allowed=0),
    activation_allowed INTEGER NOT NULL CHECK(activation_allowed=0),
    private_export_allowed INTEGER NOT NULL CHECK(private_export_allowed=0),
    team_share_allowed INTEGER NOT NULL CHECK(team_share_allowed=0)
);
CREATE TRIGGER estimator_calibration_report_draft_insert_guard BEFORE INSERT ON estimator_calibration_report_drafts
WHEN EXISTS (SELECT 1 FROM estimator_calibration_report_roots WHERE report_id=NEW.report_id)
 OR NOT EXISTS (
    SELECT 1 FROM estimator_calibration_report_append_authorizations a
    WHERE a.report_id=NEW.report_id AND a.submission_id=NEW.submission_id AND a.campaign_id=NEW.campaign_id
      AND a.authorization_tag=estimator_calibration_report_authorization_tag(a.operation_id,a.report_id,a.submission_id,a.campaign_id))
 OR NOT EXISTS (SELECT 1 FROM estimator_evidence_submissions WHERE submission_id=NEW.submission_id AND campaign_id=NEW.campaign_id AND submission_fingerprint=NEW.submission_fingerprint)
BEGIN SELECT RAISE(ABORT,'estimator calibration report draft is not authorized or lineage is invalid'); END;

CREATE TABLE estimator_calibration_report_metric_drafts (
    report_id TEXT NOT NULL REFERENCES estimator_calibration_report_drafts(report_id) ON DELETE CASCADE,
    metric_ordinal INTEGER NOT NULL CHECK(metric_ordinal BETWEEN 0 AND 1023),
    metric_key TEXT NOT NULL CHECK(length(metric_key) BETWEEN 1 AND 64 AND metric_key NOT GLOB '*[^a-z0-9._-]*'),
    contract_version TEXT NOT NULL CHECK(contract_version='calibration-metric-report-v1'),
    value_kind TEXT NOT NULL CHECK(value_kind IN ('continuous','fraction','binary','categorical')),
    state TEXT NOT NULL CHECK(state IN ('ready','partial','insufficient_data')),
    metric_fingerprint TEXT NOT NULL CHECK(length(metric_fingerprint)=64 AND metric_fingerprint NOT GLOB '*[^0-9a-f]*'),
    vocabulary_count INTEGER NOT NULL CHECK(vocabulary_count BETWEEN 0 AND 256),
    scope_count INTEGER NOT NULL CHECK(scope_count BETWEEN 1 AND 100000),
    measurement_count INTEGER NOT NULL CHECK(measurement_count BETWEEN 60 AND 6000000),
    confusion_count INTEGER NOT NULL CHECK(confusion_count BETWEEN 0 AND 1000000),
    class_count INTEGER NOT NULL CHECK(class_count BETWEEN 0 AND 1000000),
    reliability_count INTEGER NOT NULL CHECK(reliability_count BETWEEN 0 AND 1000000),
    selective_count INTEGER NOT NULL CHECK(selective_count BETWEEN 0 AND 1000000),
    agreement_count INTEGER NOT NULL CHECK(agreement_count=2),
    stability_count INTEGER NOT NULL CHECK(stability_count=4),
    resource_key_count INTEGER NOT NULL CHECK(resource_key_count BETWEEN 0 AND 60),
    missingness_count INTEGER NOT NULL CHECK(missingness_count BETWEEN 0 AND 60),
    comparison_allowed INTEGER NOT NULL CHECK(comparison_allowed=0),
    activation_allowed INTEGER NOT NULL CHECK(activation_allowed=0),
    PRIMARY KEY(report_id,metric_key), UNIQUE(report_id,metric_ordinal), UNIQUE(metric_fingerprint)
);
CREATE TABLE estimator_calibration_report_comparison_identities (
    report_id TEXT NOT NULL,
    metric_key TEXT NOT NULL,
    contract_version TEXT NOT NULL CHECK(contract_version='calibration-comparison-identity-v1'),
    metric_semantics_fingerprint TEXT NOT NULL,
    evidence_scope_fingerprint TEXT NOT NULL,
    pipeline_fingerprint TEXT NOT NULL,
    gate_policy_fingerprint TEXT NOT NULL,
    threshold_policy_fingerprint TEXT NOT NULL,
    split_fingerprint TEXT NOT NULL,
    submission_fingerprint TEXT NOT NULL,
    served_runtime_identity_fingerprint TEXT NOT NULL,
    measurement_provenance_fingerprint TEXT NOT NULL,
    report_definition_fingerprint TEXT NOT NULL,
    estimator_configuration_fingerprint TEXT NOT NULL,
    constellation_fingerprint TEXT NOT NULL,
    comparison_family_fingerprint TEXT NOT NULL,
    observation_identity_fingerprint TEXT NOT NULL,
    observation_source_fingerprint TEXT NOT NULL,
    comparison_allowed INTEGER NOT NULL CHECK(comparison_allowed=0),
    PRIMARY KEY(report_id,metric_key),
    FOREIGN KEY(report_id,metric_key) REFERENCES estimator_calibration_report_metric_drafts(report_id,metric_key) ON DELETE CASCADE,
    CHECK(length(metric_semantics_fingerprint)=64 AND metric_semantics_fingerprint NOT GLOB '*[^0-9a-f]*'),
    CHECK(length(evidence_scope_fingerprint)=64 AND evidence_scope_fingerprint NOT GLOB '*[^0-9a-f]*'),
    CHECK(length(pipeline_fingerprint)=64 AND pipeline_fingerprint NOT GLOB '*[^0-9a-f]*'),
    CHECK(length(gate_policy_fingerprint)=64 AND gate_policy_fingerprint NOT GLOB '*[^0-9a-f]*'),
    CHECK(length(threshold_policy_fingerprint)=64 AND threshold_policy_fingerprint NOT GLOB '*[^0-9a-f]*'),
    CHECK(length(split_fingerprint)=64 AND split_fingerprint NOT GLOB '*[^0-9a-f]*'),
    CHECK(length(submission_fingerprint)=64 AND submission_fingerprint NOT GLOB '*[^0-9a-f]*'),
    CHECK(length(served_runtime_identity_fingerprint)=64 AND served_runtime_identity_fingerprint NOT GLOB '*[^0-9a-f]*'),
    CHECK(length(measurement_provenance_fingerprint)=64 AND measurement_provenance_fingerprint NOT GLOB '*[^0-9a-f]*'),
    CHECK(length(report_definition_fingerprint)=64 AND report_definition_fingerprint NOT GLOB '*[^0-9a-f]*'),
    CHECK(length(estimator_configuration_fingerprint)=64 AND estimator_configuration_fingerprint NOT GLOB '*[^0-9a-f]*'),
    CHECK(length(constellation_fingerprint)=64 AND constellation_fingerprint NOT GLOB '*[^0-9a-f]*'),
    CHECK(length(comparison_family_fingerprint)=64 AND comparison_family_fingerprint NOT GLOB '*[^0-9a-f]*'),
    CHECK(length(observation_identity_fingerprint)=64 AND observation_identity_fingerprint NOT GLOB '*[^0-9a-f]*'),
    CHECK(length(observation_source_fingerprint)=64 AND observation_source_fingerprint NOT GLOB '*[^0-9a-f]*')
);
CREATE TABLE estimator_calibration_report_label_vocabulary (
    report_id TEXT NOT NULL, metric_key TEXT NOT NULL,
    ordinal INTEGER NOT NULL CHECK(ordinal BETWEEN 0 AND 255),
    label_code TEXT NOT NULL CHECK(length(label_code) BETWEEN 1 AND 128 AND label_code GLOB '[a-z]*' AND label_code NOT GLOB '*[^a-z0-9._-]*'),
    PRIMARY KEY(report_id,metric_key,label_code), UNIQUE(report_id,metric_key,ordinal),
    FOREIGN KEY(report_id,metric_key) REFERENCES estimator_calibration_report_metric_drafts(report_id,metric_key) ON DELETE CASCADE
);
CREATE TABLE estimator_calibration_report_scopes (
    report_id TEXT NOT NULL, metric_key TEXT NOT NULL,
    ordinal INTEGER NOT NULL CHECK(ordinal BETWEEN 0 AND 99999),
    scope_id TEXT NOT NULL CHECK(length(scope_id)=64 AND scope_id NOT GLOB '*[^0-9a-f]*'),
    contract_version TEXT NOT NULL CHECK(contract_version='calibration-report-scope-v1'),
    dimension TEXT NOT NULL CHECK(dimension IN ('overall','task','language','provider','project','time','evidence_availability')),
    bucket_code TEXT NOT NULL CHECK(length(bucket_code) BETWEEN 1 AND 128 AND bucket_code GLOB '[a-z]*' AND bucket_code NOT GLOB '*[^a-z0-9._-]*'),
    case_count INTEGER NOT NULL CHECK(case_count BETWEEN 0 AND 9007199254740991),
    minimum_required_count INTEGER NOT NULL CHECK(minimum_required_count BETWEEN 1 AND 9007199254740991),
    state TEXT NOT NULL CHECK(state IN ('known','insufficient_data')),
    reason_code TEXT CHECK(reason_code IS NULL OR (length(reason_code) BETWEEN 1 AND 128 AND reason_code GLOB '[a-z]*' AND reason_code NOT GLOB '*[^a-z0-9._-]*')),
    scope_fingerprint TEXT NOT NULL CHECK(length(scope_fingerprint)=64 AND scope_fingerprint NOT GLOB '*[^0-9a-f]*'),
    PRIMARY KEY(report_id,metric_key,scope_id), UNIQUE(report_id,metric_key,ordinal), UNIQUE(report_id,scope_id),
    FOREIGN KEY(report_id,metric_key) REFERENCES estimator_calibration_report_metric_drafts(report_id,metric_key) ON DELETE CASCADE
);
CREATE TABLE estimator_calibration_report_measurements (
    report_id TEXT NOT NULL, metric_key TEXT NOT NULL,
    ordinal INTEGER NOT NULL CHECK(ordinal BETWEEN 0 AND 5999999),
    scope_id TEXT NOT NULL, measurement_key TEXT NOT NULL,
    contract_version TEXT NOT NULL CHECK(contract_version='calibration-measurement-v1'),
    family TEXT NOT NULL CHECK(family IN ('coverage','classification','calibration','agreement','stability','resource','retrieval','cascade','numeric')),
    shape TEXT NOT NULL CHECK(shape IN ('count','scalar','rate')),
    unit_code TEXT NOT NULL CHECK(length(unit_code) BETWEEN 1 AND 128 AND unit_code NOT GLOB '*[^a-z0-9._-]*'),
    state TEXT NOT NULL CHECK(state IN ('known','insufficient_data','unsupported','not_applicable','incompatible')),
    scalar_value REAL CHECK(scalar_value IS NULL OR (typeof(scalar_value)='real' AND abs(scalar_value)<=1.7976931348623157e308)),
    integer_value INTEGER CHECK(integer_value IS NULL OR (typeof(integer_value)='integer' AND integer_value BETWEEN 0 AND 9007199254740991)),
    numerator INTEGER CHECK(numerator IS NULL OR (typeof(numerator)='integer' AND numerator BETWEEN 0 AND 9007199254740991)),
    denominator INTEGER CHECK(denominator IS NULL OR (typeof(denominator)='integer' AND denominator BETWEEN 0 AND 9007199254740991)),
    sample_count INTEGER NOT NULL CHECK(sample_count BETWEEN 0 AND 9007199254740991),
    reason_code TEXT CHECK(reason_code IS NULL OR (length(reason_code) BETWEEN 1 AND 128 AND reason_code GLOB '[a-z]*' AND reason_code NOT GLOB '*[^a-z0-9._-]*')),
    measurement_fingerprint TEXT NOT NULL CHECK(length(measurement_fingerprint)=64 AND measurement_fingerprint NOT GLOB '*[^0-9a-f]*'),
    PRIMARY KEY(report_id,metric_key,scope_id,measurement_key), UNIQUE(report_id,metric_key,ordinal),
    FOREIGN KEY(report_id,metric_key,scope_id) REFERENCES estimator_calibration_report_scopes(report_id,metric_key,scope_id) ON DELETE CASCADE,
    FOREIGN KEY(measurement_key) REFERENCES estimator_calibration_report_measurement_specs(measurement_key)
);
CREATE TABLE estimator_calibration_report_confusion_cells (
    report_id TEXT NOT NULL, metric_key TEXT NOT NULL, ordinal INTEGER NOT NULL,
    scope_id TEXT NOT NULL, truth_label TEXT NOT NULL, predicted_label TEXT NOT NULL,
    contract_version TEXT NOT NULL CHECK(contract_version='calibration-confusion-cell-v1'),
    count INTEGER NOT NULL CHECK(count BETWEEN 0 AND 9007199254740991), row_fingerprint TEXT NOT NULL,
    PRIMARY KEY(report_id,metric_key,scope_id,truth_label,predicted_label), UNIQUE(report_id,metric_key,ordinal),
    FOREIGN KEY(report_id,metric_key,scope_id) REFERENCES estimator_calibration_report_scopes(report_id,metric_key,scope_id) ON DELETE CASCADE,
    CHECK(length(row_fingerprint)=64 AND row_fingerprint NOT GLOB '*[^0-9a-f]*'),
    CHECK(length(truth_label) BETWEEN 1 AND 128 AND truth_label NOT GLOB '*[^a-z0-9._-]*'),
    CHECK(length(predicted_label) BETWEEN 1 AND 128 AND predicted_label NOT GLOB '*[^a-z0-9._-]*')
);
CREATE TABLE estimator_calibration_report_class_receipts (
    report_id TEXT NOT NULL, metric_key TEXT NOT NULL, ordinal INTEGER NOT NULL,
    scope_id TEXT NOT NULL, label_code TEXT NOT NULL,
    contract_version TEXT NOT NULL CHECK(contract_version='calibration-class-receipt-v1'),
    support INTEGER NOT NULL, predicted_count INTEGER NOT NULL, true_positive INTEGER NOT NULL, false_positive INTEGER NOT NULL, false_negative INTEGER NOT NULL,
    precision REAL NOT NULL, recall REAL NOT NULL, f1 REAL NOT NULL, row_fingerprint TEXT NOT NULL,
    PRIMARY KEY(report_id,metric_key,scope_id,label_code), UNIQUE(report_id,metric_key,ordinal),
    FOREIGN KEY(report_id,metric_key,scope_id) REFERENCES estimator_calibration_report_scopes(report_id,metric_key,scope_id) ON DELETE CASCADE,
    CHECK(support BETWEEN 0 AND 9007199254740991 AND predicted_count BETWEEN 0 AND 9007199254740991 AND true_positive BETWEEN 0 AND 9007199254740991 AND false_positive BETWEEN 0 AND 9007199254740991 AND false_negative BETWEEN 0 AND 9007199254740991),
    CHECK(precision BETWEEN 0.0 AND 1.0 AND recall BETWEEN 0.0 AND 1.0 AND f1 BETWEEN 0.0 AND 1.0),
    CHECK(length(label_code) BETWEEN 1 AND 128 AND label_code NOT GLOB '*[^a-z0-9._-]*'), CHECK(length(row_fingerprint)=64 AND row_fingerprint NOT GLOB '*[^0-9a-f]*')
);
CREATE TABLE estimator_calibration_report_reliability_bins (
    report_id TEXT NOT NULL, metric_key TEXT NOT NULL, ordinal INTEGER NOT NULL,
    scope_id TEXT NOT NULL, bin_index INTEGER NOT NULL CHECK(bin_index BETWEEN 0 AND 99),
    contract_version TEXT NOT NULL CHECK(contract_version='calibration-reliability-bin-v1'),
    lower_bound REAL NOT NULL CHECK(lower_bound BETWEEN 0.0 AND 1.0), upper_bound REAL NOT NULL CHECK(upper_bound BETWEEN 0.0 AND 1.0),
    count INTEGER NOT NULL CHECK(count BETWEEN 0 AND 9007199254740991), mean_confidence REAL, accuracy REAL, absolute_gap REAL, row_fingerprint TEXT NOT NULL,
    PRIMARY KEY(report_id,metric_key,scope_id,bin_index), UNIQUE(report_id,metric_key,ordinal),
    FOREIGN KEY(report_id,metric_key,scope_id) REFERENCES estimator_calibration_report_scopes(report_id,metric_key,scope_id) ON DELETE CASCADE,
    CHECK(mean_confidence IS NULL OR mean_confidence BETWEEN 0.0 AND 1.0), CHECK(accuracy IS NULL OR accuracy BETWEEN 0.0 AND 1.0), CHECK(absolute_gap IS NULL OR absolute_gap BETWEEN 0.0 AND 1.0),
    CHECK(length(row_fingerprint)=64 AND row_fingerprint NOT GLOB '*[^0-9a-f]*')
);
CREATE TABLE estimator_calibration_report_selective_points (
    report_id TEXT NOT NULL, metric_key TEXT NOT NULL, ordinal INTEGER NOT NULL,
    scope_id TEXT NOT NULL, threshold REAL NOT NULL CHECK(threshold BETWEEN 0.0 AND 1.0),
    contract_version TEXT NOT NULL CHECK(contract_version='calibration-selective-point-v1'), state TEXT NOT NULL CHECK(state IN ('known','insufficient_data')),
    coverage_numerator INTEGER NOT NULL, coverage_denominator INTEGER NOT NULL, risk_numerator INTEGER NOT NULL, risk_denominator INTEGER NOT NULL,
    reason_code TEXT, row_fingerprint TEXT NOT NULL,
    PRIMARY KEY(report_id,metric_key,scope_id,threshold), UNIQUE(report_id,metric_key,ordinal),
    FOREIGN KEY(report_id,metric_key,scope_id) REFERENCES estimator_calibration_report_scopes(report_id,metric_key,scope_id) ON DELETE CASCADE,
    CHECK(coverage_numerator BETWEEN 0 AND 9007199254740991 AND coverage_denominator BETWEEN 0 AND 9007199254740991 AND risk_numerator BETWEEN 0 AND 9007199254740991 AND risk_denominator BETWEEN 0 AND 9007199254740991),
    CHECK(reason_code IS NULL OR (length(reason_code) BETWEEN 1 AND 128 AND reason_code NOT GLOB '*[^a-z0-9._-]*')), CHECK(length(row_fingerprint)=64 AND row_fingerprint NOT GLOB '*[^0-9a-f]*')
);
CREATE TABLE estimator_calibration_report_agreement_receipts (
    report_id TEXT NOT NULL, metric_key TEXT NOT NULL, ordinal INTEGER NOT NULL CHECK(ordinal BETWEEN 0 AND 1),
    contract_version TEXT NOT NULL CHECK(contract_version='calibration-agreement-receipt-v1'), kind TEXT NOT NULL CHECK(kind IN ('human_human','model_human')),
    state TEXT NOT NULL CHECK(state IN ('known','insufficient_data','unsupported','not_applicable','incompatible')),
    case_count INTEGER NOT NULL, pair_count INTEGER NOT NULL, match_count INTEGER NOT NULL, observed_agreement REAL, cohen_kappa REAL, reason_code TEXT, row_fingerprint TEXT NOT NULL,
    PRIMARY KEY(report_id,metric_key,kind), UNIQUE(report_id,metric_key,ordinal),
    FOREIGN KEY(report_id,metric_key) REFERENCES estimator_calibration_report_metric_drafts(report_id,metric_key) ON DELETE CASCADE,
    CHECK(case_count BETWEEN 0 AND 9007199254740991 AND pair_count BETWEEN 0 AND 9007199254740991 AND match_count BETWEEN 0 AND 9007199254740991),
    CHECK(observed_agreement IS NULL OR observed_agreement BETWEEN 0.0 AND 1.0), CHECK(cohen_kappa IS NULL OR cohen_kappa BETWEEN -1.0 AND 1.0),
    CHECK(reason_code IS NULL OR (length(reason_code) BETWEEN 1 AND 128 AND reason_code NOT GLOB '*[^a-z0-9._-]*')), CHECK(length(row_fingerprint)=64 AND row_fingerprint NOT GLOB '*[^0-9a-f]*')
);
CREATE TABLE estimator_calibration_report_stability_receipts (
    report_id TEXT NOT NULL, metric_key TEXT NOT NULL, ordinal INTEGER NOT NULL CHECK(ordinal BETWEEN 0 AND 3),
    contract_version TEXT NOT NULL CHECK(contract_version='calibration-stability-receipt-v1'), condition TEXT NOT NULL CHECK(condition IN ('repeat','order','format','injection')),
    state TEXT NOT NULL CHECK(state IN ('known','insufficient_data','unsupported','not_applicable','incompatible')),
    case_count INTEGER NOT NULL, pair_count INTEGER NOT NULL, match_count INTEGER NOT NULL, stability REAL, reason_code TEXT, row_fingerprint TEXT NOT NULL,
    PRIMARY KEY(report_id,metric_key,condition), UNIQUE(report_id,metric_key,ordinal),
    FOREIGN KEY(report_id,metric_key) REFERENCES estimator_calibration_report_metric_drafts(report_id,metric_key) ON DELETE CASCADE,
    CHECK(case_count BETWEEN 0 AND 9007199254740991 AND pair_count BETWEEN 0 AND 9007199254740991 AND match_count BETWEEN 0 AND 9007199254740991),
    CHECK(stability IS NULL OR stability BETWEEN 0.0 AND 1.0), CHECK(reason_code IS NULL OR (length(reason_code) BETWEEN 1 AND 128 AND reason_code NOT GLOB '*[^a-z0-9._-]*')), CHECK(length(row_fingerprint)=64 AND row_fingerprint NOT GLOB '*[^0-9a-f]*')
);
CREATE TABLE estimator_calibration_report_resource_receipts (
    report_id TEXT NOT NULL, metric_key TEXT NOT NULL,
    contract_version TEXT NOT NULL CHECK(contract_version='calibration-resource-receipt-v1'),
    attempt_count INTEGER NOT NULL, observed_usage_count INTEGER NOT NULL, observed_resource_count INTEGER NOT NULL, observed_cost_count INTEGER NOT NULL, terminal_state_count INTEGER NOT NULL,
    measurement_key_count INTEGER NOT NULL CHECK(measurement_key_count BETWEEN 0 AND 60), row_fingerprint TEXT NOT NULL,
    PRIMARY KEY(report_id,metric_key), FOREIGN KEY(report_id,metric_key) REFERENCES estimator_calibration_report_metric_drafts(report_id,metric_key) ON DELETE CASCADE,
    CHECK(attempt_count BETWEEN 0 AND 9007199254740991 AND observed_usage_count BETWEEN 0 AND 9007199254740991 AND observed_resource_count BETWEEN 0 AND 9007199254740991 AND observed_cost_count BETWEEN 0 AND 9007199254740991 AND terminal_state_count BETWEEN 0 AND 9007199254740991),
    CHECK(length(row_fingerprint)=64 AND row_fingerprint NOT GLOB '*[^0-9a-f]*')
);
CREATE TABLE estimator_calibration_report_resource_keys (
    report_id TEXT NOT NULL, metric_key TEXT NOT NULL, ordinal INTEGER NOT NULL CHECK(ordinal BETWEEN 0 AND 59), measurement_key TEXT NOT NULL,
    PRIMARY KEY(report_id,metric_key,measurement_key), UNIQUE(report_id,metric_key,ordinal),
    FOREIGN KEY(report_id,metric_key) REFERENCES estimator_calibration_report_resource_receipts(report_id,metric_key) ON DELETE CASCADE,
    FOREIGN KEY(measurement_key) REFERENCES estimator_calibration_report_measurement_specs(measurement_key)
);
CREATE TABLE estimator_calibration_report_missingness (
    report_id TEXT NOT NULL, metric_key TEXT NOT NULL, ordinal INTEGER NOT NULL CHECK(ordinal BETWEEN 0 AND 59), measurement_key TEXT NOT NULL,
    contract_version TEXT NOT NULL CHECK(contract_version='calibration-missingness-receipt-v1'),
    state TEXT NOT NULL CHECK(state IN ('insufficient_data','unsupported','not_applicable','incompatible')),
    affected_count INTEGER NOT NULL CHECK(affected_count BETWEEN 0 AND 9007199254740991), reason_code TEXT NOT NULL, row_fingerprint TEXT NOT NULL,
    PRIMARY KEY(report_id,metric_key,measurement_key), UNIQUE(report_id,metric_key,ordinal),
    FOREIGN KEY(report_id,metric_key) REFERENCES estimator_calibration_report_metric_drafts(report_id,metric_key) ON DELETE CASCADE,
    FOREIGN KEY(measurement_key) REFERENCES estimator_calibration_report_measurement_specs(measurement_key),
    CHECK(length(reason_code) BETWEEN 1 AND 128 AND reason_code NOT GLOB '*[^a-z0-9._-]*'), CHECK(length(row_fingerprint)=64 AND row_fingerprint NOT GLOB '*[^0-9a-f]*')
);
CREATE TABLE estimator_calibration_report_metric_roots (
    report_id TEXT NOT NULL, metric_key TEXT NOT NULL, metric_ordinal INTEGER NOT NULL,
    contract_version TEXT NOT NULL CHECK(contract_version='repository-sealed-calibration-metric-root-v1'),
    metric_fingerprint TEXT NOT NULL, comparison_identity_fingerprint TEXT NOT NULL,
    vocabulary_count INTEGER NOT NULL, scope_count INTEGER NOT NULL, measurement_count INTEGER NOT NULL,
    confusion_count INTEGER NOT NULL, class_count INTEGER NOT NULL, reliability_count INTEGER NOT NULL, selective_count INTEGER NOT NULL,
    agreement_count INTEGER NOT NULL, stability_count INTEGER NOT NULL, resource_key_count INTEGER NOT NULL, missingness_count INTEGER NOT NULL,
    PRIMARY KEY(report_id,metric_key), UNIQUE(report_id,metric_ordinal),
    FOREIGN KEY(report_id,metric_key) REFERENCES estimator_calibration_report_metric_drafts(report_id,metric_key) ON DELETE CASCADE,
    CHECK(length(metric_fingerprint)=64 AND metric_fingerprint NOT GLOB '*[^0-9a-f]*'), CHECK(length(comparison_identity_fingerprint)=64 AND comparison_identity_fingerprint NOT GLOB '*[^0-9a-f]*')
);
CREATE TABLE estimator_calibration_report_roots (
    report_id TEXT PRIMARY KEY REFERENCES estimator_calibration_report_drafts(report_id) ON DELETE CASCADE,
    contract_version TEXT NOT NULL CHECK(contract_version='repository-sealed-calibration-report-v1'),
    receipt_id TEXT NOT NULL UNIQUE CHECK(length(receipt_id)=64 AND receipt_id NOT GLOB '*[^0-9a-f]*'),
    report_fingerprint TEXT NOT NULL UNIQUE CHECK(length(report_fingerprint)=64 AND report_fingerprint NOT GLOB '*[^0-9a-f]*'),
    definition_fingerprint TEXT NOT NULL REFERENCES estimator_calibration_report_definitions(definition_fingerprint),
    metric_count INTEGER NOT NULL CHECK(metric_count BETWEEN 1 AND 1024),
    derived_at_us INTEGER NOT NULL CHECK(typeof(derived_at_us)='integer' AND derived_at_us BETWEEN -62135596800000000 AND 253402300799999999),
    receipt_fingerprint TEXT NOT NULL UNIQUE CHECK(length(receipt_fingerprint)=64 AND receipt_fingerprint NOT GLOB '*[^0-9a-f]*'),
    repository_owned INTEGER NOT NULL CHECK(repository_owned=1), repository_sealed INTEGER NOT NULL CHECK(repository_sealed=1),
    persistence_state TEXT NOT NULL CHECK(persistence_state='repository_sealed'),
    comparison_allowed INTEGER NOT NULL CHECK(comparison_allowed=0), activation_allowed INTEGER NOT NULL CHECK(activation_allowed=0),
    private_export_allowed INTEGER NOT NULL CHECK(private_export_allowed=0), team_share_allowed INTEGER NOT NULL CHECK(team_share_allowed=0)
);

CREATE TRIGGER estimator_calibration_report_metric_root_counts BEFORE INSERT ON estimator_calibration_report_metric_roots
WHEN NOT EXISTS (
    SELECT 1 FROM estimator_calibration_report_metric_drafts d
    WHERE d.report_id=NEW.report_id AND d.metric_key=NEW.metric_key AND d.metric_ordinal=NEW.metric_ordinal AND d.metric_fingerprint=NEW.metric_fingerprint
      AND d.vocabulary_count=NEW.vocabulary_count AND d.scope_count=NEW.scope_count AND d.measurement_count=NEW.measurement_count
      AND d.confusion_count=NEW.confusion_count AND d.class_count=NEW.class_count AND d.reliability_count=NEW.reliability_count AND d.selective_count=NEW.selective_count
      AND d.agreement_count=NEW.agreement_count AND d.stability_count=NEW.stability_count AND d.resource_key_count=NEW.resource_key_count AND d.missingness_count=NEW.missingness_count)
 OR NEW.vocabulary_count<>(SELECT COUNT(*) FROM estimator_calibration_report_label_vocabulary WHERE report_id=NEW.report_id AND metric_key=NEW.metric_key)
 OR NEW.scope_count<>(SELECT COUNT(*) FROM estimator_calibration_report_scopes WHERE report_id=NEW.report_id AND metric_key=NEW.metric_key)
 OR NEW.measurement_count<>(SELECT COUNT(*) FROM estimator_calibration_report_measurements WHERE report_id=NEW.report_id AND metric_key=NEW.metric_key)
 OR NEW.confusion_count<>(SELECT COUNT(*) FROM estimator_calibration_report_confusion_cells WHERE report_id=NEW.report_id AND metric_key=NEW.metric_key)
 OR NEW.class_count<>(SELECT COUNT(*) FROM estimator_calibration_report_class_receipts WHERE report_id=NEW.report_id AND metric_key=NEW.metric_key)
 OR NEW.reliability_count<>(SELECT COUNT(*) FROM estimator_calibration_report_reliability_bins WHERE report_id=NEW.report_id AND metric_key=NEW.metric_key)
 OR NEW.selective_count<>(SELECT COUNT(*) FROM estimator_calibration_report_selective_points WHERE report_id=NEW.report_id AND metric_key=NEW.metric_key)
 OR NEW.agreement_count<>(SELECT COUNT(*) FROM estimator_calibration_report_agreement_receipts WHERE report_id=NEW.report_id AND metric_key=NEW.metric_key)
 OR NEW.stability_count<>(SELECT COUNT(*) FROM estimator_calibration_report_stability_receipts WHERE report_id=NEW.report_id AND metric_key=NEW.metric_key)
 OR NEW.resource_key_count<>(SELECT COUNT(*) FROM estimator_calibration_report_resource_keys WHERE report_id=NEW.report_id AND metric_key=NEW.metric_key)
 OR NEW.missingness_count<>(SELECT COUNT(*) FROM estimator_calibration_report_missingness WHERE report_id=NEW.report_id AND metric_key=NEW.metric_key)
 OR 1<>(SELECT COUNT(*) FROM estimator_calibration_report_comparison_identities WHERE report_id=NEW.report_id AND metric_key=NEW.metric_key)
 OR 1<>(SELECT COUNT(*) FROM estimator_calibration_report_resource_receipts WHERE report_id=NEW.report_id AND metric_key=NEW.metric_key)
 OR (NEW.vocabulary_count>0 AND ((SELECT MIN(ordinal) FROM estimator_calibration_report_label_vocabulary WHERE report_id=NEW.report_id AND metric_key=NEW.metric_key)<>0 OR (SELECT MAX(ordinal) FROM estimator_calibration_report_label_vocabulary WHERE report_id=NEW.report_id AND metric_key=NEW.metric_key)<>NEW.vocabulary_count-1))
 OR (NEW.scope_count>0 AND ((SELECT MIN(ordinal) FROM estimator_calibration_report_scopes WHERE report_id=NEW.report_id AND metric_key=NEW.metric_key)<>0 OR (SELECT MAX(ordinal) FROM estimator_calibration_report_scopes WHERE report_id=NEW.report_id AND metric_key=NEW.metric_key)<>NEW.scope_count-1))
 OR (NEW.measurement_count>0 AND ((SELECT MIN(ordinal) FROM estimator_calibration_report_measurements WHERE report_id=NEW.report_id AND metric_key=NEW.metric_key)<>0 OR (SELECT MAX(ordinal) FROM estimator_calibration_report_measurements WHERE report_id=NEW.report_id AND metric_key=NEW.metric_key)<>NEW.measurement_count-1))
 OR (NEW.confusion_count>0 AND ((SELECT MIN(ordinal) FROM estimator_calibration_report_confusion_cells WHERE report_id=NEW.report_id AND metric_key=NEW.metric_key)<>0 OR (SELECT MAX(ordinal) FROM estimator_calibration_report_confusion_cells WHERE report_id=NEW.report_id AND metric_key=NEW.metric_key)<>NEW.confusion_count-1))
 OR (NEW.class_count>0 AND ((SELECT MIN(ordinal) FROM estimator_calibration_report_class_receipts WHERE report_id=NEW.report_id AND metric_key=NEW.metric_key)<>0 OR (SELECT MAX(ordinal) FROM estimator_calibration_report_class_receipts WHERE report_id=NEW.report_id AND metric_key=NEW.metric_key)<>NEW.class_count-1))
 OR (NEW.reliability_count>0 AND ((SELECT MIN(ordinal) FROM estimator_calibration_report_reliability_bins WHERE report_id=NEW.report_id AND metric_key=NEW.metric_key)<>0 OR (SELECT MAX(ordinal) FROM estimator_calibration_report_reliability_bins WHERE report_id=NEW.report_id AND metric_key=NEW.metric_key)<>NEW.reliability_count-1))
 OR (NEW.selective_count>0 AND ((SELECT MIN(ordinal) FROM estimator_calibration_report_selective_points WHERE report_id=NEW.report_id AND metric_key=NEW.metric_key)<>0 OR (SELECT MAX(ordinal) FROM estimator_calibration_report_selective_points WHERE report_id=NEW.report_id AND metric_key=NEW.metric_key)<>NEW.selective_count-1))
 OR (NEW.agreement_count>0 AND ((SELECT MIN(ordinal) FROM estimator_calibration_report_agreement_receipts WHERE report_id=NEW.report_id AND metric_key=NEW.metric_key)<>0 OR (SELECT MAX(ordinal) FROM estimator_calibration_report_agreement_receipts WHERE report_id=NEW.report_id AND metric_key=NEW.metric_key)<>NEW.agreement_count-1))
 OR (NEW.stability_count>0 AND ((SELECT MIN(ordinal) FROM estimator_calibration_report_stability_receipts WHERE report_id=NEW.report_id AND metric_key=NEW.metric_key)<>0 OR (SELECT MAX(ordinal) FROM estimator_calibration_report_stability_receipts WHERE report_id=NEW.report_id AND metric_key=NEW.metric_key)<>NEW.stability_count-1))
 OR (NEW.resource_key_count>0 AND ((SELECT MIN(ordinal) FROM estimator_calibration_report_resource_keys WHERE report_id=NEW.report_id AND metric_key=NEW.metric_key)<>0 OR (SELECT MAX(ordinal) FROM estimator_calibration_report_resource_keys WHERE report_id=NEW.report_id AND metric_key=NEW.metric_key)<>NEW.resource_key_count-1))
 OR (NEW.missingness_count>0 AND ((SELECT MIN(ordinal) FROM estimator_calibration_report_missingness WHERE report_id=NEW.report_id AND metric_key=NEW.metric_key)<>0 OR (SELECT MAX(ordinal) FROM estimator_calibration_report_missingness WHERE report_id=NEW.report_id AND metric_key=NEW.metric_key)<>NEW.missingness_count-1))
BEGIN SELECT RAISE(ABORT,'estimator calibration metric root counts are inconsistent'); END;
CREATE TRIGGER estimator_calibration_report_root_insert_guard BEFORE INSERT ON estimator_calibration_report_roots
WHEN NOT EXISTS (
    SELECT 1 FROM estimator_calibration_report_drafts d
    JOIN estimator_calibration_report_append_authorizations a ON a.report_id=d.report_id AND a.submission_id=d.submission_id AND a.campaign_id=d.campaign_id
    WHERE d.report_id=NEW.report_id AND d.report_fingerprint=NEW.report_fingerprint AND d.definition_fingerprint=NEW.definition_fingerprint
      AND d.metric_count=NEW.metric_count AND d.derived_at_us IS NULL AND d.source_observed_at_us=NEW.derived_at_us
      AND a.authorization_tag=estimator_calibration_report_authorization_tag(a.operation_id,a.report_id,a.submission_id,a.campaign_id))
 OR NEW.metric_count<>(SELECT COUNT(*) FROM estimator_calibration_report_metric_roots WHERE report_id=NEW.report_id)
 OR (SELECT MIN(metric_ordinal) FROM estimator_calibration_report_metric_roots WHERE report_id=NEW.report_id)<>0
 OR (SELECT MAX(metric_ordinal) FROM estimator_calibration_report_metric_roots WHERE report_id=NEW.report_id)<>NEW.metric_count-1
BEGIN SELECT RAISE(ABORT,'estimator calibration report root lineage or counts are inconsistent'); END;
CREATE TRIGGER estimator_calibration_report_root_no_update BEFORE UPDATE ON estimator_calibration_report_roots BEGIN SELECT RAISE(ABORT,'estimator calibration report is immutable'); END;
CREATE TRIGGER estimator_calibration_report_root_no_delete BEFORE DELETE ON estimator_calibration_report_roots
WHEN EXISTS (SELECT 1 FROM estimator_calibration_report_drafts d JOIN estimator_gate_campaigns c ON c.campaign_id=d.campaign_id WHERE d.report_id=OLD.report_id)
BEGIN SELECT RAISE(ABORT,'estimator calibration report requires campaign privacy deletion'); END;
CREATE TRIGGER estimator_calibration_report_draft_no_update BEFORE UPDATE ON estimator_calibration_report_drafts BEGIN SELECT RAISE(ABORT,'estimator calibration report is immutable'); END;
CREATE TRIGGER estimator_calibration_report_draft_no_delete BEFORE DELETE ON estimator_calibration_report_drafts
WHEN EXISTS (SELECT 1 FROM estimator_gate_campaigns c WHERE c.campaign_id=OLD.campaign_id)
BEGIN SELECT RAISE(ABORT,'estimator calibration report requires campaign privacy deletion'); END;

""" + _calibration_report_guards_19() + r"""

CREATE INDEX estimator_calibration_reports_campaign_idx ON estimator_calibration_report_drafts(campaign_id,derived_at_us DESC);
CREATE INDEX estimator_calibration_reports_submission_idx ON estimator_calibration_report_drafts(submission_id);
COMMIT;
"""
