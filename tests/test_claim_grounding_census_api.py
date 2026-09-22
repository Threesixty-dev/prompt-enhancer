from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from prompt_enhancer.api import API_TOKEN_HEADER, create_app
from prompt_enhancer.application.analysis.claim_grounding_census import (
    ClaimGroundingCensusPageSnapshot, ClaimGroundingCensusRecord,
    DurableClaimGroundingCensusService, ClaimGroundingCensusOutcomeUnknownError,
)
from prompt_enhancer.application.analysis.claim_grounding_review import (
    ClaimGroundingReviewService, CurrentClaimGroundingSourceResolver,
)
from prompt_enhancer.application.analysis.requirement_plan_evidence import InMemoryRequirementPlanReviewContextStore
from prompt_enhancer.database import Database
from prompt_enhancer.infrastructure.sqlite.claim_grounding_census import SqliteClaimGroundingCensusRepository
from prompt_enhancer.config import AppSettings

from test_claim_grounding_review_api import SESSION, TOKEN, _review_service
from test_claim_grounding_review import _Ids, RUN, WINDOW
from test_claim_grounding_census_repository import _r8_record, _r8_setup
from test_model_ensemble_r8_persistence import _projection_context
from test_requirement_plan_evidence_persistence import ARTIFACT_IDS


class _LatestAuthority:
    def __init__(self, runs) -> None: self.runs = runs  # type: ignore[no-untyped-def]
    def expected_publication_fingerprint(self, *, session_id: str, source_run_id: str, source_window_fingerprint: str) -> str:
        from prompt_enhancer.application.analysis.metric_publication_v2 import metric_publication_v2_fingerprint
        latest = self.runs.get_latest(session_id)
        if latest is None or latest.session_id != session_id or latest.run_id != source_run_id or latest.input_fingerprint != source_window_fingerprint or latest.receipt.metric_publication_v2 is None:
            raise ValueError("synthetic source unavailable")
        return metric_publication_v2_fingerprint(latest.receipt.metric_publication_v2)


def _sqlite_service(database: Database, run, context):  # type: ignore[no-untyped-def]
    contexts = InMemoryRequirementPlanReviewContextStore()
    contexts.publish(run.run_id, context)
    reviews = ClaimGroundingReviewService(CurrentClaimGroundingSourceResolver(database.model_ensemble_repository(), contexts, ARTIFACT_IDS), ARTIFACT_IDS)
    census = DurableClaimGroundingCensusService(reviews, SqliteClaimGroundingCensusRepository(database._connection, database.initialize, identifiers=ARTIFACT_IDS), _LatestAuthority(database.model_ensemble_repository()), ARTIFACT_IDS)
    return reviews, census


class _MemoryCensuses:
    def __init__(self) -> None: self.rows: dict[str, ClaimGroundingCensusRecord] = {}
    def issue(self, **values):  # type: ignore[no-untyped-def]
        current = self.rows.get(values["census_id"])
        if current is not None: return current, False
        row = ClaimGroundingCensusRecord(values["census_id"], values["census"], values["manifest"], values["idempotency_key_digest"], values["command_fingerprint"], values["expected_publication_fingerprint"], values["created_at"])
        self.rows[row.census_id] = row
        return row, True
    def get(self, census_id: str): return self.rows.get(census_id)
    def get_by_idempotency(self, *, session_id: str, idempotency_key_digest: str):
        return next((x for x in self.rows.values() if x.census.session_id == session_id and x.idempotency_key_digest == idempotency_key_digest), None)
    def list_page(self, session_id: str, *, limit: int, offset: int, snapshot=None):  # type: ignore[no-untyped-def]
        rows = tuple(x for x in self.rows.values() if x.census.session_id == session_id)
        snap = snapshot or ClaimGroundingCensusPageSnapshot(
            "a" * 64, len(rows), None if not rows else rows[0].created_at,
            None if not rows else rows[0].census_id,
        )
        return rows[offset:offset + limit], snap


class _Authority:
    def expected_publication_fingerprint(self, **_values):  # type: ignore[no-untyped-def]
        return "f" * 64


