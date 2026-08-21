"""Projection r6 SQLite authority and trajectory attack tests.

Every fixture is synthetic.  The persisted surfaces contain only closed
metadata, counters, fingerprints, and UTC timestamps.
"""

from __future__ import annotations

from datetime import timedelta
import sqlite3

import pytest

from prompt_enhancer.application.analysis.metric_projection_v6 import (
    METRIC_PROJECTION_V6_VERSION,
    project_metric_states_v6,
)
from prompt_enhancer.application.analysis.metric_publication_v2 import (
    publish_metric_states_v2,
)
from prompt_enhancer.application.analysis.requirement_plan_evidence import (
    RequirementPlanEvidenceSnapshot,
)
from prompt_enhancer.application.analysis.semantic_units import (
    SemanticUnitReconciler,
)
from prompt_enhancer.application.analysis.session_model_ensemble import (
    REQUIREMENT_PLAN_AWAITING_REVIEW_FINGERPRINT,
    REQUIREMENT_PLAN_UNAVAILABLE_FINGERPRINT,
    REQUIREMENT_PLAN_UNAVAILABLE_POLICY_VERSION,
    REQUIREMENT_PLAN_UNAVAILABLE_SCHEMA_VERSION,
    RequirementPlanEvidenceSource,
    SessionModelEnsembleOutcome,
    SessionModelEnsembleRunRecord,
    SessionRequirementPlanEvidenceBinding,
)
from prompt_enhancer.database import DatabaseInvariantError
from prompt_enhancer.domain import Provider

from test_model_ensemble_r5_profile_persistence import (
    NOW,
    _STATE_COLUMNS,
    _preset_binding,
    _record,
    _without_predictive,
)
from test_probabilistic_metric_persistence import (
    IDS,
    _context,
    _database_and_session,
)
from test_requirement_plan_evidence_persistence import (
    _confirm,
    _import,
    _payload_with_withdrawal_basis,
    _setup,
)


def _snapshot_fingerprint(snapshot: RequirementPlanEvidenceSnapshot) -> str:
    return IDS.fingerprint(
        "requirement-plan-evidence-snapshot-v1",
        (
            snapshot.session_id,
            snapshot.source_window_fingerprint,
            snapshot.confirmation_id or "none",
            snapshot.proposal_id or "none",
            snapshot.schema_version,
            snapshot.policy_version,
            snapshot.review_rubric_version or "none",
            *(
                ()
                if snapshot.producer_receipt is None
                else (
                    f"producer-kind:{snapshot.producer_receipt.kind}",
                    "producer-claim:"
                    f"{snapshot.producer_receipt.claim_fingerprint}",
                    "producer-authority:"
                    f"{snapshot.producer_receipt.authority}",
                    "producer-raw-claim-persisted:"
                    f"{str(snapshot.producer_receipt.raw_claim_persisted).lower()}",
                )
            ),
            *(
                f"plan:{item.plan_id}:{item.coordinate.message_sequence}:"
                f"{item.coordinate.clause_index}"
                for item in snapshot.plan_items
            ),
            *(
                f"requirement:{item.requirement_id}:"
                f"{item.coordinate.message_sequence}:"
                f"{item.coordinate.clause_index}:{item.disposition.value}:"
                f"{','.join(item.linked_plan_ids)}"
                for item in snapshot.requirements
            ),
            *(
                "excluded-user-clause:"
                f"{item.coordinate.message_sequence}:"
                f"{item.coordinate.clause_index}:{item.reason.value}:"
                f"{('none' if item.basis_coordinate is None else f'{item.basis_coordinate.message_sequence}:{item.basis_coordinate.clause_index}')}"
                for item in snapshot.excluded_user_clauses
            ),
        ),
    )


