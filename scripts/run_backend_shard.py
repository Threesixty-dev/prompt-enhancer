"""Run a disjoint part of pytest's complete collection without omitting tests."""

from __future__ import annotations

import argparse

import pytest


class BackendShard:
    def __init__(self, number: int, count: int) -> None:
        self.number = number
        self.count = count

    @pytest.hookimpl(trylast=True)
    def pytest_collection_modifyitems(self, config, items) -> None:
        collected = len(items)
        selected = items[self.number - 1::self.count]
        selected_ids = {id(item) for item in selected}
        deselected = [item for item in items if id(item) not in selected_ids]
        config.hook.pytest_deselected(items=deselected)
        items[:] = selected
        reporter = config.pluginmanager.getplugin("terminalreporter")
        if reporter is not None:
            reporter.write_line(
                f"Backend shard {self.number}/{self.count}: "
                f"{len(selected)} of {collected} collected tests selected"
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shard", required=True, type=int)
    parser.add_argument("--shard-count", required=True, type=int)
    arguments = parser.parse_args(argv)
    if not 1 <= arguments.shard <= arguments.shard_count <= 16:
        parser.error("require 1 <= shard <= shard-count <= 16")
    return int(pytest.main(
        ["--tb=short", "--durations=15"],
        plugins=[BackendShard(arguments.shard, arguments.shard_count)],
    ))


if __name__ == "__main__":
    raise SystemExit(main())
