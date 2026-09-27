"""Prepare the reviewed offline dashboard build; never signing or release acceptance."""
import argparse
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from prompt_enhancer.infrastructure.frontend_dashboard_preparation import (
    FrontendDashboardPreparationError,
    prepare_frontend_dashboard,
)


CONTRACT = "frontend-dashboard-preparation.v1"
USAGE = (
    "usage: prepare_frontend_dashboard.py --frontend-root DIR --source-manifest FILE\n"
    "       --tooling-manifest FILE --node-executable FILE --node-sha256 HEX\n"
    "       --node-size-bytes BYTES --node-version VERSION --destination DIR\n"
    "\n"
    "Run the reviewed offline dashboard build from pinned local inputs and print one\n"
    "content-free JSON receipt. A successful build is not signing, licence closure,\n"
    "native runtime proof, or release acceptance.\n"
)
_PATH_FLAGS = ("frontend-root", "source-manifest", "tooling-manifest", "node-executable", "destination")
_TEXT_FLAGS = ("node-sha256", "node-version")
_SIZE_FLAG = "node-size-bytes"
_SHA_FIELDS = (
    "manifest_sha256", "source_manifest_sha256", "tooling_manifest_sha256", "node_sha256",
    "package_lock_sha256", "module_inventory_sha256", "package_binding_sha256",
)
_COUNT_FIELDS = (
    "manifest_size_bytes", "source_manifest_size_bytes", "tooling_manifest_size_bytes", "node_size_bytes",
    "package_lock_size_bytes", "module_inventory_size_bytes", "package_bindings_present",
    "package_bindings_missing",
)
_FLAG_FIELDS = (
    "node_modules_closure_not_pinned", "network_isolation_not_proven", "module_inventory_complete",
    "frontend_licence_closure_verified",
)
_VERSION_FIELD = "node_version"
_SERVICE_ERROR_CODES = {
    "frontend dashboard manifest is invalid": "frontend_dashboard_manifest_invalid",
    "frontend dashboard manifest is incomplete": "frontend_dashboard_manifest_incomplete",
    "frontend dashboard source manifest is too large": "frontend_dashboard_source_oversize",
    "frontend dashboard source unavailable": "frontend_dashboard_source_unavailable",
    "frontend dashboard source changed": "frontend_dashboard_source_changed",
    "frontend dashboard tooling is unsafe": "frontend_dashboard_tooling_unsafe",
    "frontend dashboard tooling changed": "frontend_dashboard_tooling_changed",
    "frontend dashboard node identity is invalid": "frontend_dashboard_node_identity_invalid",
    "frontend dashboard destination or node identity is invalid": "frontend_dashboard_destination_or_node_invalid",
    "frontend dashboard destination is unavailable": "frontend_dashboard_destination_unavailable",
    "frontend dashboard node version is invalid": "frontend_dashboard_node_version_invalid",
    "frontend dashboard command failed": "frontend_dashboard_command_failed",
    "frontend dashboard cleanup unconfirmed": "frontend_dashboard_cleanup_unconfirmed",
    "frontend dashboard typecheck failed": "frontend_dashboard_typecheck_failed",
    "frontend dashboard node-config typecheck failed": "frontend_dashboard_node_config_typecheck_failed",
    "frontend dashboard build failed": "frontend_dashboard_build_failed",
    "frontend dashboard output is invalid": "frontend_dashboard_output_invalid",
    "frontend module inventory is invalid": "frontend_dashboard_module_inventory_invalid",
    "frontend module inventory output changed": "frontend_dashboard_module_inventory_changed",
    "frontend package binding invalid": "frontend_dashboard_package_binding_invalid",
    "frontend package binding changed": "frontend_dashboard_package_binding_changed",
}
_BUILD_FAILURE_WITH_CODE = re.compile(r"frontend dashboard build failed: [a-z_]{1,64}")
CLI_INVALID = "frontend_dashboard_cli_invalid"
RECEIPT_INVALID = "frontend_dashboard_receipt_invalid"
INTERRUPTED = "frontend_dashboard_interrupted"
FALLBACK_ERROR_CODE = "frontend_dashboard_preparation_failed"
ERROR_CODES = frozenset(_SERVICE_ERROR_CODES.values()) | {CLI_INVALID, RECEIPT_INVALID, INTERRUPTED}