def _unavailable_binding(
    session_id: str,
    *,
    bound_at=NOW,  # type: ignore[no-untyped-def]
) -> SessionRequirementPlanEvidenceBinding:
    return SessionRequirementPlanEvidenceBinding(
        evidence_source=RequirementPlanEvidenceSource.UNAVAILABLE,
        session_id=session_id,
        source_window_fingerprint="a" * 64,
        evidence_fingerprint=REQUIREMENT_PLAN_UNAVAILABLE_FINGERPRINT,
        evidence_schema_version=REQUIREMENT_PLAN_UNAVAILABLE_SCHEMA_VERSION,
        evidence_policy_version=REQUIREMENT_PLAN_UNAVAILABLE_POLICY_VERSION,
        bound_at=bound_at,
    )


def _reviewed_binding(
    snapshot: RequirementPlanEvidenceSnapshot,
    *,
    bound_at=NOW,  # type: ignore[no-untyped-def]
) -> SessionRequirementPlanEvidenceBinding:
    assert snapshot.confirmation_id is not None
    assert snapshot.proposal_id is not None
    return SessionRequirementPlanEvidenceBinding(
        evidence_source=RequirementPlanEvidenceSource.REVIEWED_REQUIREMENT_PLAN,
        session_id=snapshot.session_id,
        source_window_fingerprint=snapshot.source_window_fingerprint,
        confirmation_id=snapshot.confirmation_id,
        proposal_id=snapshot.proposal_id,
        evidence_fingerprint=_snapshot_fingerprint(snapshot),
        evidence_schema_version=snapshot.schema_version,
        evidence_policy_version=snapshot.policy_version,
        bound_at=bound_at,
    )


def _r6_record(
    session_id: str,
    *,
    run_character: str,
    request_character: str,
    evidence_binding: SessionRequirementPlanEvidenceBinding,
    snapshot: RequirementPlanEvidenceSnapshot | None = None,
    profile_bound_at=NOW,  # type: ignore[no-untyped-def]
) -> SessionModelEnsembleRunRecord:
    context = _context(session_id)
    publication = publish_metric_states_v2(
        project_metric_states_v6(
            context=context,
            reconciliation=SemanticUnitReconciler(IDS).reconcile(
                context
            ).reconciliation,
            id_factory=IDS,
            requirement_plan_evidence=snapshot,
        )
    )
    profile_binding = _preset_binding(session_id).model_copy(
        update={"bound_at": profile_bound_at}
    )
    base = _without_predictive(
        _record(
            session_id,
            run_character=run_character,
            request_character=request_character,
            binding=profile_binding,
        )
    )
    return SessionModelEnsembleRunRecord.model_validate(
        {
            **base.model_dump(),
            "requirement_plan_evidence_binding": evidence_binding.model_dump(),
            "receipt": {
                **base.receipt.model_dump(),
                "metric_publication_v2": publication.model_dump(),
            },
        }
    )


def _reviewed_setup(tmp_path):  # type: ignore[no-untyped-def]
    database, session_id, source, repository, service = _setup(tmp_path)
    proposal = _import(service, session_id, source)
    confirmed = _confirm(service, session_id, source, proposal)
    assert confirmed.decision is not None
    snapshot = repository.snapshot(session_id, source.input_fingerprint)
    return (
        database,
        session_id,
        source,
        repository,
        service,
        snapshot,
        confirmed.decision.decision_id,
    )


def _bare_run(
    source: SessionModelEnsembleRunRecord,
    *,
    run_character: str,
    request_character: str,
) -> SessionModelEnsembleRunRecord:
    return SessionModelEnsembleRunRecord.model_validate(
        {
            **source.model_dump(),
            "run_id": run_character * 64,
            "request_fingerprint": request_character * 64,
            "metric_profile_binding": None,
            "requirement_plan_evidence_binding": None,
            "receipt": {
                **source.receipt.model_dump(),
                "metric_publication_v2": None,
                "predictive_projection": None,
            },
        }
    )