def test_native_gated_durable_persist_and_recovery_are_metadata_only(tmp_path) -> None:
    reviews = _review_service()
    service = DurableClaimGroundingCensusService(reviews, _MemoryCensuses(), _Authority(), _Ids(), clock=lambda: datetime(2026, 1, 1, tzinfo=UTC))
    app = create_app(settings=AppSettings(home=tmp_path), api_token=TOKEN, claim_grounding_review_service=reviews, claim_grounding_census_service=service, user_presence_confirmation=lambda _request, _body: None)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        denied = client.post(f"/v1/sessions/{SESSION}/claim-grounding-review/persist", headers={API_TOKEN_HEADER: TOKEN, "Content-Type": "application/json", "Idempotency-Key": "a" * 16}, json={})
        assert denied.status_code == 403
        browser = client.get("/auth/session")
        headers = {"Origin": "http://127.0.0.1", "X-Prompt-Enhancer-CSRF": browser.json()["csrf_token"], "Idempotency-Key": "a" * 16}
        opened = client.post(f"/v1/sessions/{SESSION}/claim-grounding-review/begin", headers=headers, json={"expected_source_run_id": RUN, "expected_source_window_fingerprint": WINDOW}).json()
        payload = {"review_receipt_id": opened["review_receipt_id"], "review_fingerprint": opened["review_fingerprint"], "manifest_fingerprint": opened["manifest"]["manifest_fingerprint"], "classifications": [{"candidate_id": x["candidate_id"], "classification": "material_claim"} for x in opened["candidates"]]}
        saved = client.post(f"/v1/sessions/{SESSION}/claim-grounding-review/persist", headers=headers, json=payload)
        assert saved.status_code == 200, saved.text
        body = saved.json()
        assert body["metadata_persisted"] is True and body["candidate_prose_persisted"] is False
        assert body["proposal_only"] is True and body["measured"] is False
        assert body["metric_authority_established"] is False
        assert "idempotency_key_digest" not in body and "classifications" not in body
        recovery = client.get(f"/v1/sessions/{SESSION}/claim-grounding-review/recovery-status", headers=headers)
        assert recovery.status_code == 200 and recovery.json()["census_id"] == body["census_id"]
        got = client.get(f"/v1/sessions/{SESSION}/claim-grounding-review/saved-census/{body['census_id']}", headers=headers)
        assert got.status_code == 200
        other = client.get(f"/v1/sessions/{'9' * 64}/claim-grounding-review/saved-census/{body['census_id']}", headers=headers)
        assert other.status_code == 404
        listed = client.get(f"/v1/sessions/{SESSION}/claim-grounding-review/saved-censuses", headers=headers)
        page = listed.json()
        replay_page = client.get(f"/v1/sessions/{SESSION}/claim-grounding-review/saved-censuses", headers=headers, params={"offset": 0, "snapshot_id": page["snapshot_id"], "snapshot_total": page["total"], "high_water_created_at": page["high_water_created_at"], "high_water_census_id": page["high_water_census_id"]})
    assert listed.status_code == 200 and listed.json()["total"] == 1
    assert replay_page.status_code == 200 and replay_page.json()["snapshot_id"] == page["snapshot_id"]


def test_empty_snapshot_round_trips(tmp_path) -> None:
    service = type("S", (), {"list_page": lambda _self, _session, **values: ((), values["snapshot"] or ClaimGroundingCensusPageSnapshot("b" * 64, 0, None, None))})()
    app = create_app(settings=AppSettings(home=tmp_path), api_token=TOKEN, claim_grounding_census_service=service)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        first = client.get(f"/v1/sessions/{SESSION}/claim-grounding-review/saved-censuses", headers={API_TOKEN_HEADER: TOKEN})
        assert first.status_code == 200
        replay = client.get(f"/v1/sessions/{SESSION}/claim-grounding-review/saved-censuses", headers={API_TOKEN_HEADER: TOKEN}, params={"snapshot_id": "b" * 64, "snapshot_total": 0})
    assert replay.status_code == 200 and replay.json()["total"] == 0


def test_real_sqlite_http_persist_replay_and_restart_recovery(tmp_path) -> None:
    database, source, plan, action, _verification_service, verification = _r8_setup(tmp_path)
    run = _r8_record(source.session_id, run_character="f", request_character="1", plan_snapshot=plan, action_snapshot=action, verification_snapshot=verification)
    database.model_ensemble_repository().save_completed(run)
    reviews, census = _sqlite_service(database, run, _projection_context(source.session_id))
    app = create_app(settings=AppSettings(home=tmp_path), api_token=TOKEN, database=database, claim_grounding_review_service=reviews, claim_grounding_census_service=census, user_presence_confirmation=lambda _request, _body: None)
    key = "k" * 16
    with TestClient(app, base_url="http://127.0.0.1") as client:
        browser = client.get("/auth/session")
        headers = {"Origin": "http://127.0.0.1", "X-Prompt-Enhancer-CSRF": browser.json()["csrf_token"], "Idempotency-Key": key}
        begin = client.post(f"/v1/sessions/{source.session_id}/claim-grounding-review/begin", headers=headers, json={"expected_source_run_id": run.run_id, "expected_source_window_fingerprint": run.input_fingerprint})
        assert begin.status_code == 200
        opened = begin.json()
        payload = {"review_receipt_id": opened["review_receipt_id"], "review_fingerprint": opened["review_fingerprint"], "manifest_fingerprint": opened["manifest"]["manifest_fingerprint"], "classifications": [{"candidate_id": item["candidate_id"], "classification": "material_claim"} for item in opened["candidates"]]}
        created = client.post(f"/v1/sessions/{source.session_id}/claim-grounding-review/persist", headers=headers, json=payload)
        assert created.status_code == 200
        replay = client.post(f"/v1/sessions/{source.session_id}/claim-grounding-review/persist", headers=headers, json=payload)
        assert replay.status_code == 200 and replay.json()["census_id"] == created.json()["census_id"]
    with database._connection(readonly=True) as connection:
        assert connection.execute("SELECT COUNT(*) FROM claim_grounding_reviewed_censuses").fetchone()[0] == 1
    restarted = Database(database.path); restarted.configure_local_artifact_id_factory(ARTIFACT_IDS)
    restart_reviews, restart_census = _sqlite_service(restarted, run, _projection_context(source.session_id))
    restarted_app = create_app(settings=AppSettings(home=tmp_path), api_token=TOKEN, database=restarted, claim_grounding_review_service=restart_reviews, claim_grounding_census_service=restart_census, user_presence_confirmation=lambda _request, _body: None)
    with TestClient(restarted_app, base_url="http://127.0.0.1") as client:
        recovered = client.get(f"/v1/sessions/{source.session_id}/claim-grounding-review/recovery-status", headers={API_TOKEN_HEADER: TOKEN, "Idempotency-Key": key})
        other = client.get(f"/v1/sessions/{'a' * 64}/claim-grounding-review/recovery-status", headers={API_TOKEN_HEADER: TOKEN, "Idempotency-Key": key})
    assert recovered.status_code == 200 and recovered.json()["census_id"] == created.json()["census_id"]
    assert other.status_code == 404


