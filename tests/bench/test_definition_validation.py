"""Definition validation remains offline and checks every publication identity."""

import copy
import json

import pytest

from enhancement_bench import cli
from enhancement_bench.errors import BenchError


@pytest.fixture
def validate(monkeypatch, tmp_path, contracts):
    def forbidden(*args, **kwargs):
        pytest.fail("definition validation must not start a runtime or deliver data")

    for name in ("Store", "DockerRuntime", "Worker", "deliver_publication"):
        monkeypatch.setattr(cli, name, forbidden)
    monkeypatch.setattr(cli.httpx, "Client", forbidden)
    monkeypatch.setattr(cli, "default_contracts", lambda: contracts.directory)

    def run(definitions):
        paths = []
        for position, definition in enumerate(definitions):
            path = tmp_path / f"example-{position}.json"
            path.write_text(json.dumps(definition))
            paths.append(str(path))
        monkeypatch.setattr("sys.argv", ["enhancement-bench", "validate", *paths])
        cli.main()

    return run


def test_validation_accepts_distinct_revisions_without_runtime_effects(validate, publication, capsys):
    original = publication.definition.model_dump()
    later = copy.deepcopy(original)
    later.update(revision="2", generation=2)
    validate([original, later])
    assert capsys.readouterr().out == "Validated 2 synthetic experiment definitions.\n"


@pytest.mark.parametrize("changes", [{}, {"generation": 2}, {"revision": "2"}])
def test_validation_rejects_duplicate_revision_or_generation(validate, publication, capsys, changes):
    original = publication.definition.model_dump()
    later = copy.deepcopy(original)
    later.update(changes)
    with pytest.raises(SystemExit) as failure:
        validate([original, later])
    assert failure.value.code == 1
    assert capsys.readouterr().out == "duplicate_experiment_revision\n"


def test_validation_checks_later_case_unit_requests(validate, publication, capsys):
    definition = publication.definition.model_dump()
    definition["units"][-1]["strategy"] = "example.unsupported.v1"
    with pytest.raises(SystemExit) as failure:
        validate([definition])
    assert failure.value.code == 1
    assert capsys.readouterr().out == "core_contract_violation\n"


def test_validation_checks_every_case_unit_pair(monkeypatch, tmp_path, contracts, publication):
    definition = publication.definition.model_dump()
    second = copy.deepcopy(definition["subjects"][0])
    second["id"] = "example-second-prompt"
    definition["subjects"].append(second)
    path = tmp_path / "example-definition.json"
    path.write_text(json.dumps(definition))
    seen = []
    request = contracts.request

    def record(run, attempt):
        seen.append((attempt["subject_id"], attempt["unit_id"]))
        return request(run, attempt)

    monkeypatch.setattr(contracts, "request", record)
    cli.validate_definitions([path], contracts)
    assert seen == [(subject["id"], unit["id"])
                    for subject in definition["subjects"] for unit in definition["units"]]


@pytest.mark.parametrize("kind", ["empty", "missing", "directory"])
def test_validation_requires_regular_definition_files(tmp_path, contracts, kind):
    paths = [] if kind == "empty" else [tmp_path / "example-missing.json" if kind == "missing" else tmp_path]
    with pytest.raises(BenchError, match="experiment_files_required"):
        cli.validate_definitions(paths, contracts)