def _copy_profile_binding(  # type: ignore[no-untyped-def]
    connection,
    target_run_id: str,
    source_run_id: str,
) -> None:
    connection.execute(
        """INSERT INTO session_model_ensemble_metric_profile_bindings
           SELECT ?,profile_source,provider,session_id,source_window_fingerprint,
                  profile_id,profile_revision,profile_fingerprint,
                  profile_schema_version,profile_policy_version,bound_at,
                  binding_fingerprint,local_only,content_persisted
           FROM session_model_ensemble_metric_profile_bindings WHERE run_id=?""",
        (target_run_id, source_run_id),
    )


def _copy_requirement_binding(
    connection,
    target_run_id: str,
    source_run_id: str,
) -> None:  # type: ignore[no-untyped-def]
    connection.execute(
        """INSERT INTO session_model_ensemble_requirement_plan_bindings
           SELECT ?,evidence_source,session_id,source_window_fingerprint,
                  confirmation_id,proposal_id,evidence_fingerprint,
                  evidence_schema_version,evidence_policy_version,bound_at,
                  binding_fingerprint,local_only,content_persisted
           FROM session_model_ensemble_requirement_plan_bindings WHERE run_id=?""",
        (target_run_id, source_run_id),
    )


def _copy_state(
    connection,
    *,
    target_table: str,
    target_run_id: str,
    target_projection: str,
    source_run_id: str,
) -> None:  # type: ignore[no-untyped-def]
    connection.execute(
        f"""INSERT INTO {target_table}({_STATE_COLUMNS})
            SELECT ?,metric_ordinal,registry_version,?,metric_key,
                   contract_version,contract_fingerprint,evidence_authority,
                   value_state,explanation_code,numerator,denominator,
                   numeric_value,censoring_lower_bound,censoring_upper_bound,
                   denominator_basis,opportunity_unit_kind,capability_available,
                   source_complete,eligible_count,met_count,not_met_count,
                   pending_count,unknown_count,superseded_excluded_count,
                   distinct_owner_count,product_metric_eligible
            FROM session_model_ensemble_metric_states_v2_r6
            WHERE run_id=? ORDER BY metric_ordinal LIMIT 1""",  # noqa: S608
        (target_run_id, target_projection, source_run_id),
    )


def _trajectory(
    database,
    session_id: str,
    first: SessionModelEnsembleRunRecord,
    second: SessionModelEnsembleRunRecord,
):  # type: ignore[no-untyped-def]
    runs = database.model_ensemble_repository()
    runs.save_completed(first)
    runs.save_completed(second)
    project_id = database.list_sessions(provider=Provider.CODEX, limit=1)[0][
        "project_id"
    ]
    watches = database.model_ensemble_watch_repository()
    watch_id = "6" * 64
    watches.enable(
        watch_id=watch_id,
        provider=Provider.CODEX,
        project_id=project_id,
        session_id=session_id,
        max_messages=100,
        now=NOW,
    )
    claimed = watches.claim_due(
        owner="7" * 64,
        now=NOW,
        lease_duration=timedelta(minutes=30),
    )
    assert claimed is not None
    _, lease = claimed
    watches.complete(
        lease,
        now=NOW + timedelta(seconds=1),
        next_check_at=NOW + timedelta(seconds=2),
        outcome=SessionModelEnsembleOutcome(run=first, applied=True),
    )
    claimed = watches.claim_due(
        owner="7" * 64,
        now=NOW + timedelta(seconds=2),
        lease_duration=timedelta(minutes=30),
    )
    assert claimed is not None
    _, lease = claimed
    watches.complete(
        lease,
        now=NOW + timedelta(seconds=3),
        next_check_at=NOW + timedelta(minutes=2),
        outcome=SessionModelEnsembleOutcome(run=second, applied=True),
    )
    return watches.list_publications(
        watch_id,
        before_generation=None,
        limit=12,
    )


