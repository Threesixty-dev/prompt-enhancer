"""Finite stdout protocol for the hash-pinned MakeAppx 26100 executable.

Templates are literal UTF-16 resources in that executable. Capacity is the
sum of concrete permitted messages, never an unbounded logging allowance.
"""
from collections import Counter
from pathlib import PureWindowsPath
import re

from prompt_enhancer.application.build_evidence.manifest import _validate_staged_relative_path


class OutputError(ValueError):
    pass


class OutputPolicy:
    def __init__(self, candidate: str, package: str, names):
        names = tuple(names)
        if not 1 <= len(names) <= 9998 or len(set(n.casefold() for n in names)) != len(names):
            raise OutputError("sdk_stdout_inputs_invalid")
        for name in names:
            _validate_staged_relative_path(name)
        if "AppxManifest.xml" not in names:
            raise OutputError("sdk_stdout_inputs_invalid")
        for path in (candidate, package):
            if len(path) > 1024 or any(ord(c) < 32 or c == '"' for c in path):
                raise OutputError("sdk_stdout_inputs_invalid")
        root = str(PureWindowsPath(candidate))
        output = str(PureWindowsPath(package))
        manifest = str(PureWindowsPath(root) / "AppxManifest.xml")
        self.lines = {}
        self.footer = "Package creation succeeded."
        self.required = {"header", "copyright", "success", "manifest", "packing"}
        self.payload = set(names) - {"AppxManifest.xml"}

        def add(line, key):
            if line in self.lines:
                raise OutputError("sdk_stdout_inputs_invalid")
            self.lines[line] = key

        add("Microsoft (R) MakeAppx Tool", "header")
        add("Copyright (C) 2013 Microsoft.  All rights reserved.", "copyright")
        add("Package creation succeeded.", "success")
        add("Using default hash method: SHA256.", "hash")
        add("Option /h specified, using custom hash method: SHA256.", "hash")
        add(f'Enumerating files from directory "{root}"', "enumeration")
        add(f'Ignoring footprint file "{manifest}".', "footprint")
        add(f'Using "{manifest}" as the manifest for the package.', "manifest")
        add(f'The path (/p) parameter is: "{output}"', "output_path")
        add(f'The content directory (/d) parameter is: "{root}"', "content_path")
        # SDK enumeration may count the separately consumed manifest. Both
        # finite summaries bind the same explicit input set, never arbitrary N.
        for count in {len(names), len(self.payload)}:
            add(f'Packing {count} file(s) in "{root}" (content directory) to "{output}" (output file name).', "packing")
        for name in sorted(self.payload):
            source = str(PureWindowsPath(root) / PureWindowsPath(name))
            for relative in {name, str(PureWindowsPath(name))}:
                add(f'Adding "{source}" to the package as a payload file.  Its path in the package is "{relative}".', ("adding", name))
                add(f'Processing "{source}" as a payload file.  Its path in the package will be "{relative}".', ("processing", name))
        # The pinned SDK canonicalizes its own absolute arguments to extended
        # paths. These alternatives bind exact supplied paths, not user input
        # admitted through the external-path policy.
        for line, key in tuple(self.lines.items()):
            extended = line.replace('"' + root, '"' + "\\\\?\\" + root)
            extended = extended.replace('"' + output, '"' + "\\\\?\\" + output)
            if extended != line:
                add(extended, key)
        # Alternative spellings share one occurrence slot, not extra capacity.
        lengths = {}
        for line, key in self.lines.items():
            lengths[key] = max(lengths.get(key, 0), len(line.encode("utf-8")))
        # Resource %1!I64u! is unsigned 64-bit decimal, never recorded in receipts.
        lengths["memory"] = len("Memory limit defaulting to ") + 20 + len(" bytes.")
        self.blank_limit = len(lengths) + 1
        self.line_limit = len(lengths) + self.blank_limit
        self.line_bytes = max(lengths.values())
        self.byte_limit = sum(length + 3 for length in lengths.values()) + 3 * self.blank_limit

    def _key(self, line):
        key = self.lines.get(line)
        if key is not None:
            return key
        match = re.fullmatch(r"Memory limit defaulting to (0|[1-9][0-9]{0,19}) bytes\.", line)
        if match and int(match[1]) <= 0xFFFFFFFFFFFFFFFF:
            return "memory"
        return None

    def validate(self, payload):
        try:
            return self._validate(payload)
        except OutputError as error:
            diagnostics = {}
            if isinstance(payload, bytes) and len(payload) <= self.byte_limit:
                normalized = re.sub(rb"\r\r\n|\r\n", b"\n", payload)
                lines = normalized.split(b"\n")
                diagnostics = {"ends_lf": payload.endswith(b"\n"), "crlf_count": payload.count(b"\r\n"),
                               "crcrlf_count": payload.count(b"\r\r\n"),
                               "lone_cr_count": normalized.count(b"\r"),
                               "max_line_bytes": max(map(len, lines), default=0), "unknown_line_count": 0}
                categories = Counter()
                for line in lines:
                    if not line:
                        categories["blank"] += 1
                        continue
                    try:
                        key = self._key(line.decode("utf-8", "strict"))
                    except UnicodeDecodeError:
                        key = None
                    categories[(key[0] if isinstance(key, tuple) else key) or "unknown"] += 1
                diagnostics["template_counts"] = dict(sorted(categories.items()))
                diagnostics["unknown_line_count"] = categories["unknown"]
            error.diagnostics = diagnostics
            raise

    def _validate(self, payload):
        if not isinstance(payload, bytes) or len(payload) > self.byte_limit:
            raise OutputError("sdk_stdout_bounds_invalid")
        try:
            text = payload.decode("utf-8", "strict")
        except UnicodeDecodeError:
            raise OutputError("sdk_stdout_encoding_invalid") from None
        normalized = re.sub(r"\r\r\n|\r\n", "\n", text)
        if "\r" in normalized:
            raise OutputError("sdk_stdout_truncated")
        lines = normalized.split("\n")
        if normalized.endswith("\n"):
            lines.pop()
        if len(lines) > self.line_limit:
            raise OutputError("sdk_stdout_bounds_invalid")
        counts = Counter()
        coverage = set()
        for line in lines:
            if len(line.encode("utf-8")) > self.line_bytes:
                raise OutputError("sdk_stdout_bounds_invalid")
            if not line:
                counts["blank"] += 1
                if counts["blank"] > self.blank_limit:
                    raise OutputError("sdk_stdout_bounds_invalid")
                continue
            key = self._key(line)
            if key is None:
                raise OutputError("sdk_stdout_unknown")
            counts[key] += 1
            if counts[key] > 1:
                raise OutputError("sdk_stdout_duplicate")
            if isinstance(key, tuple) and key[0] in {"adding", "processing", "extracting"}:
                coverage.add(key[1])
        if not self.required <= counts.keys() or coverage != self.payload:
            raise OutputError("sdk_stdout_incomplete")
        if next((line for line in reversed(lines) if line), None) != self.footer:
            raise OutputError("sdk_stdout_incomplete")
        return {"sdk_stdout_bytes": len(payload), "sdk_stdout_lines": len(lines),
                getattr(self, "coverage_field", "sdk_stdout_payload_files"): len(coverage), "sdk_stdout_limit_bytes": self.byte_limit}


