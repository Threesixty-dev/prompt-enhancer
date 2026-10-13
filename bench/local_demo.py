"""Local review demo: real bench/core containers, synthetic prompts, no model calls."""

from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path
import subprocess
import time
import uuid

import httpx

from ci import core_version

ROOT = Path(__file__).resolve().parents[1]
STATE = Path("/tmp/enhancement-bench-review-demo.json")
LABEL = "enhancement-bench.review-demo"
OPERATOR = "example-review-operator-not-a-secret"
IMPORT = "example-review-import-not-a-secret"


class DemoError(Exception):
    pass


def docker(*args, optional=False, timeout=60):
    result = subprocess.run(["docker", *args], stdin=subprocess.DEVNULL, capture_output=True, timeout=timeout)
    if result.returncode:
        if optional:
            return None
        raise DemoError("demo_container_operation_failed")
    return result.stdout.decode().strip()


def owned(state, name, *, volume=False):
    args = ["volume", "inspect"] if volume else ["inspect"]
    label = docker(*args, "--format", '{{index .Labels "' + LABEL + '"}}' if volume
                   else '{{index .Config.Labels "' + LABEL + '"}}', name, optional=True)
    if label is not None and label != state["id"]:
        raise DemoError("demo_resource_ownership_mismatch")
    return label is not None


def request(state, method, route, *, data=None, importer=False):
    with httpx.Client(base_url=state["origin"], timeout=5, trust_env=False, follow_redirects=False) as client:
        response = client.request(method, route, json=data,
            headers={"Authorization": "Bearer " + (IMPORT if importer else OPERATOR)})
        if response.status_code not in (200, 202):
            raise DemoError("demo_api_request_failed")
        return response.json()


def read_state():
    value = json.loads(STATE.read_text())
    if value.get("schema") != "enhancement-review-demo.v1":
        raise DemoError("unrecognized_demo_state")
    return value


def new_state(args):
    image = json.loads(docker("image", "inspect", args.core_image, "--format", "{{json .RepoDigests}}"))
    repository = args.core_image.rsplit(":", 1)[0]
    digest = next((value for value in image or [] if value.startswith(repository + "@sha256:")), None)
    if digest is None:
        raise DemoError("demo_requires_local_manifest_digest")
    bench_image = docker("image", "inspect", args.bench_image, "--format", "{{.Id}}")
    definition = json.loads((ROOT / "bench/examples/example-widget.json").read_text())
    definition.update(stableId="example-local-demo", title="Local review: two scripted prompt variants",
                      enhancerVersion=core_version(), consumerBinding=None)
    first = definition["units"][0]
    second = copy.deepcopy(first)
    second.update(id="acceptance", title="Acceptance-focused clarification",
                  steering={"profile": "targeted.v1", "focus": ["acceptance"]},
                  objective={"targets": [{"kind": "numeric", "evaluator_id": "prompt",
                      "metric_key": "prompt.acceptance_testability", "direction": "increase", "desired_value": None}]})
    definition["units"] = [first, second]
    identity = uuid.uuid4().hex[:12]
    # Keep the local manifest reachable after the development tag is rebuilt.
    retention_tag = repository + ":review-demo-" + identity
    docker("tag", args.core_image, retention_tag)
    return {"schema": "enhancement-review-demo.v1", "id": identity,
            "api": "enhancement-review-api-" + identity,
            "worker": "enhancement-review-worker-" + identity,
            "volume": "enhancement-review-data-" + identity,
            "origin": f"http://127.0.0.1:{args.port}", "port": args.port,
            "bench_image": bench_image, "core_retention_tag": retention_tag,
            "publication": {"schemaVersion": "bench-publication/v1",
                "definition": definition, "image": digest, "coreVersion": definition["enhancerVersion"]}}


def summary(state):
    runs = request(state, "GET", "/api/runs")["runs"]
    return {"scope": "real_containers_scripted_synthetic_prompts", "origin": state["origin"],
            "live_model_calls": False, "runs": [{"id": run["id"], "origin": run["origin"],
                "status": run["status"], "cleanup_pending": bool(run["cleanup_pending"])} for run in runs]}


