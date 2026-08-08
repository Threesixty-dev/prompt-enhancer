"""Fail closed on common secrets, personal emails, and private home paths.

This scanner is intentionally dependency-free so it can run before installing the
project. It is defense in depth, not a replacement for reviewing staged changes.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
import sys
from typing import Iterable, Sequence


_ALWAYS_SKIPPED_PARTS = frozenset({".git"})
_PROHIBITED_PRIVATE_PARTS = frozenset(
    {
        ".claude",
        ".codex",
        ".secrets",
        "archived_sessions",
        "data",
        "exports",
        "logs",
        "models",
        "secrets",
        "sessions",
        "var",
    }
)
_SKIPPED_GENERATED_PARTS = frozenset(
    {
        ".cache",
        ".mypy_cache",
        ".next",
        ".pytest_cache",
        ".ruff_cache",
        ".svelte-kit",
        ".venv",
        "__pycache__",
        "build",
        "coverage",
        "dist",
        "htmlcov",
        "node_modules",
        "runtime",
        "venv",
    }
)
_PROHIBITED_NAMES = frozenset(
    {
        ".claude.json",
        "auth.json",
        "credentials.json",
        "history.jsonl",
    }
)
_PROHIBITED_SUFFIXES = (
    ".arrow",
    ".bin",
    ".db",
    ".db-shm",
    ".db-wal",
    ".duckdb",
    ".duckdb.wal",
    ".feather",
    ".gguf",
    ".index",
    ".key",
    ".ndjson",
    ".onnx",
    ".parquet",
    ".pem",
    ".pfx",
    ".p12",
    ".pyc",
    ".safetensors",
    ".sqlite",
    ".sqlite-shm",
    ".sqlite-wal",
    ".sqlite3",
    ".sqlite3-shm",
    ".sqlite3-wal",
    ".transcript.json",
    ".transcript.jsonl",
    ".vault",
)
_MAX_TEXT_BYTES = 2 * 1024 * 1024

_EMAIL = re.compile(
    r"(?<![A-Za-z0-9.!#$%&'*+/=?^_`{|}~-])"
    r"(?P<local>[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+)@"
    r"(?P<domain>[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+)"
)
_WINDOWS_HOME = re.compile(
    r"(?i)(?<![A-Za-z0-9])(?:[A-Z]:[\\/])Users[\\/]"
    r"(?P<name>[^\\/\s`\"'<>:]+)"
)
_UNIX_HOME = re.compile(
    ("/" + r"(?:home|Users)/") + r"(?P<name>[^/\s`\"'<>:]+)"
)
_GENERIC_SECRET = re.compile(
    r"(?ix)\b(?:api[_-]?key|access[_-]?token|auth[_-]?token|client[_-]?secret|"
    r"password|passwd|private[_-]?key|refresh[_-]?token)\b\s*(?:=|:)\s*"
    r"[\"']?(?P<value>[^\s\"'`,;]{8,})"
)
_TOKEN_PATTERNS = (
    re.compile(r"\bsk-(?:ant-[A-Za-z0-9_-]+-)?[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\b(?:gh[opusr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
)
_PRIVATE_KEY = re.compile(
    "-----BEGIN " + r"(?:RSA |EC |OPENSSH )?" + "PRIVATE KEY-----"
)

_RESERVED_USERNAMES = frozenset(
    {"default", "example", "example-user", "public", "runner", "test", "user", "username"}
)
_RESERVED_EMAIL_DOMAINS = frozenset(
    {
        "example.com",
        "example.net",
        "example.org",
        "users.noreply.github.com",
    }
)
_SAFE_SECRET_MARKERS = ("example", "fake", "invalid", "placeholder", "redacted", "do_not_use")


@dataclass(frozen=True, slots=True)
class Finding:
    path: str
    line: int | None
    kind: str

    def render(self) -> str:
        location = self.path if self.line is None else f"{self.path}:{self.line}"
        return f"{location}: {self.kind}"


def _reserved_email(domain: str) -> bool:
    normalized = domain.casefold().rstrip(".")
    return normalized in _RESERVED_EMAIL_DOMAINS or normalized.endswith(
        (".example", ".invalid", ".localhost", ".test")
    )


def _safe_example_secret(value: str) -> bool:
    normalized = value.casefold()
    return any(marker in normalized for marker in _SAFE_SECRET_MARKERS)


def _line_findings(relative_path: str, number: int, line: str) -> list[Finding]:
    findings: list[Finding] = []

    for match in _EMAIL.finditer(line):
        if not _reserved_email(match.group("domain")):
            findings.append(Finding(relative_path, number, "possible personal email"))

    for pattern in (_WINDOWS_HOME, _UNIX_HOME):
        for match in pattern.finditer(line):
            if match.group("name").casefold() not in _RESERVED_USERNAMES:
                findings.append(Finding(relative_path, number, "possible private home path"))

    generic = _GENERIC_SECRET.search(line)
    if generic and not _safe_example_secret(generic.group("value")):
        findings.append(Finding(relative_path, number, "possible assigned secret"))

    if _PRIVATE_KEY.search(line):
        findings.append(Finding(relative_path, number, "private key material"))

    if any(pattern.search(line) for pattern in _TOKEN_PATTERNS):
        findings.append(Finding(relative_path, number, "possible access token"))

    return findings


def _lexical_relative(path: Path, root: Path) -> Path:
    absolute = Path(os.path.abspath(os.fspath(path)))
    return absolute.relative_to(root)


def _candidate_files(root: Path, paths: Iterable[Path] | None) -> Iterable[Path]:
    ignore_generated_directories = paths is None
    candidates = root.rglob("*") if ignore_generated_directories else paths
    for candidate in candidates:
        path = candidate if candidate.is_absolute() else root / candidate
        try:
            relative = _lexical_relative(path, root)
        except ValueError:
            continue
        directory_parts = {part.casefold() for part in relative.parts[:-1]}
        if directory_parts & _ALWAYS_SKIPPED_PARTS:
            continue
        if (
            ignore_generated_directories
            and directory_parts & _SKIPPED_GENERATED_PARTS
        ):
            continue
        if path.is_symlink() or path.is_file():
            yield path


def scan_repository(root: Path, paths: Iterable[Path] | None = None) -> list[Finding]:
    """Return privacy findings using paths relative to ``root`` only."""

    resolved_root = root.resolve(strict=True)
    findings: list[Finding] = []
    for path in _candidate_files(resolved_root, paths):
        relative_path = _lexical_relative(path, resolved_root).as_posix()
        if path.is_symlink():
            findings.append(
                Finding(relative_path, None, "prohibited repository symlink")
            )
            continue

        relative_parts = {part.casefold() for part in Path(relative_path).parts[:-1]}
        normalized_name = path.name.casefold()
        if relative_parts & _PROHIBITED_PRIVATE_PARTS:
            findings.append(
                Finding(relative_path, None, "prohibited private-data path")
            )
            continue
        if (
            normalized_name in _PROHIBITED_NAMES
            or normalized_name == ".env"
            or normalized_name.startswith(".env.")
            or normalized_name.endswith(_PROHIBITED_SUFFIXES)
        ):
            findings.append(
                Finding(relative_path, None, "prohibited repository artifact")
            )
            continue

        try:
            size = path.stat().st_size
        except OSError:
            findings.append(
                Finding(relative_path, None, "file metadata could not be read")
            )
            continue
        if size > _MAX_TEXT_BYTES:
            findings.append(
                Finding(relative_path, None, "file exceeds privacy scan size limit")
            )
            continue

        try:
            payload = path.read_bytes()
        except OSError:
            findings.append(
                Finding(relative_path, None, "file content could not be read")
            )
            continue
        if b"\x00" in payload:
            findings.append(
                Finding(relative_path, None, "binary or non-UTF-8 file")
            )
            continue
        try:
            text = payload.decode("utf-8")
        except UnicodeDecodeError:
            findings.append(
                Finding(relative_path, None, "binary or non-UTF-8 file")
            )
            continue

        for number, line in enumerate(text.splitlines(), start=1):
            findings.extend(_line_findings(relative_path, number, line))
    return findings


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    root = Path(arguments[0]) if arguments else Path(__file__).resolve().parents[1]
    findings = scan_repository(root)
    if findings:
        for finding in findings:
            print(finding.render())
        print(f"privacy scan failed with {len(findings)} finding(s)")
        return 1
    print("privacy scan passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
