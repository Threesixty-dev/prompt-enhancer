import importlib.util
from pathlib import Path
import sys


def scanner():
    root = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location("bench_privacy_scanner", root / "scripts/privacy_scan.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return root, module


def test_bench_sources_and_fixtures_pass_repository_privacy_gate():
    root, module = scanner()
    paths = []
    for directory in ("experiments", "bench/src", "bench/examples", "bench/browser", "tests/bench", "deployment/bench", "docs/bench"):
        paths += [p for p in (root / directory).rglob("*") if p.is_file() and "__pycache__" not in p.parts]
    paths += list((root / ".github/workflows").glob("bench-*.yml"))
    assert module.scan_repository(root, paths) == []


def test_fixture_scanner_keeps_secret_canary_detection(tmp_path):
    _, module = scanner()
    # Assemble a deliberately invalid provider token without storing it as source.
    (tmp_path / "canary.txt").write_text("ghp" + "_" + "x" * 30)
    assert module.scan_repository(tmp_path)