class UnpackPolicy(OutputPolicy):
    """Exact pinned SDK unpack resources; no per-file log assumption."""
    def __init__(self, package, destination, names):
        names = tuple(names)
        if not 1 <= len(names) <= 10000 or len(set(n.casefold() for n in names)) != len(names):
            raise OutputError("sdk_stdout_inputs_invalid")
        for name in names:
            _validate_staged_relative_path(name)
        for path in (package, destination):
            if len(path) > 1024 or any(ord(c) < 32 or c == '"' for c in path):
                raise OutputError("sdk_stdout_inputs_invalid")
        source, output = str(PureWindowsPath(package)), str(PureWindowsPath(destination))
        self.footer = "Package extraction succeeded."
        self.required = {"header", "copyright", "unpacking", "success"}
        self.payload = set(names)
        self.coverage_field = "sdk_stdout_extracted_files"
        self.lines = {
            "Microsoft (R) MakeAppx Tool": "header",
            "Copyright (C) 2013 Microsoft.  All rights reserved.": "copyright",
            self.footer: "success",
            f'The path (/p) parameter is: "{source}"': "input_path",
            f'The output directory (/d) parameter is: "{output}"': "output_path",
            f'Unpacking "{source}" (package name) to "{output}" (output directory).': "unpacking",
        }
        for line, key in tuple(self.lines.items()):
            extended = line.replace('"' + source, '"' + "\\\\?\\" + source).replace('"' + output, '"' + "\\\\?\\" + output)
            if extended != line:
                self.lines[extended] = key
        for name in names:
            for relative in {name, str(PureWindowsPath(name))}:
                for dest in {str(PureWindowsPath(output) / PureWindowsPath(name)), output + "/" + name}:
                    for prefix in ("", "\\\\?\\"):
                        self.lines[f"Extracting file {relative} to {prefix}{dest}"] = ("extracting", name)
        lengths = {"memory": len("Memory limit defaulting to ") + 20 + len(" bytes.")}
        for line, key in self.lines.items():
            lengths[key] = max(lengths.get(key, 0), len(line.encode("utf-8")))
        self.blank_limit = len(lengths) + 1
        self.line_limit = len(lengths) + self.blank_limit
        self.line_bytes = max(lengths.values())
        self.byte_limit = sum(length + 3 for length in lengths.values()) + 3 * self.blank_limit
