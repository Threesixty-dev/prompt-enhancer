"""Assemble explicit unsigned candidate inputs; never pack, sign, or launch."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from prompt_enhancer.infrastructure.build_staging import WindowsReleaseFile, WindowsReleaseStagePlan, stage_windows_release
from prompt_enhancer.application.build_evidence.manifest import canonical_json, MAX_STAGED_FILES
from prompt_enhancer.application.paths.policy import classify_windows_path_text, validate_private_relative_parts
from prepare_windows_launchers import read, safe
from prepare_msix_manifest import generated_files

STAGE_GROUP = "windows-application-stage-43-python31315-review1"
LAUNCHER_GROUP = "native-launchers-build-review1"
GENERATED_GROUP = "msix-generated-review1"
STAGE_SHA = "417fa8a2102e0412d3b21506cdb797181fe60ea13d19e99abc039fa13ec867e1"
LAUNCHERS = {
    "PromptEnhancer.exe": {"size": 13322, "sha256": "9d21817d02d4288e483c657ef42f45549fc285b42c5dc6ebffa2b80335517b62"},
    "PromptEnhancerMetrics.exe": {"size": 13322, "sha256": "5924cc107d7f00738ee29c48dbd271deb0bbd6f80feb037139155327a757448b"},
}
REPOSITORY = Path(__file__).resolve().parents[1]
MAX_JSON = 1024 * 1024


class CandidatePhaseError(ValueError):
    pass


def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError()
        result[key] = value
    return result


def pinned_json(path, size, digest):
    if type(size) is not int or not 0 < size <= MAX_JSON or not re.fullmatch("[0-9a-f]{64}", digest):
        raise ValueError()
    if path.lstat().st_size != size:
        raise ValueError()
    data = read(path, MAX_JSON)
    if len(data) != size or hashlib.sha256(data).hexdigest() != digest:
        raise ValueError()
    return json.loads(data, object_pairs_hook=unique, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))


def external(path):
    if classify_windows_path_text(os.fspath(path)) is not None or not path.is_absolute() or ".." in path.parts:
        raise ValueError()
    parts = PureWindowsPath(os.fspath(path)).parts
    if validate_private_relative_parts(parts[1:]) is not None:
        raise ValueError()
    for forbidden in (REPOSITORY, Path.home()):
        if path == forbidden or path in forbidden.parents or forbidden in path.parents:
            raise ValueError()
    return path


def exact_tree(root, names):
    """Inventory only the designated group; never traverse a reparse point."""
    safe(root, directory=True)
    found = set()
    pending = [root]
    count = 0
    while pending:
        directory = pending.pop()
        for item in directory.iterdir():
            count += 1
            if count > 10000:
                raise ValueError()
            metadata = item.lstat()
            if metadata.st_mode & 0o170000 == 0o040000:
                safe(item, directory=True)
                pending.append(item)
            else:
                safe(item)
                found.add(item.relative_to(root).as_posix())
    if found != set(names):
        raise ValueError()


def stage_pin(group, digest):
    if group is None and digest is None:
        return STAGE_GROUP, STAGE_SHA
    if group is None or digest is None:
        raise ValueError()
    if (not isinstance(group, str) or not 1 <= len(group) <= 128
            or "/" in group or "\\" in group
            or PurePosixPath(group).parts != (group,)
            or validate_private_relative_parts((group,)) is not None
            or not isinstance(digest, str)
            or re.fullmatch(r"[0-9a-f]{64}", digest) is None):
        raise ValueError()
    return group, digest


def stage_count(value):
    if type(value) is not int or not 1 <= value <= MAX_STAGED_FILES-len(LAUNCHERS)-len(expected_generated()):
        raise ValueError()
    return value


def make_plan(stage, launchers, revision, stage_digest, launcher_digest, *, stage_group=STAGE_GROUP, stage_file_count=2578):
    stage_group, stage_digest = stage_pin(stage_group, stage_digest)
    stage_file_count = stage_count(stage_file_count)
    rows = stage["stage"]["files"]
    if type(rows) is not list or len(rows) != stage_file_count or stage.get("artifacts") != 43:
        raise ValueError()
    if (launchers.get("contract") != "windows-native-launchers.v1" or launchers.get("files") != LAUNCHERS
            or any(launchers.get(key) is not True for key in ("build_performed", "owned_cleanup_confirmed", "two_builds_identical"))):
        raise ValueError()
    files = []
    for row in rows:
        if type(row) is not list or len(row) != 3:
            raise ValueError()
        name, size, digest = row
        files.append(WindowsReleaseFile(source_relative_path=f"{stage_group}/stage/{name}", destination_relative_path=name, size_bytes=size, sha256=digest))
    for name, pin in LAUNCHERS.items():
        files.append(WindowsReleaseFile(source_relative_path=f"{LAUNCHER_GROUP}/{name}", destination_relative_path=name, size_bytes=pin["size"], sha256=pin["sha256"]))
    for name, data in expected_generated().items():
        files.append(WindowsReleaseFile(source_relative_path=f"{GENERATED_GROUP}/{name}", destination_relative_path=name, size_bytes=len(data), sha256=hashlib.sha256(data).hexdigest()))
    return WindowsReleaseStagePlan(git_revision=revision, tool_versions=(), lockfile_hashes=(
        {"name": "stage-input-manifest", "sha256": stage_digest},
        {"name": "launcher-input-manifest", "sha256": launcher_digest},
    ), files=tuple(files))


def expected_generated():
    return generated_files(identity="Example.PromptEnhancer", publisher="CN=ExamplePublisher", version="0.1.0.0", include_metrics=True)


def assemble(args):
    selected_count = stage_count(args.stage_file_count)
    if selected_count != 2578 and (args.stage_group is None or args.stage_manifest_sha256 is None):
        raise ValueError()
    selected_stage_group, selected_stage_sha = stage_pin(
        args.stage_group, args.stage_manifest_sha256
    )
    root = safe(external(args.source_root), directory=True)
    destination = external(args.destination)
    output = external(args.manifest_output)
    for target in (destination, output):
        safe(target.parent, directory=True)
        if target.exists() or target.is_symlink() or root == target or root in target.parents or target in root.parents:
            raise ValueError()
    if output == destination or destination in output.parents or output in destination.parents:
        raise ValueError()
    stage = pinned_json(root / selected_stage_group / "stage-file-manifest.json", args.stage_manifest_size, selected_stage_sha)
    launchers = pinned_json(root / LAUNCHER_GROUP / "launcher-manifest.json", args.launcher_manifest_size, args.launcher_manifest_sha256)
    plan = make_plan(stage, launchers, args.git_revision, selected_stage_sha,
                     args.launcher_manifest_sha256, stage_group=selected_stage_group, stage_file_count=selected_count)
    exact_tree(root / selected_stage_group / "stage", [row[0] for row in stage["stage"]["files"]])
    expected = expected_generated()
    exact_tree(root / GENERATED_GROUP, expected)
    for name, data in expected.items():
        if read(root / GENERATED_GROUP / name, 1024 * 1024) != data:
            raise ValueError()
    # The existing stager owns all copying, hash verification and no-clobber publication.
    try:
        manifest = stage_windows_release(plan=plan, source_root=root, destination=destination)
    except Exception:
        raise CandidatePhaseError("candidate_staging_failed") from None
    payload = canonical_json(manifest)
    with output.open("xb") as stream:
        stream.write(payload)
    return {"contract": "msix-candidate-assembly.v1", "passed": True, "files": len(plan.files),
            "manifest_sha256": hashlib.sha256(payload).hexdigest(), "manifest_size_bytes": len(payload),
            "dirty_snapshot_provenance_limited": True, "distributable": False,
            "packed": False, "signed": False, "installed": False, "launched": False}


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError()


def main(argv=None):
    try:
        parser = Parser()
        for name in ("source-root", "destination", "manifest-output"):
            parser.add_argument("--" + name, type=Path, required=True)
        for name in ("stage-manifest-size", "launcher-manifest-size"):
            parser.add_argument("--" + name, type=int, required=True)
        for name in ("launcher-manifest-sha256", "git-revision"):
            parser.add_argument("--" + name, required=True)
        parser.add_argument("--stage-group")
        parser.add_argument("--stage-manifest-sha256")
        parser.add_argument("--stage-file-count", type=int, default=2578)
        result = assemble(parser.parse_args(argv))
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except CandidatePhaseError:
        print('{"contract":"msix-candidate-assembly.v1","passed":false,"error_code":"candidate_staging_failed"}')
        return 2
    except Exception:
        print('{"contract":"msix-candidate-assembly.v1","passed":false,"error_code":"candidate_assembly_failed"}')
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
