"""Review and reproduce two fixed native CPython GUI launchers; never run them."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import struct
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from prompt_enhancer.application.owned_process import run_owned_process

SOURCE = Path(__file__).resolve().parents[1] / "packaging" / "windows" / "launcher.c"
VERSION = "15.2.0"
TOOLS = {"gcc": "bin/gcc.exe", "as": "bin/as.exe", "ld": "bin/ld.exe",
         "cc1": "libexec/gcc/x86_64-w64-mingw32/15.2.0/cc1.exe"}
HEADERS = ("lib/gcc/x86_64-w64-mingw32/15.2.0/include", "x86_64-w64-mingw32/include")
LIBRARIES = ("x86_64-w64-mingw32/lib/libkernel32.a", "x86_64-w64-mingw32/lib/libuser32.a")
MAX_INVENTORY_BYTES = 256 * 1024 * 1024
OVERSIZED_HEADERS = {
    "x86_64-w64-mingw32/include/mshtml.h": (6847802, "1f1ad12a02bbdab6cb71bf70ae33ad61176fab2566464ab2efe0c2542da84c6c"),
    "x86_64-w64-mingw32/include/mshtml.idl": (5487144, "aee79add96a62d03e9410cf1d66c0cfe98b4da86231e10cd82bb1b9a46cae066"),
}


class PreparationError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def safe(path: Path, directory=False) -> Path:
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError()
    for part in (path, *path.parents):
        metadata = part.lstat()
        if stat.S_ISLNK(metadata.st_mode) or getattr(metadata, "st_file_attributes", 0) & 0x400:
            raise ValueError()
    if directory != path.is_dir() or (not directory and not path.is_file()):
        raise ValueError()
    return path.resolve(strict=True)


def snapshot(value):
    return (value.st_dev, value.st_ino, value.st_mode, value.st_nlink, value.st_size,
            value.st_mtime_ns, value.st_ctime_ns, getattr(value, "st_birthtime_ns", None),
            getattr(value, "st_file_attributes", 0))


def same_open_file(path, descriptor, suffix=""):
    def ordinary(value):
        return (stat.S_ISREG(value.st_mode) and value.st_nlink == 1 and value.st_ino
                and not getattr(value, "st_file_attributes", 0) & 0x400)
    if not ordinary(path) or not ordinary(descriptor):
        return False
    if os.name != "nt":
        return snapshot(path) == snapshot(descriptor)
    # Windows path stat adds synthetic executable bits based on the filename;
    # fstat has no filename. Preserve every other mode bit and raw snapshots.
    # CPython v3.11.0 Modules/posixmodule.c, win32_xstat_impl.
    path_mode = path.st_mode
    if (suffix.casefold() in {".exe", ".bat", ".cmd", ".com"}
            and path_mode == (descriptor.st_mode | 0o111)):
        path_mode = descriptor.st_mode
    def cross(value, mode):
        return (value.st_dev, value.st_ino, mode, value.st_nlink, value.st_size,
                value.st_mtime_ns, getattr(value, "st_birthtime_ns", value.st_ctime_ns),
                getattr(value, "st_file_attributes", 0))
    return cross(path, path_mode) == cross(descriptor, descriptor.st_mode)


def read(path: Path, maximum=64 * 1024 * 1024) -> bytes:
    safe(path)
    before = path.lstat()
    if before.st_nlink != 1 or not 0 < before.st_size <= maximum:
        raise ValueError()
    with path.open("rb") as stream:
        opened = os.fstat(stream.fileno())
        if not same_open_file(before, opened, path.suffix):
            raise ValueError()
        value = stream.read(maximum + 1)
        after_read = os.fstat(stream.fileno())
        after = path.lstat()
        if (snapshot(before) != snapshot(after) or snapshot(opened) != snapshot(after_read)
                or not same_open_file(after, after_read, path.suffix) or len(value) != before.st_size):
            raise ValueError()
    return value


def pe_imports(data: bytes) -> set[str]:
    """Bounded PE32+ import names for explicit tool closure and output checks."""
    if len(data) < 256 or data[:2] != b"MZ":
        raise ValueError()
    offset = struct.unpack_from("<I", data, 60)[0]
    if offset + 264 > len(data) or data[offset:offset+4] != b"PE\0\0":
        raise ValueError()
    machine, sections = struct.unpack_from("<HH", data, offset + 4)
    optional_size = struct.unpack_from("<H", data, offset + 20)[0]
    optional = offset + 24
    if machine != 0x8664 or not 1 <= sections <= 96 or struct.unpack_from("<H", data, optional)[0] != 0x20b or optional_size < 128:
        raise ValueError()
    table = optional + optional_size
    if table + sections * 40 > len(data):
        raise ValueError()

    def file_offset(rva):
        for index in range(sections):
            _, virtual, size, raw = struct.unpack_from("<IIII", data, table + index * 40 + 8)
            if virtual <= rva < virtual + size and raw + rva - virtual < len(data):
                return raw + rva - virtual
        raise ValueError()

    rva, size = struct.unpack_from("<II", data, optional + 120)
    if not rva:
        return set()
    start = file_offset(rva)
    names = set()
    for index in range(min(size // 20 + 1, 256)):
        position = start + index * 20
        if position + 20 > len(data):
            raise ValueError()
        fields = struct.unpack_from("<IIIII", data, position)
        if fields == (0, 0, 0, 0, 0):
            return names
        name_at = file_offset(fields[3])
        name = data[name_at:name_at+129].split(b"\0", 1)[0]
        if re.fullmatch(rb"[A-Za-z0-9_.-]{1,128}\.dll", name, re.IGNORECASE) is None:
            raise ValueError()
        names.add(name.decode("ascii").lower())
    raise ValueError()


def inventory(root: Path) -> dict:
    root = safe(root, directory=True)
    files = {}
    total = 0
    def add(relative, maximum=64 * 1024 * 1024, pin=None):
        nonlocal total
        if relative in files or len(files) >= 4096:
            raise ValueError()
        remaining = MAX_INVENTORY_BYTES - total
        if pin is not None and (root / relative).lstat().st_size != pin[0]:
            raise PreparationError("inventory_header_pin_mismatch")
        if remaining <= 0 or (root / relative).lstat().st_size > remaining:
            raise PreparationError("inventory_budget_exceeded")
        try:
            value = read(root / relative, min(maximum, remaining))
        except Exception:
            raise PreparationError("inventory_file_invalid") from None
        if pin is not None and hashlib.sha256(value).hexdigest() != pin[1]:
            raise PreparationError("inventory_header_pin_mismatch")
        total += len(value)
        files[relative] = {"sha256": hashlib.sha256(value).hexdigest(), "size": len(value)}
        return value
    pending = [(relative, add(relative)) for relative in TOOLS.values()]
    for relative in LIBRARIES:
        add(relative)
    system_imports = set()
    while pending:
        relative, data = pending.pop()
        try:
            imports = pe_imports(data)
        except Exception:
            raise PreparationError("inventory_pe_invalid") from None
        for name in imports:
            dependency = "bin/" + name
            if (root / dependency).is_file():
                if dependency not in files:
                    if len(files) >= 64:
                        raise ValueError()
                    pending.append((dependency, add(dependency)))
            elif name.startswith(("api-ms-win-", "ext-ms-win-")) or (Path(os.environ["SystemRoot"]) / "System32" / name).is_file():
                system_imports.add(name)
            else:
                raise PreparationError("inventory_dependency_unavailable")
    for relative in HEADERS:
        directory = safe(root / relative, directory=True)
        for path in directory.rglob("*"):
            safe(path, directory=path.is_dir())
            if path.is_file():
                name = path.relative_to(root).as_posix()
                pin = OVERSIZED_HEADERS.get(name)
                add(name, pin[0] if pin is not None else 4 * 1024 * 1024, pin)
    return {"files": dict(sorted(files.items())),
            "system_imports_not_pinned": sorted(system_imports), "compiler_version_directory": VERSION}


def digest(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def commands(root: Path, directory: Path, metrics: bool) -> tuple[list[str], list[str]]:
    compile_command = [str(root / TOOLS["gcc"]), "-c", "launcher.c", "-o", "launcher.o", "-O2",
        "-ffreestanding", "-fno-builtin", "-nostdinc", "-g0", "-frandom-seed=prompt-enhancer-launcher",
        "-B" + str(root / "bin") + os.sep, "-B" + str((root / TOOLS["cc1"]).parent) + os.sep]
    for include in HEADERS:
        compile_command.extend(("-isystem", str(root / include)))
    if metrics:
        compile_command.append("-DMETRICS_ENTRY=1")
    link_command = [str(root / TOOLS["ld"]), "-m", "i386pep", "--subsystem", "windows", "--entry", "launcher_entry",
                    "--no-insert-timestamp", "--dynamicbase", "--nxcompat", "--high-entropy-va",
                    "launcher.o", *(str(root / relative) for relative in LIBRARIES), "-o", "launcher.exe"]
    return compile_command, link_command


def prepare(toolchain: Path, output: Path, expected: str | None) -> dict:
    if os.name != "nt":
        raise ValueError()
    root = safe(toolchain, directory=True)
    parent = safe(output.parent, directory=True)
    repository, home = SOURCE.parents[2], Path.home().resolve()
    if output.exists() or not output.is_absolute() or ".." in output.parts or any(
            parent.is_relative_to(value) or value.is_relative_to(parent) for value in (repository, home)):
        raise ValueError()
    try:
        before = inventory(root)
    except PreparationError:
        raise
    except Exception:
        raise PreparationError("inventory_failed") from None
    source = read(SOURCE)
    identity = digest(before)
    if expected is not None and expected != identity:
        raise PreparationError("inventory_digest_mismatch")
    output.mkdir()
    with (output / "toolchain-manifest.json").open("x", encoding="utf-8") as stream:
        json.dump(before, stream, sort_keys=True, separators=(",", ":"))
    receipt = {"contract": "windows-native-launchers.v1", "toolchain_manifest_sha256": identity,
               "source_sha256": hashlib.sha256(source).hexdigest(), "build_performed": False,
               "launcher_execution_unproven": True, "system_runtime_closure_unpinned": True}
    if expected is None:
        return receipt
    system = os.environ["SystemRoot"]
    built = {}
    for name, metrics in (("PromptEnhancer.exe", False), ("PromptEnhancerMetrics.exe", True)):
        copies = []
        for _ in range(2):
            directory = Path(tempfile.mkdtemp(prefix="owned-build-", dir=output))
            for child in ("home", "temp"):
                (directory / child).mkdir()
            with (directory / "launcher.c").open("xb") as stream:
                stream.write(source)
            environment = {"SystemRoot": system, "WINDIR": system, "PATH": str(root / "bin") + os.pathsep + str(Path(system) / "System32"),
                           "TEMP": str(directory / "temp"), "TMP": str(directory / "temp"), "HOME": str(directory / "home"),
                           "USERPROFILE": str(directory / "home"), "SOURCE_DATE_EPOCH": "1399328544"}
            for command, limit, phase in zip(commands(root, directory, metrics), (2, 1), ("compiler", "linker"), strict=True):
                try:
                    result = run_owned_process(command, cwd=directory, env=environment, timeout=30,
                                               maximum_active_processes=limit, stdout_limit=8192, stderr_limit=8192)
                except Exception:
                    raise PreparationError(phase + "_launch_or_cleanup_failed") from None
                if result.returncode:
                    raise PreparationError(phase + "_failed")
                del result
            data = read(directory / "launcher.exe")
            if pe_imports(data) != {"kernel32.dll", "user32.dll"}:
                raise PreparationError("output_imports_mismatch")
            offset = struct.unpack_from("<I", data, 60)[0]
            optional = offset + 24
            if (struct.unpack_from("<I", data, offset + 8)[0] != 0
                    or struct.unpack_from("<H", data, optional + 68)[0] != 2
                    or struct.unpack_from("<H", data, optional + 70)[0] & 0x160 != 0x160):
                raise PreparationError("output_pe_contract_mismatch")
            copies.append(data)
        if copies[0] != copies[1]:
            raise PreparationError("output_not_reproducible")
        built[name] = copies[0]
    if inventory(root) != before or read(SOURCE) != source:
        raise PreparationError("build_inputs_changed")
    for name, data in built.items():
        with (output / name).open("xb") as stream:
            stream.write(data)
    receipt.update(build_performed=True, two_builds_identical=True, owned_cleanup_confirmed=True,
                   files={name: {"sha256": hashlib.sha256(data).hexdigest(), "size": len(data)} for name, data in built.items()})
    with (output / "launcher-manifest.json").open("x", encoding="utf-8") as stream:
        json.dump(receipt, stream, sort_keys=True, separators=(",", ":"))
    return receipt


def main(argv=None):
    class Parser(argparse.ArgumentParser):
        def error(self, message):
            raise ValueError()
    try:
        parser = Parser(description=__doc__)
        parser.add_argument("--toolchain-root", type=Path, required=True)
        parser.add_argument("--output", type=Path, required=True)
        parser.add_argument("--build-toolchain-sha256")
        args = parser.parse_args(argv)
        receipt = prepare(args.toolchain_root, args.output, args.build_toolchain_sha256)
        result = 0
    except PreparationError as error:
        receipt, result = {"contract": "windows-native-launchers.v1", "error_code": error.code}, 1
    except Exception:
        receipt, result = {"contract": "windows-native-launchers.v1", "error_code": "launcher_preparation_failed"}, 1
    print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))
    return result


if __name__ == "__main__":
    raise SystemExit(main())
