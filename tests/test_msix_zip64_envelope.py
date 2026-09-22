"""SDK-shaped synthetic ZIP64 envelopes; no SDK or signature provider runs."""
import struct

import pytest

from prompt_enhancer.infrastructure.updates import msix_preflight as module
from tests.test_msix_preflight_cli import _package_bytes, _artifact, _expectation, _SyntheticSigner


def zip64(payload=None):
    original = _package_bytes() if payload is None else payload
    end = struct.unpack_from("<4s4H2LH", original, len(original) - 22)
    central = original[end[6]:end[6] + end[5]]
    records = bytearray()
    position = 0
    while position < len(central):
        fields = list(struct.unpack_from("<4s6H3L5H2L", central, position))
        length = 46 + fields[10] + fields[11] + fields[12]
        name = central[position + 46:position + 46 + fields[10]]
        extra = struct.pack("<HH3Q", 1, 24, fields[9], fields[8], fields[16])
        fields[8] = fields[9] = fields[16] = 0xFFFFFFFF
        fields[11] = len(extra)
        records += struct.pack("<4s6H3L5H2L", *fields) + name + extra
        position += length
    offset = end[6] + len(records)
    return (original[:end[6]] + records
            + struct.pack("<4sQ2H2L4Q", b"PK\x06\x06", 44, 45, 45, 0, 0, end[4], end[4], len(records), end[6])
            + struct.pack("<4sLQL", b"PK\x06\x07", 0, offset, 1)
            + struct.pack("<4s4H2LH", b"PK\x05\x06", 65535, 65535, 65535, 65535, 0xFFFFFFFF, 0xFFFFFFFF, 0))


def valid(tmp_path, data):
    path = tmp_path / "synthetic.msix"
    path.write_bytes(data)
    with path.open("rb") as stream:
        return module._bounded_zip_central_directory(stream.fileno(), size=len(data))


def test_sdk_shape_and_classic_pass(tmp_path):
    assert valid(tmp_path, zip64())
    assert valid(tmp_path, _package_bytes())


def test_consistent_nonsentinel_legacy_values_pass(tmp_path):
    data = bytearray(zip64())
    record = struct.unpack_from("<4sQ2H2L4Q", data, len(data) - 98)
    struct.pack_into("<4s4H2LH", data, len(data) - 22, b"PK\x05\x06", 0, 0,
                     record[6], record[7], record[8], record[9], 0)
    assert valid(tmp_path, data)


@pytest.mark.parametrize("index,value", [(0, 64 * 1024 * 1024 + 1), (1, 2**63), (2, 2**63)])
def test_resolved_member_bounds_refused(tmp_path, index, value):
    data = bytearray(zip64())
    central_offset = struct.unpack_from("<4sQ2H2L4Q", data, len(data) - 98)[9]
    name_size = struct.unpack_from("<H", data, central_offset + 28)[0]
    struct.pack_into("<Q", data, central_offset + 46 + name_size + 4 + index * 8, value)
    assert not valid(tmp_path, data)


RECORDS = {
    "zip64": ("<4sQ2H2L4Q", 98, ("signature", "size", "made", "needed", "disk", "central_disk", "disk_entries", "entries", "central_size", "central_offset")),
    "locator": ("<4sLQL", 42, ("signature", "disk", "offset", "disks")),
    "classic": ("<4s4H2LH", 22, ("signature", "disk", "central_disk", "disk_entries", "entries", "central_size", "central_offset", "comment")),
}


@pytest.mark.parametrize("record,field,value", [
    ("zip64", "size", 45), ("zip64", "needed", 46), ("zip64", "disk", 1), ("zip64", "central_disk", 1),
    ("zip64", "disk_entries", 10001), ("zip64", "entries", 10001), ("zip64", "central_size", 8388609),
    ("zip64", "central_offset", 2**63), ("locator", "disk", 1), ("locator", "offset", 2**63), ("locator", "disks", 2),
    ("classic", "disk", 1), ("classic", "entries", 2), ("classic", "central_size", 1), ("classic", "central_offset", 1),
])
def test_zip64_boundaries_refused(tmp_path, record, field, value):
    data = bytearray(zip64())
    fmt, distance, names = RECORDS[record]
    fields = list(struct.unpack_from(fmt, data, len(data) - distance))
    fields[names.index(field)] = value
    struct.pack_into(fmt, data, len(data) - distance, *fields)
    assert not valid(tmp_path, data)


@pytest.mark.parametrize("cut", [1, 20, 22, 56, 76])
def test_truncated_refused(tmp_path, cut):
    assert not valid(tmp_path, zip64()[:-cut])


@pytest.mark.parametrize("extra", [b"", b"\x01", struct.pack("<HH", 1, 65535),
    struct.pack("<HHQ", 1, 8, 1), struct.pack("<HH4Q", 1, 32, 1, 2, 3, 4),
    struct.pack("<HH3Q", 1, 24, 1, 2, 3) * 2])
def test_missing_malformed_duplicate_extra_refused(extra):
    assert module._resolve_zip64_extra(extra, 0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFF, 0) is None


def test_sentinel_order_and_superfluous_extra():
    extra = struct.pack("<HH3Q", 1, 24, 7, 8, 9)
    assert module._resolve_zip64_extra(extra, 0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFF, 0) == (7, 8, 9, 0)
    assert module._resolve_zip64_extra(extra, 7, 8, 9, 0) is None


@pytest.mark.parametrize("fields,extra,expected", [
    ((7, 8, 0xFFFFFFFF, 0), struct.pack("<HHQ", 1, 8, 9), (7, 8, 9, 0)),
    ((7, 8, 9, 65535), struct.pack("<HHL", 1, 4, 0), (7, 8, 9, 0)),
])
def test_selective_sentinels(fields, extra, expected):
    assert module._resolve_zip64_extra(extra, *fields) == expected


def test_nonzero_resolved_disk_refused():
    extra = struct.pack("<HHL", 1, 4, 1)
    header = struct.pack("<4s6H3L5H2L", b"PK\x01\x02", 45, 45, 0, 0, 0, 0,
                         0, 1, 1, 1, len(extra), 0, 65535, 0, 0, 0)
    assert not module._valid_central_directory(header + b"a" + extra, expected_entries=1, central_offset=100)


def test_unsigned_zip64_still_rejected(tmp_path):
    data = zip64()
    path = tmp_path / "synthetic.msix"
    path.write_bytes(data)
    signer = _SyntheticSigner()
    signer.result = None
    result = module.MsixPackagePreflight(signer=signer).verify(package_path=path, artifact=_artifact(data), expectation=_expectation())
    assert result.reason.value == "signature_invalid"
    assert signer.calls == 1