def test_real_sqlite_stale_source_persist_leaves_no_record(tmp_path) -> None:
    database, source, plan, action, _verification_service, verification = _r8_setup(tmp_path)
    first = _r8_record(source.session_id, run_character="f", request_character="1", plan_snapshot=plan, action_snapshot=action, verification_snapshot=verification)
    database.model_ensemble_repository().save_completed(first)
    reviews, census = _sqlite_service(database, first, _projection_context(source.session_id))
    app = create_app(settings=AppSettings(home=tmp_path), api_token=TOKEN, database=database, claim_grounding_review_service=reviews, claim_grounding_census_service=census, user_presence_confirmation=lambda _request, _body: None)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        browser = client.get("/auth/session")
        headers = {"Origin": "http://127.0.0.1", "X-Prompt-Enhancer-CSRF": browser.json()["csrf_token"], "Idempotency-Key": "s" * 16}
        opened = client.post(f"/v1/sessions/{source.session_id}/claim-grounding-review/begin", headers=headers, json={"expected_source_run_id": first.run_id, "expected_source_window_fingerprint": first.input_fingerprint}).json()
        newer = _r8_record(source.session_id, run_character="d", request_character="4", plan_snapshot=plan, action_snapshot=action, verification_snapshot=verification)
        newer = newer.model_copy(update={"receipt": newer.receipt.model_copy(update={"completed_at": first.receipt.completed_at + timedelta(minutes=1)})})
        database.model_ensemble_repository().save_completed(newer)
        payload = {"review_receipt_id": opened["review_receipt_id"], "review_fingerprint": opened["review_fingerprint"], "manifest_fingerprint": opened["manifest"]["manifest_fingerprint"], "classifications": [{"candidate_id": item["candidate_id"], "classification": "material_claim"} for item in opened["candidates"]]}
        response = client.post(f"/v1/sessions/{source.session_id}/claim-grounding-review/persist", headers=headers, json=payload)
    assert response.status_code == 409 and response.json()["detail"]["code"] == "claim_grounding_census_conflict"
    with database._connection(readonly=True) as connection:
        assert connection.execute("SELECT COUNT(*) FROM claim_grounding_reviewed_censuses").fetchone()[0] == 0


def test_persist_preflight_and_unknown_outcome_are_closed_and_private(tmp_path) -> None:
    calls: list[bytes] = []
    class _Unknown:
        def consume_and_issue(self, **_values):  # type: ignore[no-untyped-def]
            raise ClaimGroundingCensusOutcomeUnknownError("synthetic")
    app = create_app(settings=AppSettings(home=tmp_path), api_token=TOKEN, claim_grounding_census_service=_Unknown(), user_presence_confirmation=lambda _request, body: calls.append(body))
    endpoint = f"/v1/sessions/{SESSION}/claim-grounding-review/persist"
    with TestClient(app, base_url="http://127.0.0.1") as client:
        browser = client.get("/auth/session")
        headers = {"Origin": "http://127.0.0.1", "X-Prompt-Enhancer-CSRF": browser.json()["csrf_token"], "Idempotency-Key": "u" * 16, "Content-Type": "application/json"}
        oversized = client.post(endpoint, headers=headers, content=b"{" + b"x" * (4 * 1_048_576))
        assert oversized.status_code == 413 and oversized.headers["cache-control"] == "no-store, private"
        unknown = client.post(endpoint, headers=headers, json={"review_receipt_id": "1" * 64, "review_fingerprint": "2" * 64, "manifest_fingerprint": "3" * 64, "classifications": []})
    assert len(calls) == 1 and len(calls[0]) < 1_000
    assert unknown.status_code == 409
    assert unknown.json()["detail"] == {"code": "claim_grounding_census_recovery_required", "message": "claim-grounding census recovery is required"}
    assert unknown.headers["cache-control"] == "no-store, private"