def test_r6_unavailable_binding_round_trips_with_exact_seal(tmp_path) -> None:
    database, session_id = _database_and_session(tmp_path)
    record = _r6_record(
        session_id,
        run_character="f",
        request_character="e",
        evidence_binding=_unavailable_binding(session_id),
    )
    repository = database.model_ensemble_repository()

    repository.save_completed(record)

    loaded = repository.get(record.run_id)
    assert loaded is not None
    assert loaded.requirement_plan_evidence_binding == (
        record.requirement_plan_evidence_binding
    )
    assert loaded.receipt.metric_publication_v2 == record.receipt.metric_publication_v2
    with sqlite3.connect(database.path) as connection:
        assert connection.execute(
            """SELECT requirement_plan_source,requirement_plan_confirmation_id,
                      requirement_plan_evidence_fingerprint
               FROM session_model_ensemble_metric_publication_v2_seals_r6
               WHERE run_id=?""",
            (record.run_id,),
        ).fetchone() == (
            "unavailable",
            None,
            REQUIREMENT_PLAN_UNAVAILABLE_FINGERPRINT,
        )
        assert connection.execute(
            """SELECT COUNT(*) FROM session_model_ensemble_metric_states_v2_r6
               WHERE run_id=?""",
            (record.run_id,),
        ).fetchone()[0] == 20


def test_r6_reviewed_binding_round_trips_with_relational_authority(tmp_path) -> None:
    database, session_id, _source, _repository, _service, snapshot, _head = (
        _reviewed_setup(tmp_path)
    )
    record = _r6_record(
        session_id,
        run_character="b",
        request_character="c",
        evidence_binding=_reviewed_binding(snapshot),
        snapshot=snapshot,
    )
    runs = database.model_ensemble_repository()

    runs.save_completed(record)

    loaded = runs.get(record.run_id)
    assert loaded is not None
    assert loaded.requirement_plan_evidence_binding == (
        record.requirement_plan_evidence_binding
    )
    assert loaded.receipt.metric_publication_v2 == record.receipt.metric_publication_v2
    with sqlite3.connect(database.path) as connection:
        assert connection.execute(
            """SELECT requirement_plan_source,requirement_plan_confirmation_id,
                      requirement_plan_proposal_id,
                      requirement_plan_evidence_fingerprint
               FROM session_model_ensemble_metric_publication_v2_seals_r6
               WHERE run_id=?""",
            (record.run_id,),
        ).fetchone() == (
            "reviewed_requirement_plan",
            snapshot.confirmation_id,
            snapshot.proposal_id,
            _snapshot_fingerprint(snapshot),
        )


@pytest.mark.parametrize(
    "reserved_fingerprint",
    (
        REQUIREMENT_PLAN_UNAVAILABLE_FINGERPRINT,
        REQUIREMENT_PLAN_AWAITING_REVIEW_FINGERPRINT,
    ),
)
def test_reviewed_binding_rejects_reserved_sentinel_at_domain_boundary(
    reserved_fingerprint: str,
) -> None:
    with pytest.raises(
        ValueError,
        match="reviewed requirement-plan authority is incomplete",
    ):
        SessionRequirementPlanEvidenceBinding(
            evidence_source=(
                RequirementPlanEvidenceSource.REVIEWED_REQUIREMENT_PLAN
            ),
            session_id="1" * 64,
            source_window_fingerprint="2" * 64,
            confirmation_id="3" * 64,
            proposal_id="4" * 64,
            evidence_fingerprint=reserved_fingerprint,
            evidence_schema_version="requirement-plan-evidence-v1",
            evidence_policy_version="reviewed-requirement-plan-v1",
            bound_at=NOW,
        )


