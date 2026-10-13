"""Transactional private storage. No provider sessions or application tables."""

from __future__ import annotations

import json
import os
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from .definitions import Definition, Overrides, Publication, canonical, definition_payload, effective_settings, fingerprint
from .errors import BenchError

TERMINAL = {"succeeded", "failed", "cancelled", "interrupted", "superseded"}


class Store:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with self.connection() as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1):
                raise BenchError("unsupported_database_schema", 503)
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript(Path(__file__).with_name("schema.sql").read_text())
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

    def import_publication(self, publication: Publication) -> dict:
        definition = publication.definition
        payload = definition_payload(definition)
        body = canonical(payload)
        spec_hash = fingerprint(publication.model_dump() | {"definition": payload})
        with self.transaction() as db:
            existing = db.execute("SELECT * FROM definitions WHERE stable_id=? AND revision=?",
                                  (definition.stableId, definition.revision)).fetchone()
            if existing:
                if existing["spec_hash"] != spec_hash:
                    raise BenchError("immutable_revision_conflict", 409)
                run = db.execute("SELECT id FROM runs WHERE stable_id=? AND revision=? AND origin='gitops'",
                                 (definition.stableId, definition.revision)).fetchone()
                return {"imported": False, "runId": run["id"] if run else None}
            if db.execute("SELECT 1 FROM definitions WHERE stable_id=? AND generation=?",
                          (definition.stableId, definition.generation)).fetchone():
                raise BenchError("generation_conflict", 409)
            db.execute("INSERT INTO definitions VALUES(?,?,?,?,?,?,?,?)",
                       (definition.stableId, definition.revision, definition.generation,
                        spec_hash, body, publication.image, definition.autoRun, time.time()))
            latest = db.execute("SELECT MAX(generation) FROM definitions WHERE stable_id=? AND auto_run=1",
                                (definition.stableId,)).fetchone()[0]
            run_id = None
            if definition.autoRun and definition.generation == latest:
                stale = db.execute("SELECT id FROM runs WHERE stable_id=? AND generation<? AND origin='gitops' AND status='queued'",
                                   (definition.stableId, latest)).fetchall()
                for row in stale:
                    self._finish(db, row["id"], "superseded", "newer_eligible_definition")
                run_id = self._enqueue(db, definition, publication.image, Overrides(), "gitops",
                                       f"auto:{definition.stableId}:{definition.revision}", None)
            return {"imported": True, "runId": run_id}

    def _enqueue(self, db, definition, image, overrides, origin, request_key, retry_of):
        effective = effective_settings(definition, overrides)
        digest = fingerprint({"effective": effective, "image": image, "retryOf": retry_of})
        previous = db.execute("SELECT id,request_hash FROM runs WHERE request_key=?", (request_key,)).fetchone()
        if previous:
            if previous["request_hash"] != digest:
                raise BenchError("idempotency_conflict", 409)
            return previous["id"]
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
            return self._enqueue(db, Definition.model_validate_json(row["body"]), row["image"],
                                 overrides, "ui", f"ui:{request_id}", retry_of)

    def definitions(self) -> list[dict]:
        with self.connection() as db:
            rows = db.execute("SELECT * FROM definitions ORDER BY stable_id,generation DESC").fetchall()
        return [{**json.loads(r["body"]), "image": r["image"], "specHash": r["spec_hash"]} for r in rows]

    def runs(self, limit: int = 100, *, before: str | None = None) -> list[dict]:
        with self.connection() as db:
            where, parameters = "", []
            if before is not None:
                cursor = db.execute("SELECT created,id FROM runs WHERE id=?", (before,)).fetchone()
                if cursor is None:
                    raise BenchError("invalid_run_cursor")
                where, parameters = " WHERE (created,id) < (?,?)", [cursor["created"], cursor["id"]]
            rows = db.execute("SELECT id,correlation_id,stable_id,revision,generation,origin,retry_of,status,assertion_outcome,cancel_requested,cleanup_pending,reconciliation_required,error_code,created,started,finished FROM runs"
                              + where + " ORDER BY created DESC,id DESC LIMIT ?",
                              (*parameters, min(max(limit, 1), 500))).fetchall()
        return [dict(row) for row in rows]

    def run(self, run_id: str) -> dict:
        with self.connection() as db:
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
        # A later retention/cleanup error cannot erase a persisted uncertain turn.
        db.execute("""UPDATE runs SET reconciliation_required=1 WHERE id=? AND EXISTS(
            SELECT 1 FROM attempts WHERE run_id=? AND status IN ('running','interrupted')
            AND json_extract(request,'$.consumer') IS NOT NULL)""", (run_id, run_id))
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
            db.execute("UPDATE runs SET cleanup_pending=0 WHERE id=?", (run_id,))
            self._event(db, run_id, "cleanup_confirmed")

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
