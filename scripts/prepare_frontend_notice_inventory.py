"""Produce external partial frontend evidence; no rendering or legal conclusion."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from prompt_enhancer.infrastructure.frontend_notice_inventory import prepare, FrontendNoticeError


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise FrontendNoticeError("frontend_notice_cli_invalid")


def main(argv=None):
    try:
        parser = Parser()
        for name in ("dependencies-root", "dashboard-root", "output"):
            parser.add_argument("--" + name, required=True, type=Path)
        for name in ("dependency-provenance-sha256", "dashboard-manifest-sha256", "graph-sha256"):
            parser.add_argument("--" + name, required=True)
        print(json.dumps(prepare(**vars(parser.parse_args(argv))), sort_keys=True))
        return 0
    except FrontendNoticeError as error:
        print(json.dumps({"passed": False, "error_code": str(error)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