@pytest.mark.parametrize(
    "reserved_fingerprint",
    (
        REQUIREMENT_PLAN_UNAVAILABLE_FINGERPRINT,
        REQUIREMENT_PLAN_AWAITING_REVIEW_FINGERPRINT,
    ),
)
def test_reviewed_binding_rejects_reserved_sentinel_at_sqlite_boundary(
    tmp_path,
    reserved_fingerprint: str,
) -> None:
    database, session_id, source, _repository, _service, snapshot, _head = (
        _reviewed_setup(tmp_path)
    )
    target = _bare_run(source, run_character="0", request_character="1")
    database.model_ensemble_repository().save_completed(target)
    assert snapshot.confirmation_id is not None
    assert snapshot.proposal_id is not None

    with sqlite3.connect(database.path) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        _copy_profile_binding(connection, target.run_id, source.run_id)
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """INSERT INTO session_model_ensemble_requirement_plan_bindings(
                       run_id,evidence_source,session_id,
                       source_window_fingerprint,confirmation_id,proposal_id,
                       evidence_fingerprint,evidence_schema_version,
                       evidence_policy_version,bound_at,binding_fingerprint,
                       local_only,content_persisted
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,1,0)""",
                (
                    target.run_id,
                    RequirementPlanEvidenceSource.REVIEWED_REQUIREMENT_PLAN.value,
                    session_id,
                    target.input_fingerprint,
                    snapshot.confirmation_id,
                    snapshot.proposal_id,
                    reserved_fingerprint,
                    snapshot.schema_version,
                    snapshot.policy_version,
                    NOW.isoformat(timespec="microseconds"),
                    "5" * 64,
                ),
            )
        assert connection.execute(
            """SELECT COUNT(*)
               FROM session_model_ensemble_requirement_plan_bindings
               WHERE run_id=?""",
            (target.run_id,),
        ).fetchone()[0] == 0


@pytest.mark.parametrize(
    ("legacy_states", "legacy_projection"),
    (
        ("session_model_ensemble_metric_states_v2", "metric-contract-v2-projection-1"),
        (
            "session_model_ensemble_metric_states_v2_r2",
            "metric-contract-v2-projection-2",
        ),
        (
            "session_model_ensemble_metric_states_v2_r3",
            "metric-contract-v2-projection-3",
        ),
        (
            "session_model_ensemble_metric_states_v2_r4",
            "metric-contract-v2-projection-4",
        ),
        (
            "session_model_ensemble_metric_states_v2_r5",
            "metric-contract-v2-projection-5",
        ),
    ),
)
def test_r6_and_r1_to_r5_reject_mixed_identity_in_both_orders(
    tmp_path,
    legacy_states: str,
    legacy_projection: str,
) -> None:
    database, session_id = _database_and_session(tmp_path)
    source = _r6_record(
        session_id,
        run_character="f",
        request_character="e",
        evidence_binding=_unavailable_binding(session_id),
    )
    target = _bare_run(source, run_character="0", request_character="1")
    runs = database.model_ensemble_repository()
    runs.save_completed(source)
    runs.save_completed(target)

    with sqlite3.connect(database.path) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        if legacy_projection == "metric-contract-v2-projection-5":
            _copy_profile_binding(connection, target.run_id, source.run_id)
        _copy_state(
            connection,
            target_table=legacy_states,
            target_run_id=target.run_id,
            target_projection=legacy_projection,
            source_run_id=source.run_id,
        )
        with pytest.raises(sqlite3.IntegrityError, match="identity conflict"):
            if legacy_projection == "metric-contract-v2-projection-5":
                _copy_requirement_binding(connection, target.run_id, source.run_id)
            else:
                _copy_profile_binding(connection, target.run_id, source.run_id)

        with pytest.raises(sqlite3.IntegrityError, match="identity conflict"):
            _copy_state(
                connection,
                target_table=legacy_states,
                target_run_id=source.run_id,
                target_projection=legacy_projection,
                source_run_id=source.run_id,
            )


