"""Transactional private storage. No provider sessions or application tables."""

from __future__ import annotations

import json
import os
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from .definitions import CoreImage, Definition, Overrides, Publication, canonical, configuration_summary, definition_payload, effective_settings, fingerprint
from .errors import BenchError
from .history import RunFilters, model_options, predicate, summarize
from .recovery import failure_summary

TERMINAL = {"succeeded", "failed", "cancelled", "interrupted", "superseded"}


class Store:
    def __init__(self, path: Path, *, core_variant: str = "default"):
        if core_variant not in {"default", "models"}:
            raise BenchError("unsupported_build_variant")
        self.core_variant = core_variant
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with self.connection() as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1, 2, 3):
                raise BenchError("unsupported_database_schema", 503)
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("BEGIN IMMEDIATE;\n" + Path(__file__).with_name("schema.sql").read_text())
            if version == 1:
                # Retain legacy registrations without rewriting any definition or run.
                for row in db.execute("SELECT body,image,created FROM definitions ORDER BY created DESC,stable_id,revision"):
                    db.execute("INSERT OR IGNORE INTO core_images VALUES(?,?,?,?,?)",
                               (json.loads(row["body"])["enhancerVersion"], self.core_variant,
                                row["image"], None, row["created"]))
            db.execute("""INSERT OR IGNORE INTO core_artifacts
                SELECT core_version,variant,image,receipt,registered FROM core_images WHERE receipt IS NOT NULL""")
            db.execute("PRAGMA user_version=3")
            db.commit()
        os.chmod(self.path, 0o600)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            yield db
        finally:
            db.close()

    @contextmanager
    def transaction(self):
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                yield db
                db.commit()
            except BaseException:
                db.rollback()
                raise

    def _event(self, db, run_id, state, code=None, attempt_id=None):
        db.execute("INSERT INTO events(run_id,attempt_id,state,code,created) VALUES(?,?,?,?,?)",
                   (run_id, attempt_id, state, code, time.time()))

    def register_core_image(self, artifact: CoreImage) -> dict:
        with self.transaction() as db:
            previous = db.execute("SELECT image,receipt FROM core_images WHERE core_version=? AND variant=?",
                                  (artifact.coreVersion, artifact.variant)).fetchone()
            if previous and previous["receipt"]:
                receipt = json.loads(previous["receipt"])
                if receipt["buildInputSha256"] != artifact.buildInputSha256:
                    raise BenchError("core_version_reused_for_changed_code", 409)
                if previous["image"] == artifact.image:
                    return {"registered": False, "coreVersion": artifact.coreVersion, "variant": artifact.variant}
            db.execute("""INSERT INTO core_images VALUES(?,?,?,?,?)
                ON CONFLICT(core_version,variant) DO UPDATE SET
                image=excluded.image,receipt=excluded.receipt,registered=excluded.registered""",
                       (artifact.coreVersion, artifact.variant, artifact.image,
                        artifact.model_dump_json(), time.time()))
            db.execute("INSERT OR IGNORE INTO core_artifacts VALUES(?,?,?,?,?)",
                       (artifact.coreVersion, artifact.variant, artifact.image,
                        artifact.model_dump_json(), time.time()))
        return {"registered": True, "coreVersion": artifact.coreVersion, "variant": artifact.variant}

    def import_publication(self, publication: Publication) -> dict:
        definition = publication.definition
        payload = definition_payload(definition)
        body = canonical(payload)
        spec_hash = (fingerprint(payload) if publication.schemaVersion == "bench-publication/v2"
                     else fingerprint(publication.model_dump() | {"definition": payload}))
        with self.transaction() as db:
            existing = db.execute("SELECT * FROM definitions WHERE stable_id=? AND revision=?",
                                  (definition.stableId, definition.revision)).fetchone()
            if existing:
                if canonical(definition_payload(Definition.model_validate_json(existing["body"]))) != body:
                    raise BenchError("immutable_revision_conflict", 409)
                run = db.execute("SELECT id FROM runs WHERE stable_id=? AND revision=? AND origin='gitops'",
                                 (definition.stableId, definition.revision)).fetchone()
                return {"imported": False, "runId": run["id"] if run else None}
            if db.execute("SELECT 1 FROM definitions WHERE stable_id=? AND generation=?",
                          (definition.stableId, definition.generation)).fetchone():
                raise BenchError("generation_conflict", 409)
            pinned_image = self._resolve_core(db, definition) if definition.coreBuild else publication.image
            db.execute("INSERT INTO definitions VALUES(?,?,?,?,?,?,?,?)",
                       (definition.stableId, definition.revision, definition.generation,
                        spec_hash, body, pinned_image or "", definition.autoRun, time.time()))
            if publication.image is not None:
                # Old publishers can bootstrap a version, never replace a newer release.
                db.execute("INSERT OR IGNORE INTO core_images VALUES(?,?,?,?,?)",
                           (definition.enhancerVersion, self.core_variant, publication.image, None, time.time()))
            latest = db.execute("SELECT MAX(generation) FROM definitions WHERE stable_id=? AND auto_run=1",
                                (definition.stableId,)).fetchone()[0]
            run_id = None
            if definition.autoRun and definition.generation == latest:
                stale = db.execute("SELECT id FROM runs WHERE stable_id=? AND generation<? AND origin='gitops' AND status='queued'",
                                   (definition.stableId, latest)).fetchall()
                for row in stale:
                    self._finish(db, row["id"], "superseded", "newer_eligible_definition")
                run_id = self._enqueue(db, definition, Overrides(), "gitops",
                                       f"auto:{definition.stableId}:{definition.revision}", None)
            return {"imported": True, "runId": run_id}

    def _enqueue(self, db, definition, overrides, origin, request_key, retry_of):
        effective = effective_settings(definition, overrides)
        previous = db.execute("SELECT id,request_hash,image FROM runs WHERE request_key=?", (request_key,)).fetchone()
        if previous:
            # Preserve v1 request hashes and retries even after the catalog changes.
            digest = fingerprint({"effective": effective, "image": previous["image"], "retryOf": retry_of})
            if previous["request_hash"] != digest:
                raise BenchError("idempotency_conflict", 409)
            return previous["id"]
        image = self._resolve_core(db, definition)
        digest = fingerprint({"effective": effective, "image": image, "retryOf": retry_of})
        run_id, correlation_id = str(uuid.uuid4()), str(uuid.uuid4())
        db.execute("""INSERT INTO runs(id,correlation_id,stable_id,revision,generation,origin,
          request_key,request_hash,retry_of,effective,image,status,created)
          VALUES(?,?,?,?,?,?,?,?,?,?,?,'queued',?)""",
                   (run_id, correlation_id, definition.stableId, definition.revision,
                    definition.generation, origin, request_key, digest, retry_of,
                    canonical(effective), image, time.time()))
        position = 0
        for subject in effective["subjects"]:
            for unit in effective["units"]:
                db.execute("INSERT INTO attempts(id,run_id,unit_id,subject_id,position) VALUES(?,?,?,?,?)",
                           (str(uuid.uuid4()), run_id, unit["id"], subject["id"], position))
                position += 1
        self._event(db, run_id, "queued")
        return run_id

    def _resolve_core(self, db, definition):
        if definition.coreBuild:
            build = definition.coreBuild
            if build.variant != self.core_variant:
                raise BenchError("core_image_variant_mismatch", 409)
            artifact = db.execute("SELECT receipt FROM core_artifacts WHERE core_version=? AND variant=? AND image=?",
                (definition.enhancerVersion, build.variant, build.image)).fetchone()
            if artifact is None:
                raise BenchError("pinned_core_build_unavailable", 409)
            if json.loads(artifact["receipt"])["buildInputSha256"] != build.buildInputSha256:
                raise BenchError("pinned_core_build_mismatch", 409)
            return build.image
        artifact = db.execute("SELECT image FROM core_images WHERE core_version=? AND variant=?",
                              (definition.enhancerVersion, self.core_variant)).fetchone()
        if artifact is None:
            raise BenchError("core_version_unavailable", 409)
        return artifact["image"]

    def enqueue_ui(self, stable_id: str, revision: str, overrides: Overrides,
                   request_id: str, retry_of: str | None = None) -> str:
        try:
            request_id = str(uuid.UUID(request_id))
        except (ValueError, TypeError, AttributeError):
            raise BenchError("invalid_request_id") from None
        with self.transaction() as db:
            row = db.execute("SELECT * FROM definitions WHERE stable_id=? AND revision=?",
                             (stable_id, revision)).fetchone()
            if row is None:
                raise BenchError("definition_not_found", 404)
            if retry_of:
                parent = db.execute("SELECT * FROM runs WHERE id=?", (retry_of,)).fetchone()
                if (parent is None or parent["stable_id"] != stable_id or parent["revision"] != revision
                        or parent["status"] not in TERMINAL or parent["cleanup_pending"] or parent["reconciliation_required"]):
                    raise BenchError("retry_requires_reconciled_terminal_run", 409)
            return self._enqueue(db, Definition.model_validate_json(row["body"]),
                                 overrides, "ui", f"ui:{request_id}", retry_of)

    def preflight(self, definition: Definition, effective: dict) -> dict:
        with self.connection() as db:
            db.execute("BEGIN")
            image = self._resolve_core(db, definition)
            counts = db.execute("""SELECT
                COUNT(CASE WHEN status='queued' THEN 1 END) AS queued,
                COUNT(CASE WHEN status='running' THEN 1 END) AS running,
                COUNT(CASE WHEN cleanup_pending=1 THEN 1 END) AS cleanup,
                COUNT(CASE WHEN reconciliation_required=1 THEN 1 END) AS reconciliation
                FROM runs""").fetchone()
        return {"schemaVersion": "bench-preflight/v1", "valid": True,
                "stableId": definition.stableId, "revision": definition.revision,
                "attemptCount": len(effective["subjects"]) * len(effective["units"]),
                "coreVersion": definition.enhancerVersion, "image": image,
                "checks": {"definition": "passed", "requests": "passed", "coreArtifact": "registered",
                           "workerLiveness": "unverified", "providerAuthentication": "unverified",
                           "modelReadiness": "unverified"},
                "queue": dict(counts), "executionReadiness": "unverified"}

    def definitions(self) -> list[dict]:
        with self.connection() as db:
            rows = db.execute("SELECT * FROM definitions ORDER BY stable_id,generation DESC").fetchall()
        return [{**json.loads(r["body"]), "specHash": r["spec_hash"]} for r in rows]

    def runs(self, limit: int = 100, *, before: str | None = None, filters: RunFilters | None = None) -> list[dict]:
        with self.connection() as db:
            db.execute("BEGIN")
            return self._runs(db, limit, before, filters or RunFilters())

    def run_history(self, limit: int, before: str | None, filters: RunFilters) -> dict:
        with self.connection() as db:
            db.execute("BEGIN")
            rows = self._runs(db, limit + 1, before, filters)
            where, parameters = predicate(filters)
            return {"runs": rows[:limit], "nextCursor": rows[limit - 1]["id"] if len(rows) > limit else None,
                    "summary": summarize(db, filters, where, parameters),
                    "modelOptions": model_options(db, filters)}

    def _runs(self, db, limit, before, filters):
        where, parameters = predicate(filters)
        if before is not None:
            cursor = db.execute("SELECT created,id FROM runs WHERE id=?", (before,)).fetchone()
            if cursor is None:
                raise BenchError("invalid_run_cursor")
            where += " AND (r.created,r.id) < (?,?)"
            parameters.extend([cursor["created"], cursor["id"]])
        rows = db.execute("SELECT r.id,r.correlation_id,r.stable_id,r.revision,r.generation,r.origin,r.retry_of,r.status,r.assertion_outcome,r.cancel_requested,r.cleanup_pending,r.reconciliation_required,r.error_code,r.created,r.started,r.finished,r.effective FROM runs r WHERE "
                          + where + " ORDER BY r.created DESC,r.id DESC LIMIT ?",
                          (*parameters, min(max(limit, 1), 500))).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["configuration"] = configuration_summary(json.loads(item.pop("effective")))
            item["failure"] = self._failure_summary(db, item)
            result.append(item)
        return result

    def _failure_summary(self, db, run):
        # Project only diagnostics; history does not load prompts or model replies.
        row = db.execute("""SELECT id,subject_id,unit_id,position,status,error_code,
            json_object('stage',json_extract(progress,'$.stage')) AS progress,
            json_object('errors',json_extract(result,'$.errors'),
                        'workflow_result',json_object('review',json_object('state',
                            json_extract(result,'$.workflow_result.review.state')))) AS result
            FROM attempts WHERE run_id=? AND (status IN ('failed','interrupted')
                OR json_array_length(json_extract(result,'$.errors'))>0
                OR json_extract(result,'$.workflow_result.review.state') IN ('reply_invalid','model_error'))
            ORDER BY position LIMIT 1""", (run["id"],)).fetchone()
        attempts = []
        if row:
            item = dict(row)
            for key in ("result", "progress"):
                item[key] = json.loads(item[key])
            attempts.append(item)
        return failure_summary(run | {"attempts": attempts})

    def recovery_queue(self):
        with self.connection() as db:
            db.execute("BEGIN")
            where = "status NOT IN ('queued','running') AND (cleanup_pending=1 OR reconciliation_required=1)"
            total = db.execute("SELECT COUNT(*) FROM runs WHERE " + where).fetchone()[0]
            rows = db.execute("SELECT id,stable_id,revision,status,error_code,started,finished,cleanup_pending,reconciliation_required FROM runs WHERE "
                              + where + " ORDER BY created,id LIMIT 100").fetchall()
            blockers = []
            for row in rows:
                item = dict(row)
                item["failure"] = self._failure_summary(db, item)
                blockers.append(item)
            return {"schemaVersion": "bench-recovery-queue/v1", "blocked": bool(total),
                    "total": total, "truncated": total > len(blockers), "runs": blockers}

    def run(self, run_id: str) -> dict:
        with self.connection() as db:
            db.execute("BEGIN")
            row = db.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
            if row is None:
                raise BenchError("run_not_found", 404)
            result = dict(row)
            result["effective"] = json.loads(result["effective"])
            result["attempts"] = []
            for attempt in db.execute("SELECT * FROM attempts WHERE run_id=? ORDER BY position", (run_id,)):
                item = dict(attempt)
                for key in ("request", "result", "progress"):
                    item[key] = json.loads(item[key]) if item[key] is not None else None
                result["attempts"].append(item)
            result["events"] = [dict(e) for e in db.execute("SELECT * FROM events WHERE run_id=? ORDER BY sequence", (run_id,))]
            for key, table in (("cleanup_check", "cleanup_checks"), ("reconciliation", "reconciliations")):
                receipt = db.execute("SELECT * FROM " + table + " WHERE run_id=?", (run_id,)).fetchone()
                result[key] = dict(receipt) if receipt else None
        return result

    def claim(self) -> dict | None:
        with self.transaction() as db:
            if db.execute("SELECT 1 FROM runs WHERE status='running' OR cleanup_pending=1 OR reconciliation_required=1").fetchone():
                return None
            row = db.execute("SELECT id FROM runs WHERE status='queued' ORDER BY created LIMIT 1").fetchone()
            if row is None:
                return None
            run_id = row["id"]
            # The name is committed before any Docker call, including create.
            db.execute("UPDATE runs SET status='running',started=?,cleanup_pending=1,container_name=? WHERE id=?",
                       (time.time(), f"enhancement-bench-{run_id}", run_id))
            self._event(db, run_id, "running")
        return self.run(run_id)

    def cancel(self, run_id: str) -> dict:
        with self.transaction() as db:
            row = db.execute("SELECT status,cancel_requested FROM runs WHERE id=?", (run_id,)).fetchone()
            if row is None:
                raise BenchError("run_not_found", 404)
            if row["status"] == "queued":
                self._finish(db, run_id, "cancelled", "cancelled_before_start")
            elif row["status"] == "running" and not row["cancel_requested"]:
                db.execute("UPDATE runs SET cancel_requested=1 WHERE id=?", (run_id,))
                self._event(db, run_id, "cancel_requested")
        return self.run(run_id)

    def attempt_started(self, run_id: str, attempt_id: str, request: dict):
        with self.transaction() as db:
            changed = db.execute("UPDATE attempts SET status='running',request=?,started=? WHERE id=? AND run_id=? AND status='queued' AND EXISTS(SELECT 1 FROM runs WHERE id=? AND status='running' AND cancel_requested=0)",
                                 (canonical(request), time.time(), attempt_id, run_id, run_id)).rowcount
            if changed != 1:
                raise BenchError("attempt_not_admitted", 409)
            self._event(db, run_id, "running", attempt_id=attempt_id)

    def attempt_progress(self, attempt_id: str, progress: dict):
        with self.transaction() as db:
            db.execute("UPDATE attempts SET progress=? WHERE id=? AND status='running'",
                       (canonical(progress), attempt_id))

    def attempt_finished(self, run_id, attempt_id, status, result=None, error=None):
        if status not in TERMINAL:
            raise BenchError("invalid_terminal_status")
        with self.transaction() as db:
            changed = db.execute("UPDATE attempts SET status=?,result=?,error_code=?,finished=? WHERE id=? AND run_id=? AND status='running'",
                                 (status, canonical(result) if result is not None else None,
                                  error, time.time(), attempt_id, run_id)).rowcount
            if changed != 1:
                raise BenchError("attempt_already_terminal", 409)
            self._event(db, run_id, status, error, attempt_id)

    def _finish(self, db, run_id, status, error=None, assertion="unknown"):
        if status == "succeeded" and db.execute("SELECT 1 FROM attempts WHERE run_id=? AND status<>'succeeded'", (run_id,)).fetchone():
            raise BenchError("unfinished_attempts_cannot_succeed", 409)
        # Evaluators can run remotely even when generation is disabled. An
        # admitted operation's uncertainty must not be inferred from its binding.
        db.execute("""UPDATE runs SET reconciliation_required=1 WHERE id=? AND EXISTS(
            SELECT 1 FROM attempts WHERE run_id=? AND status IN ('running','interrupted'))""", (run_id, run_id))
        db.execute("UPDATE runs SET status=?,error_code=?,assertion_outcome=?,finished=? WHERE id=?",
                   (status, error, assertion, time.time(), run_id))
        db.execute("UPDATE attempts SET status=?,error_code=?,finished=? WHERE run_id=? AND status='queued'",
                   (status if status in {"cancelled", "superseded"} else "skipped", error, time.time(), run_id))
        db.execute("UPDATE attempts SET status='interrupted',error_code=?,finished=? WHERE run_id=? AND status='running'",
                   (error, time.time(), run_id))
        self._event(db, run_id, status, error)

    def finish(self, run_id, status, error=None, assertion="unknown"):
        if status not in TERMINAL:
            raise BenchError("invalid_terminal_status")
        with self.transaction() as db:
            row = db.execute("SELECT status FROM runs WHERE id=?", (run_id,)).fetchone()
            if row is None or row["status"] != "running":
                raise BenchError("run_not_running", 409)
            self._finish(db, run_id, status, error, assertion)

    def recover(self):
        """Called only by the exclusive worker after obtaining its process lock."""
        with self.transaction() as db:
            rows = db.execute("SELECT id FROM runs WHERE status='running'").fetchall()
            for row in rows:
                self._finish(db, row["id"], "interrupted", "worker_restarted_no_replay")

    def pending_cleanup(self) -> list[dict]:
        with self.connection() as db:
            return [dict(r) for r in db.execute("SELECT id,container_name FROM runs WHERE cleanup_pending=1")]

    def cleanup_confirmed(self, run_id: str):
        with self.transaction() as db:
            changed = db.execute("UPDATE runs SET cleanup_pending=0 WHERE id=? AND cleanup_pending=1", (run_id,)).rowcount
            db.execute("UPDATE cleanup_checks SET state='confirmed',checked_at=?,next_check=NULL,error_code=NULL WHERE run_id=?",
                       (time.time(), run_id))
            if changed:
                self._event(db, run_id, "cleanup_confirmed")

    def cleanup_failed(self, run_id, code):
        allowed = {"container_operation_unconfirmed", "container_operation_failed", "container_response_too_large",
                   "container_ownership_mismatch", "container_cleanup_unconfirmed"}
        code = code if code in allowed else "container_cleanup_unconfirmed"
        with self.transaction() as db:
            now = time.time()
            db.execute("INSERT OR IGNORE INTO cleanup_checks VALUES(?,1,NULL,NULL,NULL,'pending')", (run_id,))
            count = db.execute("SELECT attempts FROM cleanup_checks WHERE run_id=?", (run_id,)).fetchone()[0]
            next_check = now + (5 if count < 2 else 30) if count < 3 and code != "container_ownership_mismatch" else None
            db.execute("UPDATE cleanup_checks SET state='failed',checked_at=?,next_check=?,error_code=? WHERE run_id=?",
                       (now, next_check, code, run_id))
            self._event(db, run_id, "cleanup_check_failed", code)

    def claim_cleanup_check(self):
        with self.transaction() as db:
            now = time.time()
            db.execute("""UPDATE cleanup_checks SET state='failed',next_check=NULL,error_code='container_cleanup_unconfirmed'
                WHERE state='checking' AND attempts>=3 AND next_check<=?""", (now,))
            row = db.execute("""SELECT r.id,r.container_name FROM runs r LEFT JOIN cleanup_checks c ON c.run_id=r.id
                WHERE r.cleanup_pending=1 AND r.status NOT IN ('queued','running')
                AND (c.run_id IS NULL OR (c.next_check<=? AND c.attempts<3))
                ORDER BY r.created LIMIT 1""", (now,)).fetchone()
            if row is None:
                return None
            # Reserve before Docker. A restart retains the attempt count and cooldown.
            db.execute("""INSERT INTO cleanup_checks VALUES(?,1,?,?,NULL,'checking')
                ON CONFLICT(run_id) DO UPDATE SET attempts=attempts+1,state='checking',checked_at=excluded.checked_at,
                next_check=excluded.next_check""", (row["id"], now, now + 120))
            self._event(db, row["id"], "cleanup_check_started")
            return dict(row)

    def request_cleanup_check(self, run_id):
        with self.transaction() as db:
            row = db.execute("SELECT status,cleanup_pending FROM runs WHERE id=?", (run_id,)).fetchone()
            if row is None:
                raise BenchError("run_not_found", 404)
            if row["status"] not in TERMINAL or not row["cleanup_pending"]:
                raise BenchError("cleanup_retry_not_required", 409)
            check = db.execute("SELECT next_check,attempts,state FROM cleanup_checks WHERE run_id=?", (run_id,)).fetchone()
            if check is None or (check["next_check"] is not None and check["attempts"] < 3):
                return
            if check["state"] == "checking" and check["next_check"] is not None and check["next_check"] > time.time():
                return
            db.execute("UPDATE cleanup_checks SET attempts=0,state='pending',next_check=? WHERE run_id=?", (time.time(), run_id))
            self._event(db, run_id, "cleanup_check_requested")

    def acknowledge_remote_stopped(self, run_id: str, evidence_reference: str):
        import re

        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,95}", evidence_reference):
            raise BenchError("invalid_evidence_reference")
        with self.transaction() as db:
            row = db.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
            if row is None:
                raise BenchError("run_not_found", 404)
            if row["status"] not in TERMINAL or row["cleanup_pending"]:
                raise BenchError("container_cleanup_required", 409)
            if row["reconciliation_required"]:
                db.execute("INSERT INTO reconciliations VALUES(?,?,?)", (run_id, evidence_reference, time.time()))
                db.execute("UPDATE runs SET reconciliation_required=0 WHERE id=?", (run_id,))
                self._event(db, run_id, "operator_confirmed_remote_stopped")
