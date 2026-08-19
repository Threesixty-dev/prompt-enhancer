"""Model-judge lane: a stub local model rates the redacted window; judgments are
stored apart from metrics and compared with human ratings."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import subprocess
import sys
import textwrap
import time

from fastapi.testclient import TestClient

from prompt_enhancer.api import API_TOKEN_HEADER
from prompt_enhancer.application.analysis.calibration_ratings import CALIBRATION_METRIC_KEYS, RatingLabel, RatingSubmission
from prompt_enhancer.application.analysis.model_judge import parse_judge_reply, render_window
from prompt_enhancer.application.local_models import ActivateLocalModel, AddLocalModel, DeviceMode, HardwareSummary
from prompt_enhancer.bootstrap import bootstrap_local_application
from prompt_enhancer.config import AppSettings
from prompt_enhancer.domain import DataTier, Provider


T0 = datetime(2026, 3, 5, 9, 0, tzinfo=UTC)

# A stub llama-server that answers every chat with a fixed JSON judgment.
STUB = textwrap.dedent(
    '''
    import json, sys
    from http.server import BaseHTTPRequestHandler, HTTPServer
    args = sys.argv[1:]
    port = int(args[args.index("--port") + 1])
    class H(BaseHTTPRequestHandler):
        def log_message(self, *_): pass
        def do_GET(self):
            self.send_response(200 if self.path == "/health" else 404); self.end_headers(); self.wfile.write(b"{}")
        def do_POST(self):
            n = int(self.headers.get("Content-Length", "0")); body = json.loads(self.rfile.read(n) or b"{}")
            user = body["messages"][-1]["content"]
            assert body.get("chat_template_kwargs", {}).get("enable_thinking") is False
            if user.startswith("Metric readings"):
                assert "Redacted transcript window" in user and "USER:" in user, "window missing"
                verdict = {"summary": "Clear request, verified by tests.", "strengths": ["Stated the goal", "Ran the tests"], "improvements": ["Name the files up front"], "reframed_prompt": "Add bounded retries to <specify: file>; done when the tests pass."}
            else:
                assert "Transcript window" in user and "USER:" in user, "window missing"
                verdict = {"prompt.task_definition_coverage": "high", "prompt.context_sufficiency": "medium", "outcome.verification_strategy_adequacy": "cannot_judge"}
            reply = {"choices": [{"message": {"role": "assistant", "content": json.dumps(verdict)}}], "usage": {"completion_tokens": 20}}
            data = json.dumps(reply).encode(); self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(data)
    HTTPServer(("127.0.0.1", port), H).serve_forever()
    '''
)


def _transcript(claude_home: Path, session: str) -> None:
    project = claude_home / "projects" / "-srv-example-judge"
    project.mkdir(parents=True, exist_ok=True)
    at = T0.isoformat().replace("+00:00", "Z")
    lines = [
        json.dumps({"type": "user", "message": {"role": "user", "content": "Please add bounded retries to the example uploader and run the tests."}, "timestamp": at, "sessionId": session, "cwd": "/srv/example/judge", "version": "2.1.0"}),
        json.dumps({"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": "Added three retries with backoff; tests pass."}]}, "timestamp": (T0 + timedelta(seconds=30)).isoformat().replace("+00:00", "Z"), "sessionId": session, "cwd": "/srv/example/judge", "version": "2.1.0"}),
    ]
    (project / f"{session}.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_parse_judge_reply_is_strict() -> None:
    good = '{"prompt.task_definition_coverage": "High", "prompt.context_sufficiency": "low", "outcome.verification_strategy_adequacy": "cannot_judge"}'
    assert parse_judge_reply(good) == {
        "prompt.task_definition_coverage": RatingLabel.HIGH,
        "prompt.context_sufficiency": RatingLabel.LOW,
        "outcome.verification_strategy_adequacy": RatingLabel.CANNOT_JUDGE,
    }
    assert parse_judge_reply("```json\n" + good + "\n```") is not None
    assert parse_judge_reply('{"prompt.task_definition_coverage": "excellent"}') is None
    assert parse_judge_reply("not json") is None


def test_judge_lane_end_to_end_with_stub_model(tmp_path: Path, monkeypatch) -> None:
    claude_home = tmp_path / "claude-home"
    monkeypatch.setenv("PROMPT_ENHANCER_CLAUDE_HOME", str(claude_home))
    _transcript(claude_home, "judge-session-1")
    stub = tmp_path / "stub.py"
    stub.write_text(STUB, encoding="utf-8")
    monkeypatch.setenv("PROMPT_ENHANCER_LLAMA_SERVER", str(stub))
    settings = AppSettings(home=tmp_path / "app")
    application = bootstrap_local_application(settings)
    application.database.grant_consent(Provider.CLAUDE_CODE, DataTier.REDACTED_CONTENT)
    application.create_claude_local_source_service().index(max_sessions=10)
    session_id = str(application.database.list_sessions(limit=5, offset=0)[0]["session_id"])

    # Register a tiny "model" and run it through the stub launcher.
    models = application.create_local_model_service()
    models._popen = lambda command, **kw: subprocess.Popen([sys.executable, str(stub), *command[1:]], **kw)  # noqa: SLF001
    models._hardware = lambda b: HardwareSummary(llama_server_path=str(b) if b else None)  # noqa: SLF001
    weights = tmp_path / "tiny.gguf"
    weights.write_bytes(b"GGUF" + b"\0" * 4092)
    models.add(AddLocalModel(alias="stub-judge", path=str(weights)))
    models.activate("stub-judge", ActivateLocalModel(device=DeviceMode.CPU))
    try:
        calibration = application.create_calibration_rating_service()
        judge, _ = application.create_model_judge_service(models, calibration)

        outcome = judge.judge(session_id)
        assert outcome.raw_valid and outcome.model_alias == "stub-judge"
        assert {j.metric_key: j.label for j in outcome.judgments} == {
            "prompt.task_definition_coverage": RatingLabel.HIGH,
            "prompt.context_sufficiency": RatingLabel.MEDIUM,
            "outcome.verification_strategy_adequacy": RatingLabel.CANNOT_JUDGE,
        }
        stored = application.database.model_judgment_repository().list(session_id=session_id)
        assert len(stored) == 3 and all(s.prompt_version == "judge-v1" and s.model_identity == "tiny.gguf" for s in stored)
        # No text anywhere in the stored judgments.
        dumped = json.dumps([s.model_dump(mode="json") for s in stored])
        assert "uploader" not in dumped and "retries" not in dumped

        # Interpretation: plain-language reading from metrics + window, labelled commentary.
        reading = judge.interpret(session_id)
        assert reading.model_alias == "stub-judge" and reading.strengths == ("Stated the goal", "Ran the tests")
        assert reading.improvements == ("Name the files up front",) and reading.reframed_prompt.startswith("Add bounded retries")
        assert "interpretation, not a measurement" in reading.caveat and reading.metrics_seen >= 0

        # Human rating for the same session -> agreement report pairs them.
        calibration.sample()
        calibration.rate(RatingSubmission(rater_label="Owner", session_id=session_id, ratings={
            CALIBRATION_METRIC_KEYS[0]: RatingLabel.HIGH, CALIBRATION_METRIC_KEYS[1]: RatingLabel.LOW,
        }))
        report = judge.agreement()
        assert report.model_alias == "stub-judge" and report.judged_sessions == 1
        by_key = {m.metric_key: m for m in report.metrics}
        assert by_key[CALIBRATION_METRIC_KEYS[0]].pairs == 1 and by_key[CALIBRATION_METRIC_KEYS[1]].pairs == 1
        assert by_key[CALIBRATION_METRIC_KEYS[2]].pairs == 0 and by_key[CALIBRATION_METRIC_KEYS[2]].state == "insufficient_data"
        assert "never product metrics" in report.caveat

        # Sweep over the sample is idempotent for already-judged sessions.
        status = judge.start_sweep(tuple(m.session_id for m in calibration.sample().members))
        assert status.total == 0 and status.running is False

        # HTTP: agreement and sweep status are served; judging through the route works too.
        client = TestClient(application.create_http_app(), base_url="http://127.0.0.1")
        headers = {API_TOKEN_HEADER: settings.api_token_path.read_text(encoding="utf-8").strip()}
        agreement = client.get("/v1/model-judge/agreement", headers=headers)
        assert agreement.status_code == 200, agreement.text
        assert client.get("/v1/model-judge/sweep", headers=headers).status_code == 200
        interpreted = client.post(f"/v1/model-judge/sessions/{session_id}/interpret", headers=headers)
        assert interpreted.status_code in {200, 409}, interpreted.text  # 409 when the HTTP app has no active model
        stored = client.get(f"/v1/model-judge/sessions/{session_id}", headers=headers)
        assert stored.status_code == 200, stored.text
        body = stored.json()
        assert body["session_id"] == session_id and len(body["judgments"]) == len(CALIBRATION_METRIC_KEYS)
        assert set(body["questions"]) == set(CALIBRATION_METRIC_KEYS) and "never metric values" in body["caveat"]
        assert {j["metric_key"] for j in body["judgments"]} == set(CALIBRATION_METRIC_KEYS)
        assert client.get("/v1/model-judge/sessions/not-a-pseudonym", headers=headers).status_code == 422
        # scope=all sweeps every indexed session (the HTTP app composes its own judge with no active model here,
        # so it fails closed with no_active_model rather than silently doing nothing).
        everything = client.post("/v1/model-judge/sweep?scope=all", headers=headers)
        assert everything.status_code in {200, 409}, everything.text
        if everything.status_code == 409:
            assert everything.json()["detail"]["code"] == "no_active_model"
        assert client.post("/v1/model-judge/sweep?scope=bogus", headers=headers).status_code == 422
    finally:
        models.shutdown()


def test_render_window_keeps_roles_and_bounds_length() -> None:
    from pydantic import SecretStr

    from prompt_enhancer.application.analysis.text_contracts import (
        EphemeralRedactedMessage, TextLanguage, TextMessageKind, TextRole,
    )

    class _Ctx:
        messages = (
            EphemeralRedactedMessage(message_id="a" * 64, sequence=0, role=TextRole.USER, kind=TextMessageKind.REQUEST, language=TextLanguage.ENGLISH, text=SecretStr("please do x")),
            EphemeralRedactedMessage(message_id="b" * 64, sequence=1, role=TextRole.AGENT, kind=TextMessageKind.PLAN, language=TextLanguage.ENGLISH, text=SecretStr("- [pending] step")),
            EphemeralRedactedMessage(message_id="c" * 64, sequence=2, role=TextRole.AGENT, kind=TextMessageKind.RESPONSE, language=TextLanguage.ENGLISH, text=SecretStr("done " * 5000)),
        )

    rendered = render_window(_Ctx(), max_characters=500)  # type: ignore[arg-type]
    assert rendered.startswith("[...earlier part omitted...]")
    assert len(rendered) <= 500 + 40
    full = render_window(_Ctx())  # type: ignore[arg-type]
    assert "USER: please do x" in render_window(_Ctx(), max_characters=100_000)  # type: ignore[arg-type]


def test_index_refresh_judges_new_sessions_when_a_model_is_active(tmp_path: Path, monkeypatch) -> None:
    """After each index the app sweeps the judge over newly indexed sessions (no clicks)."""

    claude_home = tmp_path / "claude-home"
    monkeypatch.setenv("PROMPT_ENHANCER_CLAUDE_HOME", str(claude_home))
    _transcript(claude_home, "judge-auto-1")
    stub = tmp_path / "stub.py"
    stub.write_text(STUB, encoding="utf-8")
    monkeypatch.setenv("PROMPT_ENHANCER_LLAMA_SERVER", str(stub))
    settings = AppSettings(home=tmp_path / "app")
    application = bootstrap_local_application(settings)
    # Make the app's own model service launch the stub (the http app composes it internally).
    original = type(application).create_local_model_service

    def stubbed_model_service(self):
        models = original(self)
        models._popen = lambda command, **kw: subprocess.Popen([sys.executable, str(stub), *command[1:]], **kw)  # noqa: SLF001
        models._hardware = lambda b: HardwareSummary(llama_server_path=str(b) if b else None)  # noqa: SLF001
        return models

    # LocalApplication is a frozen dataclass; patch the class for this test only.
    monkeypatch.setattr(type(application), "create_local_model_service", stubbed_model_service)
    app = application.create_http_app()
    client = TestClient(app, base_url="http://127.0.0.1")
    headers = {API_TOKEN_HEADER: settings.api_token_path.read_text(encoding="utf-8").strip()}
    weights = tmp_path / "tiny.gguf"
    weights.write_bytes(b"GGUF" + b"\0" * 4092)
    assert client.post("/v1/local-models", headers=headers, json={"alias": "stub-judge", "path": str(weights)}).status_code == 201
    assert client.post("/v1/local-models/stub-judge/activate", headers=headers, json={"device": "cpu"}).status_code == 200
    try:
        accepted = client.post("/v1/onboarding/accept", headers=headers, json={"providers": ["claude_code"]})
        assert accepted.status_code == 200, accepted.text
        deadline = time.time() + 30
        while time.time() < deadline:
            report = client.get("/v1/model-judge/agreement", headers=headers).json()
            if report["judged_sessions"] >= 1:
                break
            time.sleep(0.5)
        assert report["judged_sessions"] == 1 and report["model_alias"] == "stub-judge"
    finally:
        client.post("/v1/local-models/stub-judge/deactivate", headers=headers)