def test_partial_r6_state_cannot_be_sealed_or_replace_complete_head(tmp_path) -> None:
    database, session_id = _database_and_session(tmp_path)
    source = _r6_record(
        session_id,
        run_character="f",
        request_character="e",
        evidence_binding=_unavailable_binding(session_id),
    )
    partial = _bare_run(source, run_character="0", request_character="1")
    runs = database.model_ensemble_repository()
    runs.save_completed(source)
    runs.save_completed(partial)

    with sqlite3.connect(database.path) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        _copy_profile_binding(connection, partial.run_id, source.run_id)
        _copy_requirement_binding(connection, partial.run_id, source.run_id)
        _copy_state(
            connection,
            target_table="session_model_ensemble_metric_states_v2_r6",
            target_run_id=partial.run_id,
            target_projection=METRIC_PROJECTION_V6_VERSION,
            source_run_id=source.run_id,
        )
        seal_columns = tuple(
            row[1]
            for row in connection.execute(
                "PRAGMA table_info(session_model_ensemble_metric_publication_v2_seals_r6)"
            )
        )
        copied_columns = ",".join(seal_columns[1:])
        with pytest.raises(sqlite3.IntegrityError, match="incomplete"):
            connection.execute(
                f"""INSERT INTO session_model_ensemble_metric_publication_v2_seals_r6
                    SELECT ?,{copied_columns}
                    FROM session_model_ensemble_metric_publication_v2_seals_r6
                    WHERE run_id=?""",  # noqa: S608
                (partial.run_id, source.run_id),
            )
        assert connection.execute(
            """SELECT COUNT(*)
               FROM session_model_ensemble_metric_publication_v2_seals_r6
               WHERE run_id=?""",
            (partial.run_id,),
        ).fetchone()[0] == 0
        assert connection.execute(
            """SELECT COUNT(*) FROM session_model_ensemble_metric_states_v2_r6
               WHERE run_id=?""",
            (partial.run_id,),
        ).fetchone()[0] == 1

    latest = runs.get_latest(session_id)
    assert latest is not None
    assert latest.run_id == source.run_id
    assert latest.receipt.metric_publication_v2 is not None


def test_r6_bindings_states_and_seal_are_immutable_and_tamper_evident(
    tmp_path,
) -> None:
    database, session_id = _database_and_session(tmp_path)
    record = _r6_record(
        session_id,
        run_character="f",
        request_character="e",
        evidence_binding=_unavailable_binding(session_id),
    )
    repository = database.model_ensemble_repository()
    repository.save_completed(record)

    with sqlite3.connect(database.path) as connection:
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute(
                """UPDATE session_model_ensemble_requirement_plan_bindings
                   SET bound_at=bound_at WHERE run_id=?""",
                (record.run_id,),
            )
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute(
                """UPDATE session_model_ensemble_metric_states_v2_r6
                   SET source_complete=source_complete WHERE run_id=?""",
                (record.run_id,),
            )
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute(
                """UPDATE session_model_ensemble_metric_publication_v2_seals_r6
                   SET known_count=known_count WHERE run_id=?""",
                (record.run_id,),
            )

        connection.execute(
            "DROP TRIGGER session_model_ensemble_requirement_plan_bindings_no_update"
        )
        connection.execute(
            """UPDATE session_model_ensemble_requirement_plan_bindings
               SET binding_fingerprint=? WHERE run_id=?""",
            ("f" * 64, record.run_id),
        )
        connection.commit()

    with pytest.raises(
        DatabaseInvariantError,
        match="requirement-plan binding seal is invalid",
    ):
        repository.get(record.run_id)


