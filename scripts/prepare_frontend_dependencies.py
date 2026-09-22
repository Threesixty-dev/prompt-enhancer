"""Explicit, review-gated online dependency preparation; never build an app."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from prompt_enhancer.infrastructure.frontend_dependency_preparation import prepare_frontend_dependencies, FrontendDependencyPreparationError


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise FrontendDependencyPreparationError("dependency_cli_invalid")


def main(argv=None):
    try:
        parser = Parser()
        for name in ("frontend-root", "source-manifest", "node-executable", "npm-root", "npm-manifest", "destination"):
            parser.add_argument("--" + name, type=Path, required=True)
        for name in ("source-manifest-size", "node-size", "npm-manifest-size"):
            parser.add_argument("--" + name, type=int, required=True)
        for name in ("source-manifest-sha256", "node-sha256", "node-version", "npm-manifest-sha256", "npm-version"):
            parser.add_argument("--" + name, required=True)
        receipt = prepare_frontend_dependencies(**vars(parser.parse_args(argv)))
        print(json.dumps(receipt, sort_keys=True))
        return 0
    except FrontendDependencyPreparationError as error:
        print(json.dumps({"passed": False, "error_code": str(error)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
