"""Local entrypoints and content-free CI validation/delivery helpers."""

from __future__ import annotations

import argparse
import json
import os
import signal
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID, uuid4

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


def deliver_publication(publication: Publication, endpoint: str, import_token: str,
                        *, access_client_id: str | None = None,
                        access_client_secret: str | None = None) -> dict:
    endpoint = endpoint.rstrip("/")
    origin = urlsplit(endpoint)
    if (origin.scheme != "https" or not origin.hostname or origin.username is not None
            or origin.password is not None or origin.path or origin.query or origin.fragment):
        raise BenchError("https_delivery_origin_required")
    if len(import_token) < 24 or any(c in import_token for c in "\r\n"):
        raise BenchError("invalid_import_token")
    if bool(access_client_id) != bool(access_client_secret):
        raise BenchError("paired_access_credentials_required")
    headers = {"Authorization": "Bearer " + import_token, "Origin": endpoint,
               "User-Agent": "PromptEnhancer-Experiment-Publisher/1"}
    if access_client_id and access_client_secret:
        if any(c in access_client_id + access_client_secret for c in "\r\n"):
            raise BenchError("invalid_access_credentials")
        headers.update({"CF-Access-Client-Id": access_client_id,
                        "CF-Access-Client-Secret": access_client_secret})
    try:
        with httpx.Client(timeout=30, follow_redirects=False, trust_env=False) as client:
            response = client.post(endpoint + "/api/publications",
                                   json=publication.model_dump(), headers=headers)
        if response.status_code != 202:
            raise BenchError("publication_delivery_failed")
        value = response.json()
        if (not isinstance(value, dict) or "runId" not in value or type(value.get("imported")) is not bool
                or (value.get("runId") is not None and not isinstance(value["runId"], str))):
            raise BenchError("publication_acknowledgement_invalid")
        run_id = str(UUID(value["runId"])) if value["runId"] is not None else None
        return {"experiment": publication.definition.stableId,
                "revision": publication.definition.revision,
                "imported": value["imported"], "runId": run_id}
    except (httpx.HTTPError, ValueError):
        raise BenchError("publication_delivery_unconfirmed") from None


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
            receipt = deliver_publication(envelope, os.environ["BENCH_DELIVERY_URL"],
                os.environ["BENCH_IMPORT_TOKEN"],
                access_client_id=os.environ.get("BENCH_CF_ACCESS_CLIENT_ID"),
                access_client_secret=os.environ.get("BENCH_CF_ACCESS_CLIENT_SECRET"))
            print(json.dumps(receipt))
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