def start(args):
    state = read_state() if STATE.exists() else new_state(args)
    if not STATE.exists():
        with STATE.open("x") as file:
            os.chmod(STATE, 0o600)
            json.dump(state, file)
    if owned(state, state["api"]) or owned(state, state["worker"]):
        raise DemoError("demo_already_created_use_status_or_stop")
    if not owned(state, state["volume"], volume=True):
        docker("volume", "create", "--label", LABEL + "=" + state["id"], state["volume"])
    repository = state["publication"]["image"].split("@", 1)[0]
    common = ["--label", LABEL + "=" + state["id"], "--read-only", "--cap-drop=ALL",
              "--security-opt=no-new-privileges", "--init", "--pids-limit=128", "--memory=256m", "--cpus=0.5",
              "--tmpfs", "/tmp:rw,noexec,nosuid,size=32m", "--mount", "type=volume,src=" + state["volume"] + ",dst=/data",
              "--env", "BENCH_IMAGE_REPOSITORIES=" + repository]
    try:
        docker("run", "-d", "--name", state["api"], *common,
               "--publish", f"127.0.0.1:{state['port']}:8088", "--env", "BENCH_ORIGIN=" + state["origin"],
               "--env", "BENCH_OPERATOR_TOKEN=" + OPERATOR, "--env", "BENCH_IMPORT_TOKEN=" + IMPORT,
               state["bench_image"], "serve", "--host", "0.0.0.0", "--port", "8088")
        deadline = time.monotonic() + 30
        while True:
            try:
                request(state, "GET", "/health/ready")
                break
            except (httpx.HTTPError, DemoError):
                if time.monotonic() >= deadline:
                    raise DemoError("demo_readiness_timeout") from None
                time.sleep(0.25)
        # The namespace has no external network; only scripted core work is configured.
        docker("run", "-d", "--name", state["worker"], *common, "--network", "none",
               "--group-add", os.environ.get("BENCH_DOCKER_GID", "0"),
               "--mount", "type=bind,src=/var/run/docker.sock,dst=/var/run/docker.sock",
               "--env", "BENCH_WORKER_CONTAINER=" + state["worker"], state["bench_image"], "worker")
        imported = request(state, "POST", "/api/publications", data=state["publication"], importer=True)
        repeated = request(state, "POST", "/api/publications", data=state["publication"], importer=True)
        if imported["runId"] != repeated["runId"] or repeated["imported"]:
            raise DemoError("demo_import_not_idempotent")
        print(json.dumps(summary(state)))
    except BaseException:
        stop(state, remove_data=False)
        raise


def stop(state, *, remove_data):
    run_ids = []
    try:
        runs = request(state, "GET", "/api/runs")["runs"]
        run_ids = [run["id"] for run in runs]
        for run in runs:
            if run["status"] in {"running", "queued"}:
                request(state, "POST", f"/api/runs/{run['id']}/cancel", data={})
    except (httpx.HTTPError, DemoError):
        pass
    for name in (state["worker"], state["api"]):
        if owned(state, name):
            docker("stop", "--time", "30", name)
            docker("rm", name)
    for run_id in run_ids:
        name = "enhancement-bench-" + run_id
        label = docker("inspect", "--format", '{{index .Config.Labels "enhancement-bench.run"}}', name, optional=True)
        if label is not None:
            if label != run_id:
                raise DemoError("demo_core_ownership_mismatch")
            docker("rm", "--force", name)
    if remove_data:
        if owned(state, state["volume"], volume=True):
            docker("volume", "rm", state["volume"])
        STATE.unlink()
    print(json.dumps({"demo_stopped": True, "data_preserved": not remove_data}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("start", "status", "stop"))
    parser.add_argument("--port", type=int, default=8098)
    parser.add_argument("--core-image", default="local/enhancement-core:integration-review")
    parser.add_argument("--bench-image", default="local/enhancement-bench:integration-review")
    parser.add_argument("--remove-data", action="store_true", help="Explicitly delete only this demo's labelled volume on stop")
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535 or (args.remove_data and args.command != "stop"):
        parser.error("invalid demo options")
    try:
        if args.command == "start":
            start(args)
        elif args.command == "status":
            print(json.dumps(summary(read_state())))
        else:
            stop(read_state(), remove_data=args.remove_data)
    except (DemoError, OSError, ValueError, subprocess.SubprocessError, httpx.HTTPError) as error:
        raise SystemExit(str(error) if isinstance(error, DemoError) else "demo_operation_failed") from None


if __name__ == "__main__":
    main()
