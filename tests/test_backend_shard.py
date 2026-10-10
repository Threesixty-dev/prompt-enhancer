"""Synthetic CLI proof that CI shards cover every case and preserve failures."""

from pathlib import Path
import os
import sys
import sysconfig

import pytest

from prompt_enhancer.application.local_command_process import minimal_environment
from prompt_enhancer.application.owned_process import run_owned_process
from scripts.run_backend_shard import main


def test_backend_shards_cover_every_case_once_and_preserve_failure(tmp_path):
    script = Path(__file__).resolve().parents[1] / "scripts" / "run_backend_shard.py"
    fixture = "from pathlib import Path\nfrom tests.example_helpers import FAILING_CASE\n\n" + "\n".join(
        f"def test_case_{index}():\n"
        f"    marker = Path('case-{index}.ran')\n"
        "    marker.write_text(str(int(marker.read_text()) + 1) if marker.exists() else '1')\n"
        f"    assert {index} != FAILING_CASE\n"
        for index in range(6)
    )
    observed = []
    exit_codes = []
    for number in (1, 2):
        root = tmp_path / f"shard-{number}"
        root.mkdir()
        (root / "pytest.ini").write_text("[pytest]\n")
        (root / "scripts").mkdir()
        (root / "scripts" / "run_backend_shard.py").write_text(script.read_text())
        (root / "tests").mkdir()
        (root / "tests" / "__init__.py").write_text("")
        (root / "tests" / "example_helpers.py").write_text("FAILING_CASE = 3\n")
        (root / "test_example.py").write_text(fixture)
        result = run_owned_process(
            (sys._base_executable, "-m", "scripts.run_backend_shard", "--shard", str(number), "--shard-count", "2"),
            cwd=root,
            env={
                **minimal_environment(),
                "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
                "PYTHONPATH": os.pathsep.join(dict.fromkeys((
                    sysconfig.get_path("purelib"), sysconfig.get_path("platlib"),
                ))),
            },
            stdout_limit=32 * 1024,
            stderr_limit=8 * 1024,
            timeout=15,
            maximum_active_processes=1,
        )
        assert b"3 of 6 collected tests selected" in result.stdout
        markers = list(root.glob("case-*.ran"))
        assert all(marker.read_text() == "1" for marker in markers)
        observed.append({marker.name for marker in markers})
        exit_codes.append(result.returncode)
    assert observed[0].isdisjoint(observed[1])
    assert observed[0] | observed[1] == {f"case-{index}.ran" for index in range(6)}
    assert exit_codes == [0, 1]


@pytest.mark.parametrize("number,count", [(0, 2), (3, 2), (1, 0), (1, 17)])
def test_invalid_backend_shard_is_rejected_before_running_tests(number, count):
    with pytest.raises(SystemExit) as caught:
        main(["--shard", str(number), "--shard-count", str(count)])
    assert caught.value.code == 2
