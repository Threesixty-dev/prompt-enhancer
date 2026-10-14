"""Select Bench deployments while ignoring generated core-version defaults."""

from __future__ import annotations

import fnmatch
import json
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
DEPLOY_PATHS = (
    "bench/**", "contracts/enhancement/**", "deployment/bench/Dockerfile*",
    "scripts/deploy_bench.py", "scripts/deploy_coolify.py",
    "scripts/smoke_bench_image.py", "tests/bench/**",
    ".github/workflows/bench-deploy.yml",
)
VERSION_SCHEMAS = {
    "contracts/enhancement/capabilities.schema.json",
    "contracts/enhancement/readiness.schema.json",
    "contracts/enhancement/execution-result.schema.json",
}
VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+(?:-[a-z0-9.-]+)?")
REVISION = re.compile(r"[a-f0-9]{40}")


def version_metadata_only(path: str, before: bytes | None, after: bytes | None) -> bool:
    if path not in VERSION_SCHEMAS or before is None or after is None:
        return False
    try:
        documents = [json.loads(value) for value in (before, after)]
        for document in documents:
            field = document["properties"]["core_version"]
            version = field.pop("default")
            if not isinstance(version, str) or not VERSION.fullmatch(version):
                return False
        return documents[0] == documents[1]
    except (ValueError, KeyError, TypeError, AttributeError):
        return False


def git(*args: str, root: Path = ROOT) -> bytes | None:
    result = subprocess.run(["git", *args], cwd=root, capture_output=True, timeout=30)
    return result.stdout if result.returncode == 0 else None


def requires_deployment(before: str, after: str, *, root: Path = ROOT) -> bool:
    if not REVISION.fullmatch(after):
        raise ValueError("deployment_revision_invalid")
    if not REVISION.fullmatch(before) or before == "0" * 40:
        return True
    paths = git("diff", "--name-only", "--no-renames", "-z", before, after, "--", root=root)
    if paths is None:
        return True
    for path in paths.decode("utf-8").split("\0"):
        if not path or not any(fnmatch.fnmatchcase(path, pattern) for pattern in DEPLOY_PATHS):
            continue
        if not version_metadata_only(
            path, git("show", f"{before}:{path}", root=root),
            git("show", f"{after}:{path}", root=root),
        ):
            return True
    return False


def main() -> None:
    event = os.environ["GITHUB_EVENT_NAME"]
    if event not in {"push", "workflow_dispatch"}:
        raise ValueError("deployment_event_invalid")
    selected = event == "workflow_dispatch" or requires_deployment(
        os.environ.get("DEPLOY_BEFORE", ""), os.environ["DEPLOY_REVISION"],
    )
    with Path(os.environ["GITHUB_OUTPUT"]).open("a") as output:
        output.write(f"deploy={str(selected).lower()}\n")
    print("Bench deployment selected." if selected else "No Bench runtime or protocol change; deployment skipped.")


if __name__ == "__main__":
    main()
