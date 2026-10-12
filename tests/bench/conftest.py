from __future__ import annotations

import copy
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "bench/src"))

from enhancement_bench.definitions import Publication
from enhancement_bench.protocol import Contracts
from enhancement_bench.store import Store

@pytest.fixture
def publication():
    definition = json.loads((ROOT / "bench/definitions/example-widget.json").read_text())
    return Publication.model_validate({"schemaVersion": "bench-publication/v1", "definition": definition,
                                       "image": "registry.example.com/example/enhancer@sha256:" + "a" * 64,
                                       "coreVersion": "0.1.0"})


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "private" / "bench.sqlite3")


@pytest.fixture
def contracts():
    directory = Path(os.environ.get("BENCH_CONTRACTS", ROOT / "contracts/enhancement"))
    return Contracts(directory)


@pytest.fixture
def result_template(contracts):
    return json.loads((contracts.directory / "examples/result.json").read_text())


def changed(publication, **changes):
    payload = copy.deepcopy(publication.model_dump())
    payload["definition"].update(changes)
    return Publication.model_validate(payload)