def test_r6_sidecars_follow_run_and_session_privacy_cascades(tmp_path) -> None:
    database, session_id = _database_and_session(tmp_path)
    first = _r6_record(
        session_id,
        run_character="f",
        request_character="e",
        evidence_binding=_unavailable_binding(session_id),
    )
    repository = database.model_ensemble_repository()
    repository.save_completed(first)

    assert repository.delete_for_privacy(first.run_id) is True
    with sqlite3.connect(database.path) as connection:
        for table in (
            "session_model_ensemble_metric_profile_bindings",
            "session_model_ensemble_requirement_plan_bindings",
            "session_model_ensemble_metric_states_v2_r6",
            "session_model_ensemble_metric_publication_v2_seals_r6",
        ):
            assert connection.execute(
                f"SELECT COUNT(*) FROM {table}"  # noqa: S608 - closed constants
            ).fetchone()[0] == 0

    second = _r6_record(
        session_id,
        run_character="d",
        request_character="c",
        evidence_binding=_unavailable_binding(
            session_id,
            bound_at=NOW + timedelta(minutes=1),
        ),
        profile_bound_at=NOW + timedelta(minutes=1),
    )
    repository.save_completed(second)
    with database._connection() as connection:
        connection.execute("PRAGMA trusted_schema=ON")
        connection.execute("DELETE FROM sessions WHERE session_id=?", (session_id,))
        connection.commit()
        for table in (
            "session_model_ensemble_runs",
            "session_model_ensemble_metric_profile_bindings",
            "session_model_ensemble_requirement_plan_bindings",
            "session_model_ensemble_metric_states_v2_r6",
            "session_model_ensemble_metric_publication_v2_seals_r6",
        ):
            assert connection.execute(
                f"SELECT COUNT(*) FROM {table}"  # noqa: S608 - closed constants
            ).fetchone()[0] == 0
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_source_run_privacy_delete_cascades_confirmed_reviewed_authority(
    tmp_path,
) -> None:
    (
        database,
        session_id,
        source,
        evidence_repository,
        _service,
        snapshot,
        _head,
    ) = _reviewed_setup(tmp_path)
    reviewed = _r6_record(
        session_id,
        run_character="b",
        request_character="c",
        evidence_binding=_reviewed_binding(snapshot),
        snapshot=snapshot,
    )
    runs = database.model_ensemble_repository()
    runs.save_completed(reviewed)

    assert runs.delete_for_privacy(source.run_id) is True

    assert runs.get(source.run_id) is None
    assert runs.get(reviewed.run_id) is None
    assert runs.get_latest(session_id) is None
    empty_snapshot = evidence_repository.snapshot(
        session_id,
        source.input_fingerprint,
    )
    assert empty_snapshot.confirmation_id is None
    assert empty_snapshot.proposal_id is None
    assert empty_snapshot.requirements == ()
    assert empty_snapshot.excluded_user_clauses == ()
    assert empty_snapshot.plan_items == ()
    with sqlite3.connect(database.path) as connection:
        for table in (
            "session_model_ensemble_runs",
            "session_model_ensemble_metric_profile_bindings",
            "session_model_ensemble_requirement_plan_bindings",
            "session_model_ensemble_metric_states_v2_r6",
            "session_model_ensemble_metric_publication_v2_seals_r6",
            "requirement_plan_evidence_proposals",
            "requirement_plan_evidence_requirements",
            "requirement_plan_evidence_excluded_user_clauses",
            "requirement_plan_evidence_plans",
            "requirement_plan_evidence_links",
            "requirement_plan_evidence_proposal_seals",
            "requirement_plan_evidence_decisions",
        ):
            assert connection.execute(
                f"SELECT COUNT(*) FROM {table}"  # noqa: S608 - closed constants
            ).fetchone()[0] == 0
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_direct_session_delete_cascades_confirmed_reviewed_r6_graph(
    tmp_path,
) -> None:
    (
        database,
        session_id,
        _source,
        evidence_repository,
        _service,
        snapshot,
        _head,
    ) = _reviewed_setup(tmp_path)
    reviewed = _r6_record(
        session_id,
        run_character="b",
        request_character="c",
        evidence_binding=_reviewed_binding(snapshot),
        snapshot=snapshot,
    )
    database.model_ensemble_repository().save_completed(reviewed)

    with database._connection() as connection:
        connection.execute("PRAGMA trusted_schema=ON")
        connection.execute("DELETE FROM sessions WHERE session_id=?", (session_id,))
        connection.commit()
        for table in (
            "session_model_ensemble_runs",
            "session_model_ensemble_metric_profile_bindings",
            "session_model_ensemble_requirement_plan_bindings",
            "session_model_ensemble_metric_states_v2_r6",
            "session_model_ensemble_metric_publication_v2_seals_r6",
            "requirement_plan_evidence_proposals",
            "requirement_plan_evidence_requirements",
            "requirement_plan_evidence_excluded_user_clauses",
            "requirement_plan_evidence_plans",
            "requirement_plan_evidence_links",
            "requirement_plan_evidence_proposal_seals",
            "requirement_plan_evidence_decisions",
        ):
            assert connection.execute(
                f"SELECT COUNT(*) FROM {table}"  # noqa: S608 - closed constants
            ).fetchone()[0] == 0
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []

    empty_snapshot = evidence_repository.snapshot(
        session_id,
        reviewed.input_fingerprint,
    )
    assert empty_snapshot.confirmation_id is None
    assert empty_snapshot.requirements == ()
    assert empty_snapshot.excluded_user_clauses == ()


