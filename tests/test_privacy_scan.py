from __future__ import annotations

from pathlib import Path

from scripts.privacy_scan import scan_repository


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def test_repository_passes_privacy_scan() -> None:
    assert scan_repository(REPOSITORY_ROOT) == []


def test_scanner_flags_secret_email_and_private_path(tmp_path) -> None:
    unsafe = tmp_path / "unsafe.txt"
    personal_email = "alex" + "@" + "company" + ".com"
    private_path = "/" + "home/" + "alex/work"
    assigned_secret = "api_" + "key = " + "sk-" + ("A" * 32)
    unsafe.write_text(
        "\n".join((personal_email, private_path, assigned_secret)),
        encoding="utf-8",
    )

    kinds = {finding.kind for finding in scan_repository(tmp_path)}

    assert "possible personal email" in kinds
    assert "possible private home path" in kinds
    assert "possible assigned secret" in kinds
    assert "possible access token" in kinds


def test_scanner_allows_reserved_examples(tmp_path) -> None:
    safe = tmp_path / "safe.txt"
    safe.write_text(
        "\n".join(
            (
                "person@example.invalid",
                "/home/example/project",
                r"C:\Users\Example\project",
                "api_key = example_token_do_not_use",
            )
        ),
        encoding="utf-8",
    )

    assert scan_repository(tmp_path) == []


def test_scanner_allows_only_bare_unassigned_secret_type_annotation(tmp_path) -> None:
    source = tmp_path / "types.py"
    source.write_text(
        "api_" + "key: SecretStr\ncredential: pydantic.SecretBytes\n",
        encoding="utf-8",
    )
    assert scan_repository(tmp_path) == []


def test_scanner_keeps_same_line_and_annotation_secret_assignments(tmp_path) -> None:
    source = tmp_path / "unsafe.py"
    assigned = (
        "api_" + "key: SecretStr; pass" + "word = 'longactualsecret' # auth_"
        + "token: longcommentsecret\napi_" + "key: SecretStr = 'longassignedsecret'\napi_"
        + "key: 'SecretStr'\n"
    )
    source.write_text(assigned, encoding="utf-8")
    findings = [item for item in scan_repository(tmp_path) if item.kind == "possible assigned secret"]
    assert [item.line for item in findings].count(1) == 2  # password and comment token
    assert [item.line for item in findings].count(2) == 1  # annotated assignment
    assert [item.line for item in findings].count(3) == 1  # quoted annotation


def test_scanner_keeps_multiline_malformed_and_nonpython_annotation_like_text(tmp_path) -> None:
    annotation = "api_" + "key: SecretStr"
    (tmp_path / "multi.py").write_text(annotation + " = (\n    'longmultilinesecret'\n)\n", encoding="utf-8")
    (tmp_path / "bad.py").write_text(annotation + " =\n", encoding="utf-8")
    (tmp_path / "notes.txt").write_text(annotation + "\n", encoding="utf-8")
    findings = [item for item in scan_repository(tmp_path) if item.kind == "possible assigned secret"]
    assert len(findings) == 3


def test_scanner_handles_utf8_ast_columns_without_suppressing_neighbour_secret(tmp_path) -> None:
    source = tmp_path / "unicode.py"
    source.write_text(
        "π = 1; api_" + "key: SecretStr; pass" + "word = 'longactualsecret'\n",
        encoding="utf-8",
    )
    findings = [item for item in scan_repository(tmp_path) if item.kind == "possible assigned secret"]
    assert [item.line for item in findings] == [1]


def test_synthetic_scanner_fixture_sources_are_self_clean(tmp_path) -> None:
    for name in ("test_privacy_scan.py", "test_windows_python_runtime.py"):
        source = Path(__file__).with_name(name)
        (tmp_path / name).write_bytes(source.read_bytes())
    assert scan_repository(tmp_path) == []