class _Invalid(Exception):
    """Content-free local failure; the code is always from the fixed vocabulary."""

    def __init__(self, code):
        super().__init__()
        self.code = code


class Parser(argparse.ArgumentParser):
    def error(self, message):
        del message
        raise _Invalid(CLI_INVALID)

    def exit(self, status=0, message=None):
        del status, message
        raise _Invalid(CLI_INVALID)


class _Once(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        if getattr(namespace, self.dest, None) is not None:
            parser.error("repeated option")
        setattr(namespace, self.dest, values)


def _size(value):
    if not isinstance(value, str) or re.fullmatch(r"[1-9][0-9]{0,9}", value) is None:
        raise ValueError()
    return int(value)


def _parser():
    parser = Parser(prog="prepare_frontend_dashboard.py", add_help=False, allow_abbrev=False)
    for name in _PATH_FLAGS:
        parser.add_argument("--" + name, required=True, type=Path, action=_Once)
    for name in _TEXT_FLAGS:
        parser.add_argument("--" + name, required=True, action=_Once)
    parser.add_argument("--" + _SIZE_FLAG, required=True, type=_size, action=_Once)
    return parser


def _service_code(error):
    message = error.args[0] if len(error.args) == 1 else None
    if not isinstance(message, str):
        return FALLBACK_ERROR_CODE
    if _BUILD_FAILURE_WITH_CODE.fullmatch(message):
        return _SERVICE_ERROR_CODES["frontend dashboard build failed"]
    return _SERVICE_ERROR_CODES.get(message, FALLBACK_ERROR_CODE)


def _receipt(prepared):
    """Copy only the fixed scalar provenance and limitation fields, verbatim."""
    receipt = {"contract": CONTRACT, "passed": True, "release_accepted": False}
    try:
        for name in _SHA_FIELDS:
            value = getattr(prepared, name)
            if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
                raise _Invalid(RECEIPT_INVALID)
            receipt[name] = value
        for name in _COUNT_FIELDS:
            value = getattr(prepared, name)
            if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 2**53:
                raise _Invalid(RECEIPT_INVALID)
            receipt[name] = value
        for name in _FLAG_FIELDS:
            value = getattr(prepared, name)
            if not isinstance(value, bool):
                raise _Invalid(RECEIPT_INVALID)
            receipt[name] = value
        value = getattr(prepared, _VERSION_FIELD)
    except AttributeError:
        raise _Invalid(RECEIPT_INVALID) from None
    if not isinstance(value, str) or re.fullmatch(r"[0-9]{1,6}\.[0-9]{1,6}\.[0-9]{1,6}(?:-[0-9A-Za-z.]{1,32})?", value) is None:
        raise _Invalid(RECEIPT_INVALID)
    receipt[_VERSION_FIELD] = value
    return receipt


def _failure(code):
    return json.dumps({"passed": False, "error_code": code if code in ERROR_CODES else FALLBACK_ERROR_CODE})


def main(argv=None):
    arguments = list(sys.argv[1:] if argv is None else argv)
    try:
        if arguments in (["--help"], ["-h"]):
            print(USAGE, end="")
            return 0
        options = vars(_parser().parse_args(arguments))
        output = json.dumps(_receipt(prepare_frontend_dashboard(**options)), sort_keys=True)
    except _Invalid as error:
        print(_failure(error.code))
        return 1
    except FrontendDashboardPreparationError as error:
        print(_failure(_service_code(error)))
        return 1
    except KeyboardInterrupt:
        print(_failure(INTERRUPTED))
        return 130
    except Exception:
        print(_failure(FALLBACK_ERROR_CODE))
        return 1
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
