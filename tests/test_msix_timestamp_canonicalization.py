"""Synthetic timestamp-only copy tests; no SDK, signing or installation."""
import hashlib
import io
from pathlib import Path
import struct
import sys
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import canonicalize_unsigned_msix as helper
from prompt_enhancer.application.build_evidence.manifest import build_manifest, canonical_json
from tests.test_msix_zip64_envelope import zip64


def package(year=2020):
    stream = io.BytesIO()
    with ZipFile(stream, "w", ZIP_DEFLATED) as archive:
        for name in ("AppxManifest.xml", "AppxBlockMap.xml", "[Content_Types].xml"):
            info = ZipInfo(name, (year, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            archive.writestr(info, b"synthetic")
    return stream.getvalue()


def patches(tmp_path, data):
    source = tmp_path / "synthetic.msix"
    source.write_bytes(data)
    with source.open("rb") as stream:
        return helper.patch_map(stream, len(data))


@pytest.mark.parametrize("convert", [lambda x: x, zip64])
def test_only_timestamp_bytes_and_two_times_identical(tmp_path, convert):
    outputs = []
    for year in (2020, 2024):
        data = convert(package(year))
        positions = patches(tmp_path, data)
        assert len(positions) == 6
        changed = bytearray(data)
        for position in positions:
            changed[position:position + 4] = helper.STAMP
        allowed = {i for p in positions for i in range(p, p + 4)}
        assert all(a == b or i in allowed for i, (a, b) in enumerate(zip(data, changed)))
        outputs.append(changed)
    assert outputs[0] == outputs[1]


@pytest.mark.parametrize("offset,fmt,value", [(0, "L", 0), (4, "H", 99), (6, "H", 1),
    (8, "H", 0), (10, "H", 3), (14, "L", 123), (18, "L", 123), (26, "H", 1)])
def test_local_central_mismatch_refused(tmp_path, offset, fmt, value):
    data = bytearray(package())
    struct.pack_into("<" + fmt, data, offset, value)
    with pytest.raises(ValueError):
        patches(tmp_path, data)


@pytest.mark.parametrize("extra", [b"x", struct.pack("<HH", 0x5455, 0), struct.pack("<HH", 10, 0),
    struct.pack("<HH", 1, 20), struct.pack("<HH", 1, 0) * 2])
def test_unsupported_or_malformed_extras(extra):
    with pytest.raises(ValueError):
        helper.extras(extra)


def test_signature_and_encryption_refused(tmp_path):
    for signed in (True, False):
        data = bytearray(package())
        if signed:
            stream = io.BytesIO(data)
            with ZipFile(stream, "a") as archive:
                archive.writestr("AppxSignature.p7x", b"synthetic")
            data = stream.getvalue()
        else:
            central = data.find(b"PK\x01\x02")
            struct.pack_into("<H", data, central + 8, 1)
        with pytest.raises(ValueError):
            patches(tmp_path, data)


def test_overlapping_local_records_refused(tmp_path):
    data = bytearray(package())
    first = data.find(b"PK\x01\x02")
    second = data.find(b"PK\x01\x02", first + 4)
    struct.pack_into("<L", data, second + 42, 0)
    with pytest.raises(ValueError):
        patches(tmp_path, data)


def test_full_exclusive_copy_preserves_original(tmp_path, monkeypatch):
    monkeypatch.setattr(helper.pack, "REPOSITORY_ROOT", tmp_path / "reserved-repository")
    monkeypatch.setattr(helper.pack, "HOME_ROOT", tmp_path / "reserved-home")
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "AppxManifest.xml").write_bytes(b"synthetic")
    manifest = canonical_json(build_manifest(candidate, git_revision="a" * 40, tool_versions={}, lockfile_hashes={}))
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_bytes(manifest)
    source, output = tmp_path / "source.msix", tmp_path / "canonical.msix"
    data = package()
    source.write_bytes(data)
    args = (source, output, manifest_path, hashlib.sha256(manifest).hexdigest(), hashlib.sha256(data).hexdigest(), len(data))
    result = helper.canonicalize(*args)
    assert result["passed"] and result["pre_sign_canonicalization"]
    assert source.read_bytes() == data
    assert output.read_bytes() != data
    with pytest.raises(ValueError):
        helper.canonicalize(*args)


def descriptor_package():
    class Unseekable(io.BytesIO):
        def seek(self, *args):
            raise OSError("synthetic-unseekable")
    stream = Unseekable()
    with ZipFile(stream, "w", ZIP_DEFLATED) as archive:
        with archive.open("synthetic.txt", "w", force_zip64=True) as member:
            member.write(b"synthetic")
    data = bytearray(stream.getvalue())
    # Bind the synthetic ZIP64 local placeholders explicitly; Python versions
    # differ in their streaming placeholder/version fields.
    struct.pack_into("<H", data, 4, 45)
    struct.pack_into("<LL", data, 18, 0xFFFFFFFF, 0xFFFFFFFF)
    central = data.find(b"PK\x01\x02")
    struct.pack_into("<H", data, central + 6, 45)
    return bytes(data)


def test_zip64_local_sizes_and_descriptor(tmp_path):
    data = descriptor_package()
    local = struct.unpack_from("<4s5H3L2H", data)
    assert local[2] & 8
    assert local[7:9] == (0xFFFFFFFF, 0xFFFFFFFF)
    assert local[10] == 20  # ZIP64 TLV: header4 plus two uint64 values16.
    assert len(patches(tmp_path, data)) == 2


def test_descriptor_value_and_gap_refused(tmp_path):
    original = descriptor_package()
    descriptor = original.find(b"PK\x07\x08")
    assert descriptor > 0
    for relative, fmt in ((4, "L"), (8, "Q"), (16, "Q")):
        data = bytearray(original)
        struct.pack_into("<" + fmt, data, descriptor + relative, 999)
        with pytest.raises(ValueError):
            patches(tmp_path, data)
