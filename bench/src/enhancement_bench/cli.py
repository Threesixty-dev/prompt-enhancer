"""Local entrypoints and content-free CI validation/delivery helpers."""

from __future__ import annotations

import argparse
import json
import os
import signal
from pathlib import Path
from uuid import uuid4

import httpx

from .definitions import Definition, Overrides, Publication, effective_settings
from .errors import BenchError
from .protocol import Contracts
from .runtime import DockerRuntime, DockerSettings
from .store import Store
from .worker import Worker
from .client import static_consumer_ready


def default_contracts() -> Path:
    return Path(os.environ.get("BENCH_CONTRACTS", "contracts/enhancement"))


def validate_definition(path: Path, contracts: Contracts) -> Definition:
    definition = Definition.model_validate_json(path.read_text())
    run = {"stable_id": definition.stableId, "revision": definition.revision,
           "id": str(uuid4()), "correlation_id": str(uuid4()),
           "effective": effective_settings(definition, Overrides())}
    for subject in definition.subjects:
        for unit in definition.units:
            contracts.request(run, {"id": str(uuid4()), "subject_id": subject.id, "unit_id": unit.id})
    return definition


def parser():
    value = argparse.ArgumentParser(prog="enhancement-bench")
    value.add_argument("--contracts", type=Path, default=default_contracts())
    sub = value.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate")
    validate.add_argument("definitions", nargs="+", type=Path)
    serve = sub.add_parser("serve")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", default=8088, type=int)
    sub.add_parser("worker")
    envelope = sub.add_parser("envelope")
    envelope.add_argument("definition", type=Path)
    envelope.add_argument("--image", required=True)
    envelope.add_argument("--core-version", required=True)
    envelope.add_argument("--output", required=True, type=Path)
    deliver = sub.add_parser("deliver")
    deliver.add_argument("publication", type=Path)
    return value


def main():
    args = parser().parse_args()
    try:
        contracts = Contracts(args.contracts)
        if args.command == "validate":
            for path in args.definitions:
                validate_definition(path, contracts)
            print(f"Validated {len(args.definitions)} synthetic experiment definitions.")
            return
        if args.command == "envelope":
            definition = validate_definition(args.definition, contracts)
            envelope = Publication(schemaVersion="bench-publication/v1", definition=definition,
                                   image=args.image, coreVersion=args.core_version)
            args.output.write_text(envelope.model_dump_json(indent=2) + "\n")
            return
        if args.command == "deliver":
            envelope = Publication.model_validate_json(args.publication.read_text())
            endpoint = os.environ["BENCH_DELIVERY_URL"].rstrip("/")
            if not endpoint.startswith("https://"):
                raise BenchError("https_delivery_required")
            with httpx.Client(timeout=30, follow_redirects=False, trust_env=False) as client:
                # Delivery is idempotent; a lost response can safely be delivered again.
                response = client.post(endpoint + "/api/publications", json=envelope.model_dump(),
                                       headers={"Authorization": "Bearer " + os.environ["BENCH_IMPORT_TOKEN"]})
                if response.status_code != 202:
                    raise BenchError("publication_delivery_failed")
            print("Publication accepted.")
            return
        store = Store(Path(os.environ.get("BENCH_DATABASE", "/tmp/enhancement-bench/bench.sqlite3")))
        repositories = tuple(filter(None, os.environ.get("BENCH_IMAGE_REPOSITORIES", "").split(",")))
        if not repositories:
            raise BenchError("image_allowlist_required")
        if args.command == "serve":
            import uvicorn
            from .api import create_app

            app = create_app(store, contracts, operator_token=os.environ["BENCH_OPERATOR_TOKEN"],
                             import_token=os.environ["BENCH_IMPORT_TOKEN"], allowed_repositories=repositories,
                             origin=os.environ.get("BENCH_ORIGIN", f"http://127.0.0.1:{args.port}"))
            uvicorn.run(app, host=args.host, port=args.port, access_log=False, log_level="critical")
        else:
            settings = DockerSettings.from_environment(repositories, os.environ)
            readiness = None
            if os.environ.get("BENCH_REQUIRE_CONSUMER_READY") == "1":
                consumer_token = os.environ["ENHANCEMENT_CONSUMER_TOKEN"]
                readiness = lambda: static_consumer_ready(consumer_token)
            worker = Worker(store, contracts, DockerRuntime(settings), admission_check=readiness)
            for signum in (signal.SIGINT, signal.SIGTERM):
                signal.signal(signum, lambda *_: worker.stop.set())
            worker.serve()
    except (BenchError, KeyError, ValueError) as error:
        print(error.code if isinstance(error, BenchError) else "invalid_bench_configuration")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