def test_same_reviewed_authority_remains_watch_comparable_across_fresh_seals(
    tmp_path,
) -> None:
    database, session_id, _source, _repository, _service, snapshot, _head = (
        _reviewed_setup(tmp_path)
    )
    first = _r6_record(
        session_id,
        run_character="b",
        request_character="c",
        evidence_binding=_reviewed_binding(snapshot),
        snapshot=snapshot,
    )
    second = _r6_record(
        session_id,
        run_character="d",
        request_character="e",
        evidence_binding=_reviewed_binding(
            snapshot,
            bound_at=NOW + timedelta(seconds=30),
        ),
        snapshot=snapshot,
        profile_bound_at=NOW + timedelta(seconds=30),
    )

    trajectory = _trajectory(database, session_id, first, second)

    with sqlite3.connect(database.path) as connection:
        fingerprints = connection.execute(
            """SELECT requirement_plan_binding_fingerprint,
                      publication_requirement_plan_fingerprint
               FROM session_model_ensemble_metric_publication_v2_seals_r6
               WHERE run_id IN (?,?) ORDER BY run_id""",
            (first.run_id, second.run_id),
        ).fetchall()
    assert len({row[0] for row in fingerprints}) == 2
    assert len({row[1] for row in fingerprints}) == 2
    assert trajectory.points[0].comparable_to_head is True
    assert trajectory.points[1].comparable_to_head is True


def test_changed_reviewed_authority_breaks_watch_comparability(tmp_path) -> None:
    (
        database,
        session_id,
        source,
        repository,
        service,
        first_snapshot,
        first_decision_id,
    ) = _reviewed_setup(tmp_path)
    second_proposal = _import(
        service,
        session_id,
        source,
        predecessor=first_decision_id,
        suffix="0002",
        payload=_payload_with_withdrawal_basis(
            session_id,
            source,
            predecessor=first_decision_id,
        ),
    )
    _confirm(service, session_id, source, second_proposal, suffix="0002")
    second_snapshot = repository.snapshot(session_id, source.input_fingerprint)
    assert second_snapshot.confirmation_id != first_snapshot.confirmation_id
    assert second_snapshot.excluded_user_clauses != (
        first_snapshot.excluded_user_clauses
    )
    assert second_snapshot.excluded_user_clauses[0].reason.value == "withdrawn"
    assert second_snapshot.excluded_user_clauses[0].basis_coordinate is not None
    assert _snapshot_fingerprint(second_snapshot) != _snapshot_fingerprint(first_snapshot)
    first = _r6_record(
        session_id,
        run_character="b",
        request_character="c",
        evidence_binding=_reviewed_binding(first_snapshot),
        snapshot=first_snapshot,
    )
    second = _r6_record(
        session_id,
        run_character="d",
        request_character="e",
        evidence_binding=_reviewed_binding(
            second_snapshot,
            bound_at=NOW + timedelta(minutes=2),
        ),
        snapshot=second_snapshot,
        profile_bound_at=NOW + timedelta(minutes=2),
    )

    trajectory = _trajectory(database, session_id, first, second)

    assert trajectory.points[0].comparable_to_head is True
    assert trajectory.points[1].comparable_to_head is False
