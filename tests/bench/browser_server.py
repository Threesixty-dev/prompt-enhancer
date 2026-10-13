"""Owned loopback browser fixture. No Docker, model, or live infrastructure."""

import json
import os
from pathlib import Path
import tempfile

import uvicorn

from enhancement_bench.api import create_app
from enhancement_bench.definitions import Publication
from enhancement_bench.protocol import Contracts
from enhancement_bench.store import Store

from test_client_worker import make_worker


def main():
    contracts = Contracts(Path(os.environ["BENCH_CONTRACTS"]))
    root = Path(__file__).resolve().parents[2]
    definition = json.loads((root / "bench/definitions/example-widget.json").read_text())
    publication = Publication.model_validate({"schemaVersion": "bench-publication/v1", "definition": definition,
        "image": "registry.example.com/example/enhancer@sha256:" + "a" * 64, "coreVersion": "0.1.0"})
    with tempfile.TemporaryDirectory(prefix="bench-browser-") as directory:
        store = Store(Path(directory) / "bench.sqlite3")
        store.import_publication(publication)
        fixture = json.loads((contracts.directory / "examples/result.json").read_text())
        worker, _, _ = make_worker(store, contracts, fixture)
        worker.step()
        app = create_app(store, contracts,
                         allowed_repositories=("registry.example.com/example/enhancer",))
        uvicorn.run(app, host="127.0.0.1", port=8088, access_log=False, log_level="critical")


if __name__ == "__main__":
    main()
